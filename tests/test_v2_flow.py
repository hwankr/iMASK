# ==========================================================================
#  설정 60(v2_full) 응답 읽기 — 모양 구별·판정 8키·검증 사슬·탐지 항목·검토사항·연결·API (네트워크 없음)
#  자료: tests/fixtures/v2/case_<A~U>.json — 실제 응답 21건의 모양을 가상 값으로 바꾼 것(같은 원문 → 같은 가상 값, 포함 관계·꼴 유지.
#  Parse 본문은 뺐고 통과 규칙은 노드마다 앞 2개만 조건 트리가 있다. 판정 JSON 은 토큰·고정 문장이라 그대로), answers.json — 정답지 8키(가상 값 아님).
#  케이스: A 4서식 묶음(판정_상) · B·C 묶음 · E 판정_중(상_확인 red) · K·P·Q·S 판정_누락(P 판독 불가, Q 조건부 필수, S 빈 서식) · L·M 판정_형식(M 표 칸) ·
#  N·O 판정_불일치(내용_검토 모순) · R 판정_대상외(추출 없음) · T 판정_중복(같은 서식 두 건) · U 판정_불일치(서류 간 성명).
#  합성 변형은 그 자료를 고쳐 만든다. 실패 메시지에 나오는 값도 모두 가상 값이다.
# ==========================================================================

from __future__ import annotations

import copy
import functools
import json
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fake_findings import stored_result
from fake_reviews import ACTOR
from shared_ctx import ANALYSIS_KEYS, Ctx, ctx, install  # noqa: F401
from view_contract import assert_item, assert_view

from imask_backend import final_flow, items as items_module
from imask_backend.analyses import analysis_out, build_result
from imask_backend.reviews import review_scope
from imask_backend.final_flow import (
    FINAL_DOC_TYPES,
    MAX_CHECKS,
    MAX_DECISION_VALUE_LENGTH,
    MAX_LINK_DOCUMENTS,
    MAX_TREE_DEPTH,
    MAX_TREE_NODES,
    V2_DECISION_KEYS,
    V2_MAX_DECISION_ITEMS,
    V2_SELF_NAMES,
    is_v2,
    read_bundle_checks,
    read_chain,
    read_decision,
    read_links,
    read_v2_links,
    read_verdict,
)
from imask_backend.findings import UNNAMED_LABEL, UNREADABLE_VALUE, build_view, v2_is_item_key, v2_item_fields
from imask_backend.items import MISSING_DESC, MISSING_NEXT, OTHER_DESC, OTHER_NEXT, VERDICT_DESC, VERDICT_NEXT, VERDICT_TITLE, build_items
from imask_backend.results import (
    STAGE_EXTRACT,
    STAGE_REVIEW,
    STAGE_V2_CONTENT,
    STAGE_V2_VERDICT,
    STAGE_VALIDATE,
    V2_FORM_CODES,
    parse_stages,
    stage_key,
    summarize,
)
from imask_backend.textsafe import has_unpaired_surrogates

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "v2"
OLD_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "final_flow"
OLD_RUNS = ("A_smoke", "B_blank_autotransfer", "C_mismatch", "D_blank_applicant", "E_team_forms")
CASES = tuple("ABCDEFGHIJKLMNOPQRSTU")
ANSWERS: dict[str, dict[str, Any]] = json.loads((FIXTURES / "answers.json").read_bytes().decode("utf-8"))
TIME_LIMIT = 2.0
# 7갈래 → 그 판정 단계가 도는 케이스
BRANCHES = {
    "판정_상": ("A", "상", "권장_조치"),
    "판정_중": ("E", "중", "권장_조치"),
    "판정_대상외": ("R", "검토 필요", "검토_안내"),
    "판정_중복": ("T", "검토 필요", "검토_안내"),
    "판정_누락": ("K", "검토 필요", "검토_안내"),
    "판정_형식": ("L", "검토 필요", "검토_안내"),
    "판정_불일치": ("U", "검토 필요", "검토_안내"),
}
UNREADABLE_DESC = "글자를 읽을 수 없는 칸입니다."
FORMAT_DESC = "형식 검증을 통과하지 못했습니다."
RULE_MISMATCH_DESC = "값 일치 검증을 통과하지 못했습니다."
DUPLICATE_DESC = "같은 서식이 여러 건 있습니다."


@functools.cache
def _raw(case: str) -> str:
    return (FIXTURES / f"case_{case}.json").read_bytes().decode("utf-8")


def load(case: str) -> dict[str, Any]:
    return json.loads(_raw(case))


def view_of(source: str | dict[str, Any]) -> dict[str, Any]:
    return build_view({"response": load(source) if isinstance(source, str) else source})


def stages_of(source: str | dict[str, Any]) -> list[dict[str, Any]]:
    return parse_stages(load(source) if isinstance(source, str) else source)


def step(response: dict[str, Any], name: str, nth: int = 0) -> dict[str, Any]:
    return [item for item in response["output"] if item["model"] == name or item["model"].endswith(" - " + name)][nth]


def edit(response: dict[str, Any], name: str, change: Callable[[Any], Any], field: str = "text", *, nth: int = 0, content: int = 0) -> None:
    """단계 content 의 JSON 문자열(text·additional_values)을 풀어 고친 뒤 다시 넣는다. change 가 값을 돌려주면 그 값으로 바꾼다."""
    entry = step(response, name, nth)["content"][content]
    value = json.loads(entry[field])
    returned = change(value)
    entry[field] = json.dumps(value if returned is None else returned, ensure_ascii=False)


def set_value(response: dict[str, Any], form: str, key: str, value: Any, nth: int = 0) -> None:
    def change(data: dict[str, Any]) -> None:
        data[key] = value

    edit(response, f"Information Extract - {form}", change, nth=nth)


def ids(items: list[dict[str, Any]]) -> list[str]:
    return [item["id"] for item in items]


def finding(view: dict[str, Any], finding_id: str) -> dict[str, Any]:
    return next(f for f in view["findings"] if f["id"] == finding_id)


def item_of(view: dict[str, Any], item_id: str) -> dict[str, Any]:
    return next(i for i in view["items"] if i["id"] == item_id)


def same_answer(got: dict[str, Any], answer: dict[str, Any]) -> bool:
    return all((sorted(got[key]) == sorted(value)) if isinstance(value, list) else got[key] == value for key, value in answer.items())


def link_states(view: dict[str, Any]) -> dict[str, str]:
    return {link["id"]: link["state"] for link in view["links"]}


# --- 모양 구별 -------------------------------------------------------------------------------


@pytest.mark.parametrize("case", CASES)
def test_every_fixture_is_v2_and_passes_the_contract(case: str) -> None:
    response = load(case)
    assert is_v2(response) and is_v2(parse_stages(response))
    view = view_of(case)
    assert_view(view)
    assert all(document["validation"] is None for document in view["documents"])


@pytest.mark.parametrize("run", OLD_RUNS)
def test_old_fixtures_are_not_v2(run: str) -> None:
    response = json.loads((OLD_FIXTURES / f"{run}.json").read_bytes().decode("utf-8"))
    assert not is_v2(response)
    assert read_verdict(response) is None and read_chain(response) is None and read_v2_links(response) is None


@pytest.mark.parametrize(
    "name",
    [
        "Validate - 대상_확인",
        "Validate - 단위_확인",
        "Validate - 필수_확인",
        "Validate - 형식_확인",
        "Validate - 일치_확인",
        "Validate - 상_확인",
        "Instruct - 내용_검토",
        "Instruct - 판정_상",
        "Instruct - 판정_하",
        "Instruct - 판정_새갈래",
        "Information Extract - 자동이체신청서",
        "Information Extract - IRP_신규신청서",
    ],
)
@pytest.mark.parametrize("status", ["completed", "failed", "in_progress", None])
def test_v2_by_step_name_with_any_status(name: str, status: Any) -> None:
    assert is_v2([{"name": name, "status": status}])


@pytest.mark.parametrize("code", V2_FORM_CODES)
def test_v2_by_classify_code_only(code: str) -> None:
    response = {"output": [{"model": "step_2_classify", "status": "completed", "step_type": "document-classify", "content": [{"text": code}]}]}
    assert is_v2(response)


@pytest.mark.parametrize(
    "stages",
    [
        [],
        [{"name": "Validate - 묶음_검증"}],
        [{"name": "Validate - 필수항목_검증"}],
        [{"name": "Instruct - 위험도_판정"}],
        [{"name": "Information Extract - 추출_신청서"}],
        [{"name": "Information Extract - 민감정보_추출"}],
        [{"name": "step_2_classify", "contents": [{"data": "loan_application"}]}],
        [{"name": "step_2_classify", "contents": [{"data": "Other"}]}],
        [{"name": None, "key": "대상_확인"}],  # 저장된 key 는 믿지 않는다
        [{"name": 5}],
        ["문자열", None, 3],
    ],
)
def test_not_v2(stages: list[Any]) -> None:
    assert not is_v2(stages)


@pytest.mark.parametrize("value", [None, 5, "글", {"output": 5}, {"output": [None]}])
def test_is_v2_other_shapes(value: Any) -> None:
    assert not is_v2(value)


def test_is_v2_of_unparseable_response_is_false() -> None:
    response = {"output": [{"model": "Validate - 대상_확인", "content": [{"text": "[" * 100_000}]}]}
    assert is_v2(response) is False  # parse_stages 가 RecursionError — 예외 없이


def test_stage_key_returns_new_keys_not_the_old_validation() -> None:
    for node in ("대상_확인", "단위_확인", "필수_확인", "형식_확인", "일치_확인", "상_확인"):
        assert stage_key(f"Validate - {node}", "validate") == node
    assert stage_key("Instruct - 내용_검토", "instruct") == STAGE_V2_CONTENT
    assert stage_key("Instruct - 판정_상", "instruct") == STAGE_V2_VERDICT
    assert stage_key("Instruct - 판정_하", "instruct") == STAGE_V2_VERDICT
    assert stage_key("Information Extract - 위임장_상속") == STAGE_EXTRACT
    # 옛 이름은 그대로
    assert stage_key("Validate - 필수항목_검증", "validate") == STAGE_VALIDATE
    assert stage_key("Validate - 모르는_검증", "validate") == STAGE_VALIDATE
    assert stage_key("Instruct - 모르는_판정", "instruct") is None


def test_stored_old_key_does_not_route_to_the_validation_path() -> None:
    # 옛 코드가 사슬 노드를 key: 필수항목_검증 으로 저장했어도 서류별 검증(validation·missing)으로 가지 않는다
    stages = stages_of("K")
    for stage in stages:
        if str(stage["name"]).startswith("Validate - "):
            stage["key"] = STAGE_VALIDATE
    view = build_view({"stages": stages})
    assert all(document["validation"] is None for document in view["documents"])
    assert view["bundle_check"]["verdict"] == "red"
    assert ids(view["items"]) == ["missing:0:소비자피해보상금_지급신청서_신청인_주민등록번호"]


def test_stored_stages_give_the_same_view_as_the_response() -> None:
    for case in ("A", "B", "R", "U"):
        assert build_view({"stages": stages_of(case)}) == view_of(case)


# --- 서류 이름 -------------------------------------------------------------------------------


def test_new_doc_type_names_have_no_group() -> None:
    assert [code for code in FINAL_DOC_TYPES if code in V2_FORM_CODES] == list(V2_FORM_CODES)
    assert all(FINAL_DOC_TYPES[code][1] is None for code in V2_FORM_CODES)
    assert FINAL_DOC_TYPES["위임장_상속"][0] == "상속예금 위임장"
    assert FINAL_DOC_TYPES["FATCA_CRS_본인확인서"][0] == "FATCA/CRS 본인확인서"


# --- 판정 8키 --------------------------------------------------------------------------------


@pytest.mark.parametrize("case", CASES)
def test_decision_equals_the_answer_sheet(case: str) -> None:
    view = view_of(case)
    decision = view["decision"]
    assert list(decision) == list(V2_DECISION_KEYS)
    assert same_answer(decision, ANSWERS[case])
    assert view["overall"]["level"] == ANSWERS[case]["risk_level"]
    assert view["overall"]["text"] == ANSWERS[case]["reason"]
    assert view["overall"]["next_text"] == ANSWERS[case]["recommended_action"]


@pytest.mark.parametrize(("branch", "expected"), BRANCHES.items(), ids=list(BRANCHES))
def test_seven_branches(branch: str, expected: tuple[str, str, str]) -> None:
    case, level, next_stage = expected
    response = load(case)
    assert any(item["model"] == f"Instruct - {branch}" for item in response["output"])
    view = view_of(response)
    assert view["overall"]["level"] == level and view["overall"]["next_stage"] == next_stage
    summary = summarize(response)
    assert (summary["risk_level"], summary["final_stage"]) == (level, next_stage)
    stored = build_result(copy.deepcopy(response), "60")["summary"]
    assert stored == summary


