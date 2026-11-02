# ==========================================================================
#  results.py 테스트 — 손으로 만든 작은 가짜 응답(tests/fake_responses.py)으로
#  parse_stages · summarize 를 확인한다. 권장_조치·검토_안내 분기, 기타_서류_안내,
#  JSON 이 아닌 텍스트, 빈 output, 모양이 다른 항목.
# ==========================================================================

from __future__ import annotations

import json

import pytest
from fake_responses import build_response, content, item

from imask_backend.results import (
    STAGE_CLASSIFY,
    STAGE_EXTRACT,
    STAGE_PARSE,
    STAGE_REVIEW,
    parse_stages,
    stage_key,
    stages_for,
    summarize,
)


def test_parse_stages_keeps_output_order_and_parses_json():
    response = build_response()
    stages = parse_stages(response)

    assert [s["name"] for s in stages] == [i["model"] for i in response["output"]]
    parse = stages[0]
    assert parse["key"] == STAGE_PARSE
    assert parse["status"] == "completed"
    assert parse["step_type"] == "document-parse"
    assert parse["data"] == {"api": "2.0", "elements": []}
    assert parse["additional_values"] == {"document_ids": ["f"]}
    assert len(parse["contents"]) == 1


def test_parse_stages_keeps_every_content_entry():
    stages = parse_stages(build_response(types=("loan_application", "consent_form", "Other")))
    (classify,) = stages_for(stages, STAGE_CLASSIFY)
    # 첫 content 는 data·additional_values 로, 모두는 contents 로
    assert classify["data"] == "loan_application"  # JSON 이 아닌 텍스트는 문자열 그대로
    assert classify["additional_values"]["document_type"]["_value"] == "loan_application"
    assert [c["data"] for c in classify["contents"]] == ["loan_application", "consent_form", "Other"]


def test_summarize_action_branch():
    summary = summarize(build_response(types=("loan_application", "consent_form", "Other"), risk="상"))

    assert summary["stage_names"] == [
        "step_1_parse",
        "step_2_classify",
        "Information Extract - 민감정보_추출",
        "Instruct - 기타_서류_안내",
        "Validate - 필수항목_검증",
        "병합-1",
        "Instruct - 위험도_판정",
        "Instruct - 권장_조치",
    ]
    assert summary["stage_counts"]["Information Extract - 민감정보_추출"] == 2
    assert summary["stage_counts"]["Validate - 필수항목_검증"] == 2
    assert summary["document_count"] == 3
    assert summary["document_types"] == ["loan_application", "consent_form", "Other"]
    assert summary["extracted_document_count"] == 2
    assert summary["risk_level"] == "상"
    assert summary["final_stage"] == "권장_조치"
    assert summary["other_document_count"] == 1


def test_summarize_review_branch():
    response = build_response(types=("loan_application",), risk="검토 필요", final=STAGE_REVIEW)
    summary = summarize(response)

    assert summary["risk_level"] == "검토 필요"
    assert summary["final_stage"] == "검토_안내"
    assert "Instruct - 검토_안내" in summary["stage_names"]
    assert "Instruct - 권장_조치" not in summary["stage_names"]
    # 기타 서류가 없으면 기타_서류_안내 단계가 없다 → None(못 찾음)
    assert summary["other_document_count"] is None
    assert summary["document_count"] == 1


def test_summarize_several_other_documents():
    summary = summarize(build_response(types=("Other", "consent_form", "Other")))
    assert summary["other_document_count"] == 2
    assert summary["extracted_document_count"] == 1
    assert summary["document_types"].count("Other") == 2


def test_summarize_accepts_parsed_stages():
    response = build_response()
    assert summarize(parse_stages(response)) == summarize(response)


def test_stage_found_by_name_not_position():
    response = build_response()
    response["output"].reverse()
    summary = summarize(response)
    assert summary["document_count"] == 3
    assert summary["risk_level"] == "상"
    assert summary["final_stage"] == "권장_조치"


