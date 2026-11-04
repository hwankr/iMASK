# ==========================================================================
#  최종 흐름(final_imask_workflow, 설정 "1") 읽기 — imask_backend.final_flow 와 새 단계 인식(네트워크 없음)
#  자료: tests/fixtures/final_flow/ — 실제 응답 5건(A_smoke 6서류·B_blank_autotransfer 빈 서식 2서류·
#  C_mismatch 3서류·D_blank_applicant 신청인 성명 빈 2서류·E_team_forms 팀원 서식 4서류, 값은 모두 합성, 에이전트 id 는
#  <AGENT>, Upstage id 는 자리표시자)과 설정 원본(config.json, API step 형식). D·E 는 final-flow T3 에서 더함.
#  - 서류 종류 표가 설정의 분류 oneOf·경로와 같은지, 14개 이름이 화면 DOC_TYPE_NAMES 와 모두 같은지
#  - 다섯 응답의 summarize·build_view(계약 모양 그대로, 묶음_검증이 서류별 validation 에 붙지 않음)
#  - read_bundle_checks·read_links·read_decision 의 기대값과 서류 번호가 findings 와 같은지, 값이 결과에 없는지
#  - 옛 응답은 None, 응답 경계 강건성(모양·한도·서로게이트·깊은 중첩·선형 시간·예외 안전망)
# ==========================================================================

from __future__ import annotations

import copy
import functools
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

import pytest
from fake_findings import build_findings_response
from fake_responses import build_response
from view_contract import assert_view

from imask_backend import final_flow
from imask_backend.final_flow import (
    CHECK_ABSENT,
    CHECK_FAIL,
    CHECK_PASS,
    CHECK_UNKNOWN,
    DECISION_KEYS,
    DECISION_LIST_KEYS,
    EXTRACT_NODE_PREFIX,
    EXTRACT_STEP_PREFIX,
    FINAL_DOC_TYPES,
    GROUPS,
    LINK_INSUFFICIENT,
    LINK_LINKED,
    LINK_UNMATCHED,
    MAX_CHECKS,
    MAX_DECISION_ITEM_LENGTH,
    MAX_DECISION_ITEMS,
    MAX_DECISION_LINES,
    MAX_DECISION_VALUE_LENGTH,
    MAX_INDEX_DIGITS,
    MAX_LINK_DOCUMENTS,
    MAX_LINK_EXTRACTS,
    MAX_LINK_TARGETS,
    MAX_MATCHED,
    MAX_NAME_LENGTH,
    MAX_SOURCE_STEPS,
    read_bundle_checks,
    read_decision,
    read_links,
)
from imask_backend.findings import build_view
from imask_backend.results import (
    STAGE_BUNDLE_CHECK,
    STAGE_CLASSIFY,
    STAGE_EXTRACT,
    STAGE_MATCH,
    STAGE_MERGE,
    STAGE_RISK,
    STAGE_VALIDATE,
    parse_stages,
    stage_key,
    summarize,
)
from imask_backend.textsafe import has_unpaired_surrogates, text_is_safe

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "final_flow"
RULES_TS = ROOT / "src" / "display" / "rules.ts"
RUNS = ("A_smoke", "B_blank_autotransfer", "C_mismatch", "D_blank_applicant", "E_team_forms")
TIME_LIMIT = 1.0  # 큰 입력 한 묶음을 읽는 데 걸려도 되는 시간(초)

CHECK_KEYS = {"id", "name", "severity", "passed", "field", "group", "status", "documents"}
PAIR_KEYS = {"id", "target_index", "group", "status"}


@functools.cache
def _raw(name: str) -> str:
    return (FIXTURES / f"{name}.json").read_bytes().decode("utf-8")


def load(name: str) -> dict[str, Any]:
    """고정 응답의 새 사본(고쳐 써도 다른 테스트에 번지지 않게)."""
    return json.loads(_raw(name))


def stages_of(name: str) -> list[dict[str, Any]]:
    return parse_stages(load(name))


def stage_by_key(stages: list[dict[str, Any]], key: str) -> dict[str, Any]:
    return next(s for s in stages if s.get("key") == key)


def extract_stage(stages: list[dict[str, Any]], page: int) -> dict[str, Any]:
    return next(s for s in stages if s.get("key") == STAGE_EXTRACT and s["additional_values"]["page_ranges"] == [[page, page]])


def output_item(response: dict[str, Any], model: str) -> dict[str, Any]:
    return next(i for i in response["output"] if i["model"] == model)


def change_additional(entry: dict[str, Any], change: Any) -> None:
    """응답 항목 content[0].additional_values(JSON 문자열)를 풀어 고친 뒤 다시 문자열로."""
    additional = json.loads(entry["content"][0]["additional_values"])
    change(additional)
    entry["content"][0]["additional_values"] = json.dumps(additional, ensure_ascii=False)


def view_of(response: dict[str, Any]) -> dict[str, Any]:
    return build_view({"response": response})


def config() -> dict[str, Any]:
    return json.loads((FIXTURES / "config.json").read_bytes().decode("utf-8"))


def classify_step(cfg: dict[str, Any]) -> dict[str, Any]:
    return next(s for s in cfg["steps"] if s.get("type") == "document-classify")


# --- 서류 종류 표 -------------------------------------------------------------------------


def test_doc_types_follow_config_classify_order():
    schema = classify_step(config())["data"]["text"]["format"]["schema"]
    codes = [option["const"] for option in schema["oneOf"]]
    assert len(codes) == 14
    assert list(FINAL_DOC_TYPES) == codes


def test_doc_type_groups_follow_config_routes():
    step = classify_step(config())
    routes = {n["condition"]["value"]: n["step_name"] for n in step["next_steps"]}
    assert set(routes) == set(FINAL_DOC_TYPES)
    for code, (_, group) in FINAL_DOC_TYPES.items():
        if group is None:
            assert code == "Other" and routes[code] == "Instruct - 기타_서류_안내"
        else:
            assert routes[code] == f"{EXTRACT_STEP_PREFIX}{EXTRACT_NODE_PREFIX}{group}", code


def test_config_extract_nodes_are_the_four_groups():
    names = {s["name"] for s in config()["steps"] if s.get("type") == "information-extract"}
    assert names == {f"{EXTRACT_STEP_PREFIX}{EXTRACT_NODE_PREFIX}{group}" for group in GROUPS}
    assert GROUPS == ("신청서", "확인서", "증빙", "위임장")


def screen_doc_type_names() -> dict[str, str]:
    """rules.ts 의 DOC_TYPE_NAMES(읽기만)."""
    text = RULES_TS.read_bytes().decode("utf-8")
    block = re.search(r"export const DOC_TYPE_NAMES: Record<string, string> = \{(.*?)\};", text, re.DOTALL)
    assert block, "rules.ts 에 DOC_TYPE_NAMES 가 없다"
    return dict(re.findall(r"(\w+): '([^']*)'", block.group(1)))


def test_doc_type_names_match_screen_exactly():
    # 분류 코드 14개 모두 화면 DOC_TYPE_NAMES 와 같은 이름(final-flow T5). 화면에만 있는 키는 서류 kind 'other'(소문자 —
    # 코드가 아니라 기타 서류의 kind)뿐이고 이름은 'Other' 와 같다
    screen = screen_doc_type_names()
    backend = {code: name for code, (name, _group) in FINAL_DOC_TYPES.items()}
    assert len(backend) == 14
    assert {code: name for code, name in screen.items() if code != "other"} == backend
    assert screen["other"] == backend["Other"]


def test_doc_type_names_are_short_and_unique():
    names = [name for name, _ in FINAL_DOC_TYPES.values()]
    assert len(set(names)) == len(names)
    assert all(isinstance(name, str) and 0 < len(name) <= 20 for name in names)
    assert {group for _, group in FINAL_DOC_TYPES.values()} == set(GROUPS) | {None}


# --- 고정 응답: 요약과 화면용 결과 ----------------------------------------------------------

SUMMARIES = {
    # (서류 수, 추출 서류 수, 위험도, 마지막 단계)
    "A_smoke": (6, 5, "상", "권장_조치"),
    "B_blank_autotransfer": (2, 2, "검토 필요", "검토_안내"),
    "C_mismatch": (3, 3, "검토 필요", "검토_안내"),
    "D_blank_applicant": (2, 2, "검토 필요", "검토_안내"),
    "E_team_forms": (4, 3, "상", "권장_조치"),
}


@pytest.mark.parametrize("name", RUNS)
def test_fixture_summary(name):
    summary = summarize(load(name))
    documents, extracted, risk, final = SUMMARIES[name]
    assert summary["document_count"] == documents
    assert summary["extracted_document_count"] == extracted
    assert summary["risk_level"] == risk
    assert summary["final_stage"] == final


@pytest.mark.parametrize("name", RUNS)
def test_fixture_stages_are_all_recognized(name):
    stages = stages_of(name)
    assert all(s["key"] is not None for s in stages), [s["name"] for s in stages if s["key"] is None]
    for stage in stages:
        if stage["step_type"] == "information-extract":
            assert stage["key"] == STAGE_EXTRACT
    assert stage_by_key(stages, STAGE_MATCH)["name"] == "Match - 서류_대조"
    assert stage_by_key(stages, STAGE_BUNDLE_CHECK)["name"] == "Validate - 묶음_검증"
    assert stage_by_key(stages, STAGE_MERGE)["name"] == "병합-1"
    assert not [s for s in stages if s["key"] == STAGE_VALIDATE]


