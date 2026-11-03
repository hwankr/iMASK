# ==========================================================================
#  분석 결과 → 화면용 '서류'·'탐지 항목'·'전체 판정' (BRIEF §5 공통 계약)
#  build_view(result) 는 저장된 analyses.result 에서 **조회할 때 계산**한다(DB 저장 형식은 그대로라
#  예전 분석에도 적용된다). 단계는 result.response(원본)가 있으면 parse_stages 로, 없으면 저장된 stages 로.
#  status 가 completed(또는 없음)인 단계만 쓴다(results.summarize 와 같은 규칙).
#
#  - documents: 서류-분류 contents 를 output 순서대로 훑어 순번(index, 0부터 — 병합 단계 branch_key
#    "<순번>:<코드>" 와 같은 번호)을 매긴다. 분류 코드를 못 읽은 content 는 서류를 만들지 않지만 순번은 차지한다.
#    추출·검증·기타 안내 항목은 쪽 범위(page_ranges 를 정규화한 튜플)가 **정확히 같은** 서류에 붙는다.
#    정규화한 범위가 빈 쪽이 있으면(어느 쪽이든) 짝짓지 않는다 — 근거 없는 순서 짝짓기를 하지 않는다(T1-fix1).
#    짝 없는 추출 결과(범위가 빈 것 포함)는 버리지 않고 서류(type null)를 덧붙인다. 짝 없는 검증·기타 안내는 버린다.
#  - findings: 추출 짝이 있는 서류마다 추출 data 의 키 순서대로(빈 값은 건너뜀). 대응표는 fields,
#    노출 상태·가림 미리보기는 masking(표시용 가공). 좌표는 단어별 사각형 우선, 없으면 값 영역.
#  - risk: **판별하지 않는다.** 위험도_판정 단계가 [{branch_key, field, grade, reason}] 목록을 낸 경우에만
#    그 값을 옮긴다(data 목록·data 객체의 목록 값·additional_values 의 목록 값·data 문자열의 ```json 블록 —
#    블록 경계는 줄 단위 fence 파서로 읽고, json·언어 표시 없는 닫힌 블록만 푼다).
#    등급은 상·중·하만 읽는다. 본문 Markdown·citations 에서 추측하지 않는다. 없으면 unrated.
#  - other_guide: 본문이 빈 문자열(공백만)·빈 객체·빈 목록이면 null(안내가 없는 것과 같다). 객체·목록은 JSON 문자열.
#  - 한 탐지 항목을 만들다 예외가 나면 그 항목만 안전한 값(전부 가림·전체 노출·위치 없음)으로 두고 나머지는 그대로.
#    값 문자열 만들기가 실패해도 항목은 남긴다 — value 는 원문 문자열 그대로, 원문을 문자열로 만들 수 없을 때만
#    고정 문구 "(값을 읽지 못했습니다)"(빈 값은 실패가 아니라 원래 항목이 아님).
#  - 쪽 번호(page, page_ranges 의 a·b)는 1 이상 MAX_PAGE(100000) 이하만 인정한다.
#  - field·id 는 추출의 **원래 키** 그대로다(바꾸지도 다듬지도 않는다). 대응표·메타·항목별 위험등급도 원래 키로 찾는다.
#    표에 없는 키의 label 도 원래 키(비었거나 공백만이면 "(이름 없는 항목)"). 짝 없는 서로게이트가 든 값·키도 그대로
#    두고, 응답 경계(api/index.py — textsafe)가 그런 응답만 ASCII escape JSON 으로 보낸다.
#  - 항목별 위험등급의 branch_key·field 는 비어 있는지(공백만 포함)만 보고 비교·색인에는 원래 문자열 그대로 쓴다
#    (strip 하지 않음 — 공백만 다른 다른 키에 등급이 옮겨 가지 않게). grade 는 앞뒤 공백을 지우고, reason 은 빈 문자열이면 null.
#  - overall: summarize 의 risk_level(상·중·하·검토 필요)·final_stage 와 그 단계 본문(Markdown 그대로).
#  바깥 모양이 달라도 예외를 던지지 않는다. 그래도 예상 못 한 예외가 나면 값 없는 경고 로그를 남기고
#  빈 결과(documents []·findings []·overall 빈 값)를 돌려준다 — 조회가 500 이 되지 않게.
# ==========================================================================