def test_summary_keys_are_unchanged_and_other_count() -> None:
    keys = {"stage_names", "stage_counts", "document_count", "document_types", "extracted_document_count", "risk_level", "final_stage", "other_document_count"}
    summary = summarize(load("R"))
    assert set(summary) == keys
    assert summary["document_types"] == ["Other"] and summary["other_document_count"] == 1 and summary["extracted_document_count"] is None
    summary = summarize(load("A"))
    assert summary["other_document_count"] is None and summary["document_count"] == 4 and summary["extracted_document_count"] == 4


def test_verdict_low_branch_synthetic() -> None:
    # 판정_하 — 지금 없는 갈래도 읽는다
    response = load("E")
    item = step(response, "판정_중")
    item["model"] = "Instruct - 판정_하"

    def change(body: dict[str, Any]) -> None:
        body["risk_level"] = "하"

    edit(response, "판정_하", change)
    view = view_of(response)
    assert view["decision"]["risk_level"] == "하"
    assert view["overall"]["level"] == "하" and view["overall"]["next_stage"] == "권장_조치"
    summary = summarize(response)
    assert (summary["risk_level"], summary["final_stage"]) == ("하", "권장_조치")
    assert_view(view)


def _verdict_with(**fields: Any) -> dict[str, Any]:
    response = load("A")

    def change(body: dict[str, Any]) -> None:
        body.update(fields)

    edit(response, "판정_상", change)
    return response


@pytest.mark.parametrize("level", ["최상", "", " ", "높음", 5, None, ["상"], {"a": 1}, True, "상\ud800"])
def test_unknown_risk_level_is_null(level: Any) -> None:
    response = _verdict_with(risk_level=level)
    view = view_of(response)
    assert view["decision"]["risk_level"] is None
    assert view["overall"]["level"] is None and view["overall"]["next_stage"] is None
    summary = summarize(response)
    assert summary["risk_level"] is None and summary["final_stage"] is None


def test_citations_are_removed_from_text_and_lists() -> None:
    view = view_of(_verdict_with(reason="이유 【†1】입니다【†22】.", recommended_action="조치【†3】", risk_level="상【†1】", review_reasons=["값 불일치【†1】"]))
    decision = view["decision"]
    assert decision["reason"] == "이유 입니다." and decision["recommended_action"] == "조치"
    assert decision["risk_level"] == "상" and decision["review_reasons"] == ["값 불일치"]


@pytest.mark.parametrize("key", ["reason", "recommended_action"])
def test_text_length_limit(key: str) -> None:
    assert view_of(_verdict_with(**{key: "가" * MAX_DECISION_VALUE_LENGTH}))["decision"][key] == "가" * MAX_DECISION_VALUE_LENGTH
    assert view_of(_verdict_with(**{key: "가" * (MAX_DECISION_VALUE_LENGTH + 1)}))["decision"][key] is None


@pytest.mark.parametrize("key", ["reason", "recommended_action"])
@pytest.mark.parametrize("value", [5, None, ["글"], {"a": 1}, "글\ud800", ""])
def test_unreadable_text_is_null(key: str, value: Any) -> None:
    view = view_of(_verdict_with(**{key: value}))
    assert view["decision"][key] is None
    assert view["overall"]["text" if key == "reason" else "next_text"] == ""
    assert_view(view)


LIST_KEYS = ("document_types", "high_risk_items", "medium_risk_items", "low_risk_items", "review_reasons")


@pytest.mark.parametrize("key", LIST_KEYS)
@pytest.mark.parametrize("value", [["a", 5], ["a", None], [["a"]], "a", 5, None, {"a": 1}, ["a\ud800"], ["a"] * (V2_MAX_DECISION_ITEMS + 1)], ids=str)
def test_unreadable_list_is_null(key: str, value: Any) -> None:
    decision = view_of(_verdict_with(**{key: value}))["decision"]
    assert decision[key] is None
    assert list(decision) == list(V2_DECISION_KEYS)


@pytest.mark.parametrize("key", LIST_KEYS)
def test_empty_list_stays_empty_and_limit_is_not_cut(key: str) -> None:
    assert view_of(_verdict_with(**{key: []}))["decision"][key] == []
    full = [f"서식.칸{n}" for n in range(V2_MAX_DECISION_ITEMS)]
    assert view_of(_verdict_with(**{key: full}))["decision"][key] == full


@pytest.mark.parametrize("body", ["문자열 본문", ["목록"], 5, None, ""])
def test_verdict_body_must_be_an_object(body: Any) -> None:
    response = load("A")
    step(response, "판정_상")["content"][0]["text"] = json.dumps(body, ensure_ascii=False)
    view = view_of(response)
    assert view["decision"] is None
    assert view["overall"] == {"level": None, "text": "", "next_stage": None, "next_text": ""}
    assert summarize(response)["risk_level"] is None
    assert_view(view)


def test_first_usable_verdict_step_only() -> None:
    response = load("A")
    failed = copy.deepcopy(step(response, "판정_상"))
    failed["status"] = "failed"
    failed["model"] = "Instruct - 판정_중"
    response["output"].insert(len(response["output"]) - 1, failed)
    assert read_verdict(response)["risk_level"] == "상"
    second = copy.deepcopy(step(response, "판정_상"))
    second["model"] = "Instruct - 판정_대상외"
    response["output"].append(second)
    response["output"][-1]["content"][0]["text"] = json.dumps({"risk_level": "검토 필요"}, ensure_ascii=False)
    assert read_verdict(response)["risk_level"] == "상"


def test_verdict_must_be_an_instruct_step() -> None:
    stages = [{"name": "Validate - 판정_상", "step_type": "validate", "status": "completed", "data": {"risk_level": "상"}}]
    assert read_verdict(stages) is None
    stages[0]["step_type"] = None
    assert read_verdict(stages)["risk_level"] == "상"


def test_read_decision_and_old_readers_stay_silent_on_v2() -> None:
    response = load("A")
    assert read_decision(response) is None and read_bundle_checks(response) is None and read_links(response) is None


# --- 케이스별 모양: 대상 외·빈 서식·서류 여러 개 ----------------------------------------------------


def test_other_document_has_no_extract() -> None:
    response = load("R")
    assert not [item for item in response["output"] if item["step_type"] == "information-extract"]
    view = view_of(response)
    assert view["findings"] == [] and view["links"] == []
    assert view["decision"]["document_types"] == [] and view["decision"]["review_reasons"] == ["대상 외 서류"]
    assert [(d["index"], d["type"], d["kind"], d["other_guide"], d["validation"]) for d in view["documents"]] == [(0, "Other", "other", None, None)]
    assert ids(view["items"]) == ["other:0"]


def test_blank_form_has_no_items_but_review_items() -> None:
    view = view_of("S")
    assert view["findings"] == []
    assert view["documents"][0]["kind"] == "extracted"
    assert view["overall"]["level"] == "검토 필요"
    assert ids(view["items"]) == ["missing:0:자동이체신청서_예금주_성명", "missing:0:자동이체신청서_출금계좌번호"]
    assert [i["title"] for i in view["items"]] == ["예금주 성명이 없습니다", "출금계좌번호가 없습니다"]


def test_many_documents_keep_their_own_items_and_pages() -> None:
    view = view_of("A")
    assert [(d["index"], d["type"], d["page_start"], d["page_end"]) for d in view["documents"]] == [
        (0, "자동이체신청서", 1, 2),
        (1, "FATCA_CRS_본인확인서", 3, 4),
        (2, "휴면예금지급신청서", 5, 6),
        (3, "위임장_상속", 7, 7),
    ]
    spans = {d["index"]: (d["page_start"], d["page_end"]) for d in view["documents"]}
    assert {f["document_index"] for f in view["findings"]} == set(spans)
    for f in view["findings"]:
        if f["page"] is not None:
            assert spans[f["document_index"]][0] <= f["page"] <= spans[f["document_index"]][1], f["id"]
    assert "0:상_출금계좌번호" in {f["id"] for f in view["findings"]}
    assert "3:상속재산[0].상_상속재산_계좌번호" in {f["id"] for f in view["findings"]}


# --- 탐지 항목 -------------------------------------------------------------------------------


def _meta(response: dict[str, Any], form: str, nth: int = 0) -> dict[str, Any]:
    return json.loads(step(response, f"Information Extract - {form}", nth)["content"][0]["additional_values"])


def _data(response: dict[str, Any], form: str, nth: int = 0) -> dict[str, Any]:
    return json.loads(step(response, f"Information Extract - {form}", nth)["content"][0]["text"])


@pytest.mark.parametrize("case", CASES)
def test_item_grade_comes_from_the_prefix(case: str) -> None:
    for f in view_of(case)["findings"]:
        cell = f["field"].rpartition("].")[2] if "]." in f["field"] else f["field"]
        assert f["risk"] == {"상_": "high", "중_": "medium", "하_": "low"}[cell[:2]], f["id"]
        assert f["risk_source"] == "workflow" and f["risk_reason"] is None
        assert f["mapping_status"] == "ok"


@pytest.mark.parametrize("case", CASES)
def test_unprefixed_fields_and_incomplete_fields_are_not_items(case: str) -> None:
    for f in view_of(case)["findings"]:
        assert "incomplete_fields" not in f["field"]
        cell = f["field"].rpartition("].")[2] if "]." in f["field"] else f["field"]
        assert cell[:2] in ("상_", "중_", "하_"), f["id"]


def test_v2_item_fields_chooses_prefixed_cells_and_tables_only() -> None:
    data = {
        "문서명": "서식 이름",
        "요청사유": ["사유"],
        "incomplete_fields": ["중_x"],
        "중_칸": "값",
        "세대구성원": [{"중_성명": "값"}],
        "아파트": [{"아파트_구분": "값"}],
        "세대구성원_수": 3,
    }
    assert [key for key, _ in v2_item_fields(data)] == ["중_칸", "세대구성원"]


def test_prefixed_cell_location_and_label() -> None:
    response = load("A")
    view = view_of(response)
    f = finding(view, "0:상_출금계좌번호")
    meta = _meta(response, "자동이체신청서")["상_출금계좌번호"]
    assert f["document_index"] == 0 and f["field"] == "상_출금계좌번호" and f["label"] == "출금계좌번호"
    assert f["category"] == "계좌번호" and f["subject"] == "신청인" and f["risk"] == "high"
    assert f["value"] == _data(response, "자동이체신청서")["상_출금계좌번호"]
    assert f["page"] == meta["page"] and f["confidence"] == meta["confidence"]
    assert len(f["boxes"]) == (len(meta["word_coordinates"]) or 1)
    assert f["masked"] != f["value"] and len(f["masked"]) == len(f["value"])


def test_table_rows_become_items_with_row_ids() -> None:
    response = load("B")
    view = view_of(response)
    rows = _data(response, "외국인_세대구성원_확인서")["세대구성원"]
    metas = _meta(response, "외국인_세대구성원_확인서")["세대구성원"]
    assert len(rows) == 4
    for position, row in enumerate(rows):
        for cell in ("중_관계", "중_성명", "중_성별", "중_생년월일", "상_외국인등록번호"):
            f = finding(view, f"0:세대구성원[{position}].{cell}")
            meta = metas[position][cell]
            assert f["field"] == f"세대구성원[{position}].{cell}"
            assert f["value"] == row[cell]
            assert f["label"].endswith(f" {position + 1}행")
            assert f["page"] == meta["page"] and f["confidence"] == meta["confidence"]
            if meta["word_coordinates"]:
                assert f["boxes"][0][0]["x"] == pytest.approx(meta["word_coordinates"][0][0]["x"])
    f = finding(view, "0:세대구성원[2].상_외국인등록번호")
    assert f["label"] == "외국인등록번호 3행" and f["risk"] == "high" and f["category"] == "고유식별정보" and f["subject"] == "기타"
    assert finding(view, "0:세대구성원[0].중_성명")["label"] == "성명 1행"
    # 표의 접두어 없는 칸은 만들지 않는다 — 은행계좌 표의 은행이체_은행명 등
    view_a = view_of("A")
    assert not [f for f in view_a["findings"] if "은행이체_은행명" in f["field"] or "은행이체_구분" in f["field"]]
    assert [f for f in view_a["findings"] if f["field"].startswith("은행계좌[0].상_")]


def test_table_item_order_follows_keys_and_rows() -> None:
    view = view_of("B")
    own = [f["field"] for f in view["findings"] if f["document_index"] == 0]
    table = [field for field in own if field.startswith("세대구성원[")]
    assert table[:5] == [f"세대구성원[0].{c}" for c in ("중_관계", "중_성명", "중_성별", "중_생년월일", "상_외국인등록번호")]
    assert own.index("중_담보제공자_주소") < own.index(table[0])


