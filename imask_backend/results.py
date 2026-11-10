# ==========================================================================
#  Upstage 응답 파싱과 요약
#  - parse_stages(response): output[] 항목마다 단계 이름(model)·status·data(content[0].text 를
#    JSON 으로 푼 값)·additional_values(신뢰도·좌표, JSON 으로 푼 값)를 뽑는다. 순서는 output 순서.
#    한 항목에 content 가 여럿일 수 있어(서류-분류는 서류마다 하나) contents 에 모두 담는다.
#  - summarize(response 또는 stages): 단계는 순서가 아니라 **이름으로** 찾는다(BRIEF §4).
#  - 모양이 달라도 예외를 던지지 않는다. 못 찾은 값은 None.
#  - 개수는 **읽을 수 있는 항목만** 센다. 하나도 읽지 못했으면(content 없음·빈 배열·[null]·
#    JSON 아님·실패 단계) 0 이 아니라 None — '확인된 0'과 '알 수 없음'을 섞지 않는다.
#    개수·종류·위험도·마지막 단계는 status 가 completed(또는 없음)인 단계만 쓴다(stage_names·
#    stage_counts 는 전체 output 그대로). 일반 텍스트가 정상인 단계(분류 코드·기타 안내·
#    Markdown)는 텍스트 그대로 받아들인다.
#
#  실제 응답(2026-11-02, config_id 3)에서 확인한 단계 이름 — evidence/T1/stage-shapes.md:
#    step_1_parse · step_2_classify · "Information Extract - 민감정보_추출" ·
#    "Validate - 필수항목_검증" · 병합-1 · "Instruct - 위험도_판정" · "Instruct - 권장_조치" ·
#    "Instruct - 기타_서류_안내" (검토_안내 는 위험도 '검토 필요' 일 때만 나온다)
#  Studio 노드 이름 앞에 노드 종류("Instruct - " 등)가 붙어 오므로 " - <이름>" 꼴도 같은 단계로 본다.
#  서류-인식·서류-분류는 이름이 step_1_parse·step_2_classify 로 오므로 그 이름과 step_type 으로도 찾는다.
#
#  최종 흐름(final_imask_workflow, 설정 "1" — final-flow/evidence/T0/final-shapes.md)의 새 이름:
#    "Information Extract - 추출_신청서"·"…추출_확인서"·"…추출_증빙"·"…추출_위임장" · "Match - 서류_대조" ·
#    "Validate - 묶음_검증" (그 밖은 예전과 같은 이름)
#  - step_type information-extract 는 **이름과 상관없이** 민감정보_추출 로 본다(추출 노드가 여럿이고 한 노드가
#    여러 번 나올 수 있다 — 서류와는 예전처럼 쪽 범위로 잇는다).
#  - 서류_대조(Match)·묶음_검증(Validate, 묶음 하나의 판정 — 서류별 필수항목_검증 과 다르다)은 새 정규 이름.
#  - 이름으로 못 찾을 때 step_type 으로: document-parse·document-classify·match(서류_대조)·validate(필수항목_검증)·
#    merge(병합-1). instruct 는 여럿이라 이름으로만 찾는다.
#  - summarize 의 키는 그대로다(scripts/api_e2e.py 가 결과 모양을 비교한다).
#
#  설정 60(v2_full) 응답 — is_v2 가 **설정 번호가 아니라 응답 모양으로** 가른다(둘 다 처리한다, 옛 경로는 그대로):
#    단계 이름이 대상_확인·단위_확인·필수_확인·형식_확인·일치_확인·상_확인·내용_검토·판정_* (상태 무관)이거나
#    "Information Extract - <10서식 코드>" 이거나 분류 코드가 10서식 중 하나면 v2 다.
#  - 이름 판정은 " - " 뒤의 노드 이름으로 한다. 저장된 key 는 믿지 않는다 — 옛 코드는 step_type validate 라서 사슬 노드를
#    필수항목_검증 으로 저장했을 수 있다. stage_key·_key_of 가 이 이름들을 새 정규 키로 돌려 서류별 검증 경로에 들어가지 않게 한다
#    (판정_* 은 모두 STAGE_V2_VERDICT 하나 — 지금 없는 판정_하 도 같다).
#  - v6(설정 9 계열): 사슬에 가림_확인(형식 뒤)·결합_확인(일치 뒤)이 더해졌다 — V2_CHAIN 순서 = 대상 → 단위 → 필수 → 형식 → 가림 → 일치 → 결합.
#    갈래를 고르는 Validate(등급_* — 모두 STAGE_V2_GRADE 하나, IRP해지_확인, 납세자번호_확인)도 이름으로 제 키를 받는다(사슬이 아니다 —
#    final_flow 가 읽지 않는다). 이 코드보다 먼저 저장된 v6 분석은 이 단계들의 key 가 필수항목_검증 이지만 _key_of 가 이름을 먼저 보므로
#    저장된 key 와 상관없이 같은 결과다.
#  - summarize(v2): risk_level = 판정 JSON 의 risk_level(final_flow.read_verdict), final_stage = 그 판정의 다음 단계
#    (검토 필요 → 검토_안내, 상·중·하 → 권장_조치 — 단 review_reasons 가 있으면 검토_안내(v4: 검토가 필요해도 등급을 낸다),
#    못 읽음 → None), other_document_count = 분류 코드 Other 서류 수,
#    extracted_document_count = 분류 서류를 읽었는데 Extract 단계가 하나도 없으면(대상 외) 0 — 못 읽은 것이 아니라 없는 것이다.
#    Extract 단계가 있는데 읽지 못했으면 옛 응답과 같이 None 이다.
# ==========================================================================

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