from __future__ import annotations

import json
import logging
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .fields import field_info
from .masking import EXPOSED, STAR, exposure, masked
from .results import (
    FINAL_STAGES,
    STAGE_CLASSIFY,
    STAGE_EXTRACT,
    STAGE_OTHER,
    STAGE_RISK,
    STAGE_VALIDATE,
    as_stages,
    document_type,
    parse_stages,
    stage_contents,
    summarize,
    usable_stages_for,
)

logger = logging.getLogger("imask.findings")

OVERALL_LEVELS = ("상", "중", "하", "검토 필요")
GRADE_TO_RISK = {"상": "high", "중": "medium", "하": "low"}
RISK_SOURCE = "workflow"
UNRATED = "unrated"
CONFIDENCES = ("high", "low")
KIND_EXTRACTED = "extracted"
KIND_OTHER = "other"
# 쪽 번호(finding.page, page_ranges 의 a·b)로 인정하는 최대값 — 넘는 정수는 버린다(화면 JavaScript 정밀도 보호)
MAX_PAGE = 100_000
# 값을 문자열로 만들지 못했고 원문도 문자열이 아닐 때만 쓰는 value
UNREADABLE_VALUE = "(값을 읽지 못했습니다)"
# 표에 없는 키의 이름이 비었거나 공백만일 때의 label
UNNAMED_LABEL = "(이름 없는 항목)"
# 계약 키(BRIEF §5)는 _Doc.out·_findings·_overall 이 만드는 dict 그대로다 — 그 밖의 키는 넣지 않는다
# (tests/view_contract.py 가 정확히 그 키인지 확인한다)