def test_blank_cells_are_skipped_row_position_is_kept() -> None:
    response = load("B")

    def change(data: dict[str, Any]) -> None:
        rows = data["세대구성원"]
        rows[0]["중_성명"] = ""
        rows[1] = "객체가 아닌 행"
        rows[2]["중_관계"] = "   "

    edit(response, "Information Extract - 외국인_세대구성원_확인서", change)
    view = view_of(response)
    fields = {f["field"] for f in view["findings"]}
    assert "세대구성원[0].중_성명" not in fields and "세대구성원[0].중_관계" in fields
    assert not [field for field in fields if field.startswith("세대구성원[1]")]
    assert "세대구성원[2].중_관계" not in fields and "세대구성원[2].중_성명" in fields
    assert "세대구성원[3].중_성명" in fields  # 뒤 행은 원래 자리 번호
    assert finding(view, "0:세대구성원[3].중_성명")["label"] == "성명 4행"
    assert_view(view)


@pytest.mark.parametrize("meta", ["문자열", 5, None, [], [None], [{"상_x": 1}], {"0": {}}], ids=str)
def test_wrong_table_meta_means_no_location(meta: Any) -> None:
    response = load("B")

    def change(add: dict[str, Any]) -> None:
        add["세대구성원"] = meta

    edit(response, "Information Extract - 외국인_세대구성원_확인서", change, "additional_values")
    view = view_of(response)
    f = finding(view, "0:세대구성원[0].중_성명")
    assert f["page"] is None and f["boxes"] == [] and f["confidence"] is None
    assert f"nolocation:{f['id']}" in ids(view["items"])
    assert_view(view)


def test_prefixed_value_list_is_json_text_and_unknown_key_is_kept() -> None:
    response = load("F")
    set_value(response, "자동이체신청서", "중_새_칸", ["가", "나"])
    set_value(response, "자동이체신청서", "상_", "값")
    view = view_of(response)
    f = finding(view, "0:중_새_칸")
    assert f["value"] == '["가", "나"]' and f["label"] == "새_칸" and f["risk"] == "medium"
    assert (f["category"], f["subject"], f["mapping_status"]) == ("기타 개인정보", "기타", "unknown")
    assert finding(view, "0:상_")["label"] == UNNAMED_LABEL
    assert_view(view)


def test_prefixed_key_with_object_rows() -> None:
    response = load("F")
    set_value(response, "자동이체신청서", "중_표", [{"중_칸": "값"}])  # 접두어 칸이 있는 행 → 표
    set_value(response, "자동이체신청서", "중_목록", [{"칸": "값"}])  # 접두어 칸이 없으면 값 목록 → JSON 글자(버리지 않는다)
    view = view_of(response)
    assert finding(view, "0:중_표[0].중_칸")["value"] == "값"
    assert finding(view, "0:중_목록")["value"] == '[{"칸": "값"}]'
    assert_view(view)


def test_table_without_prefixed_cells_gives_no_items() -> None:
    response = load("F")
    set_value(response, "자동이체신청서", "새표", [{"구분": "값"}, "글"])
    set_value(response, "자동이체신청서", "요청사유", ["사유"])
    assert not [f for f in view_of(response)["findings"] if f["field"].startswith(("새표", "요청사유"))]


def test_id_collision_inside_a_document_gets_a_suffix() -> None:
    response = load("F")
    set_value(response, "자동이체신청서", "중_표", [{"중_칸": "첫값"}])
    set_value(response, "자동이체신청서", "중_표[0].중_칸", "둘째값")
    view = view_of(response)
    assert finding(view, "0:중_표[0].중_칸")["value"] == "첫값"
    second = finding(view, "0:중_표[0].중_칸#2")
    assert second["value"] == "둘째값" and second["field"] == "중_표[0].중_칸#2"
    assert_view(view)


def test_literal_row_key_without_a_prefix_makes_no_collision() -> None:
    response = load("B")
    set_value(response, "외국인_세대구성원_확인서", "세대구성원[0].중_성명", "글자 그대로")
    view = view_of(response)
    assert len([f for f in view["findings"] if f["field"].startswith("세대구성원[0].중_성명")]) == 1
    assert_view(view)


def test_same_form_twice_keeps_ids_apart() -> None:
    view = view_of("T")
    assert finding(view, "0:중_신청인_성명")["document_index"] == 0
    assert finding(view, "1:중_신청인_성명")["document_index"] == 1


def test_big_numbers_and_surrogates_in_values() -> None:
    # 아주 큰 수는 JSON 글자로 만들 수 없어 단계에 그대로 넣는다(바깥 모양 시험)
    stages = stages_of("F")
    data = next(s for s in stages if s["step_type"] == "information-extract")["data"]
    data["중_큰수"] = 10**400
    data["중_아주_큰수"] = 10**5000
    data["중_서로게이트"] = "값\ud800"
    data["중_표"] = [{"중_칸": 10**5000}, {"중_칸": "값\ud800"}]
    view = build_view({"stages": stages})
    assert finding(view, "0:중_큰수")["value"] == str(10**400)
    assert finding(view, "0:중_아주_큰수")["value"] == UNREADABLE_VALUE
    assert finding(view, "0:중_서로게이트")["value"] == "값\ud800"
    assert finding(view, "0:중_표[0].중_칸")["value"] == UNREADABLE_VALUE
    assert finding(view, "0:중_표[1].중_칸")["value"] == "값\ud800"
    assert_view(view)


@pytest.mark.parametrize("page", [10**400, -1, 0, "1", None, True, 100_001])
def test_wrong_page_means_no_location(page: Any) -> None:
    stages = stages_of("F")
    extract = next(s for s in stages if s["step_type"] == "information-extract")
    extract["additional_values"]["상_출금계좌번호"]["page"] = page
    view = build_view({"stages": stages})
    f = finding(view, "0:상_출금계좌번호")
    assert f["page"] is None and f["boxes"] == []


# --- 차이 경고 -------------------------------------------------------------------------------


def _gap_logs(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if "판정 목록" in r.getMessage()]


@pytest.mark.parametrize("case", CASES)
def test_no_gap_warning_on_real_shapes(case: str, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="imask"):
        view_of(case)
    assert _gap_logs(caplog) == []


def test_gap_warning_has_counts_only_and_screen_follows_extract(caplog: pytest.LogCaptureFixture) -> None:
    response = load("A")
    secret_token = "자동이체신청서.비밀_토큰_글자"

    def change(body: dict[str, Any]) -> None:
        body["high_risk_items"] = [*body["high_risk_items"][1:], secret_token]  # 하나 빠지고 하나 더함 → 차이 2
        body["low_risk_items"] = []

    reference = view_of("A")
    low = len(ANSWERS["A"]["low_risk_items"])
    edit(response, "판정_상", change)
    with caplog.at_level(logging.WARNING, logger="imask"):
        view = view_of(response)
    assert _gap_logs(caplog) == [f"판정 목록과 추출 칸이 다릅니다: 상 2개 · 중 0개 · 하 {low}개"]
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert secret_token not in logged
    assert view["findings"] == reference["findings"]  # 화면은 Extract
    assert secret_token in view["decision"]["high_risk_items"] and view["decision"]["low_risk_items"] == []  # 판정 목록은 보존


def test_unreadable_list_is_not_compared(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="imask"):
        view_of(_verdict_with(high_risk_items=None))
    assert _gap_logs(caplog) == []


# --- 검증 사슬 -------------------------------------------------------------------------------


def test_green_chain_has_no_rows() -> None:
    bundle = view_of("A")["bundle_check"]
    assert bundle == {"verdict": "green", "checks": []}
    assert read_chain(load("A")) == bundle


def test_high_check_red_is_not_a_failure() -> None:
    # E: 상_확인 red → 판정_중. 실패 항목 없음, verdict green
    response = load("E")
    assert json.loads(step(response, "상_확인")["content"][0]["additional_values"])["verdict"] == "red"
    view = view_of(response)
    assert view["bundle_check"] == {"verdict": "green", "checks": []}
    assert view["overall"]["level"] == "중"
    assert view["items"] == []


@pytest.mark.parametrize(
    ("case", "rows"),
    [
        ("K", [("소비자피해보상금_지급신청서_신청인_주민등록번호", "필수_확인", "상_신청인_주민등록번호", "신청인 주민등록번호")]),
        ("L", [("소비자피해보상금_지급신청서_신청일자", "형식_확인", "하_신청일자", "신청일자")]),
        ("M", [("외국인_세대구성원_확인서_외국인등록번호", "형식_확인", "상_외국인등록번호", "외국인등록번호")]),
        ("R", [("대상_서류_있음", "대상_확인", None, None)]),
        ("T", [("소비자피해보상금_지급신청서_한건", "단위_확인", None, None)]),
        ("N", [("내용_검토", "내용_검토", None, None)]),
        ("O", [("내용_검토", "내용_검토", None, None)]),
        ("Q", [("FATCA_납세의무_예이면_행마다_번호또는사유", "필수_확인", "해외납세의무_여부", None)]),
        (
            "P",
            [
                ("소비자피해보상금_지급신청서_못읽은칸_없음", "필수_확인", None, None),
                ("소비자피해보상금_지급신청서_신청인_성명", "필수_확인", "중_신청인_성명", "신청인 성명"),
            ],
        ),
        (
            "U",
            [
                ("서류간_본인성명_같음", "일치_확인", None, None),
                ("지급보증_신청인에_소비자피_본인포함", "일치_확인", None, None),
                ("지급보증_신청인에_외국인__본인포함", "일치_확인", None, None),
            ],
        ),
    ],
)
def test_failed_rules_only_in_chain_order(case: str, rows: list[tuple[str, str, str | None, str | None]]) -> None:
    bundle = view_of(case)["bundle_check"]
    assert bundle["verdict"] == "red"
    assert [(c["name"], c["group"], c["field"], c["label"]) for c in bundle["checks"]] == rows
    for check in bundle["checks"]:
        assert list(check) == ["id", "name", "severity", "status", "field", "label", "group"]
        assert check["status"] == "fail" and check["severity"] == "error" and check["id"] == check["name"]


def test_bundle_check_has_no_values() -> None:
    for case in ("K", "L", "M", "P", "Q", "S", "U"):
        response = load(case)
        text = json.dumps(view_of(response)["bundle_check"], ensure_ascii=False)
        values: list[str] = []
        for item in response["output"]:
            if item["step_type"] == "information-extract":
                values += [v for v in json.loads(item["content"][0]["text"]).values() if isinstance(v, str) and len(v) >= 3]
        assert not [v for v in values if v in text]
        assert "규칙 설명" not in text  # reason 글자


def _set_verdict(response: dict[str, Any], node: str, verdict: Any, *, text: Any = "same") -> None:
    def change(add: dict[str, Any]) -> None:
        add["verdict"] = verdict

    edit(response, node, change, "additional_values")
    if text != "same":
        step(response, node)["content"][0]["text"] = json.dumps(text)


@pytest.mark.parametrize(
    ("changes", "want"),
    [
        ({"필수_확인": "yellow"}, "yellow"),
        ({"필수_확인": "yellow", "일치_확인": "red"}, "red"),
        ({"형식_확인": " RED "}, "red"),
        ({"상_확인": "red"}, "green"),
        ({"대상_확인": 5, "단위_확인": 5, "필수_확인": 5, "형식_확인": 5, "일치_확인": 5}, "green"),  # 본문이 green
    ],
)
def test_chain_verdict(changes: dict[str, Any], want: str) -> None:
    response = load("A")
    for node, verdict in changes.items():
        _set_verdict(response, node, verdict)
    assert read_chain(response)["verdict"] == want


def test_chain_verdict_all_unreadable_is_null_and_partial_green_is_green() -> None:
    response = load("A")
    nodes = ("대상_확인", "단위_확인", "필수_확인", "형식_확인", "일치_확인")
    for node in nodes:
        _set_verdict(response, node, 5, text=7)
    assert read_chain(response) == {"verdict": None, "checks": []}
    _set_verdict(response, "대상_확인", "green")
    assert read_chain(response)["verdict"] == "green"


def test_failed_chain_step_is_not_read() -> None:
    response = load("A")
    _set_verdict(response, "일치_확인", "red")
    step(response, "일치_확인")["status"] = "failed"
    assert read_chain(response)["verdict"] == "green"


def test_no_chain_step_gives_null_verdict() -> None:
    response = load("A")
    response["output"] = [i for i in response["output"] if i["step_type"] != "validate" and "내용_검토" not in i["model"]]
    assert view_of(response)["bundle_check"] == {"verdict": None, "checks": []}