# 워크플로우 단계(정규 이름 = Studio 노드 이름)
STAGE_PARSE = "서류-인식"
STAGE_CLASSIFY = "서류-분류"
STAGE_EXTRACT = "민감정보_추출"
STAGE_VALIDATE = "필수항목_검증"
STAGE_MERGE = "병합-1"
STAGE_RISK = "위험도_판정"
STAGE_ACTION = "권장_조치"
STAGE_REVIEW = "검토_안내"
STAGE_OTHER = "기타_서류_안내"
# 최종 흐름에만 있는 단계
STAGE_MATCH = "서류_대조"
STAGE_BUNDLE_CHECK = "묶음_검증"
# 설정 60(v2_full)에만 있는 단계 — 검증 사슬(앞에서 red 면 뒤는 돌지 않는다)·상 항목 확인·내용 검토·판정(판정_* 모두)
STAGE_V2_TARGET = "대상_확인"
STAGE_V2_UNIT = "단위_확인"
STAGE_V2_REQUIRED = "필수_확인"
STAGE_V2_FORMAT = "형식_확인"
STAGE_V2_MASK = "가림_확인"  # v6 — 번호 칸 가림 범위
STAGE_V2_CONSISTENT = "일치_확인"
STAGE_V2_LINKAGE = "결합_확인"  # v6 — 가린 이름 + 연락처·식별 정보
STAGE_V2_HIGH = "상_확인"
STAGE_V2_CONTENT = "내용_검토"
STAGE_V2_VERDICT = "판정"
# v6 갈래 단계(등급·판정을 고르는 Validate — 실패가 아니다). 등급_* 은 모두 STAGE_V2_GRADE 하나(판정_* 과 같은 방식)
STAGE_V2_IRP = "IRP해지_확인"
STAGE_V2_TAXPAYER = "납세자번호_확인"
STAGE_V2_GRADE = "등급"
V2_CHAIN = (
    STAGE_V2_TARGET,
    STAGE_V2_UNIT,
    STAGE_V2_REQUIRED,
    STAGE_V2_FORMAT,
    STAGE_V2_MASK,
    STAGE_V2_CONSISTENT,
    STAGE_V2_LINKAGE,
)
_V2_NAMED = frozenset({*V2_CHAIN, STAGE_V2_HIGH, STAGE_V2_CONTENT, STAGE_V2_IRP, STAGE_V2_TAXPAYER})
V2_VERDICT_PREFIX = "판정_"
V2_GRADE_PREFIX = "등급_"
V2_EXTRACT_PREFIX = "Information Extract - "
# 설정 60 의 서식 코드(분류 코드·추출 노드 이름). 이름은 final_flow.FINAL_DOC_TYPES
V2_FORM_CODES = (
    "자동이체신청서",
    "휴면예금지급신청서",
    "FATCA_CRS_본인확인서",
    "위임장_상속",
    "지급보증거래_신청서",
    "소비자피해보상금_지급신청서",
    "외국인_세대구성원_확인서",
    "체크카드_가입신청서",
    "IRP_계약해지신청서",
    "IRP_신규신청서",
)
_V2_FORM_SET = frozenset(V2_FORM_CODES)

STAGE_KEYS = (
    STAGE_PARSE,
    STAGE_CLASSIFY,
    STAGE_EXTRACT,
    STAGE_VALIDATE,
    STAGE_MERGE,
    STAGE_RISK,
    STAGE_ACTION,
    STAGE_REVIEW,
    STAGE_OTHER,
    STAGE_MATCH,
    STAGE_BUNDLE_CHECK,
    *V2_CHAIN,
    STAGE_V2_HIGH,
    STAGE_V2_CONTENT,
    STAGE_V2_VERDICT,
    STAGE_V2_IRP,
    STAGE_V2_TAXPAYER,
    STAGE_V2_GRADE,
)