_BOX_MIN = -0.001
_BOX_MAX = 1.001
# 코드 블록 여는 줄: 앞 공백 0~3칸 + 백틱 3개 이상 + 정보 문자열(백틱 없음). 닫는 줄은 같은 개수 이상의 백틱만.
_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,})([^`]*)$")
_JSON_INFO = ("", "json")

Ranges = tuple[tuple[int, int], ...]


def empty_view() -> dict[str, Any]:
    return {"documents": [], "findings": [], "overall": _empty_overall()}


def _empty_overall() -> dict[str, Any]:
    return {"level": None, "text": "", "next_stage": None, "next_text": ""}


def build_view(result: Any) -> dict[str, Any]:
    """저장된 result → {"documents", "findings", "overall"}. 어떤 모양에도 예외를 던지지 않는다."""
    try:
        return _build_view(result)
    except Exception as exc:  # 조회가 500 이 되지 않게 — 값 없이 예외 종류만 남긴다
        logger.warning("분석 결과를 화면 형식으로 바꾸지 못함: %s", type(exc).__name__)
        return empty_view()


def view_stages(result: Any) -> list[Mapping[str, Any]]:
    """result.response 가 Mapping 이면 parse_stages, 아니면 저장된 stages(list)."""
    if not isinstance(result, Mapping):
        return []
    response = result.get("response")
    if isinstance(response, Mapping):
        return parse_stages(response)
    stored = result.get("stages")
    if isinstance(stored, list):
        return as_stages(stored)
    return []


# --- 작은 도우미 --------------------------------------------------------------------


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _coordinate(value: Any) -> float | None:
    """좌표 한 값 → -0.001~1.001 안이면 0~1 로 자른 float, 아니면 None. 어떤 JSON 값에도 예외를 내지 않는다.

    bool 아닌 int 는 float 로 바꾸기 전에 범위를 본다(아주 큰 정수의 float 변환 OverflowError 를 피함 — int 와
    float 비교는 정확하다). float 만 math.isfinite 로 inf·nan 을 거른다. 그 밖(문자열·bool·None 등)은 None.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return min(1.0, max(0.0, float(value))) if _BOX_MIN <= value <= _BOX_MAX else None
    if isinstance(value, float):
        if math.isfinite(value) and _BOX_MIN <= value <= _BOX_MAX:
            return min(1.0, max(0.0, value))
        return None
    return None


def _text_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _ranges(additional: Any) -> Ranges:
    """page_ranges 의 [a, b] 중 a·b 가 정수(bool 아님)이고 1 ≤ a ≤ b ≤ MAX_PAGE 인 것만, 순서대로."""
    raw = _mapping(additional).get("page_ranges")
    if not isinstance(raw, list):
        return ()
    out: list[tuple[int, int]] = []
    for pair in raw:
        if isinstance(pair, (list, tuple)) and len(pair) == 2:
            start, end = pair
            if _is_int(start) and _is_int(end) and 1 <= start <= end <= MAX_PAGE:
                out.append((start, end))
    return tuple(out)


def _first_content(stage: Mapping[str, Any]) -> tuple[Any, Any]:
    """단계의 data·additional_values(= content[0], parse_stages 와 같은 자리)."""
    return stage.get("data"), stage.get("additional_values")


# --- 서류 ---------------------------------------------------------------------------


@dataclass
class _Doc:
    index: int
    type: str | None
    ranges: Ranges
    extract: tuple[Mapping[str, Any], Mapping[str, Any]] | None = None
    validation: str | None = None
    other_guide: str | None = None

    def out(self) -> dict[str, Any]:
        if self.extract is not None:
            kind = KIND_EXTRACTED
        elif self.other_guide is not None or (self.type or "").lower() == "other":
            kind = KIND_OTHER
        else:
            kind = KIND_EXTRACTED
        return {
            "index": self.index,
            "type": self.type,
            "page_start": min(r[0] for r in self.ranges) if self.ranges else None,
            "page_end": max(r[1] for r in self.ranges) if self.ranges else None,
            "kind": kind,
            "other_guide": self.other_guide,
            "validation": self.validation,
        }


def _classify_entries(stage: Mapping[str, Any]) -> list[Any]:
    """서류-분류 단계의 content 전부(Mapping 이 아닌 것도 순번을 차지한다)."""
    contents = stage.get("contents")
    if isinstance(contents, list):
        return list(contents)
    return list(stage_contents(stage))


def _documents(stages: Sequence[Mapping[str, Any]]) -> tuple[list[_Doc], int]:
    """분류 서류 목록과 분류 content 수(덧붙일 서류의 순번 시작)."""
    docs: list[_Doc] = []
    count = 0
    for stage in usable_stages_for(stages, STAGE_CLASSIFY):
        for entry in _classify_entries(stage):
            index = count
            count += 1
            if not isinstance(entry, Mapping):
                continue
            code = document_type(entry)
            if code is None:
                continue
            docs.append(_Doc(index=index, type=code, ranges=_ranges(entry.get("additional_values"))))
    return docs, count


def _first_free(docs: Sequence[_Doc], ranges: Ranges, attr: str) -> _Doc | None:
    """범위가 정확히 같고 attr 이 아직 비어 있는 서류 중 index 가 가장 작은 것. 범위가 비면 짝 없음(None)."""
    if not ranges:
        return None  # 빈 범위(page_ranges 없음·모두 틀림)는 근거가 없어 짝짓지 않는다 — 서류 쪽 빈 범위도 () 와만 같다
    candidates = [d for d in docs if d.ranges == ranges and getattr(d, attr) is None]
    return min(candidates, key=lambda d: d.index) if candidates else None


def _attach_extracts(stages: Sequence[Mapping[str, Any]], docs: list[_Doc], next_index: int) -> None:
    for stage in usable_stages_for(stages, STAGE_EXTRACT):
        data, additional = _first_content(stage)
        if not isinstance(data, Mapping):
            continue
        ranges = _ranges(additional)
        pair = (data, _mapping(additional))
        doc = _first_free(docs, ranges, "extract")
        if doc is None:
            # 짝 없는 추출 결과(범위가 빈 것 포함)도 버리지 않는다 — 서류(type 없음)를 덧붙인다
            doc = _Doc(index=next_index, type=None, ranges=ranges)
            next_index += 1
            docs.append(doc)
        doc.extract = pair


def _verdict(data: Any, additional: Any) -> str | None:
    verdict = _text_or_none(_mapping(additional).get("verdict"))
    if verdict is not None:
        return verdict
    return _text_or_none(data)


def _guide_text(data: Any) -> str | None:
    """기타 안내 본문. 문자열은 그대로, 객체·목록은 JSON 문자열. 빈 문자열(공백만)·빈 객체·빈 목록이면 None."""
    if isinstance(data, str):
        return data if data.strip() else None
    if isinstance(data, (Mapping, list)) and data:
        return json.dumps(data, ensure_ascii=False, default=str)
    return None


def _attach_text(stages: Sequence[Mapping[str, Any]], docs: list[_Doc], key: str, attr: str) -> None:
    """검증 verdict·기타 안내 본문을 범위가 같은 서류(그 값이 아직 없는 첫 서류)에 붙인다. 범위가 비거나 짝이 없으면 버린다."""
    for stage in usable_stages_for(stages, key):
        data, additional = _first_content(stage)
        text = _verdict(data, additional) if attr == "validation" else _guide_text(data)
        if text is None:
            continue
        doc = _first_free(docs, _ranges(additional), attr)
        if doc is not None:
            setattr(doc, attr, text)


# --- 항목별 위험등급(워크플로우 값 읽기만) ------------------------------------------------


def _lists_in(value: Any) -> list[list[Any]]:
    """value 가 list 면 [그것], Mapping 이면 값 중 list 인 것들."""
    if isinstance(value, list):
        return [value]
    if isinstance(value, Mapping):
        return [v for v in value.values() if isinstance(v, list)]
    return []


def _closes(line: str, fence: int) -> bool:
    """닫는 줄: 앞뒤 공백을 뺀 내용이 백틱만이고 여는 줄 이상의 개수."""
    stripped = line.strip()
    return len(stripped) >= fence and set(stripped) == {"`"}


def json_code_blocks(text: str) -> list[str]:
    """Markdown 의 **닫힌** 코드 블록 중 정보 문자열 첫 낱말이 json(대소문자 무시)이거나 없는 것의 내용을 순서대로.

    줄 단위 상태 파서: 모든 블록을 등장 순서대로 소비한다. 다른 언어 블록은 닫는 줄까지 건너뛴다(그 안의
    ```json 줄은 내용일 뿐). 닫히지 않은 블록은 문서 끝까지 이어지므로 버린다.
    """
    lines = text.splitlines()
    blocks: list[str] = []
    i = 0
    while i < len(lines):
        opening = _FENCE_OPEN.match(lines[i])
        if opening is None:
            i += 1
            continue
        fence = len(opening.group(1))
        info = opening.group(2).split()
        end = next((j for j in range(i + 1, len(lines)) if _closes(lines[j], fence)), None)
        if end is None:
            break  # 닫히지 않은 블록 — 무시
        if (info[0].lower() if info else "") in _JSON_INFO:
            blocks.append("\n".join(lines[i + 1 : end]))
        i = end + 1
    return blocks


def _code_block_lists(text: Any) -> list[list[Any]]:
    if not isinstance(text, str) or "```" not in text:
        return []
    found: list[list[Any]] = []
    for block in json_code_blocks(text):
        try:
            parsed = json.loads(block)
        except (ValueError, TypeError, RecursionError):
            continue
        found.extend(_lists_in(parsed))
    return found


def _risk_lists(stage: Mapping[str, Any]) -> list[list[Any]]:
    """찾는 곳 순서: 1. data(list 또는 객체의 list 값) 2. additional_values 의 list 값 3. data 문자열의 json 블록."""
    lists: list[list[Any]] = []
    for content in stage_contents(stage):
        data = content.get("data")
        lists.extend(_lists_in(data))
        additional = content.get("additional_values")
        if isinstance(additional, Mapping):
            lists.extend(_lists_in(additional))
        lists.extend(_code_block_lists(data))
    return lists


def _identifier(value: Any) -> str | None:
    """식별자(branch_key·field): 비지 않은(공백만도 아닌) 문자열이면 **원래 문자열 그대로**, 아니면 None."""
    return value if isinstance(value, str) and value.strip() else None


def item_risks(stages: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], tuple[str, str | None]]:
    """(branch_key, field) → (grade, reason). 상·중·하만, 같은 (원래 문자열) 키는 처음 것.

    branch_key·field 는 다듬지 않고 비교한다 — 서류의 f"{index}:{type}"·추출의 원래 키와 정확히 같을 때만 붙는다.
    """
    risks: dict[tuple[str, str], tuple[str, str | None]] = {}
    for stage in usable_stages_for(stages, STAGE_RISK):
        for items in _risk_lists(stage):
            for item in items:
                if not isinstance(item, Mapping):
                    continue
                branch_key = _identifier(item.get("branch_key"))
                field_name = _identifier(item.get("field"))
                grade = _text_or_none(item.get("grade"))
                if branch_key is None or field_name is None or grade not in GRADE_TO_RISK:
                    continue
                risks.setdefault((branch_key, field_name), (grade, _text_or_none(item.get("reason"))))
    return risks


# --- 탐지 항목 ------------------------------------------------------------------------


def _value_text(raw: Any) -> str | None:
    """값을 문자열로. 빈 값(공백만·None·bool·빈 목록)은 None(건너뜀). ';' 가 있어도 한 값."""
    if isinstance(raw, str):
        return raw if raw.strip() else None
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, (int, float)):
        return str(raw)
    if isinstance(raw, (list, Mapping)) and raw:
        return json.dumps(raw, ensure_ascii=False, default=str)
    return None


