# ==========================================================================
#  최종 흐름(final_imask_workflow, 설정 "1") 응답의 새 재료 읽기 — 순수 함수(아직 어디에도 연결하지 않는다)
#  입력은 results.parse_stages(response) 의 결과(stages, 응답 Mapping 을 줘도 parse_stages 로 바꾼다).
#  모양: final-flow/evidence/T0/final-shapes.md
#  - FINAL_DOC_TYPES: 분류 코드 14개 → (한국어 이름, 묶음). 순서는 설정의 분류 oneOf 와 같다(테스트가 확인).
#    묶음은 추출 노드 이름 "추출_<묶음>" 의 <묶음>(신청서·확인서·증빙·위임장), Other 는 None.
#  - read_decision(stages): 위험도_판정 본문의 "키: 값" 줄(미션 2 정답지 키 5개). 등급의 기준은 여전히
#    additional_values.enum(results.summarize) — 여기 risk_level 은 '본문에 적힌 값'이다.
#  - read_bundle_checks(stages): 묶음_검증의 verdict 와 규칙별 결과(pass·fail·absent·unknown, 서류별 ok).
#  - read_links(stages): 서류_대조의 기준 서류와 대상 서류 쌍(linked·unmatched·insufficient).
#  공통 규칙
#  - 단계는 status 가 completed(또는 없음)인 **첫** 항목만 본다. 단계가 없으면(옛 워크플로우) None.
#  - 바깥 모양이 틀려도 예외 없이 그 항목만 버리고, 못 읽은 값은 None — 확인된 빈 목록 [] 과 섞지 않는다.
#    그래도 예상 못 한 예외가 나면 값 없는 경고 로그를 남기고 None(나중에 build_view 전체가 비지 않게).
#  - 원문 값(추출 값·anchor_value·target_values·검증 reason·conditions 의 값)은 결과에 넣지 않는다 — 화면은
#    탐지 항목 id("<서류 index>:<추출 키>")로 값을 찾는다.
#  - 서류 번호 index 는 findings 의 서류 번호와 같다(findings._documents — 분류 contents 순서, 0부터).
#    어느 추출 노드로 간 서류인지는 병합-1 data.source_steps 의 step_name·branch_key("<index>:<코드>") 순서로 안다
#    (분류 서류가 아닌 index·같은 서류의 두 번째 항목은 버린다).
#  - 한도(아래 상수)를 넘는 값·목록은 자르지 않고 버린다. 짝 없는 서로게이트가 든 문자열도 버린다(textsafe) —
#    원문뿐 아니라 **푼 뒤의 값**도 본다(JSON escape "\ud800" 이 풀리면 서로게이트가 된다). 마지막 안전망으로 결과 어디에든
#    남아 있으면 결과 전체를 None(결과는 늘 UTF-8 로 인코딩된다).
#    모든 처리는 입력 길이에 선형이다(정규식은 고정 글자로 시작하거나 줄 처음에 고정). findings 의 추출 짝짓기를 쓰는
#    read_links 는 서류·추출 개수 한도 안에서만 짝짓는다(MAX_LINK_DOCUMENTS·MAX_LINK_EXTRACTS).
# ==========================================================================

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from .findings import _attach_extracts, _documents, _ranges
from .results import STAGE_BUNDLE_CHECK, STAGE_EXTRACT, STAGE_MATCH, STAGE_MERGE, STAGE_RISK, as_stages, usable_stages_for
from .textsafe import has_unpaired_surrogates, text_is_safe

logger = logging.getLogger("imask.final_flow")

# --- 서류 종류와 묶음 -------------------------------------------------------------------

GROUP_APPLICATION = "신청서"
GROUP_CONFIRMATION = "확인서"
GROUP_PROOF = "증빙"
GROUP_ATTORNEY = "위임장"
GROUPS = (GROUP_APPLICATION, GROUP_CONFIRMATION, GROUP_PROOF, GROUP_ATTORNEY)
# 검증 규칙의 nodeName("추출_신청서")과 응답 단계 이름("Information Extract - 추출_신청서")의 앞부분
EXTRACT_NODE_PREFIX = "추출_"
EXTRACT_STEP_PREFIX = "Information Extract - "