@pytest.mark.parametrize(
    ("name", "step_type", "expected"),
    [
        ("step_1_parse", None, "서류-인식"),
        ("서류-분류", None, "서류-분류"),
        ("step_9_classify", "document-classify", "서류-분류"),
        ("Information Extract - 민감정보_추출", "information-extract", "민감정보_추출"),
        ("Instruct - 검토_안내", "instruct", "검토_안내"),
        ("Instruct - 기타_서류_안내", "instruct", "기타_서류_안내"),
        ("병합-1", "merge", "병합-1"),
        ("Instruct - 다른_단계", "instruct", None),
        ("민감정보_추출_v2", None, None),
        (None, None, None),
    ],
)
def test_stage_key(name, step_type, expected):
    assert stage_key(name, step_type) == expected


def test_text_that_is_not_json_stays_string():
    response = {
        "output": [
            item("Instruct - 위험도_판정", "instruct", content("상 (JSON 아님", "{깨진 json", raw_text=True)),
        ]
    }
    response["output"][0]["content"][0]["additional_values"] = "{깨진 json"
    (stage,) = parse_stages(response)
    assert stage["data"] == "상 (JSON 아님"
    assert stage["additional_values"] == "{깨진 json"
    # enum 을 못 읽으면 위험도는 None(본문을 추측해 읽지 않는다)
    assert summarize(response)["risk_level"] is None


def test_extract_with_non_json_text_is_not_counted():
    response = build_response(types=("loan_application", "consent_form"))
    extract = [i for i in response["output"] if i["model"].endswith(STAGE_EXTRACT)]
    extract[0]["content"][0]["text"] = "추출 실패"
    assert summarize(response)["extracted_document_count"] == 1


def test_empty_output():
    for response in ({"output": []}, {}, {"output": None}, None, "x", []):
        assert parse_stages(response if isinstance(response, dict) else {"output": response}) == []
        summary = summarize(response)
        assert summary == {
            "stage_names": [],
            "stage_counts": {},
            "document_count": None,
            "document_types": None,
            "extracted_document_count": None,
            "risk_level": None,
            "final_stage": None,
            "other_document_count": None,
        }


def test_odd_shapes_do_not_raise():
    response = {
        "output": [
            "not an item",
            {"model": "step_2_classify"},  # content 없음
            {"model": "Instruct - 위험도_판정", "content": []},
            {"model": "Instruct - 권장_조치", "content": ["text only"]},
            {"model": 123, "content": [{"text": None, "additional_values": None}]},
            {"content": [{"text": json.dumps({"a": 1})}]},
        ]
    }
    stages = parse_stages(response)
    assert len(stages) == 5  # dict 가 아닌 항목만 건너뛴다
    assert stages[0]["data"] is None and stages[0]["contents"] == []
    assert stages[1]["data"] is None and stages[1]["contents"] == []
    assert stages[2]["contents"] == [{"data": None, "additional_values": None}]
    assert stages[3]["name"] == 123 and stages[3]["key"] is None and stages[3]["data"] is None
    assert stages[4]["name"] is None and stages[4]["data"] == {"a": 1}

    summary = summarize(response)
    # 분류 단계는 있지만 읽을 수 있는 항목이 없다 → 0 이 아니라 None(개수를 정할 수 없음)
    assert summary["document_count"] is None
    assert summary["document_types"] is None
    assert summary["risk_level"] is None
    assert summary["final_stage"] == "권장_조치"
    assert summary["stage_names"] == ["step_2_classify", "Instruct - 위험도_판정", "Instruct - 권장_조치"]


def test_classify_type_falls_back_to_text():
    response = {"output": [item("step_2_classify", "document-classify", content("income_proof", None, raw_text=True))]}
    assert summarize(response)["document_types"] == ["income_proof"]


# --- m1: 읽지 못한 항목은 세지 않고, 하나도 못 읽으면 None ------------------------------