@pytest.mark.parametrize(("enum", "red"), [("내용 모순", True), ("조건부 누락", True), ("문제 없음", False), ("", False), (5, False), (None, False)])
def test_content_review_enum(enum: Any, red: bool) -> None:
    response = load("A")

    def change(add: dict[str, Any]) -> None:
        add["enum"] = enum

    edit(response, "내용_검토", change, "additional_values")
    bundle = read_chain(response)
    assert (bundle["verdict"] == "red") is red
    want = [{"id": "내용_검토", "name": "내용_검토", "severity": "error", "status": "fail", "field": None, "label": None, "group": "내용_검토"}]
    assert bundle["checks"] == (want if red else [])


def test_content_review_body_is_not_read() -> None:
    response = load("N")
    step(response, "내용_검토")["content"][0]["text"] = json.dumps("본문에 든 원문 값")
    assert "본문에 든 원문 값" not in json.dumps(view_of(response), ensure_ascii=False)


def _rule(name: Any, passed: Any = False, *, conditions: Any = None, severity: Any = "error") -> dict[str, Any]:
    return {"name": name, "severity": severity, "passed": passed, "reason": "규칙 설명 원문 값", "conditions": conditions}


def _with_rules(node: str, rules: list[Any], case: str = "A") -> dict[str, Any]:
    response = load(case)

    def change(add: dict[str, Any]) -> None:
        add["checks"] = rules
        add["verdict"] = "red"

    edit(response, node, change, "additional_values")
    return response


def _leaf(**left: Any) -> dict[str, Any]:
    return {"kind": "condition", "passed": False, "left": left, "operator": "filled", "right": None}


def test_unknown_status_when_passed_is_not_bool() -> None:
    response = _with_rules("필수_확인", [_rule("규칙_가", None), _rule("규칙_나", "false"), _rule("규칙_다", True), _rule("규칙_라", False)])
    bundle = read_chain(response)
    assert [(c["name"], c["status"]) for c in bundle["checks"]] == [("규칙_가", "unknown"), ("규칙_나", "unknown"), ("규칙_라", "fail")]
    assert ids(view_of(response)["items"]).count("missing:0:규칙_라") == 1
    assert "missing:0:규칙_가" not in ids(view_of(response)["items"])


def test_same_rule_name_gets_a_suffix_across_nodes() -> None:
    response = _with_rules("필수_확인", [_rule("규칙_가"), _rule("규칙_가")])

    def change(add: dict[str, Any]) -> None:
        add["checks"] = [_rule("규칙_가")]

    edit(response, "형식_확인", change, "additional_values")
    assert [c["id"] for c in read_chain(response)["checks"]] == ["규칙_가", "규칙_가#2", "규칙_가#3"]
    assert_view(view_of(response))


def test_rule_named_content_review_does_not_collide() -> None:
    response = _with_rules("일치_확인", [_rule("내용_검토")])

    def change(add: dict[str, Any]) -> None:
        add["enum"] = "내용 모순"

    edit(response, "내용_검토", change, "additional_values")
    assert [c["id"] for c in read_chain(response)["checks"]] == ["내용_검토", "내용_검토#2"]


@pytest.mark.parametrize("name", [None, 5, "", "   ", "가" * 201, "이름\ud800", ["a"]], ids=str)
def test_rule_without_a_usable_name_is_dropped(name: Any) -> None:
    response = _with_rules("필수_확인", [_rule(name), "글", None, 5])
    bundle = read_chain(response)
    assert bundle == {"verdict": "red", "checks": []}
    assert not has_unpaired_surrogates(view_of(response)["bundle_check"])


def test_rules_over_the_limit_are_dropped_but_verdict_stays() -> None:
    assert len(read_chain(_with_rules("필수_확인", [_rule(f"규칙{n}") for n in range(MAX_CHECKS)]))["checks"]) == MAX_CHECKS
    response = _with_rules("필수_확인", [_rule(f"규칙{n}") for n in range(MAX_CHECKS + 1)])
    bundle = read_chain(response)
    assert bundle == {"verdict": "red", "checks": []}
    assert_view(view_of(response))


@pytest.mark.parametrize("checks", ["글", 5, None, {"a": 1}])
def test_checks_of_wrong_shape(checks: Any) -> None:
    response = _with_rules("필수_확인", [])

    def change(add: dict[str, Any]) -> None:
        add["checks"] = checks

    edit(response, "필수_확인", change, "additional_values")
    assert read_chain(response) == {"verdict": "red", "checks": []}


def test_first_field_of_the_tree_row_field_wins() -> None:
    tree = {
        "kind": "group",
        "logic": "or",
        "conditions": [
            _leaf(path="contains(classify.categories, 'X')", value=False),
            _leaf(nodeType="extract", nodeName="외국인_세대구성원_확인서", field="세대구성원", rowField="상_외국인등록번호", value=["값"]),
            _leaf(nodeType="extract", nodeName="자동이체신청서", field="상_출금계좌번호", value="값"),
        ],
    }
    check = read_chain(_with_rules("형식_확인", [_rule("규칙_가", conditions=tree)]))["checks"][0]
    assert (check["field"], check["label"]) == ("상_외국인등록번호", "외국인등록번호")
    check = read_chain(_with_rules("형식_확인", [_rule("규칙_가", conditions=_leaf(field="없는_칸"))]))["checks"][0]
    assert (check["field"], check["label"]) == ("없는_칸", None)


def _right_only(**right: Any) -> dict[str, Any]:
    return {"kind": "condition", "passed": False, "left": {"path": "classify.categories[0]", "value": "왼쪽 원문 값"}, "operator": "eq", "right": {"value": "오른쪽 원문 값", **right}}


def test_right_operand_maps_the_document_and_the_field() -> None:
    # 왼쪽은 서식 코드 없는 path, 오른쪽에만 추출 칸 — 서류 0 체크카드 · 1 IRP 신규
    tree = _right_only(nodeType="extract", nodeName="IRP_신규신청서", field="중_가입자명")
    response = _with_rules("형식_확인", [_rule("규칙_가", conditions=tree)], "C")
    view = view_of(response)
    item = item_of(view, "format:1:규칙_가")
    assert item["document_index"] == 1 and item["title"] == "가입자명 형식이 맞지 않습니다"
    target = finding(view, "1:중_가입자명")
    assert item["evidence"][0]["finding_ids"] == [target["id"]] and item["page"] == target["page"]
    check = view["bundle_check"]["checks"][0]
    assert (check["field"], check["label"]) == ("중_가입자명", "가입자명")
    # 양쪽 value 는 어디에도 나오지 않는다
    assert "원문 값" not in json.dumps({k: view[k] for k in ("items", "bundle_check", "links")}, ensure_ascii=False)
    assert_view(view)


def test_right_operand_row_field() -> None:
    tree = _right_only(nodeName="외국인_세대구성원_확인서", field="세대구성원", rowField="상_외국인등록번호")
    response = _with_rules("형식_확인", [_rule("규칙_가", conditions=tree)], "B")
    view = view_of(response)
    assert item_of(view, "format:0:규칙_가")["title"] == "외국인등록번호 형식이 맞지 않습니다"
    assert view["bundle_check"]["checks"][0]["field"] == "상_외국인등록번호"


def test_right_operand_path_finds_the_form() -> None:
    tree = _right_only(path='contains(extract."지급보증거래_신청서"."중_신청인_성명".value, x)')
    response = _with_rules("필수_확인", [_rule("규칙_가", conditions=tree)], "B")
    assert item_of(view_of(response), "missing:1:규칙_가")["document_index"] == 1


def test_left_operand_still_comes_first() -> None:
    # 첫 칸은 왼쪽, 서식 코드는 nodeName(어느 쪽이든) → path → 규칙 이름
    both = {
        "kind": "condition",
        "passed": False,
        "left": {"nodeName": "소비자피해보상금_지급신청서", "field": "중_서명란_성명", "value": "값"},
        "operator": "eq",
        "right": {"nodeName": "지급보증거래_신청서", "field": "중_신청인_성명", "value": "값"},
    }
    rule = read_chain(_with_rules("일치_확인", [_rule("규칙_가", conditions=both)], "B"))["checks"][0]
    assert rule["field"] == "중_서명란_성명"
    assert item_of(view_of(_with_rules("일치_확인", [_rule("규칙_가", conditions=both)], "B")), "mismatch:2:규칙_가")["title"] == "서명란 성명 값이 맞지 않습니다"
    # 왼쪽 path 의 코드보다 오른쪽 nodeName 이 앞선다
    mixed = {
        "kind": "condition",
        "passed": False,
        "left": {"path": 'extract."지급보증거래_신청서"."x".value'},
        "operator": "eq",
        "right": {"nodeName": "소비자피해보상금_지급신청서", "field": "중_신청인_성명"},
    }
    assert item_of(view_of(_with_rules("필수_확인", [_rule("규칙_가", conditions=mixed)], "B")), "missing:2:규칙_가")
    # 규칙 이름은 트리에 코드가 없을 때만 쓴다 — 오른쪽 코드가 앞선다
    named = _right_only(nodeName="소비자피해보상금_지급신청서", field="중_신청인_성명")
    assert item_of(view_of(_with_rules("필수_확인", [_rule("지급보증거래_신청서_규칙", conditions=named)], "B")), "missing:2:지급보증거래_신청서_규칙")


def test_mapped_cell_can_come_from_the_right_operand() -> None:
    tree = {"kind": "condition", "passed": False, "left": {"field": "모르는_칸", "value": "값"}, "operator": "eq", "right": {"field": "상_출금계좌번호", "value": "값"}}
    response = _with_rules("필수_확인", [_rule("규칙_가", conditions=tree)], "F")
    check = read_chain(response)["checks"][0]
    assert (check["field"], check["label"]) == ("모르는_칸", None)  # 첫 칸은 왼쪽 그대로
    assert item_of(view_of(response), "missing:0:규칙_가")["title"] == "출금계좌번호가 없습니다"


@pytest.mark.parametrize("right", ["글", 5, None, [], ["a"], {"const": "상수"}, {"value": "값"}, {"field": 5, "rowField": ["a"], "nodeName": ["a"], "path": 5}], ids=str)
def test_right_operand_of_other_shapes(right: Any) -> None:
    tree = {"kind": "condition", "passed": False, "left": {"path": "x"}, "operator": "eq", "right": right}
    check = read_chain(_with_rules("필수_확인", [_rule("규칙_가", conditions=tree)]))["checks"][0]
    assert (check["field"], check["label"]) == (None, None)


def test_right_operands_respect_the_node_limit() -> None:
    # 개수 한도 밖의 조건은 오른쪽도 보지 않는다(한도는 왼쪽만 볼 때와 같다)
    far = _right_only(nodeName="자동이체신청서", field="상_출금계좌번호")
    wide = {"kind": "group", "conditions": [_leaf(path="x") for _ in range(MAX_TREE_NODES)] + [far]}
    check = read_chain(_with_rules("필수_확인", [_rule("규칙_가", conditions=wide)]))["checks"][0]
    assert check["field"] is None


def _deep_tree(depth: int) -> dict[str, Any]:
    node: dict[str, Any] = _leaf(nodeName="자동이체신청서", field="상_출금계좌번호", value="값")
    for _ in range(depth):
        node = {"kind": "group", "logic": "or", "conditions": [node]}
    return node


def test_very_deep_tree_raises_nothing_and_is_fast() -> None:
    # JSON 문자열로는 만들 수 없는 깊이 — 단계에 그대로 넣는다(바깥 모양 시험)
    stages = stages_of("A")
    chain = next(s for s in stages if s["name"] == "Validate - 필수_확인")
    chain["additional_values"]["checks"] = [_rule("규칙_가", conditions=_deep_tree(100_000))]
    chain["additional_values"]["verdict"] = "red"
    started = time.perf_counter()
    bundle = read_chain(stages)
    assert time.perf_counter() - started < TIME_LIMIT
    # 깊이 한도 밖의 칸은 보지 않는다 — 항목은 남고 예외가 없다
    assert [(c["name"], c["field"]) for c in bundle["checks"]] == [("규칙_가", None)]
    view = build_view({"stages": stages})
    assert "missing:0:규칙_가" in ids(view["items"])
    # 깊이 한도 안이면 찾는다
    chain["additional_values"]["checks"] = [_rule("규칙_가", conditions=_deep_tree(MAX_TREE_DEPTH))]
    assert read_chain(stages)["checks"][0]["field"] == "상_출금계좌번호"


def test_huge_and_odd_trees_are_fast() -> None:
    wide = {"kind": "group", "conditions": [_leaf(path="x") for _ in range(200_000)]}
    odd = {"kind": "group", "conditions": ["글", None, 5, {"conditions": "글"}, {"left": "글"}, {"left": {"field": 5, "rowField": ["a"], "nodeName": ["a"]}}]}
    stages = stages_of("A")
    chain = next(s for s in stages if s["name"] == "Validate - 필수_확인")
    chain["additional_values"]["checks"] = [_rule(f"규칙{n}", conditions=wide) for n in range(MAX_CHECKS - 1)] + [_rule("이상", conditions=odd)]
    started = time.perf_counter()
    bundle = read_chain(stages)
    assert time.perf_counter() - started < TIME_LIMIT
    assert len(bundle["checks"]) == MAX_CHECKS