def _rect(points: Any) -> list[dict[str, float]] | None:
    """점 정확히 4개, x·y 가 유한한 수(bool 아님)이고 -0.001~1.001 → 0~1 로 자른 {x, y}. 아니면 None."""
    if not isinstance(points, list) or len(points) != 4:
        return None
    out: list[dict[str, float]] = []
    for point in points:
        if not isinstance(point, Mapping):
            return None
        x, y = _coordinate(point.get("x")), _coordinate(point.get("y"))
        if x is None or y is None:
            return None
        out.append({"x": x, "y": y})
    return out


def _boxes(meta: Mapping[str, Any]) -> list[list[dict[str, float]]]:
    words = meta.get("word_coordinates")
    boxes = [r for r in (_rect(w) for w in words) if r is not None] if isinstance(words, list) else []
    if boxes:
        return boxes
    whole = _rect(meta.get("coordinates"))
    return [whole] if whole is not None else []


def _page(meta: Mapping[str, Any]) -> int | None:
    """1 이상 MAX_PAGE 이하 정수(bool 아님)만. 그 밖(-1·0·너무 큰 수 등)은 None."""
    page = meta.get("page")
    return page if _is_int(page) and 1 <= page <= MAX_PAGE else None


def _confidence(meta: Mapping[str, Any]) -> str | None:
    value = meta.get("confidence")
    if isinstance(value, str) and value.strip().lower() in CONFIDENCES:
        return value.strip().lower()
    return None


