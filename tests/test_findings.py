# ==========================================================================
#  imask_backend.findings.build_view — 저장된 결과 → documents·findings·overall (네트워크 없음)
#  자료는 손으로 지은 가짜 응답(fake_findings: 관찰 모양을 본뜸, 추출 output 순서를 섞음).
#  짝짓기(쪽 범위)·빈 값·좌표·신뢰도·표에 없는 키·';' 값·항목별 위험등급(세 곳과 무시 규칙)·overall·
#  짝 없는 추출·실패 단계·stages 만 있는 저장 결과·이상한 모양(예외 없음)·계약 모양을 본다.
# ==========================================================================

from __future__ import annotations

import copy
import json
import logging
from typing import Any

import pytest
from fake_findings import (
    ACTION_TEXT,
    EXPECTED_BOXED,
    EXPECTED_DOCUMENTS,
    EXPECTED_FINDINGS,
    OTHER_TEXT,
    RISK_TEXT,
    VALUES,
    build_findings_response,
    extract_item,
    rect,
    risk_item,
    risk_json,
    stored_result,
)
from fake_responses import content, item
from view_contract import assert_view

from imask_backend import findings as findings_module
from imask_backend.findings import build_view, empty_view
from imask_backend.results import parse_stages

PAGE_OF_DOC = {0: 1, 1: 2, 2: 3, 3: 4, 4: 5}


def view_of(response: dict[str, Any]) -> dict[str, Any]:
    result = build_view({"response": response})
    assert_view(result)
    return result