@pytest.mark.parametrize("tree", ["글", 5, None, [], {"kind": "group"}, {"kind": "group", "conditions": 5}, {"left": None}], ids=str)
def test_wrong_tree_shapes(tree: Any) -> None:
    check = read_chain(_with_rules("필수_확인", [_rule("규칙_가", conditions=tree)]))["checks"][0]
    assert (check["field"], check["label"]) == (None, None)


# --- 검토사항: 표의 재료 -----------------------------------------------------------------------


def test_missing_item_matches_the_old_shape() -> None:
    view = view_of("K")
    item = view["items"][0]
    assert item == {
        "id": "missing:0:소비자피해보상금_지급신청서_신청인_주민등록번호",
        "number": "R-01",
        "type": "missing",
        "document_index": 0,
        "page": 1,
        "finding_id": None,
        "title": "신청인 주민등록번호가 없습니다",
        "desc": MISSING_DESC,
        "next": MISSING_NEXT,
        "evidence": [{"label": "1쪽 열기", "page": 1, "finding_ids": [], "finding_id": None}],
        "link_id": None,
    }


def test_format_item_points_at_the_field() -> None:
    view = view_of("L")
    item = item_of(view, "format:0:소비자피해보상금_지급신청서_신청일자")
    assert item["type"] == "format" and item["title"] == "신청일자 형식이 맞지 않습니다"
    assert item["desc"] == FORMAT_DESC and item["next"] == MISSING_NEXT and item["link_id"] is None
    target = finding(view, "0:하_신청일자")
    assert item["evidence"] == [{"label": "1쪽 값 보기", "page": target["page"], "finding_ids": [target["id"]], "finding_id": None}]
    assert item["page"] == target["page"]


def test_format_item_on_table_cell_collects_the_rows_of_that_page() -> None:
    view = view_of("M")
    item = item_of(view, "format:0:외국인_세대구성원_확인서_외국인등록번호")
    assert item["title"] == "외국인등록번호 형식이 맞지 않습니다"
    cells = [f["id"] for f in view["findings"] if f["field"].endswith(".상_외국인등록번호")]
    assert cells and item["evidence"][0]["finding_ids"] == cells and item["evidence"][0]["label"].endswith("쪽 값 보기")


def test_format_item_without_a_finding_opens_the_first_page() -> None:
    response = load("L")
    set_value(response, "소비자피해보상금_지급신청서", "하_신청일자", "")
    item = item_of(view_of(response), "format:0:소비자피해보상금_지급신청서_신청일자")
    assert item["evidence"] == [{"label": "1쪽 열기", "page": 1, "finding_ids": [], "finding_id": None}]


def test_format_item_page_is_inside_a_multi_page_document() -> None:
    response = load("U")  # 지급보증 1~5쪽

    def rule_on(add: dict[str, Any]) -> None:
        add["checks"] = [_rule("지급보증거래_신청서_출금_계좌번호", conditions=_leaf(nodeName="지급보증거래_신청서", field="상_출금_계좌번호", value="값"))]
        add["verdict"] = "red"

    edit(response, "형식_확인", rule_on, "additional_values")

    def on_page(add: dict[str, Any]) -> None:
        add["상_출금_계좌번호"]["page"] = 3

    edit(response, "Information Extract - 지급보증거래_신청서", on_page, "additional_values")
    view = view_of(response)
    item = item_of(view, "format:0:지급보증거래_신청서_출금_계좌번호")
    assert item["page"] == 3 and item["evidence"][0]["label"] == "3쪽 값 보기" and item["document_index"] == 0


def test_rule_mismatch_item() -> None:
    tree = {
        "kind": "group",
        "logic": "or",
        "conditions": [_leaf(path="contains(classify.categories, 'x')"), _leaf(nodeName="소비자피해보상금_지급신청서", field="중_서명란_성명", value="값")],
    }
    response = _with_rules("일치_확인", [_rule("소비자_서명란_신청인", conditions=tree)], "G")
    view = view_of(response)
    item = item_of(view, "mismatch:0:소비자_서명란_신청인")
    assert item["type"] == "mismatch" and item["link_id"] is None
    assert item["title"] == "서명란 성명 값이 맞지 않습니다" and item["desc"] == RULE_MISMATCH_DESC and item["next"] == MISSING_NEXT
    assert item["evidence"][0]["finding_ids"] == ["0:중_서명란_성명"]
    assert view["links"] == []
    assert_view(view)


def test_duplicate_item_and_no_links() -> None:
    view = view_of("T")
    item = item_of(view, "duplicate:소비자피해보상금_지급신청서")
    assert item["type"] == "duplicate" and item["document_index"] == 0
    assert item["title"] == "소비자피해보상금 지급신청서 여러 건" and item["desc"] == DUPLICATE_DESC and item["next"] == MISSING_NEXT
    assert item["evidence"] == [{"label": "1쪽 열기", "page": 1, "finding_ids": [], "finding_id": None}]
    assert view["links"] == []
    assert read_v2_links(load("T"))["pairs"] == []
    assert "review:duplicate" not in ids(view["items"])


def test_duplicate_rule_points_at_the_first_document_of_that_form() -> None:
    response = _with_rules("단위_확인", [_rule("IRP_신규신청서_한건", conditions=_leaf(path="length(classify.categories[?@ == 'IRP_신규신청서'])"))], "C")
    item = item_of(view_of(response), "duplicate:IRP_신규신청서")
    assert item["document_index"] == 1 and item["title"] == "IRP 신규신청서 여러 건"


def test_unit_rule_of_another_form_uses_review_fallback() -> None:
    response = _with_rules("단위_확인", [_rule("모르는서식_한건")], "F")

    def change(body: dict[str, Any]) -> None:
        body["review_reasons"] = ["같은 서식 여러 건"]
        body["risk_level"] = "검토 필요"

    edit(response, "판정_상", change)
    assert [i for i in ids(view_of(response)["items"]) if i.startswith(("duplicate:", "review:"))] == ["review:duplicate"]


def test_unreadable_item_by_key() -> None:
    view = view_of("P")
    item = item_of(view, "unreadable:0:중_신청인_성명")
    assert item["type"] == "unreadable" and item["title"] == "신청인 성명이 판독되지 않았습니다"
    assert item["desc"] == UNREADABLE_DESC and item["next"] == MISSING_NEXT and item["page"] == 1
    assert item["evidence"] == [{"label": "1쪽 열기", "page": 1, "finding_ids": [], "finding_id": None}]
    assert "unreadable:0" not in ids(view["items"])  # 칸별 항목이 있으면 못읽은칸 규칙은 따로 만들지 않는다
    assert "missing:0:소비자피해보상금_지급신청서_못읽은칸_없음" not in ids(view["items"])
    assert "missing:0:소비자피해보상금_지급신청서_신청인_성명" in ids(view["items"])


def _with_incomplete(listed: Any, case: str = "F", form: str = "자동이체신청서") -> dict[str, Any]:
    response = load(case)
    set_value(response, form, "incomplete_fields", listed)
    return response


@pytest.mark.parametrize("entry", ["상_출금계좌번호", "출금계좌번호", "중_출금계좌번호"])
def test_unreadable_key_ignores_the_prefix_and_runs_without_the_chain(entry: str) -> None:
    # F 는 사슬이 모두 green 이어도 항목이 생긴다. id 의 키는 서류의 실제 키
    view = view_of(_with_incomplete([entry]))
    assert "unreadable:0:상_출금계좌번호" in ids(view["items"])
    assert item_of(view, "unreadable:0:상_출금계좌번호")["title"] == "출금계좌번호가 판독되지 않았습니다"
    assert_view(view)


def test_unreadable_table_cell_uses_the_cell_name() -> None:
    response = load("B")
    set_value(response, "외국인_세대구성원_확인서", "incomplete_fields", ["상_외국인등록번호"])
    item = item_of(view_of(response), "unreadable:0:상_외국인등록번호")
    assert item["title"] == "외국인등록번호가 판독되지 않았습니다"


@pytest.mark.parametrize(
    "listed",
    [
        ["원문 값이 든 글자"],
        ["상_출금계좌번호", "원문 값이 든 글자"],
        [5],
        [None],
        "원문 값이 든 글자",
        "   ",  # JMESPath 에서 공백만인 문자열은 참이다
        {"a": 1},
        7,
        0,  # JMESPath 에서 숫자 영은 참이다 — 빈 목록이 아니라 못 읽는 목록
        0.0,
        True,
        ["incomplete_fields"],
    ],
    ids=str,
)
def test_unreadable_without_a_key_has_no_raw_text(listed: Any) -> None:
    view = view_of(_with_incomplete(listed))
    item = item_of(view, "unreadable:0")
    assert item["title"] == "판독되지 않은 칸이 있습니다" and item["desc"] == UNREADABLE_DESC
    assert "원문 값이 든 글자" not in json.dumps(view["items"], ensure_ascii=False)
    assert_view(view)


@pytest.mark.parametrize("listed", [[], None, "", {}, False])
def test_empty_incomplete_list_makes_nothing(listed: Any) -> None:
    assert not [i for i in view_of(_with_incomplete(listed))["items"] if i["type"] == "unreadable"]


def test_missing_incomplete_key_makes_nothing() -> None:
    response = load("F")

    def change(data: dict[str, Any]) -> None:
        data.pop("incomplete_fields", None)

    edit(response, "Information Extract - 자동이체신청서", change)
    assert not [i for i in view_of(response)["items"] if i["type"] == "unreadable"]


def test_zero_incomplete_value_without_any_chain_step() -> None:
    # 사슬을 아직 읽을 수 없는 응답 — 뒤의 필수_확인 실패로 보충할 기회가 없어도 항목이 있어야 한다
    response = _with_incomplete(0)
    response["output"] = [item for item in response["output"] if item["step_type"] != "validate"]
    view = view_of(response)
    assert "unreadable:0" in ids(view["items"])
    assert_view(view)


@pytest.mark.parametrize(
    "listed",
    [
        [{"중_성명": "표로 새면 안 되는 값"}],
        [{"중_성명": "표로 새면 안 되는 값"}, "글", None],
        [{"상_칸": "표로 새면 안 되는 값", "칸": "표로 새면 안 되는 값"}, {"중_성명": "표로 새면 안 되는 값"}],
    ],
    ids=["한 행", "섞임", "여러 칸"],
)
def test_incomplete_fields_with_object_rows_is_not_a_table(listed: Any, caplog: pytest.LogCaptureFixture) -> None:
    reference = view_of("F")
    response = _with_incomplete(listed)
    with caplog.at_level(logging.WARNING, logger="imask"):
        view = view_of(response)
    # 탐지 항목·nolocation·위험 토큰이 생기지 않고 일반 판독 불가 재료로만 쓰인다
    assert view["findings"] == reference["findings"]
    assert not [i for i in view["items"] if i["type"] == "nolocation"]
    assert item_of(view, "unreadable:0")["title"] == "판독되지 않은 칸이 있습니다"
    assert "표로 새면 안 되는 값" not in json.dumps({k: view[k] for k in ("findings", "items", "links", "bundle_check")}, ensure_ascii=False)
    assert "판정 목록" not in "\n".join(r.getMessage() for r in caplog.records)
    assert_view(view)


def test_incomplete_fields_is_never_an_item_key_or_a_table() -> None:
    assert not v2_is_item_key("incomplete_fields")
    data = {"incomplete_fields": [{"중_성명": "값"}], "세대구성원": [{"중_성명": "값"}], "중_칸": "값"}
    assert [key for key, _ in v2_item_fields(data)] == ["세대구성원", "중_칸"]


def test_unreadable_rule_failing_without_field_items() -> None:
    tree = _leaf(path='length(extract."소비자피해보상금_지급신청서"."incomplete_fields".value || `[]`)', value=2)
    response = _with_rules("필수_확인", [_rule("소비자피해보상금_지급신청서_못읽은칸_없음", conditions=tree)], "B")
    view = view_of(response)
    assert "unreadable:2" in ids(view["items"])  # 그 서식의 서류(index 2)
    assert item_of(view, "unreadable:2")["document_index"] == 2
    assert "missing:2:소비자피해보상금_지급신청서_못읽은칸_없음" not in ids(view["items"])


def test_duplicate_incomplete_entries_make_one_item() -> None:
    view = view_of(_with_incomplete(["상_출금계좌번호", "출금계좌번호", "상_출금계좌번호"]))
    assert ids(view["items"]).count("unreadable:0:상_출금계좌번호") == 1