@pytest.mark.parametrize("name", RUNS)
def test_fixture_view_keeps_contract(name):
    view = view_of(load(name))
    assert_view(view)  # 화면용 결과의 키 목록은 그대로
    documents = {d["index"]: d for d in view["documents"]}
    assert len(documents) == SUMMARIES[name][0]
    if name != "B_blank_autotransfer":  # B 는 빈 서식이라 0 일 수 있다
        assert view["findings"]
    for finding in view["findings"]:
        assert documents[finding["document_index"]]["kind"] == "extracted", finding["id"]
    # 묶음_검증의 verdict 는 어느 서류의 validation 에도 붙지 않는다
    assert all(d["validation"] is None for d in view["documents"])
    assert view["overall"]["level"] == SUMMARIES[name][2]
    assert view["overall"]["next_stage"] == SUMMARIES[name][3]


def test_fixture_view_documents_follow_classify_order():
    view = view_of(load("A_smoke"))
    assert [(d["index"], d["type"], d["kind"]) for d in view["documents"]] == [
        (0, "loan_application", "extracted"),
        (1, "consent_form", "extracted"),
        (2, "income_proof", "extracted"),
        (3, "power_of_attorney", "extracted"),
        (4, "debt_transaction", "extracted"),
        (5, "Other", "other"),
    ]
    assert isinstance(view["documents"][5]["other_guide"], str)
    # 추출 노드 넷(추출_증빙 은 두 번)이 모두 서류에 붙는다
    assert {f["document_index"] for f in view["findings"]} == {0, 1, 2, 3, 4}


@pytest.mark.parametrize("name", RUNS)
def test_bundle_check_is_not_document_validation_even_as_unknown_validate(name):
    # 이름을 모르는 validate 는 서류별 검증(필수항목_검증)으로 보지만, 묶음 전체 쪽 범위라 어느 서류와도 짝이 없다
    response = load(name)
    output_item(response, "Validate - 묶음_검증")["model"] = "Validate - 다른_검증"
    assert stage_key("Validate - 다른_검증", "validate") == STAGE_VALIDATE
    view = view_of(response)
    assert_view(view)
    assert all(d["validation"] is None for d in view["documents"])


def test_single_range_bundle_check_still_not_attached():
    # 묶음 범위가 한 서류 범위와 같아도 이름이 묶음_검증 이면 서류별 validation 이 아니다
    response = load("C_mismatch")
    change_additional(output_item(response, "Validate - 묶음_검증"), lambda a: a.update(page_ranges=[[1, 1]]))
    assert all(d["validation"] is None for d in view_of(response)["documents"])
    # 대조: 같은 모양이라도 이름을 모르는 validate 는 예전처럼 서류별 검증으로 붙는다
    output_item(response, "Validate - 묶음_검증")["model"] = "Validate - 다른_검증"
    assert view_of(response)["documents"][0]["validation"] == "yellow"


# --- read_bundle_checks -----------------------------------------------------------------

BUNDLE_EXPECTED = {
    "A_smoke": (
        "green",
        {
            "신청서_신청인_성명": (CHECK_PASS, [(0, True)]),
            "확인서_신청인_성명": (CHECK_PASS, [(1, True)]),
            "증빙_신청인_성명": (CHECK_PASS, [(2, True), (4, True)]),
            "위임장_위임인_성명": (CHECK_PASS, [(3, True)]),
            "위임장_대리인_성명": (CHECK_PASS, [(3, True)]),
        },
    ),
    "B_blank_autotransfer": (
        "red",
        {
            "신청서_신청인_성명": (CHECK_FAIL, [(0, False)]),
            "확인서_신청인_성명": (CHECK_ABSENT, None),
            "증빙_신청인_성명": (CHECK_ABSENT, None),
            "위임장_위임인_성명": (CHECK_FAIL, [(1, False)]),
            "위임장_대리인_성명": (CHECK_FAIL, [(1, False)]),
        },
    ),
    "C_mismatch": (
        "yellow",
        {
            "신청서_신청인_성명": (CHECK_PASS, [(0, True)]),
            "확인서_신청인_성명": (CHECK_PASS, [(1, True)]),
            "증빙_신청인_성명": (CHECK_PASS, [(2, True)]),
            "위임장_위임인_성명": (CHECK_ABSENT, None),
            "위임장_대리인_성명": (CHECK_ABSENT, None),
        },
    ),
    "D_blank_applicant": (
        "red",
        {
            "신청서_신청인_성명": (CHECK_FAIL, [(0, False)]),
            "확인서_신청인_성명": (CHECK_PASS, [(1, True)]),
            "증빙_신청인_성명": (CHECK_ABSENT, None),
            "위임장_위임인_성명": (CHECK_ABSENT, None),
            "위임장_대리인_성명": (CHECK_ABSENT, None),
        },
    ),
    "E_team_forms": (
        "yellow",
        {
            "신청서_신청인_성명": (CHECK_PASS, [(0, True)]),
            "확인서_신청인_성명": (CHECK_PASS, [(1, True)]),
            "증빙_신청인_성명": (CHECK_ABSENT, None),
            "위임장_위임인_성명": (CHECK_PASS, [(2, True)]),
            "위임장_대리인_성명": (CHECK_PASS, [(2, True)]),
        },
    ),
}


def _documents_pairs(documents: Any) -> Any:
    return None if documents is None else [(d["index"], d["ok"]) for d in documents]


@pytest.mark.parametrize("name", RUNS)
def test_bundle_checks_of_fixtures(name):
    result = read_bundle_checks(stages_of(name))
    verdict, expected = BUNDLE_EXPECTED[name]
    assert set(result) == {"verdict", "checks"}
    assert result["verdict"] == verdict
    got = {c["name"]: (c["status"], _documents_pairs(c["documents"])) for c in result["checks"]}
    assert got == expected
    for check in result["checks"]:
        assert set(check) == CHECK_KEYS
        assert check["id"] == check["name"]
        assert check["severity"] == ("error" if check["name"].startswith("신청서") else "warning")
        assert check["passed"] is (check["status"] == CHECK_PASS)
        assert check["group"] == check["name"].split("_")[0]
    fields = {c["name"]: c["field"] for c in result["checks"]}
    assert fields["위임장_대리인_성명"] == "other_person_name"
    assert fields["신청서_신청인_성명"] == "applicant_name"


@pytest.mark.parametrize("name", RUNS)
def test_reader_indexes_match_view_documents(name):
    # 서류 번호는 findings 의 서류 번호와 같다 — 규칙·쌍의 묶음과 그 서류 종류의 묶음이 맞는다
    stages = stages_of(name)
    types = {d["index"]: d["type"] for d in view_of(load(name))["documents"]}
    for check in read_bundle_checks(stages)["checks"]:
        for document in check["documents"] or []:
            assert FINAL_DOC_TYPES[types[document["index"]]][1] == check["group"]
    links = read_links(stages)
    assert FINAL_DOC_TYPES[types[links["anchor_index"]]][1] == "신청서"
    for pair in links["pairs"]:
        assert FINAL_DOC_TYPES[types[pair["target_index"]]][1] == pair["group"]


# --- read_links ---------------------------------------------------------------------------

LINKS_EXPECTED = {
    "A_smoke": {1: ("확인서", LINK_LINKED), 2: ("증빙", LINK_LINKED), 4: ("증빙", LINK_LINKED), 3: ("위임장", LINK_LINKED)},
    "B_blank_autotransfer": {1: ("위임장", LINK_INSUFFICIENT)},
    "C_mismatch": {1: ("확인서", LINK_UNMATCHED), 2: ("증빙", LINK_LINKED)},
    "D_blank_applicant": {1: ("확인서", LINK_INSUFFICIENT)},  # 기준(신청서) 신청인 성명이 비어 있다
    "E_team_forms": {1: ("확인서", LINK_LINKED), 2: ("위임장", LINK_LINKED)},
}


@pytest.mark.parametrize("name", RUNS)
def test_links_of_fixtures(name):
    result = read_links(stages_of(name))
    assert set(result) == {"field", "anchor_index", "pairs"}
    assert result["anchor_index"] == 0
    assert result["field"] == "applicant_name"
    pairs = result["pairs"]
    assert {p["target_index"]: (p["group"], p["status"]) for p in pairs} == LINKS_EXPECTED[name]
    # 쌍 순서는 대상(targets) 순서 → 그 노드로 간 서류 순서
    assert [p["target_index"] for p in pairs] == list(LINKS_EXPECTED[name])
    for pair in pairs:
        assert set(pair) == PAIR_KEYS
        assert pair["id"] == f"link:0:{pair['target_index']}"


# --- read_decision ------------------------------------------------------------------------

DECISION_EXPECTED = {
    "A_smoke": ("상", ["loan_application", "consent_form", "income_proof", "power_of_attorney", "debt_transaction"], []),
    "B_blank_autotransfer": ("검토 필요", ["auto_transfer_application", "power_of_attorney"], ["필수 항목 누락"]),
    "C_mismatch": ("검토 필요", ["loan_application", "consent_form", "income_proof"], ["서류 간 불일치"]),
    "D_blank_applicant": ("검토 필요", ["loan_application", "consent_form"], ["필수 항목 누락"]),
    "E_team_forms": ("상", ["debit_card_application", "fatca_crs_certification", "power_of_attorney"], []),
}