def by_id(view: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {f["id"]: f for f in view["findings"]}


@pytest.fixture
def base() -> dict[str, Any]:
    return view_of(build_findings_response())


# --- documents ----------------------------------------------------------------------


def test_documents_follow_classification_with_other_guide_and_validation(base: dict[str, Any]) -> None:
    docs = base["documents"]
    assert len(docs) == EXPECTED_DOCUMENTS
    assert [d["index"] for d in docs] == [0, 1, 2, 3, 4, 5]
    assert [d["type"] for d in docs] == [
        "loan_application",
        "consent_form",
        "income_proof",
        "power_of_attorney",
        "debt_transaction",
        "Other",
    ]
    assert [(d["page_start"], d["page_end"]) for d in docs] == [(p, p) for p in range(1, 7)]
    assert [d["kind"] for d in docs] == ["extracted"] * 5 + ["other"]
    assert [d["validation"] for d in docs] == ["green"] * 5 + [None]
    assert [d["other_guide"] for d in docs] == [None] * 5 + [OTHER_TEXT]


def test_shuffled_extracts_pair_by_page_ranges(base: dict[str, Any]) -> None:
    # 추출 output 은 3·1·5·2·4쪽 순서지만 서류 index 순(=분류 순)으로, 각 서류의 값이 붙는다
    for doc_index, page in PAGE_OF_DOC.items():
        got = {f["field"]: f["value"] for f in base["findings"] if f["document_index"] == doc_index}
        assert got == VALUES[page]
    assert [f["document_index"] for f in base["findings"]] == sorted(f["document_index"] for f in base["findings"])


def test_unreadable_classify_content_keeps_its_index() -> None:
    response = build_findings_response()
    classify = response["output"][1]
    classify["content"][1]["text"] = "   "  # 분류 코드 못 읽음 → 서류는 없지만 순번 1 은 차지한다
    classify["content"][1]["additional_values"] = "{}"
    view = view_of(response)
    assert [d["index"] for d in view["documents"]][:2] == [0, 2]
    # 2쪽 추출은 짝이 없어 덧붙인 서류(index = 분류 content 수 6 + 0)
    appended = view["documents"][-1]
    assert appended == {
        "index": 6,
        "type": None,
        "page_start": 2,
        "page_end": 2,
        "kind": "extracted",
        "other_guide": None,
        "validation": "green",
    }
    assert {f["document_index"] for f in view["findings"] if f["field"] == "applicant_birth_date"} == {6}


def test_unpaired_extract_becomes_appended_document_and_stays_unrated() -> None:
    response = build_findings_response()
    extra = extract_item(1, ranges=[[7, 8]])
    response["output"].insert(7, extra)
    items = [{"branch_key": "6:None", "field": "applicant_name", "grade": "상"}]
    response["output"][-2] = risk_item(additional={"items": items})
    view = view_of(response)
    assert len(view["documents"]) == 7
    appended = view["documents"][6]
    assert appended["index"] == 6 and appended["type"] is None and appended["kind"] == "extracted"
    assert (appended["page_start"], appended["page_end"]) == (7, 8)
    mine = [f for f in view["findings"] if f["document_index"] == 6]
    assert len(mine) == len(VALUES[1])
    assert all(f["risk"] == "unrated" for f in mine)  # type 이 없는 서류는 늘 unrated


def test_missing_page_ranges_give_null_pages() -> None:
    response = build_findings_response()
    for entry in response["output"][1]["content"]:
        entry["additional_values"] = '{"document_type": {"_value": "loan_application"}}'
    view = view_of(response)
    assert all(d["page_start"] is None and d["page_end"] is None for d in view["documents"][:6])


def test_multi_range_document_uses_min_start_and_max_end() -> None:
    response = build_findings_response()
    classify = response["output"][1]["content"][0]
    classify["additional_values"] = '{"document_type": {"_value": "loan_application"}, "page_ranges": [[3, 4], [1, 2], [0, 9], [5, true]]}'
    view = view_of(response)
    doc = view["documents"][0]
    assert (doc["page_start"], doc["page_end"]) == (1, 4)


# --- findings -----------------------------------------------------------------------


def test_findings_count_and_boxes(base: dict[str, Any]) -> None:
    assert len(base["findings"]) == EXPECTED_FINDINGS == 29
    assert sum(1 for f in base["findings"] if f["boxes"]) == EXPECTED_BOXED == 28


def test_finding_fields_from_mapping_table(base: dict[str, Any]) -> None:
    found = by_id(base)
    name = found["0:applicant_name"]
    assert name["category"] == "이름" and name["label"] == "신청인 성명" and name["subject"] == "신청인"
    assert name["mapping_status"] == "ok"
    assert name["masked"] == "김*짜" and name["exposure"] == "전체 노출"
    staff = found["0:staff_contact"]
    assert staff["subject"] == "기타 · 은행 직원" and staff["mapping_status"] == "ok"
    other = found["3:other_person_name"]
    assert other["subject"] == "기타" and other["mapping_status"] == "needs_review"


def test_semicolon_value_is_one_finding(base: dict[str, Any]) -> None:
    staff = by_id(base)["0:staff_contact"]
    assert staff["value"] == VALUES[1]["staff_contact"]
    assert staff["value"].count(";") == 3
    assert staff["masked"].count(";") == 3 and len(staff["masked"]) == len(staff["value"])
    assert len([f for f in base["findings"] if f["field"] == "staff_contact"]) == 1


def test_already_masked_values(base: dict[str, Any]) -> None:
    found = by_id(base)
    assert found["2:applicant_rrn"]["exposure"] == "부분 마스킹"
    assert found["2:applicant_rrn"]["masked"] == "900101-1******"
    assert found["4:card_number"]["exposure"] == "부분 마스킹"
    assert found["4:card_number"]["masked"] == VALUES[5]["card_number"]


def test_word_boxes_first_then_coordinates_then_none(base: dict[str, Any]) -> None:
    found = by_id(base)
    address = found["0:applicant_address"]
    assert address["page"] == 1
    assert len(address["boxes"]) == 3  # 단어별 사각형 우선
    assert address["boxes"][0] == rect(0.1, 0.3)
    fallback = found["4:credit_negative_info"]
    assert fallback["page"] == 5 and len(fallback["boxes"]) == 1  # 단어 좌표 없음 → 값 영역
    assert fallback["boxes"][0][1]["x"] == pytest.approx(0.6)
    missing = found["2:income_info"]
    assert missing["page"] is None and missing["boxes"] == []  # page -1


def test_box_validation_drops_bad_rectangles_and_clamps() -> None:
    response = build_findings_response()
    extract = response["output"][3]  # 1쪽 추출
    additional = json.loads(extract["content"][0]["additional_values"])
    additional["applicant_address"]["word_coordinates"] = [
        [{"x": -0.0005, "y": 0.2}, {"x": 1.0009, "y": 0.2}, {"x": 1.0, "y": 0.3}, {"x": 0, "y": 0.3}],  # 잘라서 0~1
        [{"x": 1.2, "y": 0.2}, {"x": 0.5, "y": 0.2}, {"x": 0.5, "y": 0.3}, {"x": 0.4, "y": 0.3}],  # 범위 밖 → 버림
        [{"x": True, "y": 0.2}, {"x": 0.5, "y": 0.2}, {"x": 0.5, "y": 0.3}, {"x": 0.4, "y": 0.3}],  # bool → 버림
        [{"x": 0.1, "y": 0.2}, {"x": 0.5, "y": 0.2}, {"x": 0.5, "y": 0.3}],  # 점 3개 → 버림
        "x",
    ]
    additional["applicant_rrn"]["word_coordinates"] = [[{"x": 2, "y": 2}] * 4]
    additional["applicant_rrn"]["coordinates"] = [{"x": float("nan"), "y": 0.1}] * 4
    extract["content"][0]["additional_values"] = json.dumps(additional, ensure_ascii=False)
    found = by_id(view_of(response))
    assert found["0:applicant_address"]["boxes"] == [
        [{"x": 0.0, "y": 0.2}, {"x": 1.0, "y": 0.2}, {"x": 1.0, "y": 0.3}, {"x": 0.0, "y": 0.3}]
    ]
    assert found["0:applicant_rrn"]["boxes"] == []  # 둘 다 유효하지 않음
    assert found["0:applicant_rrn"]["page"] == 1


def test_confidence(base: dict[str, Any]) -> None:
    found = by_id(base)
    assert found["0:applicant_name"]["confidence"] == "high"
    assert found["0:loan_info"]["confidence"] == "low"


def test_unknown_key_is_kept_as_unknown() -> None:
    response = build_findings_response()
    data = {"applicant_name": "김가짜", "new_secret_field": "가짜 값 123"}
    response["output"][3] = extract_item(1, data=data)
    found = by_id(view_of(response))
    unknown = found["0:new_secret_field"]
    assert unknown["mapping_status"] == "unknown"
    assert unknown["label"] == "new_secret_field"
    assert unknown["category"] == "기타 개인정보" and unknown["subject"] == "기타"
    assert unknown["masked"] == "가* 값 1**"  # 기본 text 규칙(토큰마다 첫 글자만)


def test_value_types_and_empty_values() -> None:
    response = build_findings_response()
    data = {"a": 0, "b": 1.5, "c": True, "d": None, "e": ["x", 1], "f": {"k": "값"}, "g": [], "h": "   ", "i": ""}
    response["output"][3] = extract_item(1, data=data)
    found = {f["field"]: f["value"] for f in view_of(response)["findings"] if f["document_index"] == 0}
    assert found == {"a": "0", "b": "1.5", "e": '["x", 1]', "f": '{"k": "값"}'}


def test_default_risk_is_unrated(base: dict[str, Any]) -> None:
    assert {f["risk"] for f in base["findings"]} == {"unrated"}
    assert {f["risk_source"] for f in base["findings"]} == {None}
    assert {f["risk_reason"] for f in base["findings"]} == {None}


# --- 항목별 위험등급(워크플로우 값 읽기만) -------------------------------------------------

ITEMS = [
    {"branch_key": "0:loan_application", "field": "applicant_rrn", "grade": "상", "reason": "가짜 이유"},
    {"branch_key": "3:power_of_attorney", "field": "other_person_rrn", "grade": " 중 ", "reason": ""},
    {"branch_key": "4:debt_transaction", "field": "card_number", "grade": "하"},
    {"branch_key": "0:loan_application", "field": "applicant_rrn", "grade": "하", "reason": "두 번째 — 무시"},
    {"branch_key": "0:loan_application", "field": "applicant_phone", "grade": "검토 필요"},
    {"branch_key": "0:loan_application", "field": "applicant_email", "grade": "high"},
    {"branch_key": "1:loan_application", "field": "applicant_name", "grade": "상"},  # 틀린 branch_key
    {"branch_key": "0:loan_application", "field": "no_such_field", "grade": "상"},  # 없는 field
    {"branch_key": "", "field": "applicant_name", "grade": "상"},
    "not a mapping",
]


def _assert_rated(view: dict[str, Any]) -> None:
    found = by_id(view)
    assert (found["0:applicant_rrn"]["risk"], found["0:applicant_rrn"]["risk_source"]) == ("high", "workflow")
    assert found["0:applicant_rrn"]["risk_reason"] == "가짜 이유"  # 처음 것
    assert (found["3:other_person_rrn"]["risk"], found["3:other_person_rrn"]["risk_reason"]) == ("medium", None)
    assert found["4:card_number"]["risk"] == "low"
    for fid in ("0:applicant_phone", "0:applicant_email", "1:applicant_name", "0:applicant_name"):
        assert (found[fid]["risk"], found[fid]["risk_source"]) == ("unrated", None)
    rated = [f for f in view["findings"] if f["risk"] != "unrated"]
    assert len(rated) == 3


def test_item_risks_from_data_list() -> None:
    stage = risk_item(text=ITEMS, raw_text=False)
    view = view_of(build_findings_response(risk_stage=stage))
    _assert_rated(view)
    assert view["overall"]["text"] == ""  # data 가 문자열이 아니면 본문은 빈 값
    assert view["overall"]["level"] == "상"


def test_item_risks_from_data_mapping() -> None:
    stage = risk_item(text={"summary": "가짜", "items": ITEMS}, raw_text=False)
    _assert_rated(view_of(build_findings_response(risk_stage=stage)))


def test_item_risks_from_additional_values() -> None:
    stage = risk_item(additional={"items": ITEMS})
    view = view_of(build_findings_response(risk_stage=stage))
    _assert_rated(view)
    assert view["overall"]["text"] == RISK_TEXT


@pytest.mark.parametrize("fence", ["```json\n", "```\n", "```JSON \n"])
def test_item_risks_from_json_code_block(fence: str) -> None:
    text = f"## 위험도 판정\n상\n\n{fence}{risk_json(ITEMS)}\n```\n\n## 비고\n```\n깨진 블록\n```"
    stage = risk_item(text=text)
    view = view_of(build_findings_response(risk_stage=stage))
    _assert_rated(view)
    assert view["overall"]["text"] == text


def test_markdown_and_citations_are_not_guessed() -> None:
    text = "## 위험도 판정\napplicant_rrn: 상【†1】\n| 0:loan_application | applicant_rrn | 상 |"
    stage = risk_item(text=text)
    view = view_of(build_findings_response(risk_stage=stage))
    assert {f["risk"] for f in view["findings"]} == {"unrated"}


def test_first_location_wins_across_places() -> None:
    first = [{"branch_key": "0:loan_application", "field": "applicant_rrn", "grade": "중"}]
    second = [{"branch_key": "0:loan_application", "field": "applicant_rrn", "grade": "상"}]
    stage = risk_item(text={"items": first}, raw_text=False, additional={"items": second})
    found = by_id(view_of(build_findings_response(risk_stage=stage)))
    assert found["0:applicant_rrn"]["risk"] == "medium"


# --- overall ------------------------------------------------------------------------


def test_overall_with_action(base: dict[str, Any]) -> None:
    assert base["overall"] == {"level": "상", "text": RISK_TEXT, "next_stage": "권장_조치", "next_text": ACTION_TEXT}
    assert "【†1】" in base["overall"]["text"]


def test_overall_with_review_guide() -> None:
    view = view_of(build_findings_response(risk="검토 필요", final="검토_안내"))
    assert view["overall"]["level"] == "검토 필요"
    assert view["overall"]["next_stage"] == "검토_안내"
    assert view["overall"]["next_text"].startswith("## 검토 안내")


@pytest.mark.parametrize("enum", ["매우 높음", "high", "", 3, None])
def test_overall_odd_enum_is_null(enum: Any) -> None:
    assert view_of(build_findings_response(risk=enum))["overall"]["level"] is None


def test_overall_without_stages() -> None:
    view = view_of(build_findings_response(with_risk=False, final=None))
    assert view["overall"] == {"level": None, "text": "", "next_stage": None, "next_text": ""}


# --- 단계 상태·저장 형식 ----------------------------------------------------------------


def test_failed_stages_are_ignored() -> None:
    response = build_findings_response()
    response["output"][3]["status"] = "failed"  # 1쪽 추출
    response["output"][-2]["status"] = "failed"  # 위험도
    response["output"][-1]["status"] = "in_progress"  # 권장 조치
    view = view_of(response)
    assert not [f for f in view["findings"] if f["document_index"] == 0]
    assert view["documents"][0]["kind"] == "extracted"  # 짝은 없지만 Other 가 아니다
    assert view["overall"] == {"level": None, "text": "", "next_stage": None, "next_text": ""}


def test_stored_stages_without_response_give_same_view() -> None:
    with_response = build_view(stored_result())
    stages_only = stored_result(keep_response=False)
    assert "response" not in stages_only
    assert build_view(stages_only) == with_response
    assert len(with_response["findings"]) == EXPECTED_FINDINGS


def test_response_wins_over_stored_stages() -> None:
    result = stored_result()
    result["stages"] = parse_stages(build_findings_response(final="검토_안내", risk="검토 필요"))
    assert build_view(result)["overall"]["next_stage"] == "권장_조치"


# --- 이상한 모양 ----------------------------------------------------------------------

WEIRD_RESULTS: list[Any] = [
    None,
    "x",
    1,
    [],
    {},
    {"response": "x"},
    {"response": {"output": "x"}},
    {"response": {"output": [None, 1, "x", {"model": 1}, {"model": "step_2_classify", "content": "x"}]}},
    {"stages": "x"},
    {"stages": [None, 1, {"key": "민감정보_추출", "data": {"a": "b"}, "additional_values": "x"}]},
    {"stages": [{"key": "서류-분류", "contents": [None, 1, {"data": 5}, {"data": "Other", "additional_values": {"page_ranges": "x"}}]}]},
    {"stages": [{"key": "위험도_판정", "data": ["x", {"branch_key": 1}], "additional_values": {"enum": ["상"], "items": "x"}}]},
    {"stages": [{"key": "위험도_판정", "data": "```json\n{not json\n```", "additional_values": None}]},
    {"stages": [{"key": "민감정보_추출", "data": {"applicant_name": "가", 3: "x"}, "additional_values": {"applicant_name": {"page": True, "word_coordinates": "x", "coordinates": 5, "confidence": 1}, "page_ranges": [[1]]}}]},
    {"stages": [{"key": "필수항목_검증", "data": 1, "additional_values": {"verdict": ["x"], "page_ranges": [[2, 1], [0, 1], [True, 2]]}}]},
    {"stages": [{"key": "기타_서류_안내", "data": {"k": "v"}, "additional_values": {}}]},
]


@pytest.mark.parametrize("result", WEIRD_RESULTS)
def test_weird_shapes_never_raise(result: Any) -> None:
    view = build_view(copy.deepcopy(result))
    assert_view(view)


def test_weird_extract_meta_falls_back() -> None:
    view = build_view(WEIRD_RESULTS[13])
    assert_view(view)
    (finding,) = view["findings"]
    assert finding["page"] is None and finding["boxes"] == [] and finding["confidence"] is None
    assert finding["document_index"] == 0  # 분류 없음 → 덧붙인 서류


def test_other_guide_mapping_becomes_json_text() -> None:
    result = {"stages": [{"key": "서류-분류", "data": "Other", "additional_values": {"page_ranges": [[1, 1]]}}, {"key": "기타_서류_안내", "data": {"k": "값"}, "additional_values": {"page_ranges": [[1, 1]]}}]}
    (doc,) = build_view(result)["documents"]
    assert doc["kind"] == "other" and doc["other_guide"] == '{"k": "값"}'


def test_unexpected_exception_returns_empty_view(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    def boom(*_args: Any) -> Any:
        raise RuntimeError("값 김가짜 900101-1234567")

    monkeypatch.setattr(findings_module, "_documents", boom)
    with caplog.at_level(logging.WARNING, logger="imask.findings"):
        view = build_view(stored_result())
    assert view == empty_view()
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "RuntimeError" in logged
    assert "김가짜" not in logged and "900101" not in logged


def test_contract_shape_of_full_view(base: dict[str, Any]) -> None:
    # items: 검토사항(review-items §5.3) · links·decision·bundle_check: 최종 흐름 재료(final-flow T3 — 옛 응답은 빈 값)
    assert list(base) == ["documents", "findings", "overall", "items", "links", "decision", "bundle_check"]
    assert (base["links"], base["decision"], base["bundle_check"]) == ([], None, None)
    assert_view(base)


def test_classify_content_without_contents_list() -> None:
    result = {"stages": [item_like("서류-분류", "loan_application", [[1, 1]]), item_like("민감정보_추출", {"applicant_name": "가짜"}, [[1, 1]])]}
    view = build_view(result)
    assert [d["type"] for d in view["documents"]] == ["loan_application"]
    assert view["findings"][0]["id"] == "0:applicant_name"


def item_like(key: str, data: Any, ranges: list[list[int]]) -> dict[str, Any]:
    return {"key": key, "data": data, "additional_values": {"page_ranges": ranges}}


def test_parse_of_real_item_helpers_roundtrip() -> None:
    # fake_responses.item·content 로 만든 단계도 같은 규칙으로 읽힌다(분류 코드가 text 에만 있는 경우)
    response = {
        "output": [
            item("step_2_classify", "document-classify", content("consent_form", {"page_ranges": [[1, 1]]}, raw_text=True)),
            item("Information Extract - 민감정보_추출", "information-extract", content({"applicant_name": "가짜"}, {"page_ranges": [[1, 1]], "applicant_name": {"page": 1, "coordinates": rect(0.1, 0.1)}})),
        ]
    }
    view = view_of(response)
    assert view["documents"][0]["type"] == "consent_form"
    assert view["findings"][0]["boxes"] == [rect(0.1, 0.1)]


# --- T1-fix1: 빈 쪽 범위끼리는 짝짓지 않는다(코디네이터 결정) ------------------------------------


def _stage(key: str, data: Any, ranges: Any = None, **extra: Any) -> dict[str, Any]:
    additional: dict[str, Any] = dict(extra)
    if ranges is not None:
        additional["page_ranges"] = ranges
    return {"key": key, "status": "completed", "data": data, "additional_values": additional}


def _classify(*codes_and_ranges: tuple[str, Any]) -> dict[str, Any]:
    contents = []
    for code, ranges in codes_and_ranges:
        additional: dict[str, Any] = {"document_type": {"_value": code}}
        if ranges is not None:
            additional["page_ranges"] = ranges
        contents.append({"data": code, "additional_values": additional})
    return {"key": "서류-분류", "status": "completed", "data": None, "additional_values": None, "contents": contents}


NO_RANGE_RISK = [
    {"branch_key": "0:loan_application", "field": "applicant_name", "grade": "상"},
    {"branch_key": "2:consent_form", "field": "applicant_birth_date", "grade": "중"},
]


def test_empty_ranges_never_pair_extracts_go_to_appended_documents() -> None:
    stages = [
        _classify(("loan_application", None), ("Other", None), ("consent_form", None)),
        _stage("민감정보_추출", {"applicant_name": "김가짜", "applicant_rrn": "900101-1234567"}),
        _stage("민감정보_추출", {"applicant_birth_date": "2001년 2월 3일"}, ranges="x"),  # 틀린 범위 → 빈 범위
        _stage("필수항목_검증", "green", verdict="green"),
        _stage("필수항목_검증", "green", ranges=[[0, 0]], verdict="green"),  # 정규화하면 빈 범위
        _stage("기타_서류_안내", "예상_서류_종류=가짜"),
        _stage("위험도_판정", "## 판정", enum="상", items=NO_RANGE_RISK),
    ]
    view = build_view({"stages": stages})
    assert_view(view)
    docs = view["documents"]
    assert [(d["index"], d["type"], d["kind"]) for d in docs] == [
        (0, "loan_application", "extracted"),
        (1, "Other", "other"),
        (2, "consent_form", "extracted"),
        (3, None, "extracted"),
        (4, None, "extracted"),
    ]
    # 범위가 빈 분류 서류에는 아무것도 붙지 않고, 범위 없는 검증·기타 안내는 어디에도 붙지 않는다
    for doc in docs:
        assert doc["validation"] is None and doc["other_guide"] is None
        assert doc["page_start"] is None and doc["page_end"] is None
    # 추출 항목은 버리지 않는다 — 덧붙인 서류에 남고, type 이 없어 모두 unrated
    assert [(f["document_index"], f["field"]) for f in view["findings"]] == [
        (3, "applicant_name"),
        (3, "applicant_rrn"),
        (4, "applicant_birth_date"),
    ]
    assert {f["risk"] for f in view["findings"]} == {"unrated"}
    assert {f["risk_source"] for f in view["findings"]} == {None}


def test_empty_ranges_from_real_shaped_response() -> None:
    # 관찰 모양의 가짜 응답에서 page_ranges 를 모두 지우면 — 예전처럼 output 순서로 짝지어 Other 에 붙지 않는다
    response = build_findings_response()
    for entry in (c for o in response["output"] for c in o["content"]):
        if "additional_values" in entry:
            additional = json.loads(entry["additional_values"])
            additional.pop("page_ranges", None)
            entry["additional_values"] = json.dumps(additional, ensure_ascii=False)
    view = view_of(response)
    docs = view["documents"]
    assert len(docs) == 6 + 5
    assert [d["kind"] for d in docs[:6]] == ["extracted"] * 5 + ["other"]
    assert all(d["validation"] is None and d["other_guide"] is None for d in docs)
    assert [d["type"] for d in docs[6:]] == [None] * 5
    assert {f["document_index"] for f in view["findings"]} == {6, 7, 8, 9, 10}
    assert len(view["findings"]) == EXPECTED_FINDINGS  # 항목은 그대로
    assert {f["risk"] for f in view["findings"]} == {"unrated"}


@pytest.mark.parametrize(
    ("doc_ranges", "item_ranges"),
    [([[1, 1]], None), (None, [[1, 1]]), ([[1, 1]], [[2, 1]]), ([[True, 1]], [[1, 1]])],
    ids=["only_document_has_range", "only_item_has_range", "item_range_invalid", "document_range_invalid"],
)
def test_one_sided_range_does_not_pair(doc_ranges: Any, item_ranges: Any) -> None:
    stages = [
        _classify(("loan_application", doc_ranges)),
        _stage("민감정보_추출", {"applicant_name": "김가짜"}, ranges=item_ranges),
        _stage("필수항목_검증", "green", ranges=item_ranges, verdict="green"),
        _stage("기타_서류_안내", "예상_서류_종류=가짜", ranges=item_ranges),
    ]
    view = build_view({"stages": stages})
    assert_view(view)
    first = view["documents"][0]
    assert (first["index"], first["validation"], first["other_guide"]) == (0, None, None)
    appended = view["documents"][1]
    assert appended["index"] == 1 and appended["type"] is None and appended["kind"] == "extracted"
    assert [f["document_index"] for f in view["findings"]] == [1]
    # 덧붙인 서류는 추출의 범위를 그대로 가진다 — 범위가 있으면 같은 범위의 검증·기타 안내는 그 서류에 붙는다
    if _ranges_ok(item_ranges):
        assert appended["validation"] == "green" and appended["other_guide"] == "예상_서류_종류=가짜"
        assert (appended["page_start"], appended["page_end"]) == (1, 1)
    else:
        assert appended["validation"] is None and appended["other_guide"] is None
        assert (appended["page_start"], appended["page_end"]) == (None, None)


def _ranges_ok(ranges: Any) -> bool:
    return ranges == [[1, 1]]


def test_non_empty_equal_ranges_still_pair() -> None:
    stages = [
        _classify(("loan_application", [[1, 2]]), ("Other", None)),
        _stage("민감정보_추출", {"applicant_name": "김가짜"}, ranges=[[1, 2]]),
        _stage("필수항목_검증", "green", ranges=[[1, 2]], verdict="green"),
        _stage("기타_서류_안내", "예상_서류_종류=가짜"),  # 범위 없음 → Other 에도 붙지 않는다
    ]
    view = build_view({"stages": stages})
    docs = view["documents"]
    assert [(d["index"], d["kind"], d["validation"], d["other_guide"]) for d in docs] == [
        (0, "extracted", "green", None),
        (1, "other", None, None),
    ]
    assert view["findings"][0]["id"] == "0:applicant_name"



# --- T1-fix2: 큰 정수 좌표(B2)·항목 하나의 실패(B2)·코드 블록 경계(M1)·빈 안내(m1) ----------------------


def _with_meta(response: dict[str, Any], output_index: int, change: Any) -> dict[str, Any]:
    """output[output_index] 추출 항목의 additional_values(JSON 문자열)를 풀어 change(additional) 로 고친다."""
    entry = response["output"][output_index]["content"][0]
    additional = json.loads(entry["additional_values"])
    change(additional)
    entry["additional_values"] = json.dumps(additional, ensure_ascii=False)
    return response


def test_huge_integer_coordinate_drops_only_that_rectangle() -> None:
    def change(additional: dict[str, Any]) -> None:
        additional["applicant_address"]["word_coordinates"][1][0]["x"] = 10**400  # 단어 사각형 3개 중 하나만
        additional["applicant_rrn"]["word_coordinates"][0][2]["y"] = 10**400  # 하나뿐 → coordinates 대체
        additional["applicant_phone"]["word_coordinates"][0][0]["x"] = -(10**400)
        additional["applicant_phone"]["coordinates"][3]["y"] = 10**400  # 둘 다 틀림 → []

    view = view_of(_with_meta(build_findings_response(), 3, change))  # output[3] = 1쪽 추출
    assert len(view["documents"]) == EXPECTED_DOCUMENTS
    assert len(view["findings"]) == EXPECTED_FINDINGS
    found = by_id(view)
    assert found["0:applicant_address"]["boxes"] == [rect(0.1, 0.3), rect(0.1 + 0.12 * 2, 0.3)]
    assert found["0:applicant_rrn"]["boxes"] == [rect(0.1, 0.3, 0.5, 0.02)]
    assert found["0:applicant_phone"]["boxes"] == [] and found["0:applicant_phone"]["page"] == 1
    assert sum(1 for f in view["findings"] if f["boxes"]) == EXPECTED_BOXED - 1


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, 0.0),
        (1, 1.0),
        (0.5, 0.5),
        (-0.0005, 0.0),
        (1.0009, 1.0),
        (2, None),
        (-1, None),
        (10**400, None),
        (-(10**400), None),
        (float("inf"), None),
        (float("-inf"), None),
        (float("nan"), None),
        (1.5, None),
        ("0.5", None),
        (True, None),
        (False, None),
        (None, None),
        ([0.5], None),
        ({"v": 0.5}, None),
    ],
    ids=[
        "int_0",
        "int_1",
        "float_mid",
        "float_just_below_0",
        "float_just_above_1",
        "int_2",
        "int_minus_1",
        "huge_int",
        "huge_negative_int",
        "inf",
        "minus_inf",
        "nan",
        "float_1_5",
        "string",
        "true",
        "false",
        "none",
        "list",
        "dict",
    ],
)
def test_coordinate_values_never_raise(value: Any, expected: Any) -> None:
    got = findings_module._coordinate(value)  # noqa: SLF001 — 좌표 한 값 검사
    assert got == expected
    if expected is not None:
        assert isinstance(got, float)