@pytest.mark.parametrize(
    ("rule", "tree", "index"),
    [
        ("규칙_가", _leaf(nodeName="소비자피해보상금_지급신청서", field="중_신청인_성명"), 2),  # nodeName
        ("규칙_나", _leaf(path='extract."지급보증거래_신청서"."중_신청인_성명".value'), 1),  # path
        ("지급보증거래_신청서_규칙", None, 1),  # 규칙 이름 앞부분
        ("규칙_다", _leaf(nodeName="자동이체신청서", field="상_출금계좌번호"), 0),  # 묶음에 없는 서식 → 첫 보이는 서류
        ("규칙_라", None, 0),  # 못 찾음 → 첫 보이는 서류
    ],
)
def test_rule_to_document(rule: str, tree: Any, index: int) -> None:
    response = _with_rules("필수_확인", [_rule(rule, conditions=tree)], "B")  # 서류 0 외국인 · 1 지급보증 · 2 소비자피해
    assert item_of(view_of(response), f"missing:{index}:{rule}")["document_index"] == index


def test_rule_order_node_name_before_path_before_rule_name() -> None:
    tree = {
        "kind": "group",
        "conditions": [_leaf(path='extract."지급보증거래_신청서"."x".value'), _leaf(nodeName="소비자피해보상금_지급신청서", field="중_신청인_성명")],
    }
    response = _with_rules("필수_확인", [_rule("외국인_세대구성원_확인서_규칙", conditions=tree)], "B")
    assert item_of(view_of(response), "missing:2:외국인_세대구성원_확인서_규칙")


@pytest.mark.parametrize(
    ("rule", "title"),
    [
        ("FATCA_납세의무_예이면_행마다_번호또는사유", "납세자번호 또는 미제출 사유가 없습니다"),
        ("휴면_대리신청이면_대리인", "대리인 성명이 없습니다"),
    ],
)
def test_rule_labels_in_required_items(rule: str, title: str) -> None:
    assert item_of(view_of(_with_rules("필수_확인", [_rule(rule)], "F")), f"missing:0:{rule}")["title"] == title


@pytest.mark.parametrize(
    ("rule", "title"),
    [
        ("FATCA_미국국적_납세의무", "해외납세의무 여부 값이 맞지 않습니다"),
        ("서류간_본인성명_같음", "본인 성명 값이 맞지 않습니다"),
        ("지급보증_신청인에_소비자피_본인포함", "신청인 성명 값이 맞지 않습니다"),
        ("지급보증_신청인에_외국인__본인포함", "신청인 성명 값이 맞지 않습니다"),
    ],
)
def test_rule_labels_in_consistency_items(rule: str, title: str) -> None:
    # 연결에 unmatched 쌍이 없을 때만 만든다(F 는 서류 하나)
    assert item_of(view_of(_with_rules("일치_확인", [_rule(rule)], "F")), f"mismatch:0:{rule}")["title"] == title


def test_label_falls_back_to_first_mapped_cell_then_rule_name() -> None:
    tree = {"kind": "group", "conditions": [_leaf(field="모르는_칸"), _leaf(field="상_출금계좌번호"), _leaf(field="중_예금주_성명")]}
    assert item_of(view_of(_with_rules("필수_확인", [_rule("규칙_가", conditions=tree)], "F")), "missing:0:규칙_가")["title"] == "출금계좌번호가 없습니다"
    assert item_of(view_of(_with_rules("필수_확인", [_rule("규칙_나", conditions=_leaf(field="모르는_칸"))], "F")), "missing:0:규칙_나")["title"] == "규칙_나가 없습니다"


def test_cross_document_rules_are_dropped_when_a_link_is_unmatched() -> None:
    view = view_of("U")
    assert ids(view["items"]) == ["mismatch:1:0", "lowconf:0", "mismatch:1:2"]
    assert all(i["link_id"] in {"link:1:0", "link:1:2"} for i in view["items"] if i["type"] == "mismatch")


def test_cross_document_rules_are_made_when_no_link_is_unmatched() -> None:
    rules = [_rule("서류간_본인성명_같음"), _rule("지급보증_신청인에_소비자피_본인포함")]
    response = _with_rules("일치_확인", rules, "B")
    assert all(state == "linked" for state in link_states(view_of(response)).values())
    view = view_of(response)
    # 트리에 서식 코드가 없으면 첫 보이는 서류, 코드가 있으면 그 서식의 서류
    assert {"mismatch:0:서류간_본인성명_같음", "mismatch:0:지급보증_신청인에_소비자피_본인포함"} <= set(ids(view["items"]))
    tree = _leaf(path='contains(extract."지급보증거래_신청서"."중_신청인_성명".value, x)')
    response = _with_rules("일치_확인", [_rule("지급보증_신청인에_소비자피_본인포함", conditions=tree)], "B")
    assert "mismatch:1:지급보증_신청인에_소비자피_본인포함" in ids(view_of(response)["items"])
    assert_view(view_of(response))


def test_other_consistency_rules_stay_when_a_link_is_unmatched() -> None:
    response = load("U")

    def change(add: dict[str, Any]) -> None:
        add["checks"] = [*add["checks"], _rule("소비자_서명란_신청인", conditions=_leaf(nodeName="소비자피해보상금_지급신청서", field="중_서명란_성명", value="값"))]

    edit(response, "일치_확인", change, "additional_values")
    view = view_of(response)
    assert "mismatch:2:소비자_서명란_신청인" in ids(view["items"])
    assert_view(view)


def test_target_check_failure_is_left_to_the_other_item() -> None:
    view = view_of("R")
    assert ids(view["items"]) == ["other:0"]
    assert view["items"][0]["desc"] == OTHER_DESC and view["items"][0]["next"] == OTHER_NEXT


def test_digit_only_consistency_rule_is_not_a_link_item() -> None:
    response = _with_rules("일치_확인", [_rule("12345")], "F")
    view = view_of(response)
    assert "mismatch:0:12345" not in ids(view["items"])
    assert_view(view)


# --- 검토사항: 사유 보충 ------------------------------------------------------------------------


def test_content_contradiction_gets_review_mismatch() -> None:
    for case in ("N", "O"):
        view = view_of(case)
        item = item_of(view, "review:mismatch")
        assert item["type"] == "mismatch" and item["link_id"] is None and item["title"] == "값 불일치"
        assert item["desc"] == RULE_MISMATCH_DESC and item["next"] == MISSING_NEXT and item["document_index"] == 0
        assert view["bundle_check"]["verdict"] == "red"
        assert [c["name"] for c in view["bundle_check"]["checks"]] == ["내용_검토"]
        assert_view(view)


def test_conditional_missing_gets_review_missing() -> None:
    response = load("N")
    item = step(response, "판정_불일치")
    item["model"] = "Instruct - 판정_누락"

    def body(value: dict[str, Any]) -> None:
        value["review_reasons"] = ["필수 항목 누락 또는 판독 불가"]

    edit(response, "판정_누락", body)

    def enum(add: dict[str, Any]) -> None:
        add["enum"] = "조건부 누락"

    edit(response, "내용_검토", enum, "additional_values")
    view = view_of(response)
    review = item_of(view, "review:missing")
    assert review["type"] == "missing" and review["title"] == "필수 항목 누락 또는 판독 불가"
    assert review["desc"] == MISSING_DESC and review["next"] == MISSING_NEXT


@pytest.mark.parametrize(
    ("reason", "item_id", "kind", "desc", "next_step"),
    [
        ("값 불일치", "review:mismatch", "mismatch", RULE_MISMATCH_DESC, MISSING_NEXT),
        ("필수 항목 누락 또는 판독 불가", "review:missing", "missing", MISSING_DESC, MISSING_NEXT),
        ("형식 오류", "review:format", "format", FORMAT_DESC, MISSING_NEXT),
        ("같은 서식 여러 건", "review:duplicate", "duplicate", DUPLICATE_DESC, MISSING_NEXT),
        ("대상 외 서류", "review:other", "other", OTHER_DESC, OTHER_NEXT),
    ],
)
def test_review_fallback_for_each_known_reason(reason: str, item_id: str, kind: str, desc: str, next_step: str) -> None:
    view = view_of(_verdict_with(review_reasons=[reason], risk_level="검토 필요"))
    item = item_of(view, item_id)
    assert (item["type"], item["title"], item["desc"], item["next"], item["link_id"]) == (kind, reason, desc, next_step, None)
    assert item["document_index"] == 0 and item["page"] == 1
    assert_view(view)


def test_same_reason_twice_makes_one_item_and_keeps_the_verdict_list() -> None:
    response = _verdict_with(review_reasons=["형식 오류", "형식 오류", "값 불일치", "형식 오류"], risk_level="검토 필요")
    view = view_of(response)
    all_ids = ids(view["items"])
    assert len(all_ids) == len(set(all_ids))
    assert all_ids.count("review:format") == 1 and all_ids.count("review:mismatch") == 1
    assert all_ids.index("review:format") < all_ids.index("review:mismatch")  # 처음 나온 순서
    # 판정 8키의 원래 목록은 그대로
    assert view["decision"]["review_reasons"] == ["형식 오류", "형식 오류", "값 불일치", "형식 오류"]
    assert_view(view)
    scope = review_scope({"status": "done"}, view)
    assert [target.writable for target in scope.items] == [True] * len(all_ids)


def test_unknown_reason_twice_makes_one_verdict_item() -> None:
    view = view_of(_verdict_with(review_reasons=["모르는 사유", "모르는 사유"], risk_level="검토 필요"))
    assert ids(view["items"]).count("verdict:0") == 1
    assert_view(view)


def test_known_reason_with_an_item_gets_no_fallback() -> None:
    for case, prefix in (("K", "missing"), ("P", "unreadable"), ("L", "format"), ("T", "duplicate"), ("R", "other"), ("U", "mismatch")):
        kinds = ids(view_of(case)["items"])
        assert not [i for i in kinds if i.startswith("review:")], (case, prefix)
        assert [i for i in kinds if i.startswith(prefix)], (case, prefix)


def test_unreadable_only_covers_the_missing_reason() -> None:
    response = _verdict_with(review_reasons=["필수 항목 누락 또는 판독 불가"], risk_level="검토 필요")
    set_value(response, "자동이체신청서", "incomplete_fields", ["상_출금계좌번호"])
    assert "review:missing" not in ids(view_of(response)["items"])


def test_unknown_reason_makes_a_verdict_item_without_its_text() -> None:
    view = view_of(_verdict_with(review_reasons=["원문 값이 든 사유"], risk_level="검토 필요"))
    item = item_of(view, "verdict:0")
    assert (item["title"], item["desc"], item["next"]) == (VERDICT_TITLE, VERDICT_DESC, VERDICT_NEXT)
    assert "원문 값이 든 사유" not in json.dumps(view["items"], ensure_ascii=False)
    assert "원문 값이 든 사유" in view["decision"]["review_reasons"]  # 판정 출력은 보존


def test_review_level_without_any_item_makes_a_verdict_item() -> None:
    for reasons in ([], None):
        response = load("E")

        def change(body: dict[str, Any], value: Any = reasons) -> None:
            body["risk_level"] = "검토 필요"
            body["review_reasons"] = value

        edit(response, "판정_중", change)
        assert ids(view_of(response)["items"]) == ["verdict:0"]


def test_review_items_go_after_the_first_documents_items() -> None:
    view = view_of(_verdict_with(review_reasons=["값 불일치"], risk_level="검토 필요"))
    order = [(i["document_index"], i["id"]) for i in view["items"]]
    position = order.index((0, "review:mismatch"))
    assert all(index == 0 for index, _ in order[: position + 1])
    assert all(index > 0 for index, _ in order[position + 1 :])
    assert [i["number"] for i in view["items"]] == [f"R-{n:02d}" for n in range(1, len(order) + 1)]


def test_no_visible_document_means_no_items() -> None:
    response = load("R")

    def no_pages(add: dict[str, Any]) -> None:
        add["page_ranges"] = []

    edit(response, "step_2_classify", no_pages, "additional_values")
    view = view_of(response)
    assert view["documents"][0]["page_start"] is None and view["decision"]["review_reasons"] == ["대상 외 서류"]
    assert view["items"] == []
    assert_view(view)


def test_build_items_without_review_keeps_the_old_order() -> None:
    documents = [{"index": 0, "type": "x", "page_start": 1, "page_end": 1, "kind": "extracted", "other_guide": None, "validation": "red"}]
    assert ids(build_items(documents, [], [None])) == ["verdict:0"]
    assert ids(build_items(documents, [], [None], None, None)) == ["verdict:0"]