# 정규 이름과 다르게 오는 실제 이름(output[].model)
_STAGE_ALIASES = {
    "step_1_parse": STAGE_PARSE,
    "step_2_classify": STAGE_CLASSIFY,
}

# 이름과 상관없이 정규 이름을 정하는 step_type(추출 노드는 이름이 여럿 — 추출_신청서·…·민감정보_추출)
_STEP_TYPE_FIRST = {
    "information-extract": STAGE_EXTRACT,
}

# 이름으로 못 찾을 때 쓰는 step_type(instruct 는 여럿이라 쓰지 않는다. validate 는 서류별 검증으로 본다)
_STEP_TYPE_STAGES = {
    "document-parse": STAGE_PARSE,
    "document-classify": STAGE_CLASSIFY,
    "match": STAGE_MATCH,
    "validate": STAGE_VALIDATE,
    "merge": STAGE_MERGE,
}

# 마지막 단계 후보(위험도 상·중·하 → 권장_조치, 검토 필요 → 검토_안내)
FINAL_STAGES = (STAGE_ACTION, STAGE_REVIEW)


def _loads(value: Any) -> Any:
    """문자열이면 JSON 으로 풀고, 실패하면 원래 문자열. 문자열이 아니면 그대로."""
    if isinstance(value, (str, bytes, bytearray)):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return value
    return value


def _node_name(name: str) -> str:
    """단계 이름의 노드 이름 — "Validate - 대상_확인" 의 첫 " - " 뒤. 없으면 이름 그대로."""
    _, sep, node = name.partition(" - ")
    return node if sep else name


def _v2_key(name: Any) -> str | None:
    """설정 60 에만 있는 단계 이름 → 정규 키. 그 밖은 None(이름만 본다 — 저장된 key·상태와 무관)."""
    if not isinstance(name, str):
        return None
    node = _node_name(name)
    if node in _V2_NAMED:
        return node
    if node.startswith(V2_VERDICT_PREFIX):
        return STAGE_V2_VERDICT
    if node.startswith(V2_GRADE_PREFIX):
        return STAGE_V2_GRADE
    if name.startswith(V2_EXTRACT_PREFIX) and node in _V2_FORM_SET:
        return STAGE_EXTRACT
    return None


def stage_key(name: Any, step_type: Any = None) -> str | None:
    """output[].model(과 step_type)을 정규 단계 이름으로. 모르는 단계는 None.

    순서: 0. 설정 60 이름(_v2_key) 1. information-extract 는 이름과 상관없이 민감정보_추출 2. 이름(정규 이름·별칭·" - <정규 이름>")
    3. 그 밖의 step_type(_STEP_TYPE_STAGES).
    """
    v2 = _v2_key(name)
    if v2 is not None:
        return v2
    if isinstance(step_type, str) and step_type in _STEP_TYPE_FIRST:
        return _STEP_TYPE_FIRST[step_type]
    if isinstance(name, str):
        if name in STAGE_KEYS:
            return name
        if name in _STAGE_ALIASES:
            return _STAGE_ALIASES[name]
        for key in STAGE_KEYS:
            if name.endswith(" - " + key):
                return key
    if isinstance(step_type, str):
        return _STEP_TYPE_STAGES.get(step_type)
    return None


def _content_entry(entry: Any) -> dict[str, Any]:
    if not isinstance(entry, Mapping):
        return {"data": None, "additional_values": None}
    additional = entry.get("additional_values")
    return {
        "data": _loads(entry.get("text")),
        "additional_values": None if additional is None else _loads(additional),
    }


def parse_stages(response: Any) -> list[dict[str, Any]]:
    """응답의 output[] 를 단계 목록으로 바꾼다. 모양이 달라도 예외 없이 빈 목록·None 으로.

    항목마다: name(output[].model 원문), key(정규 단계 이름 또는 None), status, step_type,
    data·additional_values(content[0] 을 푼 값), contents(content[] 전부를 같은 방식으로 푼 목록).
    """
    if not isinstance(response, Mapping):
        return []
    output = response.get("output")
    if not isinstance(output, list):
        return []
    stages: list[dict[str, Any]] = []
    for item in output:
        if not isinstance(item, Mapping):
            continue
        content = item.get("content")
        contents = [_content_entry(c) for c in content] if isinstance(content, list) else []
        first = contents[0] if contents else {"data": None, "additional_values": None}
        name = item.get("model")
        step_type = item.get("step_type")
        stages.append(
            {
                "name": name,
                "key": stage_key(name, step_type),
                "status": item.get("status"),
                "step_type": step_type,
                "data": first["data"],
                "additional_values": first["additional_values"],
                "contents": contents,
            }
        )
    return stages