def test_one_failing_finding_keeps_the_rest(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    target = VALUES[1]["applicant_email"]  # 1쪽에만 있는 값
    real = findings_module.masked

    def flaky(value: str, kind: str) -> str:
        if value == target:
            raise RuntimeError(f"가짜 실패 {value}")
        return real(value, kind)

    items = [{"branch_key": "0:loan_application", "field": "applicant_email", "grade": "상", "reason": "가짜 이유"}]
    response = build_findings_response(risk_stage=risk_item(additional={"items": items}))
    normal = by_id(view_of(copy.deepcopy(response)))
    monkeypatch.setattr(findings_module, "masked", flaky)
    with caplog.at_level(logging.WARNING, logger="imask.findings"):
        view = view_of(response)
    assert len(view["documents"]) == EXPECTED_DOCUMENTS and len(view["findings"]) == EXPECTED_FINDINGS
    found = by_id(view)
    bad = found["0:applicant_email"]
    keep = ("id", "document_index", "field", "category", "label", "subject", "mapping_status", "value")
    assert {k: bad[k] for k in keep} == {k: normal["0:applicant_email"][k] for k in keep}
    assert bad["masked"] == "*" * len(target)
    assert (bad["exposure"], bad["page"], bad["boxes"], bad["confidence"]) == ("전체 노출", None, [], None)
    assert (bad["risk"], bad["risk_source"], bad["risk_reason"]) == ("high", "workflow", "가짜 이유")  # 위험등급은 정상 조회값
    assert {fid: f for fid, f in found.items() if fid != "0:applicant_email"} == {
        fid: f for fid, f in normal.items() if fid != "0:applicant_email"
    }
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "applicant_email" in logged and "RuntimeError" in logged
    assert target not in logged and "가짜 실패" not in logged


DETAIL_KEYS = {"masked", "exposure", "page", "boxes", "confidence"}


def _failing_value_text(monkeypatch: pytest.MonkeyPatch, target: Any) -> None:
    """_value_text 가 raw == target 일 때만 예외를 내게 한다(나머지는 진짜 도우미)."""
    real = findings_module._value_text  # noqa: SLF001

    def flaky(raw: Any) -> str | None:
        if raw == target:
            raise ValueError(f"가짜 변환 실패 {raw}")
        return real(raw)

    monkeypatch.setattr(findings_module, "_value_text", flaky)


def test_value_conversion_failure_keeps_the_finding(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    # fix3 B2-R2: 값 문자열 만들기가 실패해도 항목을 버리지 않는다 — 원문 문자열 그대로 + 대체 detail
    target = VALUES[1]["staff_contact"]  # 1쪽에만 있는 값
    items = [{"branch_key": "0:loan_application", "field": "staff_contact", "grade": "중", "reason": "가짜 이유"}]
    response = build_findings_response(risk_stage=risk_item(additional={"items": items}))
    normal = by_id(view_of(copy.deepcopy(response)))
    _failing_value_text(monkeypatch, target)
    with caplog.at_level(logging.WARNING, logger="imask.findings"):
        view = view_of(response)
    assert len(view["findings"]) == EXPECTED_FINDINGS and len(view["documents"]) == EXPECTED_DOCUMENTS
    found = by_id(view)
    kept = found["0:staff_contact"]
    assert kept["value"] == target  # 원문 문자열 그대로
    assert {k: v for k, v in kept.items() if k not in DETAIL_KEYS} == {
        k: v for k, v in normal["0:staff_contact"].items() if k not in DETAIL_KEYS
    }  # id·document_index·field·대응표·value·risk(medium/workflow/이유) 보존
    assert (kept["risk"], kept["risk_source"], kept["risk_reason"]) == ("medium", "workflow", "가짜 이유")
    assert kept["masked"] == "*" * len(target)
    assert (kept["exposure"], kept["page"], kept["boxes"], kept["confidence"]) == ("전체 노출", None, [], None)
    assert {fid: f for fid, f in found.items() if fid != "0:staff_contact"} == {
        fid: f for fid, f in normal.items() if fid != "0:staff_contact"
    }
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "staff_contact" in logged and "ValueError" in logged
    assert target not in logged and "가짜 변환 실패" not in logged


def test_non_string_value_conversion_failure_uses_fixed_text(monkeypatch: pytest.MonkeyPatch) -> None:
    response = build_findings_response()
    data = {**VALUES[1], "loan_amount_number": 12345, "loan_terms_object": {"기간": 12}}
    response["output"][3] = extract_item(1, data=data)  # output[3] = 1쪽 추출
    _failing_value_text(monkeypatch, 12345)
    found = by_id(view_of(response))
    number = found["0:loan_amount_number"]
    assert number["value"] == "(값을 읽지 못했습니다)"  # 원문을 문자열로 만들 수 없을 때만 고정 문구
    assert number["masked"] == "*" * len(number["value"]) and number["exposure"] == "전체 노출"
    assert number["mapping_status"] == "unknown" and number["page"] is None
    assert found["0:loan_terms_object"]["value"] == '{"기간": 12}'  # 다른 항목은 정상 변환
    assert len(found) == EXPECTED_FINDINGS + 2


def test_conversion_failure_on_empty_values_still_means_no_finding(monkeypatch: pytest.MonkeyPatch) -> None:
    # 빈 값(공백만·None·bool·빈 목록/객체)은 실패가 아니라 원래 항목이 아니다 — 도우미가 실패해도 만들지 않는다
    def always_fail(_raw: Any) -> str | None:
        raise RuntimeError("가짜")

    monkeypatch.setattr(findings_module, "_value_text", always_fail)
    data = {"a": "", "b": "   ", "c": None, "d": False, "e": [], "f": {}, "g": "남는 값", "h": 7}
    result = {"stages": [{"key": "민감정보_추출", "data": data, "additional_values": {}}]}
    view = build_view(result)
    assert_view(view)
    assert [(f["field"], f["value"]) for f in view["findings"]] == [("g", "남는 값"), ("h", "(값을 읽지 못했습니다)")]


FENCE_ITEMS = [{"branch_key": "0:loan_application", "field": "applicant_name", "grade": "상"}]
FENCE_JSON = risk_json(FENCE_ITEMS)


@pytest.mark.parametrize(
    ("text", "rated"),
    [
        (f"```json\n{FENCE_JSON}\n```", True),
        (f"```python\npass\n```\n\n```json\n{FENCE_JSON}\n```", True),  # python 블록 뒤의 json 블록
        (f"```python\npass\n```\n\n{FENCE_JSON}\n\n```python\npass\n```", False),  # 두 python 블록 사이의 맨 목록
        (f"```python\n```json\n{FENCE_JSON}\n```\n", False),  # python 블록 안의 ```json 줄은 내용
        (f"````json\n{FENCE_JSON}\n````", True),  # 백틱 4개 fence
        (f"````python\n```json\n{FENCE_JSON}\n```\n````", False),  # 4개 fence 안의 3개는 닫는 줄이 아님
        (f"```JSON 설명\n{FENCE_JSON}\n```", True),  # 정보 문자열 첫 낱말 json(대소문자 무시)
        (f"```\n{FENCE_JSON}\n  ```  ", True),  # 언어 표시 없음 · 닫는 줄 앞뒤 공백
        (f"   ```json\n{FENCE_JSON}\n```", True),  # 여는 줄 앞 공백 3칸까지
        (f"    ```json\n{FENCE_JSON}\n    ```", False),  # 4칸이면 fence 가 아님
        (f"```json\n{FENCE_JSON}\n", False),  # 닫히지 않은 블록은 무시
        (f"```jsonc\n{FENCE_JSON}\n```", False),  # 다른 언어
        (f"{FENCE_JSON}\n본문 목록은 코드 블록이 아니다", False),
    ],
    ids=[
        "plain_json",
        "json_after_python",
        "list_between_python_blocks",
        "json_line_inside_python",
        "four_backticks",
        "three_inside_four",
        "info_with_words",
        "bare_fence_trailing_space",
        "indent_three",
        "indent_four",
        "unclosed",
        "other_language",
        "markdown_list",
    ],
)
def test_code_block_boundaries(text: str, rated: bool) -> None:
    view = view_of(build_findings_response(risk_stage=risk_item(text=text)))
    finding = by_id(view)["0:applicant_name"]
    assert (finding["risk"], finding["risk_source"]) == (("high", "workflow") if rated else ("unrated", None))
    assert view["overall"]["text"] == text  # 본문은 그대로


def test_json_code_blocks_reads_all_blocks_in_order() -> None:
    text = "```json\n[1]\n```\n```python\n```json\n[9]\n```\n```\n[2]\n```\n````JSON\n[3]\n````\n```json\n[4]"
    assert findings_module.json_code_blocks(text) == ["[1]", "[2]", "[3]"]


def test_first_block_item_wins_and_other_places_come_first() -> None:
    first = [{"branch_key": "0:loan_application", "field": "applicant_name", "grade": "하"}]
    text = f"```json\n{risk_json(first)}\n```\n```json\n{FENCE_JSON}\n```"
    found = by_id(view_of(build_findings_response(risk_stage=risk_item(text=text))))
    assert found["0:applicant_name"]["risk"] == "low"  # 블록 안에서도 처음 것
    stage = risk_item(text=f"```json\n{FENCE_JSON}\n```", additional={"items": first})
    found = by_id(view_of(build_findings_response(risk_stage=stage)))
    assert found["0:applicant_name"]["risk"] == "low"  # additional_values(2)가 코드 블록(3)보다 먼저


@pytest.mark.parametrize("guide", [{}, [], "", "   \n "], ids=["empty_object", "empty_list", "empty_string", "blank"])
def test_empty_other_guide_is_null(guide: Any) -> None:
    # 코디네이터 결정(fix2 m1): 빈 문자열·빈 객체·빈 목록 안내는 안내가 없는 것과 같다 → null
    result = {
        "stages": [
            {"key": "서류-분류", "data": "Other", "additional_values": {"page_ranges": [[1, 1]]}},
            {"key": "기타_서류_안내", "data": guide, "additional_values": {"page_ranges": [[1, 1]]}},
        ]
    }
    (doc,) = build_view(result)["documents"]
    assert doc["other_guide"] is None and doc["kind"] == "other"


# --- T1-fix3: 쪽 번호의 상식 범위(1~100000) ---------------------------------------------------------


@pytest.mark.parametrize(
    ("page", "expected"),
    [(10**400, None), (100_001, None), (100_000, 100_000), (1, 1), (0, None)],
    ids=["huge_int", "just_above_limit", "limit", "one", "zero"],
)
def test_page_number_limit(page: Any, expected: Any) -> None:
    def change(additional: dict[str, Any]) -> None:
        additional["applicant_name"]["page"] = page

    found = by_id(view_of(_with_meta(build_findings_response(), 3, change)))  # output[3] = 1쪽 추출
    name = found["0:applicant_name"]
    assert name["page"] == expected
    assert (name["boxes"] != []) == (expected is not None)  # page 가 없으면 boxes []


def test_page_range_beyond_limit_is_dropped() -> None:
    stages = [
        _classify(("loan_application", [[1, 10**400]]), ("consent_form", [[2, 100_001]]), ("income_proof", [[3, 100_000]])),
        _stage("민감정보_추출", {"applicant_name": "김가짜"}, ranges=[[1, 10**400]]),
        _stage("민감정보_추출", {"applicant_name": "이가짜"}, ranges=[[3, 100_000]]),
    ]
    view = build_view({"stages": stages})
    assert_view(view)
    docs = view["documents"]
    assert [(d["index"], d["page_start"], d["page_end"]) for d in docs] == [
        (0, None, None),  # 범위 쌍을 버려 빈 범위 → 짝짓지 않는다(fix1)
        (1, None, None),
        (2, 3, 100_000),
        (3, None, None),  # 범위가 버려진 추출은 덧붙인 서류로
    ]
    assert [(f["document_index"], f["value"]) for f in view["findings"]] == [(2, "이가짜"), (3, "김가짜")]


# --- T1-fix4·fix5: 표에 없는 키의 label 은 원래 키(비면 "(이름 없는 항목)") ----------------------------------


def test_unknown_key_label_is_original_key_or_placeholder() -> None:
    data = {"": "값 하나", "   ": "값 둘", "brand_new": "값 셋", "applicant_name": "김가짜"}
    view = build_view({"stages": [{"key": "민감정보_추출", "data": data, "additional_values": {}}]})
    assert_view(view)
    rows = [(f["id"], f["field"], f["label"], f["mapping_status"]) for f in view["findings"]]
    assert rows == [
        ("0:", "", "(이름 없는 항목)", "unknown"),
        ("0:   ", "   ", "(이름 없는 항목)", "unknown"),
        ("0:brand_new", "brand_new", "brand_new", "unknown"),
        ("0:applicant_name", "applicant_name", "신청인 성명", "ok"),  # 대응표에 있는 키는 표의 label
    ]


# --- T1-fix5 M2-R4: 항목별 위험등급의 field·branch_key 는 다듬지 않고 정확히 비교한다 -------------------------


def _rated_view(data: dict[str, Any], items: list[Any]) -> dict[str, dict[str, Any]]:
    stages = [
        _classify(("loan_application", [[1, 1]])),
        _stage("민감정보_추출", data, ranges=[[1, 1]]),
        {"key": "위험도_판정", "status": "completed", "data": "## 판정", "additional_values": {"enum": "상", "items": items}},
    ]
    view = build_view({"stages": stages})
    assert_view(view)
    return {f["field"]: f for f in view["findings"]}


def _risk(finding: dict[str, Any]) -> tuple[Any, Any, Any]:
    return finding["risk"], finding["risk_source"], finding["risk_reason"]


def test_risk_field_is_compared_without_stripping() -> None:
    data = {"applicant_name": "김가짜", " applicant_name ": "이가짜"}
    items = [{"branch_key": "0:loan_application", "field": " applicant_name ", "grade": " 상 ", "reason": "  "}]
    found = _rated_view(data, items)
    assert _risk(found[" applicant_name "]) == ("high", "workflow", None)  # grade 는 다듬고, 빈 reason 은 null
    assert _risk(found["applicant_name"]) == ("unrated", None, None)  # 공백만 다른 키에 옮겨 가지 않는다


def test_unknown_key_with_spaces_and_surrogate_keeps_its_grade() -> None:
    key = " 메모" + "\ud800" + " "
    found = _rated_view({key: "가짜 값"}, [{"branch_key": "0:loan_application", "field": key, "grade": "중"}])
    assert _risk(found[key]) == ("medium", "workflow", None)
    assert found[key]["label"] == key and found[key]["mapping_status"] == "unknown"


def test_blank_risk_identifiers_are_ignored() -> None:
    data = {"applicant_name": "김가짜", "   ": "공백 이름 값"}
    items = [
        {"branch_key": "0:loan_application", "field": "", "grade": "상"},
        {"branch_key": "0:loan_application", "field": "   ", "grade": "상"},  # 공백만인 field → 무시(같은 이름의 키가 있어도)
        {"branch_key": "   ", "field": "applicant_name", "grade": "상"},
        {"branch_key": " 0:loan_application", "field": "applicant_name", "grade": "상"},  # branch_key 앞 공백 → 다른 문자열
        {"branch_key": "0:loan_application ", "field": "applicant_name", "grade": "상"},
    ]
    found = _rated_view(data, items)
    assert {_risk(f) for f in found.values()} == {("unrated", None, None)}


def test_same_original_key_takes_the_first_grade() -> None:
    items = [
        {"branch_key": "0:loan_application", "field": "applicant_name", "grade": "하", "reason": "처음"},
        {"branch_key": "0:loan_application", "field": "applicant_name", "grade": "상", "reason": "나중"},
        {"branch_key": "0:loan_application", "field": "applicant_name ", "grade": "중"},  # 다른 원래 문자열
    ]
    found = _rated_view({"applicant_name": "김가짜", "applicant_name ": "이가짜"}, items)
    assert _risk(found["applicant_name"]) == ("low", "workflow", "처음")
    assert _risk(found["applicant_name "]) == ("medium", "workflow", None)