@pytest.mark.parametrize("name", RUNS)
def test_decision_of_fixtures(name):
    result = read_decision(stages_of(name))
    level, document_types, review_reasons = DECISION_EXPECTED[name]
    assert set(result) == set(DECISION_KEYS)
    assert result["risk_level"] == level
    assert result["risk_level"] == summarize(load(name))["risk_level"]  # 본문 값과 enum 이 같은 응답들
    assert result["document_types"] == document_types
    assert result["review_reasons"] == review_reasons
    assert isinstance(result["sensitive_categories"], list)
    assert all(isinstance(c, str) and c for c in result["sensitive_categories"])
    assert isinstance(result["reason"], str) and len(result["reason"]) > 20
    for value in (result["reason"], *result["sensitive_categories"], *result["review_reasons"]):
        assert "【" not in value and "†" not in value and "】" not in value
    assert result["reason"] == result["reason"].strip()


def test_decision_sensitive_categories_of_fixtures():
    assert len(read_decision(stages_of("A_smoke"))["sensitive_categories"]) == 5
    assert read_decision(stages_of("B_blank_autotransfer"))["sensitive_categories"] == []
    assert len(read_decision(stages_of("C_mismatch"))["sensitive_categories"]) == 4
    assert len(read_decision(stages_of("D_blank_applicant"))["sensitive_categories"]) == 3
    assert len(read_decision(stages_of("E_team_forms"))["sensitive_categories"]) == 4


# --- 값이 결과에 없다 · 응답을 그대로 줘도 된다 -------------------------------------------------


def _strings(value: Any, out: set[str]) -> None:
    if isinstance(value, str):
        if value.strip():
            out.add(value.strip())
    elif isinstance(value, dict):
        for child in value.values():
            _strings(child, out)
    elif isinstance(value, list):
        for child in value:
            _strings(child, out)


def raw_values(stages: list[dict[str, Any]]) -> set[str]:
    """추출 값·서류_대조의 기준 값·대상 값(원문)."""
    values: set[str] = set()
    for stage in stages:
        if stage["key"] == STAGE_EXTRACT:
            _strings(stage["data"], values)
        if stage["key"] == STAGE_MATCH:
            _strings(stage["data"], values)
            additional = stage["additional_values"]
            for meta in additional["anchor"].values():
                _strings(meta.get("_value"), values)
            for target in additional["targets"]:
                _strings(target["document_match"].get("anchor_value"), values)
                for matched in target["document_match"]["matched"]:
                    _strings(matched.get("target_values"), values)
    return values


@pytest.mark.parametrize("name", RUNS)
def test_reader_results_hold_no_raw_values(name):
    stages = stages_of(name)
    results = [read_decision(stages), read_bundle_checks(stages), read_links(stages)]
    dumped = json.dumps(results, ensure_ascii=False, allow_nan=False)
    hits = [len(v) for v in raw_values(stages) if v in dumped]
    assert hits == [], "원문 값이 결과에 들어 있다(길이만 표시)"
    # 검증 reason·conditions 의 내부 값도 없다
    bundle = stage_by_key(stages, STAGE_BUNDLE_CHECK)["additional_values"]
    for check in bundle["checks"]:
        assert check["reason"] not in dumped
    assert "gte" not in dumped and "nodeType" not in dumped


@pytest.mark.parametrize("name", RUNS)
def test_readers_accept_the_response_itself(name):
    stages = stages_of(name)
    response = load(name)
    assert read_decision(response) == read_decision(stages)
    assert read_bundle_checks(response) == read_bundle_checks(stages)
    assert read_links(response) == read_links(stages)


# --- 옛 응답(예시 #3)은 None ------------------------------------------------------------------


@pytest.mark.parametrize(
    "response",
    [
        build_response(),
        build_response(types=("loan_application",), risk="검토 필요", final="검토_안내"),
        build_findings_response(),
    ],
    ids=["action", "review", "findings-fake"],
)
def test_old_workflow_gives_none(response):
    stages = parse_stages(response)
    assert read_decision(stages) is None  # Markdown 본문 — 키 줄 없음
    assert read_bundle_checks(stages) is None  # 서류별 필수항목_검증 만 있다
    assert read_links(stages) is None


@pytest.mark.parametrize(
    "text",
    [
        "## 위험도 판정\n상【†1】\n\n## 근거\n- 가짜 근거【†2】",
        "## 종합 위험도: 상\n- **판정 근거**: 가짜\n- 다음 단계: 권장 조치",
        "위험도: 검토 필요\n이유: 가짜",
        "level: 상\nnote: 가짜",  # 모르는 키만
        "",
    ],
)
def test_old_markdown_decision_gives_none(text):
    assert decision(text) is None


@pytest.mark.parametrize("stages", [[], None, "x", 5, [None, "x", 3], {"output": []}, {}])
def test_no_stages_gives_none(stages):
    assert read_decision(stages) is None
    assert read_bundle_checks(stages) is None
    assert read_links(stages) is None


# --- 경계: 묶음_검증 ----------------------------------------------------------------------

_MISSING = object()


def check(
    name: Any = "규칙",
    *,
    severity: Any = "warning",
    passed: Any = False,
    node: Any = "추출_신청서",
    field: Any = "applicant_name",
    value: Any = _MISSING,
) -> dict[str, Any]:
    left: dict[str, Any] = {"nodeType": "extract", "nodeName": node, "field": field, "attr": "length"}
    if value is not _MISSING:
        left["value"] = value
    return {
        "name": name,
        "severity": severity,
        "passed": passed,
        "reason": "내부 값 길이 3",
        "conditions": {"kind": "condition", "passed": passed, "left": left, "operator": "gte", "right": {"const": 1}},
    }


def bundle_with(checks: Any, name: str = "A_smoke", **additional: Any) -> dict[str, Any] | None:
    stages = stages_of(name)
    stage = stage_by_key(stages, STAGE_BUNDLE_CHECK)
    stage["additional_values"]["checks"] = checks
    stage["additional_values"].update(additional)
    return read_bundle_checks(stages)


def one_check(item: dict[str, Any], name: str = "A_smoke") -> dict[str, Any]:
    (result,) = bundle_with([item], name)["checks"]
    return result


@pytest.mark.parametrize(
    ("additional_verdict", "data", "expected"),
    [
        ("green", "red", "green"),
        (" GREEN ", None, "green"),
        ("blue", "green", None),  # 값이 있으면 그 값만 본다
        (_MISSING, "red", "red"),
        ("", "yellow", "yellow"),
        (5, "yellow", "yellow"),
        (_MISSING, None, None),
        (_MISSING, ["green"], None),
        ("g" * 1000, None, None),
    ],
)
def test_bundle_verdict(additional_verdict, data, expected):
    stages = stages_of("A_smoke")
    stage = stage_by_key(stages, STAGE_BUNDLE_CHECK)
    stage["data"] = data
    if additional_verdict is _MISSING:
        del stage["additional_values"]["verdict"]
    else:
        stage["additional_values"]["verdict"] = additional_verdict
    assert read_bundle_checks(stages)["verdict"] == expected


@pytest.mark.parametrize("additional", [None, "not json", "{깨진", [1, 2], 5, 1.5, True])
def test_bundle_additional_values_not_object(additional):
    stages = stages_of("A_smoke")
    stage = stage_by_key(stages, STAGE_BUNDLE_CHECK)
    stage["additional_values"] = additional
    assert read_bundle_checks(stages) == {"verdict": "green", "checks": None}  # verdict 는 본문에서


def test_bundle_stage_without_content():
    response = load("A_smoke")
    output_item(response, "Validate - 묶음_검증")["content"] = []
    assert read_bundle_checks(parse_stages(response)) == {"verdict": None, "checks": None}
    del output_item(response, "Validate - 묶음_검증")["content"]
    assert read_bundle_checks(parse_stages(response)) == {"verdict": None, "checks": None}


@pytest.mark.parametrize("checks", [None, "x", {"name": "a"}, 5, True])
def test_bundle_checks_not_a_list(checks):
    assert bundle_with(checks)["checks"] is None


def test_bundle_checks_empty_list_is_confirmed_empty():
    assert bundle_with([])["checks"] == []


def test_bundle_check_items_that_are_not_objects_are_skipped():
    result = bundle_with([1, "x", None, [], True, check("남는 규칙", passed=True, value=[3])])
    assert [c["name"] for c in result["checks"]] == ["남는 규칙"]


@pytest.mark.parametrize("passed", ["true", "false", 1, 0, None, [True]])
def test_bundle_passed_must_be_bool(passed):
    result = one_check(check(passed=passed, value=[0]))
    assert result["passed"] is None
    assert result["status"] == CHECK_UNKNOWN


@pytest.mark.parametrize(
    ("value", "documents"),
    [
        ([3, 0], [(2, True), (4, False)]),
        ([0, 0], [(2, False), (4, False)]),
        ([10**30, 1], [(2, True), (4, True)]),
        ([3], None),  # 서류 수(2)와 다름
        ([3, 3, 3], None),
        ([-1, 3], None),
        ([3.0, 3], None),
        ([True, 3], None),
        ([float("nan"), 3], None),
        ([float("inf"), 3], None),
        (["3", 3], None),
        ([None, 3], None),
        ([[3], 3], None),
        (list(range(100_000)), None),
    ],
    ids=lambda v: str(v)[:20],
)
def test_bundle_documents_values(value, documents):
    result = one_check(check(node="추출_증빙", value=value))
    assert _documents_pairs(result["documents"]) == documents
    assert result["status"] == CHECK_FAIL  # passed False + 값이 목록


@pytest.mark.parametrize("value", ["3", 3, {"a": 1}, True, 1.5])
def test_bundle_value_not_list_or_null_is_unknown(value):
    result = one_check(check(value=value))
    assert result["status"] == CHECK_UNKNOWN
    assert result["documents"] is None