def _as_stages(response_or_stages: Any) -> list[Mapping[str, Any]]:
    if isinstance(response_or_stages, Mapping):
        return parse_stages(response_or_stages)
    if isinstance(response_or_stages, Sequence) and not isinstance(response_or_stages, (str, bytes)):
        return [s for s in response_or_stages if isinstance(s, Mapping)]
    return []


def _key_of(stage: Mapping[str, Any]) -> str | None:
    v2 = _v2_key(stage.get("name"))  # 저장된 key 보다 먼저 — 옛 코드가 사슬 노드를 필수항목_검증 으로 저장했을 수 있다
    if v2 is not None:
        return v2
    key = stage.get("key")
    if key in STAGE_KEYS:
        return key
    return stage_key(stage.get("name"), stage.get("step_type"))


def stages_for(stages: Sequence[Mapping[str, Any]], key: str) -> list[Mapping[str, Any]]:
    """정규 이름이 key 인 단계를 모두(output 순서대로)."""
    return [s for s in stages if _key_of(s) == key]


def _usable(stage: Mapping[str, Any]) -> bool:
    """요약에 쓸 단계: status 가 completed 이거나 없음(손으로 만든 stages). 실패·진행 중은 뺀다."""
    return stage.get("status") in (None, "completed")


def _usable_for(stages: Sequence[Mapping[str, Any]], key: str) -> list[Mapping[str, Any]]:
    return [s for s in stages_for(stages, key) if _usable(s)]


def _count_or_none(count: int) -> int | None:
    """하나도 읽지 못했으면 None(개수를 정할 수 없음)."""
    return count if count > 0 else None


def _has_text_or_object(data: Any) -> bool:
    return (isinstance(data, str) and bool(data.strip())) or isinstance(data, Mapping)