# 분류 코드 → (짧은 한국어 이름, 묶음). 기존 5개 이름은 화면 src/display/rules.ts DOC_TYPE_NAMES 와 같다
FINAL_DOC_TYPES: dict[str, tuple[str, str | None]] = {
    "loan_application": ("대출신청서", GROUP_APPLICATION),
    "consent_form": ("동의서", GROUP_CONFIRMATION),
    "income_proof": ("소득 증빙", GROUP_PROOF),
    "power_of_attorney": ("위임장", GROUP_ATTORNEY),
    "debt_transaction": ("채무내역", GROUP_PROOF),
    "payment_guarantee_application": ("지급보증거래 신청서", GROUP_APPLICATION),
    "consumer_compensation_claim": ("소비자피해보상금 지급신청서", GROUP_APPLICATION),
    "foreign_household_confirmation": ("외국인 세대구성원 확인서", GROUP_CONFIRMATION),
    "debit_card_application": ("체크카드 가입신청서", GROUP_APPLICATION),
    "auto_transfer_application": ("자동이체 신청서", GROUP_APPLICATION),
    "dormant_deposit_claim": ("휴면예금 지급신청서", GROUP_APPLICATION),
    "fatca_crs_certification": ("FATCA/CRS 본인확인서", GROUP_CONFIRMATION),
    "retirement_pension_application": ("퇴직연금 신청서", GROUP_APPLICATION),
    "Other": ("기타", None),
}

# --- 한도 -------------------------------------------------------------------------------

# 이름·식별자(검증 규칙 이름, 필드 이름, 대조 키) 길이
MAX_NAME_LENGTH = 200
# 병합-1 source_steps 항목 수(넘으면 서류 경로를 모르는 것으로 본다)
MAX_SOURCE_STEPS = 1000
# branch_key 앞의 서류 번호 자릿수(아주 긴 숫자 문자열을 int 로 바꾸지 않게)
MAX_INDEX_DIGITS = 6
# 묶음_검증 checks 항목 수
MAX_CHECKS = 200
# 서류_대조 targets·matched 항목 수
MAX_LINK_TARGETS = 50
MAX_MATCHED = 1000
# 서류_대조 쌍을 만들 때 대상 서류의 추출 항목을 findings 와 같은 짝짓기(_attach_extracts)로 붙인다. 그 짝짓기는
# 추출마다 서류 목록 전체를 훑고 짝 없는 추출을 목록에 덧붙여 (추출 수 × (서류 수 + 추출 수)) 시간이 든다 —
# 분류 서류 수와 쓸 수 있는 추출 단계 수가 한도를 넘으면 짝짓기 전에 pairs 를 None 으로 둔다(일부만 잘라 잇지 않는다).
# 실제 묶음은 서류 수십 개 안쪽이고, 추출은 서류마다 하나다(MAX_SOURCE_STEPS 1000 과 같은 폭).
MAX_LINK_DOCUMENTS = 500
MAX_LINK_EXTRACTS = 1000
# 위험도_판정 본문: 읽는 줄 수, 값 길이(인용 표시를 지운 뒤), 목록 항목 수·항목 길이
MAX_DECISION_LINES = 200
MAX_DECISION_VALUE_LENGTH = 2000
MAX_DECISION_ITEMS = 50
MAX_DECISION_ITEM_LENGTH = 100
# 열거 값(verdict·severity)으로 볼 최대 길이
_MAX_ENUM_LENGTH = 32

# --- 값 -------------------------------------------------------------------------------

VERDICTS = ("green", "yellow", "red")
SEVERITIES = ("error", "warning")
CHECK_PASS = "pass"
CHECK_FAIL = "fail"
CHECK_ABSENT = "absent"  # 그 종류 서류가 묶음에 없음('필수 항목 없음'이 아니다)
CHECK_UNKNOWN = "unknown"
LINK_LINKED = "linked"
LINK_UNMATCHED = "unmatched"
LINK_INSUFFICIENT = "insufficient"  # 근거 부족 — 기준 서류 없음·빈 값끼리의 '일치' 등
# 기준 서류를 못 찾았을 때 쌍 id 의 기준 자리
NO_ANCHOR = "-"