def test_bundle_absent_rules():
    # B: 확인서로 간 서류가 없고 value 가 null → absent(필수 항목 없음이 아님)
    assert one_check(check(node="추출_확인서", value=None), "B_blank_autotransfer")["status"] == CHECK_ABSENT
    # passed True 면 value 와 상관없이 pass
    assert one_check(check(node="추출_확인서", passed=True, value=None), "B_blank_autotransfer")["status"] == CHECK_PASS
    # A: 신청서로 간 서류가 있는데 null → 모순이라 unknown
    assert one_check(check(node="추출_신청서", value=None))["status"] == CHECK_UNKNOWN
    # value 키가 없거나 left 가 객체가 아니면 unknown
    assert one_check(check(node="추출_확인서"), "B_blank_autotransfer")["status"] == CHECK_UNKNOWN
    broken = check(value=None)
    broken["conditions"]["left"] = "not an object"
    result = one_check(broken, "B_blank_autotransfer")
    assert result["status"] == CHECK_UNKNOWN and result["field"] is None and result["group"] is None
    no_conditions = check(value=None)
    del no_conditions["conditions"]
    assert one_check(no_conditions)["status"] == CHECK_UNKNOWN


def test_bundle_without_merge_stage_has_no_documents():
    stages = [s for s in stages_of("A_smoke") if s["key"] != STAGE_MERGE]
    result = read_bundle_checks(stages)
    assert result["verdict"] == "green"
    assert all(c["documents"] is None for c in result["checks"])
    assert all(c["status"] == CHECK_PASS for c in result["checks"])
    # 경로를 모르면 null 은 스펙대로 absent
    stages = [s for s in stages_of("C_mismatch") if s["key"] != STAGE_MERGE]
    statuses = {c["name"]: c["status"] for c in read_bundle_checks(stages)["checks"]}
    assert statuses["위임장_위임인_성명"] == CHECK_ABSENT


@pytest.mark.parametrize(
    ("name", "kept"),
    [
        ("규칙", True),
        ("가" * MAX_NAME_LENGTH, True),
        ("가" * (MAX_NAME_LENGTH + 1), False),
        ("", False),
        ("   ", False),
        (None, False),
        (5, False),
        (["규칙"], False),
        ("규칙\ud800", False),
    ],
    ids=["plain", "max", "too-long", "empty", "blank", "none", "number", "list", "surrogate"],
)
def test_bundle_rule_name(name, kept):
    result = bundle_with([check(name, value=[3])])["checks"]
    assert len(result) == (1 if kept else 0)


def test_bundle_duplicate_names_get_numbered_ids():
    names = ["a", "a", "a#2", "b", "a"]
    result = bundle_with([check(n, value=[3]) for n in names])["checks"]
    ids = [c["id"] for c in result]
    assert ids == ["a", "a#2", "a#2#2", "b", "a#3"]
    assert len(set(ids)) == len(ids)
    assert [c["name"] for c in result] == names


@pytest.mark.parametrize(
    ("severity", "expected"),
    [("error", "error"), (" Warning ", "warning"), ("info", None), (5, None), (None, None), ("e" * 100, None)],
)
def test_bundle_severity(severity, expected):
    assert one_check(check(severity=severity, value=[3]))["severity"] == expected


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("applicant_name", "applicant_name"),
        ("f" * MAX_NAME_LENGTH, "f" * MAX_NAME_LENGTH),
        ("f" * (MAX_NAME_LENGTH + 1), None),
        ("필드\udfff", None),
        (5, None),
        ("", None),
    ],
    ids=["plain", "max", "too-long", "surrogate", "number", "empty"],
)
def test_bundle_field(field, expected):
    assert one_check(check(field=field, value=[3]))["field"] == expected


@pytest.mark.parametrize(
    ("node", "group"),
    [
        ("추출_신청서", "신청서"),
        ("추출_위임장", "위임장"),
        ("추출_기타", None),
        ("신청서", None),
        ("추출_", None),
        (5, None),
        ("추출_" + "x" * 10_000, None),
    ],
)
def test_bundle_group(node, group):
    result = one_check(check(node=node, value=None))
    assert result["group"] == group
    if group is None:
        assert result["documents"] is None


def test_bundle_unknown_node_with_value_null_is_absent():
    # 그 노드로 간 서류가 없다(경로는 앎) → null 은 absent
    assert one_check(check(node="추출_기타", value=None))["status"] == CHECK_ABSENT


def test_bundle_checks_limit():
    assert len(bundle_with([check(f"r{i}", value=[3]) for i in range(MAX_CHECKS)])["checks"]) == MAX_CHECKS
    assert bundle_with([check(f"r{i}", value=[3]) for i in range(MAX_CHECKS + 1)])["checks"] is None


def test_bundle_failed_stage_is_skipped_for_next_completed():
    stages = stages_of("A_smoke")
    bundle = stage_by_key(stages, STAGE_BUNDLE_CHECK)
    failed = copy.deepcopy(bundle)
    failed["status"] = "failed"
    failed["additional_values"]["verdict"] = "red"
    stages.insert(stages.index(bundle), failed)
    assert read_bundle_checks(stages)["verdict"] == "green"
    assert read_bundle_checks([failed]) is None
    # completed 가 둘이면 첫 것
    second = copy.deepcopy(bundle)
    second["additional_values"]["verdict"] = "yellow"
    stages.append(second)
    assert read_bundle_checks(stages)["verdict"] == "green"


# --- 경계: 병합-1 경로(branch_key·source_steps) ---------------------------------------------


def _merge(stages: list[dict[str, Any]]) -> dict[str, Any]:
    return stage_by_key(stages, STAGE_MERGE)


def proof_documents(stages: list[dict[str, Any]]) -> Any:
    checks = read_bundle_checks(stages)["checks"]
    return next(_documents_pairs(c["documents"]) for c in checks if c["name"] == "증빙_신청인_성명")


@pytest.mark.parametrize("source_steps", [None, "x", {"a": 1}, 5])
def test_source_steps_not_a_list(source_steps):
    stages = stages_of("A_smoke")
    _merge(stages)["data"]["source_steps"] = source_steps
    assert proof_documents(stages) is None


@pytest.mark.parametrize("data", [None, "병합", [1, 2], 5])
def test_merge_data_not_object(data):
    stages = stages_of("A_smoke")
    _merge(stages)["data"] = data
    assert proof_documents(stages) is None


def test_odd_source_steps_are_skipped():
    stages = stages_of("A_smoke")
    steps = _merge(stages)["data"]["source_steps"]
    proof = EXTRACT_STEP_PREFIX + "추출_증빙"
    junk = [
        None,
        "2:income_proof",
        {"branch_key": "x:income_proof", "step_name": proof},
        {"branch_key": "-1:income_proof", "step_name": proof},
        {"branch_key": "٣:income_proof", "step_name": proof},  # ASCII 가 아닌 숫자
        {"branch_key": "1" * (MAX_INDEX_DIGITS + 1) + ":x", "step_name": proof},
        {"branch_key": "9" * 5000 + ":x", "step_name": proof},  # 아주 긴 숫자 — int 로 바꾸지 않는다
        {"branch_key": "99:income_proof", "step_name": proof},  # 분류 서류가 아님
        {"branch_key": "5:Other", "step_name": proof},  # 분류 서류지만 아래 길이 [3, 3] 과 수가 맞지 않게 될 서류
        {"branch_key": "2", "step_name": proof},
        {"branch_key": 2, "step_name": proof},
        {"branch_key": "2:income_proof", "step_name": 5},
        {"branch_key": "0:loan_application", "step_name": proof},  # 이미 신청서로 간 서류 — 버린다
    ]
    steps[:0] = junk[:-1]  # 앞에 끼워도 정상 항목은 그대로
    steps.append(junk[-1])
    # "5:Other" 는 분류 서류(5)라 증빙 경로에 들어간다 → 서류 수 3 ≠ 길이 2 → documents 없음
    assert proof_documents(stages) is None
    steps.remove(junk[8])
    assert proof_documents(stages) == [(2, True), (4, True)]
    statuses = {c["name"]: _documents_pairs(c["documents"]) for c in read_bundle_checks(stages)["checks"]}
    assert statuses["신청서_신청인_성명"] == [(0, True)]


def test_source_steps_limit():
    stages = stages_of("A_smoke")
    steps = _merge(stages)["data"]["source_steps"]
    steps.extend({"branch_key": "99:x", "step_name": "x"} for _ in range(MAX_SOURCE_STEPS - len(steps)))
    assert proof_documents(stages) == [(2, True), (4, True)]
    steps.append({"branch_key": "99:x", "step_name": "x"})
    assert proof_documents(stages) is None


# --- 경계: 서류_대조 ----------------------------------------------------------------------


def links_with(name: str = "A_smoke", change: Any = None) -> dict[str, Any] | None:
    stages = stages_of(name)
    if change is not None:
        change(stages, stage_by_key(stages, STAGE_MATCH)["additional_values"])
    return read_links(stages)


def statuses(result: dict[str, Any]) -> dict[int, str]:
    return {p["target_index"]: p["status"] for p in result["pairs"]}