def test_one_failing_review_step_does_not_empty_the_items(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    reference = view_of("U")

    def boom(*_: Any, **__: Any) -> Any:
        raise RuntimeError("원문 값")

    monkeypatch.setattr(items_module, "_review_items", boom)
    with caplog.at_level(logging.WARNING, logger="imask"):
        view = view_of("U")
    assert view["items"] == reference["items"]
    assert "원문 값" not in "\n".join(r.getMessage() for r in caplog.records)
    monkeypatch.setattr(items_module, "_rule_item", boom)
    response = _with_rules("필수_확인", [_rule("규칙_가")], "F")
    with caplog.at_level(logging.WARNING, logger="imask"):
        view = view_of(response)
    assert "missing:0:규칙_가" not in ids(view["items"])
    assert "원문 값" not in "\n".join(r.getMessage() for r in caplog.records)
    assert view["decision"] is not None and view["findings"]


@pytest.mark.parametrize("case", CASES)
def test_items_have_no_values(case: str) -> None:
    view = view_of(case)
    text = json.dumps(view["items"], ensure_ascii=False)
    masked_free = [f["value"] for f in view["findings"] if len(f["value"]) >= 3]
    assert [v for v in masked_free if v in text] == []
    assert "규칙 설명" not in text and "내용 검토 본문" not in text


# --- 연결 ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("case", "anchor", "states"),
    [
        ("A", 0, {1: "linked", 2: "linked", 3: "insufficient"}),  # FATCA·휴면예금 연결, 위임장 근거 부족
        ("B", 0, {1: "linked", 2: "linked"}),  # 지급보증·소비자피해 연결
        ("C", 0, {1: "linked"}),  # IRP 신규 연결
        ("U", 1, {0: "unmatched", 2: "unmatched"}),  # 지급보증·소비자피해 불일치(기준은 외국인 확인서)
    ],
)
def test_expected_links(case: str, anchor: int, states: dict[int, str]) -> None:
    response = load(case)
    links = read_v2_links(response)
    assert links["anchor_index"] == anchor and links["label"] == "본인 성명"
    assert {pair["target_index"]: pair["status"] for pair in links["pairs"]} == states
    assert all(pair["id"] == f"link:{anchor}:{pair['target_index']}" and pair["group"] is None for pair in links["pairs"])
    assert set(links) == {"field", "anchor_index", "pairs", "doc_fields", "label"}
    view = view_of(response)
    assert link_states(view) == {f"link:{anchor}:{target}": state for target, state in states.items()}


def test_link_rows_use_each_documents_field_and_fixed_label() -> None:
    view = view_of("B")
    row = next(link for link in view["links"] if link["id"] == "link:0:1")
    assert row["title"] == "외국인 세대구성원 확인서 · 지급보증거래 신청서"
    assert row["field"] == "중_본인_성명" and row["label"] == "본인 성명"
    assert row["basis"] == ["두 서류의 본인 성명이 같습니다."] and row["missing"] == ""
    assert row["docs"][0]["fields"].startswith("본인 성명 ") and row["docs"][0]["finding_ids"] == ["0:중_본인_성명"]
    assert row["docs"][1]["fields"].startswith("신청인 성명 ") and row["docs"][1]["finding_ids"] == ["1:중_신청인_성명"]
    target = finding(view, "1:중_신청인_성명")
    assert row["docs"][1]["fields"] == f"신청인 성명 {target['masked']}"[:80] and target["value"] not in row["docs"][1]["fields"]


def test_weak_link_row_of_the_attorney_form() -> None:
    view = view_of("A")
    row = next(link for link in view["links"] if link["id"] == "link:0:3")
    assert row["state"] == "insufficient" and row["missing"] == "비교할 본인 성명이 없습니다."
    assert row["docs"][1]["fields"] == "본인 성명 값 없음" and row["docs"][1]["finding_ids"] == []
    item = item_of(view, "weaklink:0:3")
    assert item["link_id"] == "link:0:3" and item["desc"] == "비교할 본인 성명이 없습니다."


def test_mismatch_item_of_a_link() -> None:
    view = view_of("U")
    item = item_of(view, "mismatch:1:2")
    assert item["title"] == "외국인 세대구성원 확인서와 본인 성명이 다릅니다"
    assert item["link_id"] == "link:1:2" and item["document_index"] == 2
    assert item["evidence"][0]["finding_ids"] == ["2:중_신청인_성명"]


def _bundle(*forms: tuple[str, Any]) -> dict[str, Any]:
    """분류 순서대로 서식(코드, 본인 칸 값)을 가진 합성 응답 — Other 는 값 없음, 값이 ... 면 추출 단계가 없음."""
    classify, steps = [], []
    for number, (code, value) in enumerate(forms, 1):
        ranges = [[number, number]]
        classify.append({"text": code, "additional_values": json.dumps({"document_type": {"_value": code}, "page_ranges": ranges}, ensure_ascii=False)})
        if code == "Other" or value is ...:
            continue
        key = "중_신청인_성명" if code == "지급보증거래_신청서" else V2_SELF_NAMES.get(code, "중_대리인_성명")
        meta = {key: {"_value": value, "confidence": "high", "page": number, "coordinates": [], "word_coordinates": []}, "page_ranges": ranges}
        steps.append(
            {
                "model": f"Information Extract - {code}",
                "status": "completed",
                "step_type": "information-extract",
                "content": [{"text": json.dumps({key: value}, ensure_ascii=False), "additional_values": json.dumps(meta, ensure_ascii=False)}],
            }
        )
    return {"output": [{"model": "step_2_classify", "status": "completed", "step_type": "document-classify", "content": classify}, *steps]}


SELF = "소비자피해보상금_지급신청서"
IRP = "IRP_신규신청서"
G = "지급보증거래_신청서"
W = "위임장_상속"
AUTO = "자동이체신청서"
FOREIGN = "외국인_세대구성원_확인서"


def statuses(*forms: tuple[str, Any]) -> tuple[int | None, list[tuple[int, str]]]:
    links = read_v2_links(_bundle(*forms))
    return links["anchor_index"], [(pair["target_index"], pair["status"]) for pair in links["pairs"]]


@pytest.mark.parametrize(
    ("forms", "anchor", "pairs"),
    [
        # 지급보증: 기준 값이 들어 있으면 linked, 아니면 unmatched, 비면 insufficient
        (((SELF, "가나다"), (G, "회사 대표 가나다")), 0, [(1, "linked")]),
        (((SELF, "가나다"), (G, "가나")), 0, [(1, "unmatched")]),
        (((SELF, "가나다"), (G, "")), 0, [(1, "insufficient")]),
        # 지급보증은 본인 칸이 없어 기준이 될 수 없다(분류 순서에서 뒤 서류가 기준)
        (((G, "회사 대표 가나다"), (SELF, "가나다")), 1, [(0, "linked")]),
        # 값이 정확히 같아야 한다 — 공백을 정리하지 않는다
        (((SELF, "가나다"), (IRP, "가나다")), 0, [(1, "linked")]),
        (((SELF, "가나다"), (IRP, "가나다 ")), 0, [(1, "unmatched")]),
        (((SELF, "가 나 다"), (IRP, "가나다")), 0, [(1, "unmatched")]),
        # 공백만인 문자열은 값이다([?@] 참) — 빈 값이 아니라 기준이 될 수 있다
        (((SELF, "   "), (IRP, "가나다")), 0, [(1, "unmatched")]),
        (((SELF, "   "), (IRP, "   ")), 0, [(1, "linked")]),
        (((SELF, "가나다"), (IRP, "   ")), 0, [(1, "unmatched")]),
        (((SELF, "   "), (G, "대표   이름")), 0, [(1, "linked")]),
        # 빈 값: 빈 문자열·null·빈 목록·빈 객체·false
        (((SELF, ""), (IRP, "가나다")), 1, [(0, "insufficient")]),
        (((SELF, None), (IRP, "가나다")), 1, [(0, "insufficient")]),
        (((SELF, []), (IRP, "가나다")), 1, [(0, "insufficient")]),
        (((SELF, {}), (IRP, "가나다")), 1, [(0, "insufficient")]),
        (((SELF, False), (IRP, "가나다")), 1, [(0, "insufficient")]),
        (((SELF, "가나다"), (IRP, "")), 0, [(1, "insufficient")]),
        (((SELF, ""), (IRP, "")), None, []),
        # 문자열이 아닌 값은 비교할 수 없다(0·true·목록은 빈 값이 아니다)
        (((SELF, "가나다"), (IRP, 5)), 0, [(1, "insufficient")]),
        (((SELF, "가나다"), (IRP, 0)), 0, [(1, "insufficient")]),
        (((SELF, "가나다"), (IRP, True)), 0, [(1, "insufficient")]),
        (((SELF, "가나다"), (IRP, ["가나다"])), 0, [(1, "insufficient")]),
        (((SELF, 5), (IRP, "가나다")), 0, [(1, "insufficient")]),
        (((SELF, 0), (IRP, "0")), 0, [(1, "insufficient")]),
        (((SELF, ["가"]), (G, "가")), 0, [(1, "insufficient")]),
        # 위임장은 늘 근거 부족, 대상 서류의 추출이 없어도 근거 부족
        (((SELF, "가나다"), (W, "가나다")), 0, [(1, "insufficient")]),
        (((W, "가나다"), (SELF, "가나다")), 1, [(0, "insufficient")]),
        (((SELF, "가나다"), (IRP, ...)), 0, [(1, "insufficient")]),
        (((SELF, ...), (IRP, "가나다")), 1, [(0, "insufficient")]),
        (((W, "가"), (G, "가")), None, []),  # 본인 칸이 있는 서류 없음
        # 같은 서식 둘째 서류도 대상
        (((SELF, "가나다"), (SELF, "다른이"), (IRP, "가나다")), 0, [(1, "unmatched"), (2, "linked")]),
        # Other 는 서류가 아니다 — 서식이 1종이면 연결 없음
        (((SELF, "가나다"), ("Other", None)), None, []),
        (((SELF, "가나다"), (SELF, "다른이")), None, []),
        (((SELF, "가나다"),), None, []),
        (((SELF, "가나다"), ("Other", None), (IRP, "가나다")), 0, [(2, "linked")]),
    ],
)
def test_link_status_rules(forms: tuple[tuple[str, Any], ...], anchor: int | None, pairs: list[tuple[int, str]]) -> None:
    assert statuses(*forms) == (anchor, pairs)
    assert_view(view_of(_bundle(*forms)))


@pytest.mark.parametrize(
    ("forms", "anchor", "pairs"),
    [
        # 소비자피해·외국인 확인서가 둘 다 없음 — 일치_확인 에 지급보증을 비교하는 규칙이 없다: 다름 → insufficient, 포함 → linked
        (((AUTO, "가나다"), (G, "다른 이름")), 0, [(1, "insufficient")]),
        (((AUTO, "가나다"), (G, "회사 대표 가나다")), 0, [(1, "linked")]),
        (((G, "다른 이름"), (AUTO, "가나다")), 1, [(0, "insufficient")]),
        (((IRP, "가나다"), (G, "다른 이름"), (AUTO, "가나다")), 0, [(1, "insufficient"), (2, "linked")]),
        (((AUTO, "가나다"), (W, "가나다"), (G, "다른 이름")), 0, [(1, "insufficient"), (2, "insufficient")]),
        # 둘 중 하나라도 있으면 그 규칙이 돈다: 다름 → unmatched
        (((AUTO, "가나다"), (FOREIGN, "가나다"), (G, "다른 이름")), 0, [(1, "linked"), (2, "unmatched")]),
        (((AUTO, "가나다"), (SELF, "가나다"), (G, "다른 이름")), 0, [(1, "linked"), (2, "unmatched")]),
        (((FOREIGN, "가나다"), (SELF, "가나다"), (G, "다른 이름")), 0, [(1, "linked"), (2, "unmatched")]),
        (((FOREIGN, "가나다"), (G, "회사 대표 가나다")), 0, [(1, "linked")]),
        # 분류 코드 기준 — 그 서류의 추출이 없어도 묶음에 있는 것으로 친다
        (((AUTO, "가나다"), (FOREIGN, ...), (G, "다른 이름")), 0, [(1, "insufficient"), (2, "unmatched")]),
        # 칸이 비면 언제나 insufficient
        (((AUTO, "가나다"), (G, "")), 0, [(1, "insufficient")]),
        (((AUTO, "가나다"), (G, None)), 0, [(1, "insufficient")]),
        (((AUTO, "가나다"), (SELF, "가나다"), (G, "")), 0, [(1, "linked"), (2, "insufficient")]),
        (((AUTO, "가나다"), (FOREIGN, "가나다"), (G, [])), 0, [(1, "linked"), (2, "insufficient")]),
    ],
)
def test_guarantee_link_follows_the_rule_scope(forms: tuple[tuple[str, Any], ...], anchor: int, pairs: list[tuple[int, str]]) -> None:
    assert statuses(*forms) == (anchor, pairs)
    assert_view(view_of(_bundle(*forms)))