def _finding_detail(value: str, kind: str, meta: Mapping[str, Any]) -> dict[str, Any]:
    """가림 미리보기·노출 상태·위치·신뢰도(바깥 메타를 읽는 부분 — 실패하면 _fallback_detail 로)."""
    page = _page(meta)
    return {
        "masked": masked(value, kind),
        "exposure": exposure(value, kind),
        "page": page,
        "boxes": _boxes(meta) if page is not None else [],
        "confidence": _confidence(meta),
    }


def _fallback_detail(value: str) -> dict[str, Any]:
    """한 항목을 만들다 예외가 났을 때의 안전한 값: 전부 가림·전체 노출·위치 없음."""
    return {"masked": STAR * len(value), "exposure": EXPOSED, "page": None, "boxes": [], "confidence": None}


def _is_empty_raw(raw: Any) -> bool:
    """빈 값(공백만인 문자열·None·bool·빈 목록/객체) — 실패가 아니라 원래 항목이 아닌 것."""
    try:
        if isinstance(raw, str):
            return not raw.strip()
        if raw is None or isinstance(raw, bool):
            return True
        return isinstance(raw, (list, Mapping)) and not raw
    except Exception:
        return False


def _fallback_value(raw: Any) -> str | None:
    """값 변환이 실패했을 때의 value: 빈 값이면 None(항목 아님), 문자열이면 원문 그대로, 그 밖은 고정 문구.

    고정 문구는 원문을 문자열로 만들 수 없을 때만 쓴다.
    """
    if _is_empty_raw(raw):
        return None
    return raw if isinstance(raw, str) else UNREADABLE_VALUE