def _targets(additional: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {t["result_key"]: t for t in additional["targets"]}


@pytest.mark.parametrize("additional", [None, "not json", [1], 5, True])
def test_links_additional_values_not_object(additional):
    stages = stages_of("A_smoke")
    stage_by_key(stages, STAGE_MATCH)["additional_values"] = additional
    assert read_links(stages) == {"field": None, "anchor_index": None, "pairs": None}


def test_links_stage_without_content():
    response = load("C_mismatch")
    output_item(response, "Match - 서류_대조")["content"] = [None]
    assert read_links(parse_stages(response)) == {"field": None, "anchor_index": None, "pairs": None}


@pytest.mark.parametrize("targets", [None, "x", {"a": 1}, 5])
def test_links_targets_not_a_list(targets):
    result = links_with(change=lambda s, a: a.update(targets=targets))
    assert result == {"field": None, "anchor_index": 0, "pairs": None}


def test_links_target_items_not_objects_are_skipped():
    def change(stages, additional):
        additional["targets"][:0] = [None, 1, "x", []]
        additional["targets"].append({"step_name": 5, "document_match": {}})

    result = links_with(change=change)
    assert result["field"] == "applicant_name"
    assert statuses(result) == {1: LINK_LINKED, 2: LINK_LINKED, 4: LINK_LINKED, 3: LINK_LINKED}


@pytest.mark.parametrize("matched", [None, "x", {"page_ranges": [[2, 2]]}, 5])
def test_links_matched_not_a_list_is_insufficient(matched):
    def change(stages, additional):
        _targets(additional)["추출_확인서"]["document_match"]["matched"] = matched

    assert statuses(links_with(change=change))[1] == LINK_INSUFFICIENT


@pytest.mark.parametrize(
    "page_ranges",
    [[[2, 1]], [[-2, -2]], [["2", "2"]], [[True, True]], [[2]], "2", None, [[2.0, 2.0]], [[2, 2], [9, 9]]],
    ids=["reversed", "negative", "strings", "bools", "short", "string", "none", "floats", "extra-range"],
)
def test_links_odd_matched_ranges_never_link(page_ranges):
    def change(stages, additional):
        _targets(additional)["추출_확인서"]["document_match"]["matched"] = [{"page_ranges": page_ranges}, "x", None]

    assert statuses(links_with(change=change))[1] == LINK_UNMATCHED


def test_links_same_document_twice_in_matched():
    def change(stages, additional):
        match = _targets(additional)["추출_확인서"]["document_match"]
        match["matched"] = match["matched"] * 2

    result = links_with(change=change)
    assert [p["target_index"] for p in result["pairs"]].count(1) == 1
    assert statuses(result)[1] == LINK_LINKED


@pytest.mark.parametrize("page_ranges", [None, [], [[1, 0]], "1", [[-1, 1]], [[9, 9]]])
def test_links_anchor_not_found(page_ranges):
    result = links_with(change=lambda s, a: a.update(page_ranges=page_ranges))
    assert result["anchor_index"] is None
    assert set(statuses(result).values()) == {LINK_INSUFFICIENT}
    assert {p["id"] for p in result["pairs"]} == {"link:-:1", "link:-:2", "link:-:3", "link:-:4"}


@pytest.mark.parametrize("anchor_value", ["", "   ", None, [], {}, True, _MISSING])
def test_links_blank_anchor_value_is_insufficient(anchor_value):
    def change(stages, additional):
        match = _targets(additional)["추출_증빙"]["document_match"]
        if anchor_value is _MISSING:
            del match["anchor_value"]
        else:
            match["anchor_value"] = anchor_value

    result = statuses(links_with(change=change))
    assert result[2] == result[4] == LINK_INSUFFICIENT
    assert result[1] == result[3] == LINK_LINKED  # 다른 대상은 그대로


def test_links_numeric_anchor_value_is_not_blank():
    def change(stages, additional):
        _targets(additional)["추출_증빙"]["document_match"]["anchor_value"] = 0

    assert statuses(links_with(change=change))[2] == LINK_LINKED


@pytest.mark.parametrize("value", ["", "  ", None, False, []])
def test_links_blank_target_value_is_insufficient(value):
    def change(stages, additional):
        extract_stage(stages, 2)["data"]["applicant_name"] = value  # 확인서(서류 1, 2쪽)

    result = statuses(links_with(change=change))
    assert result[1] == LINK_INSUFFICIENT
    assert result[2] == LINK_LINKED


def test_links_target_without_extract_is_insufficient():
    def change(stages, additional):
        stages.remove(extract_stage(stages, 2))

    assert statuses(links_with(change=change))[1] == LINK_INSUFFICIENT


def test_links_target_key_falls_back_to_anchor_key():
    def change(stages, additional):
        match = _targets(additional)["추출_확인서"]["document_match"]
        del match["target_key"]

    assert statuses(links_with(change=change))[1] == LINK_LINKED

    def both_missing(stages, additional):
        for target in additional["targets"]:
            target["document_match"].pop("target_key")
            target["document_match"].pop("anchor_key")

    result = links_with(change=both_missing)
    assert result["field"] is None
    assert set(statuses(result).values()) == {LINK_INSUFFICIENT}


def test_links_target_key_points_to_another_field():
    def change(stages, additional):
        _targets(additional)["추출_확인서"]["document_match"]["target_key"] = "card_number"  # 확인서에서 빈 칸

    assert statuses(links_with(change=change))[1] == LINK_INSUFFICIENT


@pytest.mark.parametrize(
    "anchor_key", [5, "", "k" * (MAX_NAME_LENGTH + 1), "이름\ud800"], ids=["number", "empty", "too-long", "surrogate"]
)
def test_links_odd_field(anchor_key):
    def change(stages, additional):
        additional["targets"][0]["document_match"]["anchor_key"] = anchor_key

    assert links_with(change=change)["field"] is None


def test_links_same_target_twice_and_anchor_as_target():
    def change(stages, additional):
        additional["targets"].append(copy.deepcopy(additional["targets"][0]))
        additional["targets"].append({"result_key": "추출_신청서", "step_name": EXTRACT_STEP_PREFIX + "추출_신청서"})

    result = links_with(change=change)
    assert [p["target_index"] for p in result["pairs"]] == [1, 2, 4, 3]  # 첫 쌍만, 기준 서류 자신은 없음


def test_links_unknown_target_group():
    def change(stages, additional):
        _merge(stages)["data"]["source_steps"][1]["step_name"] = "Information Extract - 다른_노드"
        additional["targets"][0]["step_name"] = "Information Extract - 다른_노드"

    result = links_with(change=change)
    pair = next(p for p in result["pairs"] if p["target_index"] == 1)
    assert pair["group"] is None and pair["status"] == LINK_LINKED


def test_links_without_merge_stage():
    stages = [s for s in stages_of("A_smoke") if s["key"] != STAGE_MERGE]
    assert read_links(stages) == {"field": "applicant_name", "anchor_index": 0, "pairs": None}


def test_links_limits():
    def fill_targets(count):
        def change(stages, additional):
            additional["targets"].extend([None] * (count - len(additional["targets"])))

        return change

    assert links_with(change=fill_targets(MAX_LINK_TARGETS))["pairs"] is not None
    assert links_with(change=fill_targets(MAX_LINK_TARGETS + 1))["pairs"] is None

    def fill_matched(count):
        def change(stages, additional):
            match = _targets(additional)["추출_확인서"]["document_match"]
            match["matched"].extend([None] * (count - len(match["matched"])))

        return change

    assert statuses(links_with(change=fill_matched(MAX_MATCHED)))[1] == LINK_LINKED
    assert statuses(links_with(change=fill_matched(MAX_MATCHED + 1)))[1] == LINK_INSUFFICIENT


def test_links_failed_stage_only():
    stages = stages_of("A_smoke")
    stage_by_key(stages, STAGE_MATCH)["status"] = "failed"
    assert read_links(stages) is None


def test_links_pairs_hold_no_values():
    result = links_with()
    for pair in result["pairs"]:
        assert set(pair) == PAIR_KEYS
    stages = stages_of("A_smoke")
    for target in stage_by_key(stages, STAGE_MATCH)["additional_values"]["targets"]:
        assert target["document_match"]["anchor_value"] not in json.dumps(result, ensure_ascii=False)


# --- 경계: 위험도_판정 본문 -------------------------------------------------------------------


def risk_stage(text: Any, status: str = "completed") -> dict[str, Any]:
    return {
        "name": "Instruct - 위험도_판정",
        "key": STAGE_RISK,
        "status": status,
        "step_type": "instruct",
        "data": text,
        "additional_values": {"enum": "상"},
    }


def decision(text: Any) -> dict[str, Any] | None:
    return read_decision([risk_stage(text)])


def decision_value(line: str, key: str) -> Any:
    result = decision(line)
    assert result is not None
    return result[key]


@pytest.mark.parametrize("text", [None, 5, {"risk_level": "상"}, ["risk_level: 상"], True])
def test_decision_text_not_string(text):
    assert decision(text) is None


def test_decision_unread_keys_are_none():
    assert decision("risk_level: 상") == {
        "risk_level": "상",
        "document_types": None,
        "sensitive_categories": None,
        "review_reasons": None,
        "reason": None,
    }


def test_decision_key_line_with_dropped_value_still_counts():
    assert decision("risk_level: 매우 높음") == dict.fromkeys(DECISION_KEYS)


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("risk_level: 상", "상"),
        ("risk_level: 검토 필요", "검토 필요"),
        ("risk_level:하", "하"),
        ("  risk_level  :  중  ", "중"),
        ("- risk_level: 중", "중"),
        ("* risk_level: 중", "중"),
        ("- **risk_level**: 하", "하"),
        ("**risk_level:** 상", "상"),
        ("risk_level: **상**", "상"),
        ("RISK_LEVEL: 상", "상"),
        ("risk_level: 상【†1】", "상"),
        ("risk_level: 검토 필요【†1】【†2】【†3】", "검토 필요"),
        ("risk_level: 상【†1】 【†2】", "상"),
        ("risk_level: 상입니다", None),
        ("risk_level: high", None),
        ("risk_level: 상.", None),
        ("risk_level:", None),
        ("risk_level: 상【†x】", None),  # 숫자가 아닌 표시는 지우지 않는다
    ],
)
def test_decision_risk_level(line, expected):
    assert decision_value(line, "risk_level") == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("이유입니다.", "이유입니다."),
        ("  이유  ", "이유"),
        ("가 【†1】나", "가 나"),
        ("가【†1】 나", "가 나"),
        ("가 【†1】 나", "가 나"),
        ("가【†1】나", "가나"),
        ("가【†1】, 나", "가, 나"),
        ("가 【†1】.", "가."),
        ("가입니다【†17】【†18】.", "가입니다."),
        ("【†1】가", "가"),
        ("가.【†5】 나.【†6】", "가. 나."),
        ("A: B 형식도 값", "A: B 형식도 값"),
        ("", None),
        ("【†1】", None),
        ("   ", None),
    ],
)
def test_decision_reason_citations(raw, expected):
    assert decision_value(f"reason: {raw}", "reason") == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("[a, b]", ["a", "b"]),
        ("[]", []),
        ("[ ]", []),
        ("[ , , ]", []),
        ("a, b", ["a", "b"]),
        ("a", ["a"]),
        ("[a,, b ,]", ["a", "b"]),
        ('["a", "b"]', ["a", "b"]),
        ('["a, b", "c"]', ["a, b", "c"]),
        ("['a', 'b']", ["a", "b"]),
        ("[“가”, ‘나’, `다`]", ["가", "나", "다"]),
        ('[""]', []),
        ("[1, 2]", ["1", "2"]),
        ("[필수 항목 누락]【†4】", ["필수 항목 누락"]),
        ("[a, b] 【†1】 【†2】", ["a", "b"]),
        ("[a, b", None),
        ("[a] 설명", None),
        ("", None),
        ("【†1】", None),
    ],
)
def test_decision_lists(raw, expected):
    for key in ("document_types", "sensitive_categories", "review_reasons"):
        assert decision_value(f"{key}: {raw}", key) == expected