def test_guarantee_out_of_rule_scope_is_a_weak_link_item() -> None:
    view = view_of(_bundle((AUTO, "가나다"), (G, "다른 이름")))
    assert link_states(view) == {"link:0:1": "insufficient"}
    item = item_of(view, "weaklink:0:1")
    assert item["link_id"] == "link:0:1" and item["desc"] == "비교할 본인 성명이 없습니다."
    assert not [i for i in view["items"] if i["type"] == "mismatch"]
    assert_view(view)


def test_guarantee_inside_rule_scope_is_a_mismatch_item() -> None:
    view = view_of(_bundle((AUTO, "가나다"), (FOREIGN, "가나다"), (G, "다른 이름")))
    assert link_states(view) == {"link:0:1": "linked", "link:0:2": "unmatched"}
    item = item_of(view, "mismatch:0:2")
    assert item["link_id"] == "link:0:2" and item["title"] == "자동이체 신청서와 본인 성명이 다릅니다"
    assert not [i for i in view["items"] if i["type"] == "weaklink"]


def test_links_are_computed_even_if_the_chain_stopped_early() -> None:
    # U 는 일치_확인 에서, T 처럼 단위_확인 에서 멈춘 묶음도 Extract 값이 있으면 같은 방법으로 계산한다
    response = load("B")
    response["output"] = [i for i in response["output"] if not (i["step_type"] == "validate" and i["model"] != "Validate - 대상_확인") and "내용_검토" not in i["model"]]
    assert link_states(view_of(response)) == {"link:0:1": "linked", "link:0:2": "linked"}


def test_no_links_when_too_many_documents() -> None:
    forms = [(SELF, "가나다"), (IRP, "가나다")] + [("Other", None)] * MAX_LINK_DOCUMENTS
    links = read_v2_links(_bundle(*forms))
    assert links["pairs"] is None and links["anchor_index"] is None
    assert view_of(_bundle(*forms))["links"] == []


def test_links_have_no_values() -> None:
    links = read_v2_links(_bundle((SELF, "원문이름"), (IRP, "원문이름")))
    assert "원문이름" not in json.dumps(links, ensure_ascii=False)


def test_link_pairs_keeps_the_old_way_without_doc_fields() -> None:
    from imask_backend.items import link_pairs

    documents = view_of("B")["documents"]
    findings = view_of("B")["findings"]
    old = {"field": "중_신청인_성명", "anchor_index": 1, "pairs": [{"id": "link:1:2", "target_index": 2, "group": None, "status": "linked"}]}
    pair = link_pairs(documents, findings, old, {})[0]
    assert pair.label == "중_신청인_성명"  # 옛 대응표에 없는 키는 키 그대로
    assert pair.target.finding_ids == ("2:중_신청인_성명",)


# --- 경계 ------------------------------------------------------------------------------------


def test_view_contract_item_rule_splits_by_id_form() -> None:
    spans, own = {0: (1, 1)}, {0: set()}

    def row(item_id: str, kind: str, link_id: str | None) -> dict[str, Any]:
        return {
            "id": item_id,
            "number": "R-01",
            "type": kind,
            "document_index": 0,
            "page": 1,
            "finding_id": None,
            "title": "t",
            "desc": "d",
            "next": "n",
            "evidence": [],
            "link_id": link_id,
        }

    assert_item(row("mismatch:0:규칙", "mismatch", None), spans, own)
    assert_item(row("review:mismatch", "mismatch", None), spans, own)
    assert_item(row("mismatch:1:0", "mismatch", "link:1:0"), spans, own)
    with pytest.raises(AssertionError):
        assert_item(row("mismatch:1:0", "mismatch", None), spans, own)
    with pytest.raises(AssertionError):
        assert_item(row("weaklink:1:0", "weaklink", None), spans, own)
    with pytest.raises(AssertionError):
        assert_item(row("mismatch:0:규칙", "mismatch", "link:1:0"), spans, own)


def test_one_reader_failing_keeps_the_rest(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    reference = view_of("A")

    def boom(*_: Any, **__: Any) -> Any:
        raise RuntimeError("원문 값")

    monkeypatch.setattr(final_flow, "read_verdict", boom)
    with caplog.at_level(logging.WARNING, logger="imask"):
        view = build_view({"response": load("A")})
    assert view["decision"] is None and view["findings"] == reference["findings"] and view["links"] == reference["links"]
    assert view["overall"] == {"level": None, "text": "", "next_stage": None, "next_text": ""}
    assert "원문 값" not in "\n".join(r.getMessage() for r in caplog.records)
    monkeypatch.undo()
    monkeypatch.setattr(final_flow, "read_v2_links", boom)
    view = build_view({"response": load("A")})
    assert view["links"] == [] and view["decision"] == reference["decision"] and view["findings"] == reference["findings"]
    monkeypatch.undo()
    monkeypatch.setattr(final_flow, "read_chain_rules", boom)
    view = build_view({"response": load("A")})
    assert view["bundle_check"] is None and view["decision"] == reference["decision"]


def test_warnings_have_no_values(caplog: pytest.LogCaptureFixture) -> None:
    response = load("F")
    set_value(response, "자동이체신청서", "중_아주_큰수", "원문값")
    stages = parse_stages(response)
    stage = next(s for s in stages if s["step_type"] == "information-extract")
    stage["data"]["중_아주_큰수"] = 10**5000
    with caplog.at_level(logging.WARNING, logger="imask"):
        build_view({"stages": stages})
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "ValueError" in logged and "원문값" not in logged and "아주_큰수" not in logged


@pytest.mark.parametrize("value", [None, "글", 5, [], {"a": 1}, [None], [{"output": 1}]])
def test_shape_breaks_in_extract_and_meta_keep_the_view(value: Any) -> None:
    stages = stages_of("B")
    extract = next(s for s in stages if s["step_type"] == "information-extract")
    extract["additional_values"]["중_본인_성명"] = value
    extract["data"]["세대구성원"] = extract["data"]["세대구성원"] + ([value] if value is not None else [])
    view = build_view({"stages": stages})
    assert_view(view)
    assert finding(view, "0:중_본인_성명")["page"] is None


def test_large_response_is_linear() -> None:
    stages = stages_of("B")
    extract = next(s for s in stages if s["step_type"] == "information-extract")
    extract["data"]["세대구성원"] = [{"중_성명": "가", "중_관계": "나"} for _ in range(10_000)]
    extract["additional_values"]["세대구성원"] = []
    extract["data"]["incomplete_fields"] = ["중_없는칸"] * 100_000
    chain = next(s for s in stages if s["name"] == "Validate - 형식_확인")
    chain["additional_values"]["checks"] = [_rule(f"규칙{n}", conditions=_leaf(nodeName="외국인_세대구성원_확인서", field="세대구성원", rowField="중_성명")) for n in range(MAX_CHECKS)]
    chain["additional_values"]["verdict"] = "red"
    started = time.perf_counter()
    view = build_view({"stages": stages})
    assert time.perf_counter() - started < TIME_LIMIT * 5
    assert len([i for i in view["items"] if i["type"] == "format"]) == MAX_CHECKS
    assert len(view["findings"]) >= 20_000


@pytest.mark.parametrize("case", CASES)
def test_results_are_json_ready(case: str) -> None:
    view = view_of(case)
    json.dumps(view, ensure_ascii=False, allow_nan=False).encode("utf-8")
    assert not has_unpaired_surrogates(view)


def test_final_flow_old_list_limit_is_kept() -> None:
    assert final_flow.MAX_DECISION_ITEMS == 50 and V2_MAX_DECISION_ITEMS == 500


# --- API·검토 동작 --------------------------------------------------------------------------


def _done(ctx: Ctx, case: str | dict[str, Any]) -> str:  # noqa: F811
    response = load(case) if isinstance(case, str) else case
    return ctx.store.put(status="done", job_id="job_done", result=stored_result(response))


@pytest.mark.parametrize("case", CASES)
def test_get_over_http_passes_the_contract(ctx: Ctx, case: str) -> None:  # noqa: F811
    analysis_id = _done(ctx, case)
    body = ctx.get(analysis_id).json()
    assert set(body) == ANALYSIS_KEYS
    result = body["result"]
    assert_view(result)
    assert "response" not in result and "stages" not in result
    assert same_answer(result["decision"], ANSWERS[case])
    assert result["summary"]["risk_level"] == ANSWERS[case]["risk_level"]
    assert body["review"] is not None
    ctx.no_upstage()


def test_list_uses_the_stored_summary_level(ctx: Ctx) -> None:  # noqa: F811
    want = {_done(ctx, "A"): "상", _done(ctx, "E"): "중", _done(ctx, "K"): "검토 필요"}
    rows = ctx.list().json()["analyses"]
    assert {row["id"]: row["risk_level"] for row in rows} == want


def test_analysis_out_hides_the_response_keeps_keys() -> None:
    row = {"id": "x", "status": "done", "documents": [], "result": build_result(load("B"), "60")}
    out = analysis_out(row)
    assert "response" not in out["result"] and "stages" not in out["result"]
    assert_view(out["result"])


def test_review_actions_on_a_table_cell_id(ctx: Ctx) -> None:  # noqa: F811
    analysis_id = _done(ctx, "B")
    target = "0:세대구성원[1].상_외국인등록번호"
    response = ctx.act(analysis_id, "set_status", finding_id=target, status="confirmed", reason="원본 확인")
    assert response.status_code == 200, response.text
    review = response.json()["analysis"]["review"]
    assert review["findings"][target]["status"] == "confirmed"
    last = review["history"][-1]
    assert last["kind"] == "confirm" and last["change"] == "미확인 → 확인함" and last["target"].endswith("고유식별정보")
    response = ctx.act(analysis_id, "mark_false_positive", finding_id="0:세대구성원[0].중_성명", reason_type="기타", note="메모")
    assert response.status_code == 200, response.text
    assert response.json()["analysis"]["review"]["history"][-1]["target"].endswith("성명 1행")
    ctx.no_upstage()


@pytest.mark.parametrize(
    ("case", "item_id", "label"),
    [
        ("L", "format:0:소비자피해보상금_지급신청서_신청일자", "형식 오류"),
        ("T", "duplicate:소비자피해보상금_지급신청서", "같은 서식 여러 건"),
        ("P", "unreadable:0:중_신청인_성명", "판독 불가"),
        ("N", "review:mismatch", "값 불일치"),
        ("U", "mismatch:1:0", "값 불일치"),
        ("K", "missing:0:소비자피해보상금_지급신청서_신청인_주민등록번호", "필수 항목 없음"),
    ],
)
def test_resolve_and_reopen_new_item_kinds(ctx: Ctx, case: str, item_id: str, label: str) -> None:  # noqa: F811
    analysis_id = _done(ctx, case)
    body = ctx.get(analysis_id).json()
    number = next(i["number"] for i in body["result"]["items"] if i["id"] == item_id)
    response = ctx.act(analysis_id, "resolve_item", item_id=item_id, note="원본 확인")
    assert response.status_code == 200, response.text
    review = response.json()["analysis"]["review"]
    assert review["items"][item_id]["resolved"] is True and review["items"][item_id]["resolved_by"] == ACTOR
    assert review["history"][-1]["target"] == f"{number} {label}"
    assert ctx.act(analysis_id, "reopen_item", item_id=item_id).status_code == 200
    ctx.no_upstage()


def test_same_reason_twice_can_be_fully_resolved(ctx: Ctx) -> None:  # noqa: F811
    analysis_id = _done(ctx, _verdict_with(review_reasons=["형식 오류", "형식 오류"], risk_level="검토 필요"))
    items = ctx.get(analysis_id).json()["result"]["items"]
    assert len({i["id"] for i in items}) == len(items) and [i["number"] for i in items] == [f"R-{n:02d}" for n in range(1, len(items) + 1)]
    for item in items:
        assert ctx.act(analysis_id, "resolve_item", item_id=item["id"], note="원본 확인").status_code == 200
    response = ctx.act(analysis_id, "complete_review", note="")
    assert response.status_code == 200, response.text
    assert "미해결 검토사항" not in response.json()["analysis"]["review"]["history"][-1]["change"]
    ctx.no_upstage()


def test_review_scope_of_a_blank_form_and_other_document(ctx: Ctx) -> None:  # noqa: F811
    for case in ("S", "R"):
        analysis_id = _done(ctx, case)
        body = ctx.get(analysis_id).json()
        assert body["review"]["findings"] == {} and body["result"]["findings"] == []
        assert body["review"]["history"][1]["change"].startswith("분석 완료 · 탐지 0건 · 위험등급 검토 필요 · 검토사항 ")
        item_id = body["result"]["items"][0]["id"]
        assert ctx.act(analysis_id, "resolve_item", item_id=item_id, note="").status_code == 200


def test_final_stage_constant_is_the_old_review_stage() -> None:
    assert summarize(load("K"))["final_stage"] == STAGE_REVIEW