def _log_name(key: str) -> str:
    """로그용 필드 이름(60자까지). 짝 없는 서로게이트도 로그 출력에서 예외가 나지 않게 \\uXXXX 로."""
    return key[:60].encode("utf-8", "backslashreplace").decode("utf-8")


def _findings(docs: Sequence[_Doc], risks: Mapping[tuple[str, str], tuple[str, str | None]]) -> list[dict[str, Any]]:
    """추출 짝이 있는 서류마다 항목을 만든다. 한 항목이 실패해도 그 항목만 대체 값으로 두고 나머지는 그대로."""
    out: list[dict[str, Any]] = []
    for doc in sorted(docs, key=lambda d: d.index):
        if doc.extract is None:
            continue
        data, additional = doc.extract
        branch_key = f"{doc.index}:{doc.type}" if doc.type is not None else None
        for key, raw in data.items():
            if not isinstance(key, str):
                continue
            failed = False
            try:
                value = _value_text(raw)
            except Exception as exc:  # 항목은 버리지 않는다 — 원문 문자열이면 그대로, 아니면 고정 문구
                logger.warning("탐지 항목 값을 읽지 못해 대체 값으로 둠: %s (%s)", _log_name(key), type(exc).__name__)
                value = _fallback_value(raw)
                failed = True
            if value is None:
                continue
            info = field_info(key)
            # 표에 없는 키는 원래 키를 그대로 이름으로(비었거나 공백만이면 고정 문구) — field·id 도 원래 키
            label = info.label if info.mapping_status != "unknown" else (key if key.strip() else UNNAMED_LABEL)
            rated = risks.get((branch_key, key)) if branch_key is not None else None
            if failed:
                detail = _fallback_detail(value)
            else:
                try:
                    detail = _finding_detail(value, info.kind, _mapping(additional.get(key)))
                except Exception as exc:  # 전체 view 를 비우지 않고 이 항목만 안전한 값으로
                    logger.warning("탐지 항목 하나를 대체 값으로 둠: %s (%s)", _log_name(key), type(exc).__name__)
                    detail = _fallback_detail(value)
            out.append(
                {
                    "id": f"{doc.index}:{key}",
                    "document_index": doc.index,
                    "field": key,
                    "category": info.category,
                    "label": label,
                    "subject": info.subject,
                    "mapping_status": info.mapping_status,
                    "value": value,
                    "masked": detail["masked"],
                    "exposure": detail["exposure"],
                    "risk": GRADE_TO_RISK[rated[0]] if rated else UNRATED,
                    "risk_source": RISK_SOURCE if rated else None,
                    "risk_reason": rated[1] if rated else None,
                    "page": detail["page"],
                    "boxes": detail["boxes"],
                    "confidence": detail["confidence"],
                }
            )
    return out


# --- 전체 판정 ------------------------------------------------------------------------


def _overall(stages: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    summary = summarize(stages)
    level = summary.get("risk_level")
    risk_stages = usable_stages_for(stages, STAGE_RISK)
    text = risk_stages[0].get("data") if risk_stages else None
    next_stage = summary.get("final_stage")
    next_stage = next_stage if next_stage in FINAL_STAGES else None
    next_text: Any = None
    if next_stage is not None:
        final = usable_stages_for(stages, next_stage)
        next_text = final[0].get("data") if final else None
    return {
        "level": level if level in OVERALL_LEVELS else None,
        "text": text if isinstance(text, str) else "",
        "next_stage": next_stage,
        "next_text": next_text if isinstance(next_text, str) else "",
    }


def _build_view(result: Any) -> dict[str, Any]:
    stages = view_stages(result)
    docs, classify_count = _documents(stages)
    _attach_extracts(stages, docs, classify_count)
    _attach_text(stages, docs, STAGE_VALIDATE, "validation")
    _attach_text(stages, docs, STAGE_OTHER, "other_guide")
    documents = [d.out() for d in sorted(docs, key=lambda d: d.index)]
    return {
        "documents": documents,
        "findings": _findings(docs, item_risks(stages)),
        "overall": _overall(stages),
    }