def test_decision_deep_json_list_does_not_raise():
    depth = MAX_DECISION_VALUE_LENGTH // 2
    raw = "[" * depth + "]" * depth  # json.loads 가 RecursionError 를 낼 수 있는 깊이 — 글로 읽고, 긴 한 항목은 버린다
    assert decision_value(f"review_reasons: {raw}", "review_reasons") is None


def test_decision_list_with_only_long_items_is_not_confirmed_empty():
    longer = "가" * (MAX_DECISION_ITEM_LENGTH + 1)
    assert decision_value(f"review_reasons: [{longer}]", "review_reasons") is None
    assert decision_value(f"review_reasons: [{longer}, b]", "review_reasons") == ["b"]


def test_decision_duplicate_key_first_line_wins():
    text = "risk_level: 매우 높음\nrisk_level: 상\nreason: 첫 이유\nreason: 둘째 이유"
    result = decision(text)
    assert result["risk_level"] is None  # 첫 줄이 정한다(못 읽어도 다음 줄을 보지 않음)
    assert result["reason"] == "첫 이유"


def test_decision_unknown_keys_are_ignored():
    result = decision("note: 가짜\nrisk_level: 중\nlevel: 상\n상")
    assert result["risk_level"] == "중"
    assert set(result) == set(DECISION_KEYS)


def test_decision_crlf_lines():
    result = decision("risk_level: 하【†1】\r\nreview_reasons: [a]\r\nreason: 이유\r\n하")
    assert (result["risk_level"], result["review_reasons"], result["reason"]) == ("하", ["a"], "이유")


def test_decision_line_limit():
    filler = ["- 가짜 줄"] * (MAX_DECISION_LINES - 1)
    assert decision("\n".join([*filler, "risk_level: 상"]))["risk_level"] == "상"  # MAX 번째 줄은 읽는다
    assert decision("\n".join([*filler, "- 한 줄 더", "risk_level: 상"])) is None  # MAX+1 번째 줄은 읽지 않는다


def test_decision_value_length_limit():
    exact = "가" * MAX_DECISION_VALUE_LENGTH
    assert decision_value(f"reason: {exact}", "reason") == exact
    assert decision_value(f"reason: {exact}【†1】【†2】", "reason") == exact  # 인용 표시는 길이에 들지 않는다
    assert decision_value(f"reason: {exact}가", "reason") is None  # 자르지 않고 버린다
    long_list = "[" + ", ".join(["a"] * MAX_DECISION_VALUE_LENGTH) + "]"
    assert decision_value(f"document_types: {long_list}", "document_types") is None


def test_decision_list_item_limits():
    items = [f"i{n}" for n in range(MAX_DECISION_ITEMS)]
    assert decision_value(f"document_types: [{', '.join(items)}]", "document_types") == items
    assert decision_value(f"document_types: [{', '.join([*items, 'one-more'])}]", "document_types") is None
    exact, longer = "가" * MAX_DECISION_ITEM_LENGTH, "가" * (MAX_DECISION_ITEM_LENGTH + 1)
    assert decision_value(f"review_reasons: [{exact}, {longer}, b]", "review_reasons") == [exact, "b"]


@pytest.mark.parametrize("key", DECISION_KEYS)
def test_decision_surrogate_value_is_dropped(key):
    text = f"{key}: 상\ud800" if key != "document_types" else f"{key}: [a, b\udc00]"
    assert decision(text)[key] is None


def test_decision_stage_status_and_order():
    assert read_decision([risk_stage("risk_level: 상", status="failed")]) is None
    stages = [risk_stage("risk_level: 하", status="failed"), risk_stage("risk_level: 중"), risk_stage("risk_level: 상")]
    assert read_decision(stages)["risk_level"] == "중"


# --- 깊은 중첩 · 큰 입력(선형 시간) · 예외 안전망 ---------------------------------------------------


def _nested(depth: int) -> list[Any]:
    value: list[Any] = []
    for _ in range(depth):
        value = [value]
    return value


def test_deep_json_in_response_is_handled():
    # content 의 JSON 이 아주 깊으면 parse_stages 가 RecursionError 를 낸다 — 응답을 그대로 줘도 예외 없이 None
    response = load("A_smoke")
    deep = "[" * 100_000 + "]" * 100_000
    output_item(response, "Validate - 묶음_검증")["content"][0]["additional_values"] = deep
    assert read_bundle_checks(response) is None
    assert read_links(response) is None
    assert read_decision(response) is None


def test_deeply_nested_values_in_stages():
    nested = _nested(100_000)
    stages = stages_of("A_smoke")
    bundle = stage_by_key(stages, STAGE_BUNDLE_CHECK)["additional_values"]
    bundle["checks"] = [nested, check(value=nested), check("b", node=nested, field=nested, value=[nested])]
    result = read_bundle_checks(stages)
    assert [c["status"] for c in result["checks"]] == [CHECK_FAIL, CHECK_FAIL]
    assert all(c["documents"] is None for c in result["checks"])

    match = stage_by_key(stages, STAGE_MATCH)["additional_values"]
    match["targets"][0]["document_match"]["matched"] = [nested, {"page_ranges": nested}]
    match["targets"][1]["document_match"]["anchor_value"] = nested
    match["targets"].append(nested)
    links = statuses(read_links(stages))
    assert links[1] == LINK_UNMATCHED and links[2] == LINK_LINKED

    stage_by_key(stages, STAGE_RISK)["data"] = nested
    assert read_decision(stages) is None


def _timed(fn: Any) -> tuple[Any, float]:
    start = time.perf_counter()
    value = fn()
    return value, time.perf_counter() - start


def test_large_decision_inputs_are_linear():
    texts = {
        "many-lines": "risk_level: 상\n" + "x: y\n" * 100_000,
        "long-citations": "reason: " + "가 【†1】 " * 100_000,
        "space-runs": "reason: " + (" " * 10 + "【†1】") * 100_000 + "끝",
        "spaces": "reason: " + " " * 1_000_000 + "끝",
        "brackets": "document_types: [" + "a," * 100_000 + "]",
        "surrogate": "reason: " + "가" * 1_000_000 + "\ud800",
        "open-citation": "reason: " + "【†" * 100_000,
        "one-line": "가" * 1_000_000,
    }
    results, elapsed = _timed(lambda: {name: decision(text) for name, text in texts.items()})
    assert elapsed < TIME_LIMIT, elapsed
    assert results["many-lines"]["risk_level"] == "상"
    assert results["long-citations"]["reason"] is None  # 지운 뒤에도 한도를 넘는다
    assert results["space-runs"]["reason"] == "끝"
    assert results["spaces"]["reason"] == "끝"
    assert results["brackets"]["document_types"] is None
    assert results["surrogate"]["reason"] is None
    assert results["open-citation"]["reason"] is None
    assert results["one-line"] is None