def _contents_of(stage: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    contents = stage.get("contents")
    if isinstance(contents, list):
        return [c for c in contents if isinstance(c, Mapping)]
    # contents 가 없는 목록(손으로 만든 stages 등)은 data·additional_values 하나로 본다
    return [{"data": stage.get("data"), "additional_values": stage.get("additional_values")}]


def _document_type(content: Mapping[str, Any]) -> str | None:
    """서류-분류 content 하나의 서류 종류: additional_values.document_type._value, 없으면 text.

    비지 않은 문자열만 인정한다(읽지 못한 항목은 None → 서류로 세지 않음).
    """
    additional = content.get("additional_values")
    if isinstance(additional, Mapping):
        doc_type = additional.get("document_type")
        if isinstance(doc_type, Mapping):
            doc_type = doc_type.get("_value")
        if isinstance(doc_type, str) and doc_type.strip():
            return doc_type.strip()
    data = content.get("data")
    if isinstance(data, str) and data.strip():
        return data.strip()
    return None


def _risk_level(stage: Mapping[str, Any]) -> str | None:
    """위험도_판정 의 additional_values.enum(상·중·하·검토 필요)."""
    additional = stage.get("additional_values")
    if isinstance(additional, Mapping):
        value = additional.get("enum")
        if isinstance(value, str) and value:
            return value
    return None


def is_v2(response_or_stages: Any) -> bool:
    """설정 60(v2_full) 모양의 응답인지 — 설정 번호를 보지 않는다(머리 주석). 못 읽는 입력(아주 깊은 JSON 등)은 False, 예외 없음."""
    try:
        stages = _as_stages(response_or_stages)
        if any(_v2_key(s.get("name")) is not None for s in stages):
            return True
        return any(
            _document_type(c) in _V2_FORM_SET for s in stages_for(stages, STAGE_CLASSIFY) for c in _contents_of(s)
        )
    except Exception:  # 응답 경계 — 뒤따르는 읽기가 값 없는 경고를 남긴다
        return False


def v2_next_stage(level: Any, reasons: Any = None) -> str | None:
    """설정 60 판정의 다음 단계 — 검토 필요 → 검토_안내, 상·중·하 → 권장_조치, 그 밖 None.

    검토 사유(review_reasons)에 글자가 하나라도 있으면 등급과 상관없이 검토_안내다. v4 워크플로우는 등급과 검토를 나눠
    검토가 필요해도 risk_level 에 상·중을 낸다(옛 판은 검토 사유가 있으면 risk_level 이 검토 필요라 결과가 같다).
    """
    if level == "검토 필요":
        return STAGE_REVIEW
    if level in ("상", "중", "하"):
        has_reason = isinstance(reasons, list) and any(isinstance(r, str) and r.strip() for r in reasons)
        return STAGE_REVIEW if has_reason else STAGE_ACTION
    return None


def summarize(response_or_stages: Any) -> dict[str, Any]:
    """응답(또는 parse_stages 결과)에서 요약값을 뽑는다. 못 찾은 값은 None, 예외 없음.

    읽는 위치(evidence/T1/stage-shapes.md). 아래 여섯 값은 status 가 completed(또는 없음)인 단계만 쓴다
    (stage_names·stage_counts 는 상태와 상관없이 전체 output 을 그대로 센다):
      document_count           서류-분류 content[] 중 분류 코드를 읽을 수 있는 항목 수(서류마다 하나)
      document_types           그 항목들의 additional_values.document_type._value (없으면 text)
      extracted_document_count 민감정보_추출(추출 노드 모두) output 항목 중 data 가 JSON 객체인 수(서류마다 하나)
      risk_level               위험도_판정 additional_values.enum
      final_stage              권장_조치·검토_안내 중 나온 단계의 정규 이름
      other_document_count     기타_서류_안내 output 항목 중 본문(text)이 있는 수
    세 개수와 document_types 는 하나도 읽지 못했으면(단계 없음 포함) None.
    설정 60 응답(is_v2): risk_level·final_stage·other_document_count 는 머리 주석대로 판정 JSON·분류 코드로 읽고,
    분류 서류를 읽었는데 추출 단계가 하나도 없으면 extracted_document_count 는 0 이다(대상 외).
    """
    stages = _as_stages(response_or_stages)
    names = [s.get("name") for s in stages if isinstance(s.get("name"), str)]

    document_types = [
        t
        for s in _usable_for(stages, STAGE_CLASSIFY)
        for t in (_document_type(c) for c in _contents_of(s))
        if t is not None
    ]

    extracted = sum(1 for s in _usable_for(stages, STAGE_EXTRACT) if isinstance(s.get("data"), Mapping))
    extracted_count = _count_or_none(extracted)

    if is_v2(stages):
        from .final_flow import read_verdict  # 순환 import(final_flow → findings → results) — 여기서 늦게

        decision = read_verdict(stages)
        risk_level = decision.get("risk_level") if isinstance(decision, Mapping) else None
        final_stage = v2_next_stage(risk_level, decision.get("review_reasons") if isinstance(decision, Mapping) else None)
        others = sum(1 for t in document_types if t.lower() == "other")
        if document_types and not stages_for(stages, STAGE_EXTRACT):
            extracted_count = 0  # 대상 외 — 추출 단계 자체가 없다(머리 주석)
    else:
        risk_level = next((r for r in (_risk_level(s) for s in _usable_for(stages, STAGE_RISK)) if r), None)
        final_stage = next((k for k in (_key_of(s) for s in stages if _usable(s)) if k in FINAL_STAGES), None)
        others = sum(1 for s in _usable_for(stages, STAGE_OTHER) if _has_text_or_object(s.get("data")))

    return {
        "stage_names": list(dict.fromkeys(names)),
        "stage_counts": dict(Counter(names)),
        "document_count": _count_or_none(len(document_types)),
        "document_types": document_types or None,
        "extracted_document_count": extracted_count,
        "risk_level": risk_level,
        "final_stage": final_stage,
        "other_document_count": _count_or_none(others),
    }


# --- 다른 모듈(findings 등)이 쓰는 공개 도우미 — 위 요약과 같은 규칙을 그대로 쓴다 -----------------


def as_stages(response_or_stages: Any) -> list[Mapping[str, Any]]:
    """응답(Mapping)이면 parse_stages, 단계 목록이면 Mapping 인 것만. 그 밖은 빈 목록."""
    return _as_stages(response_or_stages)


def usable_stages_for(stages: Sequence[Mapping[str, Any]], key: str) -> list[Mapping[str, Any]]:
    """정규 이름이 key 이고 쓸 수 있는(completed 또는 상태 없음) 단계를 output 순서대로."""
    return _usable_for(stages, key)


def stage_contents(stage: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """단계의 content 목록(Mapping 인 것만). contents 가 없으면 data·additional_values 하나로 본다."""
    return _contents_of(stage)


def document_type(content: Mapping[str, Any]) -> str | None:
    """서류-분류 content 하나의 분류 코드(document_type._value, 없으면 text). 못 읽으면 None."""
    return _document_type(content)