DECISION_KEYS = ("risk_level", "document_types", "sensitive_categories", "review_reasons", "reason")
DECISION_LIST_KEYS = frozenset({"document_types", "sensitive_categories", "review_reasons"})
DECISION_LEVELS = ("상", "중", "하", "검토 필요")

# 인용 표시 【†n】 — 고정 글자로 시작해 선형
_CITATION = re.compile(r"【†\d{1,9}】")
# 키 줄: 줄 처음(글머리·굵게를 뗀 뒤)의 영문 키 + ':' — match 로 한 번만 시도한다
_KEY_LINE = re.compile(r"([A-Za-z_]{1,40})[ \t]*:")
# 지운 인용 표시 앞뒤를 띄어 쓰지 않는 글자(문장 부호)
_NO_SPACE_BEFORE = frozenset(",.;:!?)]}…。、")
_QUOTE_PAIRS = (('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’"), ("`", "`"))

Stages = list[Mapping[str, Any]]


# --- 공통 도우미 ------------------------------------------------------------------------


def _guarded(reader: Callable[[Stages], Any], stages: Any) -> Any:
    """reader(as_stages(stages)). 예상 못 한 예외는 값 없는 경고 후 None.

    마지막 안전망: 결과 어딘가에 짝 없는 서로게이트가 남아 있으면(각 값의 검사가 빠진 버그) 결과 전체를 None —
    결과는 늘 json.dumps(…, ensure_ascii=False).encode("utf-8") 로 인코딩된다.
    """
    try:
        result = reader(as_stages(stages))
        if has_unpaired_surrogates(result):
            logger.warning("최종 흐름 재료에 인코딩할 수 없는 글자가 남아 버림(%s)", reader.__name__)
            return None
        return result
    except Exception as exc:  # 바깥 모양 때문에 화면 전체가 비지 않게 — 값 없이 예외 종류만
        logger.warning("최종 흐름 재료를 읽지 못함(%s): %s", reader.__name__, type(exc).__name__)
        return None


def _first(stages: Stages, key: str) -> Mapping[str, Any] | None:
    found = usable_stages_for(stages, key)
    return found[0] if found else None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _name(value: Any) -> str | None:
    """이름·식별자: 비지 않은(공백만도 아닌) 문자열, MAX_NAME_LENGTH 이하, 짝 없는 서로게이트 없음 → 원래 문자열 그대로."""
    if isinstance(value, str) and len(value) <= MAX_NAME_LENGTH and value.strip() and text_is_safe(value):
        return value
    return None


def _enum(value: Any, allowed: Sequence[str]) -> str | None:
    """앞뒤 공백을 지우고 소문자로 바꾼 값이 allowed 중 하나면 그 값."""
    if isinstance(value, str) and len(value) <= _MAX_ENUM_LENGTH:
        cleaned = value.strip().lower()
        if cleaned in allowed:
            return cleaned
    return None


def _group_of_node(node_name: Any) -> str | None:
    """'추출_<묶음>' → <묶음>(알려진 묶음만). 그 밖은 None."""
    if isinstance(node_name, str) and node_name.startswith(EXTRACT_NODE_PREFIX):
        group = node_name[len(EXTRACT_NODE_PREFIX) :]
        return group if group in GROUPS else None
    return None


def _group_of_step(step_name: Any) -> str | None:
    """'Information Extract - 추출_<묶음>' → <묶음>."""
    if isinstance(step_name, str) and step_name.startswith(EXTRACT_STEP_PREFIX):
        return _group_of_node(step_name[len(EXTRACT_STEP_PREFIX) :])
    return None


def _branch_index(branch_key: Any) -> int | None:
    """'<index>:<코드>' 의 index(ASCII 숫자 MAX_INDEX_DIGITS 자리 이하). 아니면 None."""
    if not isinstance(branch_key, str):
        return None
    head, sep, _ = branch_key.partition(":")
    if not sep or not head or len(head) > MAX_INDEX_DIGITS or not (head.isascii() and head.isdigit()):
        return None
    return int(head)


def _routes(stages: Stages, known: set[int]) -> dict[str, list[int]] | None:
    """추출 단계 이름 → 그 단계로 간 서류 index(source_steps 순서). 병합-1 을 못 읽으면 None(경로를 모름).

    index 가 분류 서류(known)가 아니거나 앞에서 이미 나온 서류면 그 항목을 버린다.
    """
    merge = _first(stages, STAGE_MERGE)
    if merge is None:
        return None
    steps = _mapping(merge.get("data")).get("source_steps")
    if not isinstance(steps, list) or len(steps) > MAX_SOURCE_STEPS:
        return None
    routes: dict[str, list[int]] = {}
    seen: set[int] = set()
    for step in steps:
        if not isinstance(step, Mapping):
            continue
        name = step.get("step_name")
        index = _branch_index(step.get("branch_key"))
        if not isinstance(name, str) or index is None or index not in known or index in seen:
            continue
        seen.add(index)
        routes.setdefault(name, []).append(index)
    return routes


def _blank(value: Any) -> bool:
    """빈 값인지 — findings 가 탐지 항목을 만들지 않는 값과 같다(공백만인 문자열·None·bool·빈 목록/객체·그 밖의 꼴)."""
    if isinstance(value, str):
        return not value.strip()
    if value is None or isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return False
    if isinstance(value, (list, Mapping)):
        return not value
    return True


class _UniqueIds:
    """같은 이름이 또 나오면 '이름#2'·'이름#3'(이미 쓴 id 와도 겹치지 않게)."""

    def __init__(self) -> None:
        self._used: set[str] = set()
        self._counts: dict[str, int] = {}

    def next(self, name: str) -> str:
        count = self._counts.get(name, 0)
        while True:
            count += 1
            candidate = name if count == 1 else f"{name}#{count}"
            if candidate not in self._used:
                break
        self._counts[name] = count
        self._used.add(candidate)
        return candidate


# --- 위험도_판정 본문 ---------------------------------------------------------------------


def read_decision(stages: Any) -> dict[str, Any] | None:
    """위험도_판정 첫 completed 항목 본문의 "키: 값" 줄 → {risk_level, document_types, sensitive_categories,
    review_reasons, reason}. 못 읽은 키는 None. 단계가 없거나 본문이 문자열이 아니거나 키 줄이 하나도 없으면 None.

    - 앞 MAX_DECISION_LINES 줄만 읽는다. 모르는 키는 버리고, 같은 키는 첫 줄이 정한다(그 값을 못 읽어도 다음 줄을 보지 않음).
    - 줄의 앞뒤 공백·글머리("- "·"* ")·굵게("**")를 떼고, 값의 인용 표시 【†n】(여러 개·사이 공백)를 지운다.
    - 값에 짝 없는 서로게이트가 있거나(원문, 그리고 JSON 목록을 푼 뒤·다듬은 뒤의 값 — 목록은 한 항목이라도 그렇면 전체)
      인용 표시를 지운 값이 MAX_DECISION_VALUE_LENGTH 를 넘으면 그 값은 None.
    - risk_level 은 상·중·하·검토 필요 중 하나만. reason 은 빈 값이면 None.
    - 목록 키: "[a, b]"·"[]"·"a, b"(JSON 문자열 목록도) → 목록. 따옴표를 떼고 빈 항목은 버린다.
      항목이 MAX_DECISION_ITEMS 개를 넘으면 그 값은 None, MAX_DECISION_ITEM_LENGTH 를 넘는 항목은 버린다(모두 버려지면 None).
      값이 비었거나 '['로 시작해 ']'로 끝나지 않으면 None('확인된 빈 목록'은 빈 항목만 있는 "[]" 꼴뿐).
    """
    return _guarded(_read_decision, stages)


def _read_decision(stages: Stages) -> dict[str, Any] | None:
    stage = _first(stages, STAGE_RISK)
    if stage is None:
        return None
    text = stage.get("data")
    if not isinstance(text, str):
        return None
    found: dict[str, Any] = {}
    for line in text.split("\n", MAX_DECISION_LINES)[:MAX_DECISION_LINES]:
        parsed = _key_line(line)
        if parsed is None:
            continue
        key, raw = parsed
        if key not in found:
            found[key] = _decision_value(key, raw)
    if not found:
        return None
    return {key: found.get(key) for key in DECISION_KEYS}


def _key_line(line: str) -> tuple[str, str] | None:
    """(키, 값 원문) — 키가 DECISION_KEYS 중 하나인 줄만."""
    body = line.strip()
    if body[:2] in ("- ", "* "):
        body = body[2:].lstrip()
    body = body.replace("**", "")
    match = _KEY_LINE.match(body)
    if match is None:
        return None
    key = match.group(1).lower()
    if key not in DECISION_KEYS:
        return None
    return key, body[match.end() :]


def _strip_citations(text: str) -> str:
    """인용 표시 【†n】 와 그 앞 공백을 지운다. 지운 자리 양쪽이 글자면 한 칸 띄운다(문장 부호 앞은 붙인다)."""
    if "【" not in text:
        return text
    parts = _CITATION.split(text)
    last = len(parts) - 1
    out: list[str] = []
    gap = False  # 지운 표시 앞에 공백이 있었는지
    for i, part in enumerate(parts):
        body = part.rstrip() if i < last else part
        if body:
            if gap and out and not body[0].isspace() and body[0] not in _NO_SPACE_BEFORE:
                out.append(" ")
            out.append(body)
            gap = False
        if len(body) < len(part):
            gap = True
    return "".join(out)


def _decision_value(key: str, raw: str) -> Any:
    if not text_is_safe(raw):
        return None
    value = _strip_citations(raw).strip()
    if len(value) > MAX_DECISION_VALUE_LENGTH:
        return None
    if key in DECISION_LIST_KEYS:
        result: Any = _decision_list(value)
    elif key == "risk_level":
        result = value if value in DECISION_LEVELS else None
    else:
        result = value or None
    # 다듬고 푼 **뒤의** 값도 같은 기준으로 본다(JSON escape 가 짝 없는 서로게이트로 풀릴 수 있다)
    return result if _safe_value(result) else None


def _safe_value(value: Any) -> bool:
    """None·문자열·문자열 목록이 모두 UTF-8 로 인코딩되는지(짝 없는 서로게이트 없음)."""
    if isinstance(value, str):
        return text_is_safe(value)
    if isinstance(value, list):
        return all(isinstance(item, str) and text_is_safe(item) for item in value)
    return value is None


def _json_strings(value: str) -> list[str] | None:
    """JSON 문자열 목록이면 그 목록(따옴표 안의 쉼표를 지키려고). 아니면 None."""
    try:
        parsed = json.loads(value)
    except (ValueError, RecursionError):
        return None
    if isinstance(parsed, list) and all(isinstance(item, str) for item in parsed):
        return parsed
    return None


def _unquote(item: str) -> str:
    for opening, closing in _QUOTE_PAIRS:
        if len(item) >= 2 and item.startswith(opening) and item.endswith(closing):
            return item[1:-1].strip()
    return item


def _decision_list(value: str) -> list[str] | None:
    if not value:
        return None
    if value.startswith("["):
        if not value.endswith("]"):
            return None
        items = _json_strings(value)
        if items is None:
            items = value[1:-1].split(",")
        elif not all(text_is_safe(item) for item in items):
            # 원문은 ASCII 여도 "\ud800" 같은 escape 가 짝 없는 서로게이트로 풀린다 — 그 키의 값 전체를 버린다
            return None
    else:
        items = value.split(",")
    cleaned = [item for item in (_unquote(i.strip()) for i in items) if item]
    if len(cleaned) > MAX_DECISION_ITEMS:
        return None
    kept = [item for item in cleaned if len(item) <= MAX_DECISION_ITEM_LENGTH]
    # 항목이 있었는데 모두 길어서 버렸으면 '확인된 빈 목록'이 아니다
    return kept if kept or not cleaned else None


# --- 묶음_검증 --------------------------------------------------------------------------


def read_bundle_checks(stages: Any) -> dict[str, Any] | None:
    """묶음_검증 첫 completed 항목 → {"verdict", "checks"}. 단계가 없으면 None.

    - verdict: additional_values.verdict(비지 않은 문자열이 아니면 본문)가 green·yellow·red 면 그 값, 아니면 None.
    - checks: additional_values.checks 가 목록이 아니거나 MAX_CHECKS 개를 넘으면 None. 항목마다
      {id, name, severity, passed, field, group, status, documents} — 이름이 없는(문자열 아님·빈 값·너무 김·
      서로게이트) 규칙은 버린다. reason·conditions 의 값은 넣지 않는다.
      status: passed True → pass / passed False 이고 left.value 가 null → absent(그 종류 서류 없음 — 다만 병합-1 이
      그 노드로 간 서류를 보여 주면 모순이라 unknown) / passed False 이고 값이 목록 → fail / 그 밖 unknown.
      documents: left.value 가 0 이상 정수 목록이고 길이가 그 추출 노드로 간 서류 수와 같으면
      [{index, ok: 길이 > 0}](서류 순서 = 병합-1 source_steps), 아니면 None.
    """
    return _guarded(_read_bundle_checks, stages)


def _read_bundle_checks(stages: Stages) -> dict[str, Any] | None:
    stage = _first(stages, STAGE_BUNDLE_CHECK)
    if stage is None:
        return None
    additional = _mapping(stage.get("additional_values"))
    raw = additional.get("verdict")
    verdict = _enum(raw if isinstance(raw, str) and raw.strip() else stage.get("data"), VERDICTS)
    return {"verdict": verdict, "checks": _checks(stages, additional.get("checks"))}


def _checks(stages: Stages, raw: Any) -> list[dict[str, Any]] | None:
    if not isinstance(raw, list) or len(raw) > MAX_CHECKS:
        return None
    docs, _ = _documents(stages)
    routes = _routes(stages, {d.index for d in docs})
    ids = _UniqueIds()
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        name = _name(item.get("name"))
        if name is None:
            continue
        left = _mapping(_mapping(item.get("conditions")).get("left"))
        node = _name(left.get("nodeName"))
        node_docs = routes.get(EXTRACT_STEP_PREFIX + node, []) if routes is not None and node is not None else None
        passed = item.get("passed")
        passed = passed if isinstance(passed, bool) else None
        out.append(
            {
                "id": ids.next(name),
                "name": name,
                "severity": _enum(item.get("severity"), SEVERITIES),
                "passed": passed,
                "field": _name(left.get("field")),
                "group": _group_of_node(node),
                "status": _check_status(passed, left, node_docs),
                "documents": _check_documents(left.get("value"), node_docs),
            }
        )
    return out


def _check_status(passed: bool | None, left: Mapping[str, Any], node_docs: list[int] | None) -> str:
    if passed is True:
        return CHECK_PASS
    if passed is False:
        if "value" in left and left["value"] is None:
            # 그 종류 서류가 묶음에 없음. 병합-1 이 그 노드로 간 서류를 보여 주면 모순 — 단정하지 않는다
            return CHECK_ABSENT if not node_docs else CHECK_UNKNOWN
        if isinstance(left.get("value"), list):
            return CHECK_FAIL
    return CHECK_UNKNOWN


def _check_documents(value: Any, node_docs: list[int] | None) -> list[dict[str, Any]] | None:
    if node_docs is None or not isinstance(value, list) or len(value) != len(node_docs):
        return None
    if not all(_is_int(length) and length >= 0 for length in value):
        return None
    return [{"index": index, "ok": length > 0} for index, length in zip(node_docs, value)]


# --- 서류_대조 --------------------------------------------------------------------------


def read_links(stages: Any) -> dict[str, Any] | None:
    """서류_대조 첫 completed 항목 → {"field", "anchor_index", "pairs"}. 단계가 없으면 None.

    - anchor_index: 분류 서류 중 쪽 범위가 additional_values.page_ranges 와 같은 첫 서류(빈 범위는 짝 없음).
    - field: 첫 대상(targets 의 첫 객체)의 document_match.anchor_key.
    - pairs: targets 가 목록이 아니거나 MAX_LINK_TARGETS 개를 넘거나 병합-1 을 못 읽거나, 분류 서류가 MAX_LINK_DOCUMENTS 개·
      쓸 수 있는 추출 단계가 MAX_LINK_EXTRACTS 개를 넘으면(짝짓기 시간 한도) None. 대상(targets[].step_name)
      마다 그 추출 노드로 간 서류마다 {id: "link:<anchor_index>:<target_index>", target_index, group, status}
      (기준 서류를 못 찾으면 id 의 기준 자리는 "-"). 같은 대상 서류는 첫 쌍만, 기준 서류 자신은 넣지 않는다.
      status — insufficient: 기준 서류 없음, anchor_value 가 빔, matched 를 못 읽음(목록 아님·한도 넘음),
      대조 키를 모름, 대상 서류의 추출 항목이 없거나 그 키 값이 빔 / linked: 대상 서류 쪽 범위가 matched[].page_ranges
      중 하나와 같음 / unmatched: 그 밖.
    값(anchor_value·target_values)은 넣지 않는다.
    """
    return _guarded(_read_links, stages)


def _matched_ranges(raw: Any) -> set[tuple[tuple[int, int], ...]] | None:
    if not isinstance(raw, list) or len(raw) > MAX_MATCHED:
        return None
    return {ranges for ranges in (_ranges(entry) for entry in raw if isinstance(entry, Mapping)) if ranges}


def _read_links(stages: Stages) -> dict[str, Any] | None:
    stage = _first(stages, STAGE_MATCH)
    if stage is None:
        return None
    additional = _mapping(stage.get("additional_values"))
    docs, classify_count = _documents(stages)
    by_index = {doc.index: doc for doc in docs}  # 분류 서류만(아래에서 덧붙는 짝 없는 추출 서류는 넣지 않는다)
    anchor_ranges = _ranges(additional)
    anchor = next((doc for doc in docs if anchor_ranges and doc.ranges == anchor_ranges), None)
    anchor_index = anchor.index if anchor is not None else None

    targets = additional.get("targets")
    if not isinstance(targets, list) or len(targets) > MAX_LINK_TARGETS:
        return {"field": None, "anchor_index": anchor_index, "pairs": None}
    first = next((t for t in targets if isinstance(t, Mapping)), None)
    field = _name(_mapping(first.get("document_match")).get("anchor_key")) if first is not None else None

    routes = _routes(stages, set(by_index))
    if routes is None:
        return {"field": field, "anchor_index": anchor_index, "pairs": None}
    if len(docs) > MAX_LINK_DOCUMENTS or len(usable_stages_for(stages, STAGE_EXTRACT)) > MAX_LINK_EXTRACTS:
        return {"field": field, "anchor_index": anchor_index, "pairs": None}  # 짝짓기가 제곱 시간이 되기 전에 멈춘다
    _attach_extracts(stages, docs, classify_count)  # 대상 서류의 추출 항목 — findings 와 같은 짝짓기
    anchor_part = str(anchor_index) if anchor_index is not None else NO_ANCHOR
    seen: set[int] = set()
    pairs: list[dict[str, Any]] = []
    for target in targets:
        if not isinstance(target, Mapping):
            continue
        step_name = target.get("step_name")
        if not isinstance(step_name, str):
            continue
        match = _mapping(target.get("document_match"))
        key = _name(match.get("target_key")) or _name(match.get("anchor_key"))
        matched = _matched_ranges(match.get("matched"))
        weak = anchor_index is None or _blank(match.get("anchor_value")) or matched is None or key is None
        group = _group_of_step(step_name)
        for index in routes.get(step_name, []):
            if index in seen or index == anchor_index:
                continue
            seen.add(index)
            doc = by_index[index]
            data = doc.extract[0] if doc.extract is not None else None
            if weak or data is None or _blank(data.get(key)):
                status = LINK_INSUFFICIENT
            elif doc.ranges and matched is not None and doc.ranges in matched:
                status = LINK_LINKED
            else:
                status = LINK_UNMATCHED
            pairs.append({"id": f"link:{anchor_part}:{index}", "target_index": index, "group": group, "status": status})
    return {"field": field, "anchor_index": anchor_index, "pairs": pairs}