def test_large_bundle_inputs_are_linear():
    stages = stages_of("A_smoke")
    stages[:0] = [{"name": None, "status": "completed"} for _ in range(100_000)]
    bundle = stage_by_key(stages, STAGE_BUNDLE_CHECK)["additional_values"]
    huge_value = list(range(100_000))
    long_name = "가" * 1_000_000
    many_checks = [check(f"r{i}", value=huge_value) for i in range(100_000)]
    capped_checks = [check(long_name if i % 2 else f"r{i}", node="추출_증빙", value=huge_value) for i in range(MAX_CHECKS)]
    many_steps = [{"branch_key": "2:x", "step_name": "y"}] * 100_000

    def run() -> list[Any]:
        out = []
        bundle["checks"] = many_checks
        out.append(read_bundle_checks(stages)["checks"])
        bundle["checks"] = capped_checks
        out.append(read_bundle_checks(stages)["checks"])
        _merge(stages)["data"]["source_steps"] = many_steps
        out.append(read_bundle_checks(stages)["checks"])
        return out

    (over, capped, no_routes), elapsed = _timed(run)
    assert elapsed < TIME_LIMIT, elapsed
    assert over is None
    assert len(capped) == MAX_CHECKS // 2 and all(c["documents"] is None for c in capped)
    assert all(c["documents"] is None for c in no_routes)


def test_large_link_inputs_are_linear():
    stages = stages_of("A_smoke")
    stages[:0] = [{"name": None, "status": "completed"} for _ in range(100_000)]
    match = stage_by_key(stages, STAGE_MATCH)["additional_values"]
    original = copy.deepcopy(match["targets"])

    def run() -> list[Any]:
        out = []
        match["targets"] = [None] * 100_000
        out.append(read_links(stages)["pairs"])
        match["targets"] = copy.deepcopy(original)
        match["targets"][0]["document_match"]["matched"] = [{"page_ranges": [[2, 2]]}] * 100_000
        match["targets"][1]["document_match"]["matched"].append({"page_ranges": [[9, 9]] * 100_000})
        match["targets"][2]["document_match"]["anchor_value"] = " " * 1_000_000
        out.append(statuses(read_links(stages)))
        match["page_ranges"] = [[1, 1]] * 100_000
        out.append(read_links(stages)["anchor_index"])
        return out

    (over, linked, anchor), elapsed = _timed(run)
    assert elapsed < TIME_LIMIT, elapsed
    assert over is None
    assert linked == {1: LINK_INSUFFICIENT, 2: LINK_LINKED, 4: LINK_LINKED, 3: LINK_INSUFFICIENT}
    assert anchor is None


@pytest.mark.parametrize(
    ("reader", "target"),
    [(read_links, "_documents"), (read_bundle_checks, "_routes"), (read_decision, "_key_line")],
)
def test_unexpected_error_gives_none_and_quiet_log(monkeypatch, caplog, reader, target):
    def boom(*args, **kwargs):
        raise ValueError("가짜값 새면 안 됨")

    monkeypatch.setattr(final_flow, target, boom)
    with caplog.at_level(logging.WARNING, logger="imask.final_flow"):
        assert reader(stages_of("A_smoke")) is None
    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert "ValueError" in message and "가짜값" not in message


# --- 고정 자료에 Upstage 식별자 값이 없다(BRIEF §2 — T1-fix1 에서 자리표시자로 가림) ----------------------------

_UPSTAGE_ID = re.compile(r"(?<![A-Za-z0-9_])(?:file|job|resp|msg)_[A-Za-z0-9]{8,}(?![A-Za-z0-9_])")
_FIXTURE_ID = re.compile(r"(?:file|job|resp|msg)_FIXTURE[A-E][0-9]*")
_OTHER_ID = re.compile(r"(?<![A-Za-z0-9])(?:agt|cfg|proj)_[A-Za-z0-9]")


def _all_texts(raw: str) -> list[str]:
    """원문 + 푼 JSON 의 모든 키·문자열(문자열 안의 JSON 도 풀어서) — \\u escape 로 숨은 꼴도 본다. 반복문."""
    texts = [raw]
    stack: list[Any] = [json.loads(raw)]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            texts.extend(key for key in node if isinstance(key, str))
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
        elif isinstance(node, str):
            texts.append(node)
            if node.lstrip()[:1] in ("{", "["):
                try:
                    stack.append(json.loads(node))
                except ValueError:
                    pass
    return texts


@pytest.mark.parametrize("name", [*RUNS, "config"])
def test_fixtures_hold_no_upstage_ids(name):
    texts = _all_texts((FIXTURES / f"{name}.json").read_bytes().decode("utf-8"))
    ids = {m.group(0) for text in texts for m in _UPSTAGE_ID.finditer(text)}
    real = [len(i) for i in ids if not _FIXTURE_ID.fullmatch(i)]
    assert real == [], "자리표시자가 아닌 Upstage id 꼴이 있다(길이만 표시)"
    assert not any(_OTHER_ID.search(text) for text in texts), "agt_·cfg_·proj_ 꼴이 있다"
    if name == "config":
        assert ids == set()
        return
    letter = name[0]
    # 같은 원래 값은 같은 자리표시자 — 작업 id(최상위 id·job_execution_id)와 파일 id 가 한 가지씩
    assert ids == {f"job_FIXTURE{letter}", f"file_FIXTURE{letter}1"}
    response = load(name)
    assert response["id"] == f"job_FIXTURE{letter}" and response["model"] == "<AGENT>"
    stages = parse_stages(response)
    assert {s["additional_values"]["job_execution_id"] for s in stages} == {f"job_FIXTURE{letter}"}
    assert stages[0]["additional_values"]["document_ids"] == [f"file_FIXTURE{letter}1"]


def test_id_pattern_catches_real_shapes_but_not_key_names():
    # 검사 꼴이 비어 있게 통과하지 않게 — 실행 중에 조립한 가짜 id 는 걸리고 키 이름은 걸리지 않는다
    fake_file = "file_" + "x1Y2" * 5 + "zz"
    fake_job = "job_" + "Ab3" * 7 + "c"
    assert {m.group(0) for m in _UPSTAGE_ID.finditer(f'"file_id": "{fake_file}", "job_execution_id": "{fake_job}"')} == {
        fake_file,
        fake_job,
    }
    for key in ("file_id", "file_name", "file_index", "job_execution_id", "source_job_ids"):
        assert _UPSTAGE_ID.search(f'"{key}": null') is None
    assert _OTHER_ID.search("agt" + "_abc123") and _OTHER_ID.search("x cfg" + "_9") and not _OTHER_ID.search("tagt" + "_x")


@pytest.mark.parametrize("name", RUNS)
def test_reader_results_are_plain_json(name):
    stages = stages_of(name)
    for result in (read_decision(stages), read_bundle_checks(stages), read_links(stages)):
        assert json.loads(json.dumps(result, ensure_ascii=False, allow_nan=False)) == result


# --- fix2 M1: 푼 뒤의 짝 없는 서로게이트 -------------------------------------------------------------

# JSON escape 글자 그대로(역슬래시 + u + 네 자리) — 이 파이썬 문자열에는 서로게이트가 없고 ASCII 다
ESCAPED_SURROGATES = ("\\ud800", "\\udc00")
ESCAPED_PAIR = "\\ud83d\\ude00"  # 정상 surrogate pair → 이모지 한 글자


def decision_from_response(text: str) -> dict[str, Any] | None:
    """응답 입력: 고정 응답 A 의 위험도_판정 본문(content[0].text)을 바꿔 응답 그대로 읽는다."""
    response = load("A_smoke")
    output_item(response, "Instruct - 위험도_판정")["content"][0]["text"] = text
    return read_decision(response)


def read_decision_from(source: str, text: str) -> dict[str, Any] | None:
    return decision(text) if source == "stages" else decision_from_response(text)


def assert_utf8(result: Any) -> None:
    assert not has_unpaired_surrogates(result)
    json.dumps(result, ensure_ascii=False).encode("utf-8")  # UnicodeEncodeError 가 나지 않는다


@pytest.mark.parametrize("source", ["stages", "response"])
@pytest.mark.parametrize("escape", ESCAPED_SURROGATES, ids=["high", "low"])
@pytest.mark.parametrize("key", sorted(DECISION_LIST_KEYS))
def test_decision_escaped_surrogate_in_json_list_drops_the_value(key, escape, source):
    text = f'risk_level: 상\n{key}: ["ok", "가{escape}"]\nreason: 이유'
    assert text_is_safe(text) and "\\u" in text  # 원문 검사로는 걸리지 않는 입력
    result = read_decision_from(source, text)
    assert result[key] is None  # 한 항목이라도 안전하지 않으면 그 키의 값 전체
    assert result["risk_level"] == "상" and result["reason"] == "이유"  # 다른 키는 그대로
    assert_utf8(result)


@pytest.mark.parametrize("source", ["stages", "response"])
@pytest.mark.parametrize("key", sorted(DECISION_LIST_KEYS))
def test_decision_escaped_surrogate_pair_is_kept(key, source):
    result = read_decision_from(source, f'{key}: ["{ESCAPED_PAIR}", "b"]')
    assert result[key] == ["\U0001f600", "b"]
    assert_utf8(result)


def test_decision_plain_text_list_keeps_escape_as_text():
    # JSON 이 아닌 목록은 풀지 않는다 — 역슬래시 글자 그대로(안전한 글)
    result = decision(f"review_reasons: [a, {ESCAPED_SURROGATES[0]}]")
    assert result["review_reasons"] == ["a", ESCAPED_SURROGATES[0]]
    assert_utf8(result)