@pytest.mark.parametrize(
    "classify_item",
    [
        {"model": "step_2_classify"},  # content 없음
        {"model": "step_2_classify", "content": []},
        {"model": "step_2_classify", "content": [None]},
        {"model": "step_2_classify", "content": [{"type": "output_text"}]},  # text·additional_values 없음
        {"model": "step_2_classify", "content": [{"text": "   "}]},  # 빈 코드
        {"model": "step_2_classify", "content": "not a list"},
    ],
    ids=["no-content", "empty", "null", "no-text", "blank-text", "not-list"],
)
def test_unreadable_classify_gives_none(classify_item):
    summary = summarize({"output": [classify_item]})
    assert summary["document_count"] is None
    assert summary["document_types"] is None
    assert summary["stage_names"] == ["step_2_classify"]


def test_only_readable_classify_entries_are_counted():
    good = content("consent_form", {"document_type": {"_value": "consent_form"}}, raw_text=True)
    response = {"output": [item("step_2_classify", "document-classify", good, {"text": None})]}
    response["output"][0]["content"].insert(0, None)
    summary = summarize(response)
    assert summary["document_count"] == 1
    assert summary["document_types"] == ["consent_form"]


def test_failed_stages_are_not_counted():
    # V-T1-1 재현: 실패 단계들(content 비어 있음)
    sparse = {
        "status": "failed",
        "output": [
            {"model": "step_2_classify", "status": "failed", "content": []},
            {"model": "Information Extract - 민감정보_추출", "status": "failed", "content": []},
            {"model": "Instruct - 위험도_판정", "status": "failed", "content": []},
            {"model": "Instruct - 기타_서류_안내", "status": "failed", "content": []},
        ],
    }
    summary = summarize(sparse)
    assert summary["document_count"] is None
    assert summary["document_types"] is None
    assert summary["extracted_document_count"] is None
    assert summary["risk_level"] is None
    assert summary["other_document_count"] is None
    assert summary["final_stage"] is None


def test_failed_stage_with_readable_content_is_still_ignored():
    response = build_response(types=("loan_application", "consent_form", "Other"))
    for entry in response["output"]:
        entry["status"] = "failed"
    summary = summarize(response)
    assert summary["document_count"] is None
    assert summary["extracted_document_count"] is None
    assert summary["risk_level"] is None
    assert summary["final_stage"] is None
    assert summary["other_document_count"] is None


def test_in_progress_stage_is_ignored():
    response = build_response(types=("loan_application", "consent_form"))
    risk = next(i for i in response["output"] if i["model"].endswith("위험도_판정"))
    risk["status"] = "in_progress"
    assert summarize(response)["risk_level"] is None
    assert summarize(response)["document_count"] == 2


@pytest.mark.parametrize("bad_text", ["not-json", "", "[1, 2]", "\"just a string\""])
def test_extract_unreadable_everywhere_gives_none(bad_text):
    response = {"output": [{"model": "Information Extract - 민감정보_추출", "content": [{"text": bad_text}]}]}
    assert summarize(response)["extracted_document_count"] is None


def test_extract_mixed_counts_only_objects():
    response = build_response(types=("loan_application", "consent_form", "income_proof"))
    extract = [i for i in response["output"] if i["model"].endswith(STAGE_EXTRACT)]
    extract[0]["content"][0]["text"] = "추출 실패"
    extract[1]["content"] = []
    assert summarize(response)["extracted_document_count"] == 1


def test_other_stage_without_text_gives_none():
    response = build_response(types=("loan_application", "Other"))
    other = next(i for i in response["output"] if i["model"].endswith("기타_서류_안내"))
    other["content"] = [{"type": "output_text", "text": ""}]
    assert summarize(response)["other_document_count"] is None


def test_plain_text_stages_still_accepted():
    # 분류 코드·기타 안내·위험도 Markdown 은 JSON 이 아닌 텍스트가 정상이다
    summary = summarize(build_response(types=("Other", "consent_form")))
    assert summary["document_types"] == ["Other", "consent_form"]
    assert summary["other_document_count"] == 1
    assert summary["risk_level"] == "상"