@pytest.mark.parametrize("key", DECISION_KEYS)
def test_decision_surrogate_decoded_by_parse_stages_is_dropped(key):
    # 본문 자체가 JSON 문자열이면 parse_stages 가 escape 를 풀어 서로게이트가 된다 → 원문 검사에서 버린다
    value = '["가' + ESCAPED_SURROGATES[0] + '"]' if key in DECISION_LIST_KEYS else "상" + ESCAPED_SURROGATES[1]
    # JSON 문자열 글자로 만들되 escape 하나는 그대로 둔다 → parse_stages 가 풀면 짝 없는 서로게이트
    text = json.dumps(f"{key}: {value}", ensure_ascii=False).replace("\\\\u", "\\u")
    assert text_is_safe(text) and not text_is_safe(json.loads(text))
    result = decision_from_response(text)
    assert result[key] is None
    assert_utf8(result)


def test_decision_values_are_checked_after_cleaning(monkeypatch):
    # 다듬은 뒤의 값도 같은 기준으로 본다 — 다듬기가 서로게이트를 남기는 경우(가정): 글 목록·reason 모두 버린다
    monkeypatch.setattr(final_flow, "_strip_citations", lambda text: text.replace("이유", "이유\ud800").replace("a", "a\ud800"))
    result = decision("risk_level: 상\nreason: 이유\nreview_reasons: [a, b]\ndocument_types: [c]")
    assert result == {
        "risk_level": "상",
        "document_types": ["c"],
        "sensitive_categories": None,
        "review_reasons": None,
        "reason": None,
    }
    assert_utf8(result)


@pytest.mark.parametrize(
    ("reader", "target", "value"),
    [
        (read_bundle_checks, "_name", "x\ud800"),
        (read_links, "_group_of_step", "x\udc00"),
        (read_decision, "text_is_safe", True),  # 값마다의 서로게이트 검사를 모두 끈다(가정)
    ],
    ids=["bundle", "links", "decision"],
)
def test_last_safety_net_drops_unsafe_result(monkeypatch, caplog, reader, target, value):
    # 값마다의 검사가 빠져도(가정) 결과에 서로게이트가 남으면 결과 전체가 None — 결과는 늘 UTF-8 로 인코딩된다
    monkeypatch.setattr(final_flow, target, lambda *args, **kwargs: value)
    stages = stages_of("A_smoke")
    if reader is read_decision:
        stage_by_key(stages, STAGE_RISK)["data"] = 'review_reasons: ["' + ESCAPED_SURROGATES[0] + '"]'
    with caplog.at_level(logging.WARNING, logger="imask.final_flow"):
        assert reader(stages) is None
    (record,) = caplog.records
    assert reader.__name__ in record.getMessage()
    assert text_is_safe(record.getMessage())


def test_response_path_surrogates_in_bundle_and_links_are_dropped():
    # 같은 원인의 다른 길: additional_values JSON 의 escape 가 parse_stages 에서 풀린 이름·필드·키
    response = load("A_smoke")

    def bundle_change(additional):
        additional["checks"][0]["name"] = "규칙\ud800"
        additional["checks"][1]["conditions"]["left"]["field"] = "f\udc00"
        additional["checks"][2]["conditions"]["left"]["nodeName"] = "추출_증빙\ud800"
        additional["verdict"] = "green\ud800"

    def match_change(additional):
        additional["targets"][0]["document_match"]["anchor_key"] = "applicant_name\udc00"
        additional["targets"][1]["step_name"] = "Information Extract - 추출_증빙\ud800"

    change_additional(output_item(response, "Validate - 묶음_검증"), bundle_change)
    change_additional(output_item(response, "Match - 서류_대조"), match_change)
    raw = output_item(response, "Validate - 묶음_검증")["content"][0]["additional_values"]
    assert "\ud800" in raw  # 저장된 JSON 문자열 안에 서로게이트(파싱하면 그대로 풀린다)

    bundle = read_bundle_checks(response)
    assert [c["name"] for c in bundle["checks"]] == ["확인서_신청인_성명", "증빙_신청인_성명", "위임장_위임인_성명", "위임장_대리인_성명"]
    assert bundle["verdict"] is None
    assert bundle["checks"][0]["field"] is None
    assert bundle["checks"][1]["group"] is None and bundle["checks"][1]["documents"] is None
    links = read_links(response)
    assert links["field"] is None
    assert {p["target_index"] for p in links["pairs"]} == {1, 3}  # 이름이 틀린 대상(증빙)은 경로가 없다
    for result in (bundle, links, read_decision(response)):
        assert_utf8(result)


# --- fix2 M2: read_links 짝짓기 한도 ------------------------------------------------------------


def link_stages(documents: int, matched: int, unmatched: int) -> list[dict[str, Any]]:
    """서류 documents 개(0 = 신청서, 나머지 확인서, 쪽 i+1), 서류 쪽과 같은 추출 matched 개, 짝 없는 추출 unmatched 개.

    병합 경로는 모든 서류, 대조 대상은 확인서 하나(matched 에 확인서 서류 쪽 모두)."""
    codes = ["loan_application"] + ["consent_form"] * (documents - 1)
    contents = [
        {"data": code, "additional_values": {"document_type": {"_value": code}, "page_ranges": [[i + 1, i + 1]]}}
        for i, code in enumerate(codes)
    ]

    def stage(key: str, data: Any = None, additional: Any = None, **extra: Any) -> dict[str, Any]:
        return {"name": key, "key": key, "status": "completed", "data": data, "additional_values": additional, **extra}

    nodes = ["추출_신청서"] + ["추출_확인서"] * (documents - 1)
    extracts = [stage(STAGE_EXTRACT, {"applicant_name": "가짜"}, {"page_ranges": [[i + 1, i + 1]]}) for i in range(matched)]
    extracts += [stage(STAGE_EXTRACT, {"applicant_name": "가짜"}, {"page_ranges": [[99_999, 99_999]]}) for _ in range(unmatched)]
    steps = [{"branch_key": f"{i}:{codes[i]}", "step_name": EXTRACT_STEP_PREFIX + nodes[i]} for i in range(documents)]
    target = {
        "step_name": EXTRACT_STEP_PREFIX + "추출_확인서",
        "document_match": {
            "anchor_key": "applicant_name",
            "target_key": "applicant_name",
            "anchor_value": "가짜",
            "matched": [{"page_ranges": [[i + 1, i + 1]]} for i in range(1, documents)],
        },
    }
    return [
        stage(STAGE_CLASSIFY, contents=contents),
        *extracts,
        stage(STAGE_MERGE, {"source_steps": steps}),
        stage(STAGE_MATCH, {}, {"page_ranges": [[1, 1]], "targets": [target]}),
    ]


def test_link_limits_are_constants():
    assert (MAX_LINK_DOCUMENTS, MAX_LINK_EXTRACTS) == (500, 1000)
    assert MAX_LINK_DOCUMENTS - 1 <= MAX_MATCHED and MAX_LINK_DOCUMENTS <= MAX_SOURCE_STEPS  # 한도 안 입력이 다른 한도에 먼저 걸리지 않게


def test_link_document_limit():
    inside = read_links(link_stages(MAX_LINK_DOCUMENTS, MAX_LINK_DOCUMENTS, 0))
    assert inside["anchor_index"] == 0 and len(inside["pairs"]) == MAX_LINK_DOCUMENTS - 1
    assert {p["status"] for p in inside["pairs"]} == {LINK_LINKED}
    outside = read_links(link_stages(MAX_LINK_DOCUMENTS + 1, MAX_LINK_DOCUMENTS + 1, 0))
    assert outside == {"field": "applicant_name", "anchor_index": 0, "pairs": None}  # 일부만 잘라 잇지 않는다


def test_link_extract_limit():
    inside = read_links(link_stages(3, 3, MAX_LINK_EXTRACTS - 3))
    assert statuses(inside) == {1: LINK_LINKED, 2: LINK_LINKED}
    outside = read_links(link_stages(3, 3, MAX_LINK_EXTRACTS - 2))
    assert outside == {"field": "applicant_name", "anchor_index": 0, "pairs": None}
    # 실패한 추출 단계는 세지 않는다(짝짓기도 쓰지 않는다)
    stages = link_stages(3, 3, MAX_LINK_EXTRACTS - 2)
    stages[-3]["status"] = "failed"
    assert statuses(read_links(stages)) == {1: LINK_LINKED, 2: LINK_LINKED}


def test_link_worst_case_inside_limits_is_fast():
    # 서류 500·추출 1000(짝 있는 500 + 짝 없는 500) — 한도 안 최악
    stages = link_stages(MAX_LINK_DOCUMENTS, MAX_LINK_DOCUMENTS, MAX_LINK_EXTRACTS - MAX_LINK_DOCUMENTS)
    result, elapsed = _timed(lambda: read_links(stages))
    assert elapsed < TIME_LIMIT, elapsed
    assert len(result["pairs"]) == MAX_LINK_DOCUMENTS - 1
    assert {p["status"] for p in result["pairs"]} == {LINK_LINKED}


@pytest.mark.parametrize("unmatched", [MAX_LINK_EXTRACTS, 16_000, 100_000])
def test_link_over_limit_returns_without_pairing(monkeypatch, unmatched):
    def boom(*args, **kwargs):
        raise AssertionError("한도를 넘으면 짝짓기를 부르지 않는다")

    monkeypatch.setattr(final_flow, "_attach_extracts", boom)
    stages = link_stages(3, 3, unmatched)
    result, elapsed = _timed(lambda: read_links(stages))
    assert result == {"field": "applicant_name", "anchor_index": 0, "pairs": None}
    assert elapsed < TIME_LIMIT / 4, elapsed
