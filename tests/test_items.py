# ==========================================================================
#  imask_backend.items — 검토사항 만들기(review-items BRIEF §5.3, 네트워크 없음 · 합성 값만)
#  - 지금 워크플로우(위임장 합침 — fake_items.merged_result)와 예전 응답(위임장 따로 — fake_findings.stored_result) 모양의
#    종류·개수·id·번호·쪽·근거, 검증 실패 서류(missing:<i>:applicant_name_detected · 신청인 성명이 없습니다 · 1쪽 열기)
#  - 경계 강건성: checks·passed·name·conditions/left·verdict·조사·탐지 항목·서류·계약 id·저장 키·예외 격리·로그에 값 없음·성능
#  - 응답 모양(키 순서·R-nn·근거 키), findings.py 짝짓기(verdict + checks 한 번에), build_items 실패 → items [] 만
#  - RTYPE 동기화(src/display/rules.ts 를 읽기만), reviews.review_scope 와 같은 번호·이름
# ==========================================================================

from __future__ import annotations

import logging
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from api_fakes import FakeStore
from fake_findings import stored_result
from fake_items import (
    BOX,
    NAME_RULE,
    NO_VALUE,
    Spec,
    bundle_result,
    failing_result,
    merged_result,
    rule,
    vdoc,
    vfinding,
)
from view_contract import ITEM_KEYS, assert_items, assert_view

from imask_backend import findings as findings_module
from imask_backend import items as items_module
from imask_backend.findings import build_view
from imask_backend.items import ITEM_TYPES, MAX_CHECKS, MATERIALS, Material, build_items
from imask_backend.reviews import review_scope, row_view, storage_key

ROOT = Path(__file__).resolve().parents[1]
RULES_TS = ROOT / "src" / "display" / "rules.ts"

OPEN_FIRST = {"label": "1쪽 열기", "finding_ids": [], "finding_id": None}
MISSING_TEXT = ("필수 항목 검증을 통과하지 못했습니다.", "원본에서 직접 확인해 주세요.")
VERDICT_TEXT = (
    "필수 항목 검증을 통과하지 못했습니다",
    "통과하지 못한 항목을 결과에서 찾지 못했습니다.",
    "원본에서 필수 항목을 직접 확인해 주세요.",
)


def ids(items: list[dict[str, Any]]) -> list[str]:
    return [i["id"] for i in items]


def one_doc(checks: Any = None, *, validation: Any = "green", kind: str = "extracted", start: int = 1, end: int | None = None) -> list[dict[str, Any]]:
    return build_items([vdoc(0, start, end, kind=kind, validation=validation)], [], [checks])


@contextmanager
def imask_log() -> Iterator[list[str]]:
    """'imask' 로거(propagate=False)에 직접 붙인 핸들러로 모든 로그 글을 모은다(test_review_quiet_reads 와 같은 방식)."""
    lines: list[str] = []

    class Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            lines.append(self.format(record))

    logger = logging.getLogger("imask")
    handler = Collect(logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))
    level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        yield lines
    finally:
        logger.removeHandler(handler)
        logger.setLevel(level)


# --- 실제 응답 모양(합성 재현) ---------------------------------------------------------------------------------


def test_merged_workflow_shape_items() -> None:
    # 2026-11-04 워크플로우(위임장 합침): lowconf 3(서류 0·2·3) + other 1, 검증은 모두 통과 → missing 없음
    view = build_view(merged_result())
    assert_view(view)
    assert (len(view["documents"]), len(view["findings"])) == (5, 26)
    items = view["items"]
    assert [(i["number"], i["id"], i["type"], i["document_index"], i["page"]) for i in items] == [
        ("R-01", "lowconf:0", "lowconf", 0, 1),
        ("R-02", "lowconf:2", "lowconf", 2, 3),
        ("R-03", "lowconf:3", "lowconf", 3, 5),
        ("R-04", "other:4", "other", 4, 6),
    ]
    assert [i["title"] for i in items[:3]] == ["인식 신뢰도가 낮은 항목 4건", "인식 신뢰도가 낮은 항목 3건", "인식 신뢰도가 낮은 항목 3건"]
    assert items[0]["desc"] == "D1-06, D1-08, D1-09, D1-10의 값이 틀렸을 수 있습니다."
    assert items[1]["desc"] == "D3-05, D3-06, D3-09의 값이 틀렸을 수 있습니다."
    # 서류 2 는 3–4쪽 — low 항목이 3쪽 2개·4쪽 1개라 근거 2개(서류 안 쪽 1·2)
    assert items[1]["evidence"] == [
        {"label": "1쪽 값 보기", "page": 3, "finding_ids": ["2:employer_info", "2:income_info"], "finding_id": None},
        {"label": "2쪽 값 보기", "page": 4, "finding_ids": ["2:other_person_contact"], "finding_id": None},
    ]
    assert items[3]["evidence"] == [{**OPEN_FIRST, "page": 6}]
    assert (items[3]["title"], items[3]["desc"], items[3]["next"]) == (
        "기타 서류로 분류된 문서",
        "워크플로우가 지원 서류 종류에 해당하지 않는 기타 서류로 분류했습니다.",
        "원본에 개인정보가 있는지 직접 확인해 주세요.",
    )


def test_old_workflow_shape_items() -> None:
    # 예전 응답(위임장 따로): lowconf 4 + nolocation 1(3쪽 income_info — page -1·좌표 없음) + other 1
    view = build_view(stored_result())
    assert_view(view)
    items = view["items"]
    assert ids(items) == ["lowconf:0", "nolocation:2:income_info", "lowconf:2", "lowconf:3", "lowconf:4", "other:5"]
    assert [i["number"] for i in items] == ["R-01", "R-02", "R-03", "R-04", "R-05", "R-06"]
    nolocation = items[1]
    assert nolocation == {
        "id": "nolocation:2:income_info",
        "number": "R-02",
        "type": "nolocation",
        "document_index": 2,
        "page": 3,
        "finding_id": "2:income_info",
        "title": "원문 위치가 없는 탐지 항목",
        "desc": "D3-05 소득 정보 — 원문 좌표가 없어 강조할 수 없습니다.",
        "next": "원본에서 직접 찾아 확인해 주세요.",
        "evidence": [{"label": "1쪽 열기", "page": 3, "finding_ids": ["2:income_info"], "finding_id": "2:income_info"}],
        "link_id": None,
    }
    # 위치 없는 low 항목(income_info)은 수(n)에는 들고 근거에는 없다
    assert (items[2]["title"], items[2]["desc"]) == ("인식 신뢰도가 낮은 항목 2건", "D3-04, D3-05의 값이 틀렸을 수 있습니다.")
    assert items[2]["evidence"] == [{"label": "1쪽 값 보기", "page": 3, "finding_ids": ["2:employer_info"], "finding_id": None}]


def test_failed_validation_document_makes_missing_item() -> None:
    view = build_view(failing_result())
    assert_view(view)
    assert view["items"] == [
        {
            "id": "missing:1:applicant_name_detected",
            "number": "R-01",
            "type": "missing",
            "document_index": 1,
            "page": 2,  # 서류 첫 쪽(2–3쪽 서류)
            "finding_id": None,
            "title": "신청인 성명이 없습니다",
            "desc": MISSING_TEXT[0],
            "next": MISSING_TEXT[1],
            "evidence": [{**OPEN_FIRST, "page": 2}],
            "link_id": None,
        }
    ]
    assert [d["validation"] for d in view["documents"]] == ["green", "red", "green"]  # documents[].validation 은 그대로


def test_items_text_has_no_raw_values() -> None:
    # 원문 값·검증 reason·verdict 글자·기타 안내 본문은 검토사항 글에 넣지 않는다
    specs = [
        Spec("loan_application", (1, 1), {"applicant_name": ("원문값센티널", None, "low")}, validate=("verdict센티널", [rule()])),
        Spec("Other", (2, 2), validate=None, guide="안내본문센티널"),
    ]
    view = build_view(bundle_result(specs))
    text = repr(view["items"])
    for sentinel in ("원문값센티널", "verdict센티널", "합성 사유 문장", "안내본문센티널"):
        assert sentinel not in text
    assert ids(view["items"]) == ["missing:0:applicant_name_detected", "nolocation:0:applicant_name", "lowconf:0", "other:1"]


# --- 응답 모양 --------------------------------------------------------------------------------------------


def test_item_and_evidence_keys_are_exact_and_ordered() -> None:
    items = build_items(
        [vdoc(0, validation="red", kind="other")],
        [vfinding(0, "a", boxes=[]), vfinding(0, "b", confidence="low")],
        [[rule()]],
    )
    assert [i["type"] for i in items] == ["missing", "nolocation", "lowconf", "other"]  # 한 서류 안 종류 순서
    for item in items:
        assert tuple(item) == ITEM_KEYS
        for evidence in item["evidence"]:
            assert tuple(evidence) == ("label", "page", "finding_ids", "finding_id")


def test_documents_then_kinds_order_and_numbers_continue() -> None:
    docs = [vdoc(1, kind="other"), vdoc(0, validation="red")]  # documents 순서와 상관없이 index 순
    finds = [vfinding(1, "x", boxes=[]), vfinding(0, "y", confidence="low")]
    items = build_items(docs, finds, [None, None])
    assert ids(items) == ["verdict:0", "lowconf:0", "nolocation:1:x", "other:1"]
    assert [i["number"] for i in items] == ["R-01", "R-02", "R-03", "R-04"]


def test_numbers_get_three_digits_from_one_hundred() -> None:
    finds = [vfinding(0, f"k{n}", boxes=[]) for n in range(120)]
    items = build_items([vdoc(0)], finds)
    assert items[98]["number"] == "R-99" and items[99]["number"] == "R-100" and items[119]["number"] == "R-120"
    assert_items(items, [vdoc(0)], finds)


def test_no_documents_no_items() -> None:
    assert build_items([], []) == []
    assert build_items(None, None) == []
    assert build_view({})["items"] == []
    assert build_view(None)["items"] == []


# --- checks 모양 -----------------------------------------------------------------------------------------


@pytest.mark.parametrize("checks", [NO_VALUE, None, "문자열", {"name": NAME_RULE, "passed": False}, 5, []], ids=["없음", "null", "문자열", "객체", "숫자", "빈 목록"])
def test_checks_that_are_not_a_list_make_no_rule_item_but_verdict_still_counts(checks: Any) -> None:
    value = None if checks is NO_VALUE else checks
    assert one_doc(value, validation="green") == []
    assert ids(one_doc(value, validation="red")) == ["verdict:0"]


def test_checks_without_validation_content_in_the_result() -> None:
    # 검증 content 가 아예 없거나(verdict·checks 둘 다 없음) checks 키만 없는 경우
    view = build_view(bundle_result([Spec("loan_application", (1, 1), validate=None)]))
    assert view["items"] == [] and view["documents"][0]["validation"] is None
    view = build_view(bundle_result([Spec("loan_application", (1, 1), validate=("red", NO_VALUE))]))
    assert ids(view["items"]) == ["verdict:0"]


def test_non_object_entries_in_checks_are_skipped() -> None:
    items = one_doc([None, 1, "규칙", [rule()], rule(name="진짜 규칙", field_name="모르는키")])
    assert ids(items) == ["missing:0:진짜 규칙"] and items[0]["title"] == "진짜 규칙이 없습니다"


def test_only_the_first_200_checks_are_read() -> None:
    passed = [rule(name=f"r{n}", passed=True) for n in range(MAX_CHECKS)]
    assert one_doc([*passed, rule(name="r201")]) == []  # 201번째 실패는 무시
    assert ids(one_doc([*passed[:-1], rule(name="r200")])) == ["missing:0:r200"]  # 200번째는 본다


def test_huge_checks_list_is_fast() -> None:
    checks = [rule(name=f"r{n}") for n in range(100_000)]
    started = time.perf_counter()
    items = one_doc(checks)
    assert time.perf_counter() - started < 2.0
    assert len(items) == MAX_CHECKS


@pytest.mark.parametrize("passed", ["false", 0, 1, None, NO_VALUE, [], True], ids=["문자열", "0", "1", "null", "없음", "목록", "True"])
def test_passed_must_be_exactly_false(passed: Any) -> None:
    check = rule(passed=None if passed is NO_VALUE else passed, omit=("passed",) if passed is NO_VALUE else ())
    assert one_doc([check]) == []


# --- 규칙 이름 ----------------------------------------------------------------------------------------------

JS_SPACES = "\t\n\v\f\r         　﻿"


@pytest.mark.parametrize(
    "name",
    [NO_VALUE, None, 5, "", "   ", JS_SPACES, "a" * 101, "a" * 100_000, "a\x00b", "a\ud800b", "a\x07b", "a\x1fb", "\U0001f600" * 101],
    ids=["없음", "null", "숫자", "빈", "공백만", "JS공백만", "101자", "100000자", "NUL", "서로게이트", "제어문자", "제어문자2", "비BMP101"],
)
def test_bad_rule_names_are_skipped(name: Any) -> None:
    check = rule(name=None if name is NO_VALUE else name, omit=("name",) if name is NO_VALUE else ())
    assert one_doc([check]) == []
    assert ids(one_doc([check], validation="red")) == ["verdict:0"]  # 규칙 항목이 없으니 1′ 은 만든다


def test_rule_name_limits_count_code_points() -> None:
    assert ids(one_doc([rule(name="a" * 100)])) == ["missing:0:" + "a" * 100]
    emoji = "\U0001f600" * 100  # 비 BMP 글자도 코드 포인트 하나
    assert ids(one_doc([rule(name=emoji)])) == ["missing:0:" + emoji]


def test_rule_names_are_js_trimmed_and_deduplicated() -> None:
    items = one_doc([rule(name="　규칙A﻿ "), rule(name="규칙A"), rule(name="규칙B", passed=True), rule(name=" 규칙B")])
    assert ids(items) == ["missing:0:규칙A", "missing:0:규칙B"]  # 같은 이름 두 번 실패 → 처음만, 통과 뒤 실패 → 실패 하나


def test_first_failure_of_a_name_wins_its_label() -> None:
    items = one_doc([rule(name="r", field_name="applicant_email"), rule(name="r", field_name="applicant_name")])
    assert [i["title"] for i in items] == ["이메일 주소가 없습니다"]


def test_huge_rule_name_is_fast() -> None:
    checks = [rule(name="가" * 100_000) for _ in range(MAX_CHECKS)]
    started = time.perf_counter()
    assert one_doc(checks) == []
    assert time.perf_counter() - started < 2.0


# --- conditions / left -----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "title"),
    [
        ({"field_name": "applicant_name"}, "신청인 성명이 없습니다"),
        ({"field_name": "applicant_email"}, "이메일 주소가 없습니다"),
        ({"field_name": "모르는_키"}, "applicant_name_detected이(가) 없습니다"),
        ({"field_name": 5}, "applicant_name_detected이(가) 없습니다"),
        ({"field_name": None}, "applicant_name_detected이(가) 없습니다"),
        ({"conditions": NO_VALUE, "omit": ("conditions",)}, "applicant_name_detected이(가) 없습니다"),
        ({"conditions": "객체 아님"}, "applicant_name_detected이(가) 없습니다"),
        ({"conditions": {"left": "객체 아님"}}, "applicant_name_detected이(가) 없습니다"),
        ({"conditions": {"left": {"field": "applicant_rrn"}}}, "주민등록번호가 없습니다"),  # value 키 없음 → 서류 단위
        ({"value": 3}, "신청인 성명이 없습니다"),  # 정수 → 서류 단위
        ({"value": NO_VALUE}, "신청인 성명이 없습니다"),  # 없음 → 서류 단위
        ({"value": "글"}, "신청인 성명이 없습니다"),
    ],
    ids=["대응표", "대응표2", "모르는키", "숫자", "null", "conditions없음", "conditions글", "left글", "value키없음", "정수", "value없음", "value글"],
)
def test_label_comes_from_the_field_table_or_the_rule_name(kwargs: dict[str, Any], title: str) -> None:
    items = one_doc([rule(**kwargs)])
    assert [i["title"] for i in items] == [title]
    assert ids(items) == ["missing:0:applicant_name_detected"]


@pytest.mark.parametrize("value", [None, [], [1, 0, 2]], ids=["null", "빈목록", "목록"])
def test_bundle_shaped_failures_make_no_item_and_block_the_verdict_item(value: Any) -> None:
    assert one_doc([rule(value=value)], validation="red") == []
    # 묶음 모양 실패와 서류 단위 실패가 함께면 서류 단위만
    assert ids(one_doc([rule(value=value), rule(name="r2")], validation="red")) == ["missing:0:r2"]
    # 묶음 모양이라도 통과면 상관없다 — 1′ 은 그대로 따진다
    assert ids(one_doc([rule(value=value, passed=True)], validation="red")) == ["verdict:0"]


# --- verdict(1′) ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("verdict", ["green", " Green ", "GREEN", "　green﻿"])
def test_green_verdicts_make_no_verdict_item(verdict: str) -> None:
    assert one_doc([], validation=verdict) == []


@pytest.mark.parametrize("verdict", ["yellow", "red", "모르는 글자", " RED "])
def test_other_verdicts_make_one_verdict_item(verdict: str) -> None:
    items = one_doc([], validation=verdict, start=3, end=5)
    assert items == [
        {
            "id": "verdict:0",
            "number": "R-01",
            "type": "missing",
            "document_index": 0,
            "page": 3,
            "finding_id": None,
            "title": VERDICT_TEXT[0],
            "desc": VERDICT_TEXT[1],
            "next": VERDICT_TEXT[2],
            "evidence": [{**OPEN_FIRST, "page": 3}],
            "link_id": None,
        }
    ]
    assert verdict.strip() not in repr(items)  # verdict 글자는 어디에도 내지 않는다


@pytest.mark.parametrize("verdict", ["", "   ", JS_SPACES, None, 5, {"v": "red"}, ["red"], True], ids=["빈", "공백", "JS공백", "null", "숫자", "객체", "목록", "bool"])
def test_missing_or_non_text_verdicts_make_no_verdict_item(verdict: Any) -> None:
    assert one_doc([], validation=verdict) == []


def test_rule_items_suppress_the_verdict_item() -> None:
    assert ids(one_doc([rule()], validation="red")) == ["missing:0:applicant_name_detected"]


def test_verdict_via_build_view_variants() -> None:
    for verdict, expected in (("green", []), ("  GREEN ", []), ("yellow", ["verdict:0"]), ("", []), (NO_VALUE, [])):
        view = build_view(bundle_result([Spec("loan_application", (1, 1), validate=(verdict, []))]))
        assert ids(view["items"]) == expected, verdict


# --- 주격 조사·자르기 --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "title"),
    [
        ("신청인 성명", "신청인 성명이 없습니다"),  # 받침 있음
        ("이메일 주소", "이메일 주소가 없습니다"),  # 받침 없음
        ("required_name", "required_name이(가) 없습니다"),  # 영문
        ("규칙7", "규칙7이(가) 없습니다"),  # 숫자
        ("규칙(필수)", "규칙(필수)이(가) 없습니다"),  # 괄호
        ("ㄱㄴ", "ㄱㄴ이(가) 없습니다"),  # 한글 자모만(음절 아님)
        ("가" * 41, "가" * 39 + "…이(가) 없습니다"),  # 40자 자르기 → '…' 로 끝남
        ("가" * 40, "가" * 40 + "가 없습니다"),  # 40자는 그대로
        ("핳", "핳이 없습니다"),  # 마지막 음절(U+D7A3)
    ],
)
def test_subject_particle_and_clipping(name: str, title: str) -> None:
    items = one_doc([rule(name=name, field_name="모르는키")])
    assert [i["title"] for i in items] == [title]


def test_clip_counts_code_points_and_replaces_after_clipping() -> None:
    assert items_module.clip_name("\U0001f600" * 40) == "\U0001f600" * 40
    assert items_module.clip_name("\U0001f600" * 41) == "\U0001f600" * 39 + "…"
    assert items_module.clip_name("a\x00b\ud800") == "a�b�"
    assert items_module.clip_name("\x00" * 100) == "�" * 39 + "…"


# --- 탐지 항목 ----------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("page", "located"),
    [(None, False), (0, False), (-1, False), (3, False), (True, False), (False, False), (10**30, False), ("1", False), (1.0, False), (1, True)],
    ids=["null", "0", "-1", "범위밖", "True", "False", "아주큰수", "문자열", "실수", "범위안"],
)
def test_location_needs_an_in_range_integer_page(page: Any, located: bool) -> None:
    items = build_items([vdoc(0, 1, 2)], [vfinding(0, "a", page=page)])
    if located:
        assert items == []
    else:
        assert ids(items) == ["nolocation:0:a"]
        assert items[0]["page"] == 1 and items[0]["evidence"][0]["page"] == 1  # 범위 밖·null → 서류 page_start


@pytest.mark.parametrize(("boxes", "located"), [([], False), (None, False), ("상자", False), ({}, False), (BOX, True), ([[]], True)])
def test_location_needs_a_non_empty_boxes_list(boxes: Any, located: bool) -> None:
    items = build_items([vdoc(0)], [vfinding(0, "a", boxes=boxes)])
    assert ids(items) == ([] if located else ["nolocation:0:a"])


def test_file_page_of_an_unlocated_finding_ignores_boxes() -> None:
    # 범위 안 page + 상자 없음 → 위치 없음이지만 쪽은 그 page(서류 안 쪽 3)
    items = build_items([vdoc(0, 5, 9)], [vfinding(0, "a", page=7, boxes=[])])
    assert items[0]["page"] == 7 and items[0]["evidence"] == [{"label": "3쪽 열기", "page": 7, "finding_ids": ["0:a"], "finding_id": "0:a"}]


def test_page_end_before_page_start_uses_the_start_as_the_range() -> None:
    items = build_items([vdoc(0, 4, 2)], [vfinding(0, "a", page=4, confidence="low"), vfinding(0, "b", page=3, boxes=BOX)])
    assert ids(items) == ["nolocation:0:b", "lowconf:0"]
    assert items[0]["page"] == 4 and items[1]["evidence"][0]["page"] == 4


@pytest.mark.parametrize(("confidence", "low"), [("low", True), ("high", False), (None, False), ("LOW", False), (" low", False), (0, False)])
def test_only_exact_low_confidence_counts(confidence: Any, low: bool) -> None:
    items = build_items([vdoc(0)], [vfinding(0, "a", confidence=confidence)])
    assert ids(items) == (["lowconf:0"] if low else [])


def test_findings_of_invisible_documents_are_ignored() -> None:
    docs = [vdoc(0), {**vdoc(1), "page_start": None, "page_end": None}]
    finds = [vfinding(1, "a", boxes=[]), vfinding(9, "b", boxes=[]), vfinding(True, "c", boxes=[]), "항목 아님", None]
    assert build_items(docs, finds) == []


def test_surrogate_and_nul_names_become_replacement_in_text() -> None:
    items = build_items([vdoc(0)], [vfinding(0, "x", label="이름\ud800\x00끝", boxes=[]), vfinding(0, "f\ud800", label="  ", boxes=[])])
    assert items[0]["desc"] == "D1-01 이름��끝 — 원문 좌표가 없어 강조할 수 없습니다."
    assert items[1]["desc"] == "D1-02 f� — 원문 좌표가 없어 강조할 수 없습니다."  # label 이 공백만이면 field


def test_unnamed_and_long_finding_names() -> None:
    items = build_items([vdoc(0)], [vfinding(0, "", label="", boxes=[]), vfinding(0, "x", label="가" * 100_000, boxes=[])])
    assert items[0]["desc"].startswith("D1-01 이름 없는 항목 — ")
    assert items[1]["desc"] == "D1-02 " + "가" * 39 + "… — 원문 좌표가 없어 강조할 수 없습니다."


def test_hundredth_finding_in_a_document_is_numbered_with_three_digits() -> None:
    finds = [vfinding(0, f"k{n}") for n in range(99)] + [vfinding(0, "last", boxes=[])]
    items = build_items([vdoc(0)], finds)
    assert items[0]["desc"].startswith("D1-100 last ")


def test_six_or_more_low_findings_use_the_rest_count() -> None:
    finds = [vfinding(0, f"k{n}", confidence="low") for n in range(8)]
    items = build_items([vdoc(0)], finds)
    assert items[0]["title"] == "인식 신뢰도가 낮은 항목 8건"
    assert items[0]["desc"] == "D1-01, D1-02, D1-03, D1-04, D1-05 외 3건의 값이 틀렸을 수 있습니다."
    five = build_items([vdoc(0)], finds[:5])
    assert five[0]["desc"] == "D1-01, D1-02, D1-03, D1-04, D1-05의 값이 틀렸을 수 있습니다."


def test_low_findings_spread_over_many_pages_keep_the_first_20_pages() -> None:
    # 30쪽 서류, 쪽마다 low 항목 하나(계약 순서는 쪽 역순) — 근거는 쪽 오름차순 앞 20쪽, n 은 30
    finds = [vfinding(0, f"k{p}", page=p, confidence="low") for p in range(30, 0, -1)]
    items = build_items([vdoc(0, 1, 30)], finds)
    item = items[0]
    assert item["title"] == "인식 신뢰도가 낮은 항목 30건"
    assert [e["page"] for e in item["evidence"]] == list(range(1, 21))
    assert [e["label"] for e in item["evidence"][:2]] == ["1쪽 값 보기", "2쪽 값 보기"]
    assert item["page"] == 1
    assert_items(items, [vdoc(0, 1, 30)], finds)


def test_low_findings_on_one_page_are_grouped_in_contract_order() -> None:
    finds = [vfinding(0, "b", page=2, confidence="low"), vfinding(0, "a", page=1, confidence="low"), vfinding(0, "c", page=2, confidence="low")]
    items = build_items([vdoc(0, 1, 2)], finds)
    assert items[0]["evidence"] == [
        {"label": "1쪽 값 보기", "page": 1, "finding_ids": ["0:a"], "finding_id": None},
        {"label": "2쪽 값 보기", "page": 2, "finding_ids": ["0:b", "0:c"], "finding_id": None},
    ]


def test_low_findings_without_location_have_no_evidence() -> None:
    items = build_items([vdoc(0, 3, 4)], [vfinding(0, "a", page=None, confidence="low")])
    assert ids(items) == ["nolocation:0:a", "lowconf:0"]
    assert items[1]["evidence"] == [] and items[1]["page"] == 3  # 근거가 없으면 서류 page_start


def test_finding_without_a_string_id_is_counted_but_not_referenced() -> None:
    finds = [vfinding(0, "a", fid=5, boxes=[], confidence="low"), vfinding(0, "b", confidence="low")]
    items = build_items([vdoc(0)], finds)
    assert ids(items) == ["lowconf:0"]  # nolocation 은 id 가 없어 만들지 않는다
    assert items[0]["title"] == "인식 신뢰도가 낮은 항목 2건" and items[0]["evidence"][0]["finding_ids"] == ["0:b"]


def test_duplicate_finding_ids_make_one_nolocation_item() -> None:
    items = build_items([vdoc(0)], [vfinding(0, "a", boxes=[]), vfinding(0, "a", boxes=[])])
    assert ids(items) == ["nolocation:0:a"]


# --- 서류 --------------------------------------------------------------------------------------------------------------


def test_invisible_documents_make_no_items() -> None:
    bad = [
        {**vdoc(0), "page_start": None},
        {**vdoc(1), "page_end": None},
        {**vdoc(2), "page_start": 0},
        {**vdoc(3), "index": -1},
        {**vdoc(4), "index": True},
        {**vdoc(5), "page_start": True},
        "서류 아님",
    ]
    assert build_items(bad, [], [[rule()]] * len(bad)) == []
    assert build_items([{**vdoc(0, kind="other"), "page_start": None, "page_end": None}], []) == []


def test_same_index_twice_uses_the_first_document_and_its_checks() -> None:
    docs = [vdoc(0, 3, 3, validation="red"), vdoc(0, 1, 1, kind="other")]
    items = build_items(docs, [], [[rule()], None])
    assert ids(items) == ["missing:0:applicant_name_detected"] and items[0]["page"] == 3


def test_other_kind_documents() -> None:
    assert ids(build_items([vdoc(0, kind="other")], [])) == ["other:0"]
    assert build_items([vdoc(0, kind="Other")], []) == []  # 화면 readDocSources 처럼 정확히 'other' 만
    view = build_view(bundle_result([Spec("Other", (1, 1), validate=None, guide="안내")]))
    assert ids(view["items"]) == ["other:0"]
    view = build_view(bundle_result([Spec("Other", (1, 1), validate=None)]))  # 안내 없어도 분류 코드가 Other 면 other
    assert ids(view["items"]) == ["other:0"]


# --- 계약 id·저장 키 ---------------------------------------------------------------------------------------------------------


def test_rule_names_with_special_characters_keep_them_in_the_id() -> None:
    name = 'a:b"c\\d 가\U0001f600'
    items = one_doc([rule(name=name)])
    assert ids(items) == ["missing:0:" + name]
    key = storage_key(items[0]["id"])
    assert key.isascii() and key == 'missing:0:a:b\\"c\\\\d \\uac00\\ud83d\\ude00'


def test_surrogate_finding_id_flows_into_the_nolocation_id_and_an_ascii_key() -> None:
    items = build_items([vdoc(0)], [vfinding(0, "x\ud800", boxes=[])])
    assert ids(items) == ["nolocation:0:x\ud800"] and items[0]["finding_id"] == "0:x\ud800"
    assert storage_key(items[0]["id"]) == "nolocation:0:x\\ud800"


def test_surrogate_ids_survive_build_view() -> None:
    view = build_view(bundle_result([Spec("loan_application", (1, 1), {"키\ud800": ("값", None, "high")})]))
    assert ids(view["items"]) == ["nolocation:0:키\ud800"]


# --- 짝짓기(findings.py) ------------------------------------------------------------------------------------------------------


def test_checks_pair_with_the_document_of_the_same_range() -> None:
    specs = [
        Spec("loan_application", (1, 1), validate=("green", [rule(passed=True)])),
        Spec("consent_form", (2, 2), validate=("green", [rule(name="r2")])),
    ]
    view = build_view(bundle_result(specs))
    assert ids(view["items"]) == ["missing:1:r2"]
    assert "checks" not in view["documents"][0]  # 응답 documents 에는 넣지 않는다


def test_checks_only_content_takes_the_slot_and_can_move_a_later_verdict() -> None:
    # 같은 쪽 범위의 서류 둘: 첫 검증 content 는 verdict 없이 checks 만, 둘째는 verdict 만 — 각각 한 서류씩 차지.
    # verdict 정규화 규칙은 그대로지만 배정은 달라진다: 예전(checks 만 있는 content 를 건너뜀)에는 red 가 서류 0 에,
    # 지금은 첫 자리를 checks 만 있는 content 가 차지해 서류 1 에 붙는다(review-items §5.3 이 허용한 변경 — V-T1-1 N1)
    specs = [
        Spec("loan_application", (1, 1), validate=(NO_VALUE, [rule(name="첫")])),
        Spec("consent_form", (1, 1), validate=("red", NO_VALUE)),
    ]
    view = build_view(bundle_result(specs))
    assert [d["validation"] for d in view["documents"]] == [None, "red"]
    assert ids(view["items"]) == ["missing:0:첫", "verdict:1"]


def test_content_without_verdict_or_checks_is_skipped() -> None:
    specs = [
        Spec("loan_application", (1, 1), validate=(NO_VALUE, NO_VALUE)),
        Spec("consent_form", (1, 1), validate=None),
    ]
    view = build_view(bundle_result(specs))
    assert [d["validation"] for d in view["documents"]] == [None, None] and view["items"] == []


def test_null_checks_with_no_verdict_is_skipped_like_before() -> None:
    specs = [Spec("loan_application", (1, 1), validate=(NO_VALUE, None)), Spec("consent_form", (1, 1), validate=("red", [rule()]))]
    view = build_view(bundle_result(specs))
    assert [d["validation"] for d in view["documents"]] == ["red", None]  # null checks 는 '없음' — 자리를 차지하지 않는다
    assert ids(view["items"]) == ["missing:0:applicant_name_detected"]


# --- 예외 격리·로그 ----------------------------------------------------------------------------------------------------------------

SECRET_RULE = "규칙센티널R9"
SECRET_FIELD = "필드센티널F3"


def test_one_candidate_failing_drops_only_that_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    original = items_module._nolocation_item

    def flaky(ctx: Any, finding: Any) -> Any:
        if finding.id == f"0:{SECRET_FIELD}":
            raise RuntimeError(f"값 {SECRET_FIELD}")
        return original(ctx, finding)

    monkeypatch.setattr(items_module, "_nolocation_item", flaky)
    docs = [vdoc(0, kind="other", validation="red")]
    finds = [vfinding(0, SECRET_FIELD, boxes=[]), vfinding(0, "b", boxes=[], confidence="low")]
    with imask_log() as log:
        items = build_items(docs, finds, [[rule(name=SECRET_RULE)]])
    assert ids(items) == [f"missing:0:{SECRET_RULE}", "nolocation:0:b", "lowconf:0", "other:0"]
    assert [i["number"] for i in items] == ["R-01", "R-02", "R-03", "R-04"]
    text = "\n".join(log)
    assert "RuntimeError" in text and "nolocation" in text
    assert SECRET_FIELD not in text and SECRET_RULE not in text


def test_one_material_failing_drops_only_that_material(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_ctx: Any) -> Any:
        raise ValueError(SECRET_RULE)

    patched = tuple(Material(m.name, m.type, boom) if m.name == "lowconf" else m for m in MATERIALS)
    monkeypatch.setattr(items_module, "MATERIALS", patched)
    with imask_log() as log:
        view = build_view(stored_result())
    assert ids(view["items"]) == ["nolocation:2:income_info", "other:5"]
    assert len(view["findings"]) == 29 and len(view["documents"]) == 6
    text = "\n".join(log)
    assert "ValueError" in text and SECRET_RULE not in text


def test_a_failing_check_is_skipped_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    original = items_module.failed_rule

    def flaky(check: Any) -> Any:
        if isinstance(check, dict) and check.get("name") == SECRET_RULE:
            raise KeyError(SECRET_RULE)
        return original(check)

    monkeypatch.setattr(items_module, "failed_rule", flaky)
    with imask_log() as log:
        items = one_doc([rule(name=SECRET_RULE), rule(name="다음")], validation="red")
    assert ids(items) == ["missing:0:다음"]
    assert SECRET_RULE not in "\n".join(log) and "KeyError" in "\n".join(log)


def test_a_failing_finding_is_left_out_of_the_materials_but_keeps_numbering(monkeypatch: pytest.MonkeyPatch) -> None:
    original = items_module._visible_finding

    def flaky(finding: Any, num: str, start: int, end: int) -> Any:
        if finding.get("field") == SECRET_FIELD:
            raise TypeError(SECRET_FIELD)
        return original(finding, num, start, end)

    monkeypatch.setattr(items_module, "_visible_finding", flaky)
    with imask_log() as log:
        items = build_items([vdoc(0)], [vfinding(0, SECRET_FIELD, boxes=[]), vfinding(0, "b", boxes=[])])
    assert [(i["id"], i["desc"][:5]) for i in items] == [("nolocation:0:b", "D1-02")]  # 번호는 그대로(reviews 와 같은 번호)
    assert SECRET_FIELD not in "\n".join(log)


def test_build_items_failing_empties_only_items(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: Any) -> Any:
        raise RuntimeError(f"값 {SECRET_FIELD}")

    monkeypatch.setattr(items_module, "_contexts", boom)
    with imask_log() as log:
        view = build_view(stored_result())
    assert view["items"] == []
    monkeypatch.undo()
    reference = build_view(stored_result())
    assert (view["documents"], view["findings"], view["overall"]) == (reference["documents"], reference["findings"], reference["overall"])
    text = "\n".join(log)
    assert "RuntimeError" in text and SECRET_FIELD not in text


def test_build_view_passes_the_imported_build_items(monkeypatch: pytest.MonkeyPatch) -> None:
    # findings 가 쓰는 build_items 가 실패해도(예: 다른 모양) items [] 만
    def boom(*_a: Any) -> Any:
        raise OverflowError("x")

    monkeypatch.setattr(findings_module, "build_items", boom)
    view = build_view(stored_result())
    assert view["items"] == [] and len(view["findings"]) == 29


def test_odd_mapping_values_do_not_raise() -> None:
    class Weird(dict):  # type: ignore[type-arg]
        def get(self, key: Any, default: Any = None) -> Any:
            raise RuntimeError("이상한 객체")

    # 서류가 이상하면 맥락 만들기가 실패 → [](예외는 밖으로 나가지 않는다)
    assert build_items([vdoc(0), Weird(index=1)], [vfinding(0, "a", boxes=[])]) == []
    # 탐지 항목·check 가 이상하면 그것만 빠진다
    items = build_items([vdoc(0)], [Weird(), vfinding(0, "a", boxes=[])], [[Weird(), rule()]])
    assert ids(items) == ["missing:0:applicant_name_detected", "nolocation:0:a"]


# --- 성능(선형) ---------------------------------------------------------------------------------------------------------------------


def test_large_inputs_finish_quickly() -> None:
    # 탐지 10,000(신뢰도 low·위치 없음 섞음)·규칙 10,000·이름 100,000자 — 이중 반복이 없음을 보이는 정도의 넉넉한 상한
    keys = {f"k{n}": ("값", None if n % 3 == 0 else 1, "low" if n % 2 == 0 else "high") for n in range(10_000)}
    keys["x" * 100_000] = ("값", None, "low")
    checks = [rule(name=("가" * 100_000) if n == 0 else f"r{n}") for n in range(10_000)]
    result = bundle_result([Spec("loan_application", (1, 1), keys, validate=("red", checks))])
    started = time.perf_counter()
    view = build_view(result)
    elapsed = time.perf_counter() - started
    assert elapsed < 2.0, elapsed
    kinds = [i["type"] for i in view["items"]]
    assert kinds.count("missing") == MAX_CHECKS - 1  # 첫 규칙은 이름이 길어 버림, 앞 200개만
    assert kinds.count("nolocation") == 3335 and kinds.count("lowconf") == 1


def test_many_documents_and_findings_stay_linear() -> None:
    # 서류 5,000 × 탐지 10,000 — 서류마다 탐지 항목을 다시 훑으면 5천만 번이라 넉넉한 상한도 넘는다
    docs = [vdoc(i) for i in range(5_000)]
    finds = [vfinding(n % 5_000, f"k{n}", boxes=[] if n % 2 else BOX, confidence="low" if n % 3 == 0 else "high") for n in range(10_000)]
    checks = [[rule(name=f"r{i}")] for i in range(5_000)]
    started = time.perf_counter()
    items = build_items(docs, finds, checks)
    assert time.perf_counter() - started < 2.0
    assert len(items) == 5_000 + 5_000 + sum(1 for i in range(5_000) if any((i + 5_000 * k) % 3 == 0 for k in range(2)))


# --- RTYPE 동기화·reviews 와 같은 번호 ----------------------------------------------------------------------------------------------


def test_item_types_match_screen_rtype() -> None:
    text = RULES_TS.read_text(encoding="utf-8")
    match = re.search(r"export const RTYPE = (\{.*?\n\}) (?:as const|satisfies)", text, re.DOTALL)
    assert match, "rules.ts 에 RTYPE 가 없다"
    pairs = re.findall(r"^\s*(\w+): \{ label: '([^']*)'", match.group(1), re.MULTILINE)
    assert pairs == list(ITEM_TYPES.items())  # 키·라벨·순서
    assert list(ITEM_TYPES)[-3:] == ["missing", "lowconf", "other"]
    assert {m.type for m in MATERIALS} <= set(ITEM_TYPES)


def _tricky_view() -> dict[str, Any]:
    docs = [vdoc(2, 5, 6), vdoc(0), {**vdoc(1), "page_start": None}, vdoc(0, 9, 9), "x", vdoc(7, 8, 8)]
    finds = [
        vfinding(0, "a", label=" 　이름﻿ "),
        vfinding(2, "b", label="", page=6),
        vfinding(1, "c"),  # 보이지 않는 서류
        "항목 아님",
        vfinding(0, "  ", label="  "),
        vfinding(7, "d", label=None, boxes=[]),
        vfinding(2, "e", label=5),
        vfinding(True, "f"),
        vfinding(0, "g", fid=3),
        *[vfinding(7, f"h{n}", confidence="low") for n in range(101)],
    ]
    finds[5]["label"] = None
    return {"documents": docs, "findings": finds, "overall": {}, "items": []}


def test_review_scope_numbers_and_names_match_the_items_module() -> None:
    view = _tricky_view()
    row = {"status": "done", "result": {}, "documents": []}
    scope = review_scope(row, view)
    assert scope is not None
    from_scope = sorted((t.num, t.label) for t in scope.targets)
    contexts = items_module._contexts(view["documents"], view["findings"], None)
    from_items = sorted((f.num, f.name) for ctx in contexts for f in ctx.findings)
    assert from_scope == from_items
    assert {("D1-01", "이름"), ("D1-02", "이름 없는 항목"), ("D1-03", "g"), ("D2-01", "b"), ("D2-02", "e"), ("D3-01", "d")} <= set(from_items)
    assert ("D3-102", "h100") in from_items and len(from_items) == 6 + 101
    # 서류 순번도 같다
    assert {ctx.index: ctx.number for ctx in contexts} == {0: 1, 2: 2, 7: 3}


def test_nolocation_text_uses_the_review_scope_number_and_name() -> None:
    view = _tricky_view()
    view["items"] = build_items(view["documents"], view["findings"])
    scope = review_scope({"status": "done", "result": {}, "documents": []}, view)
    assert scope is not None
    by_id = {t.id: t for t in scope.targets}
    nolocation = [i for i in view["items"] if i["type"] == "nolocation"]
    assert nolocation
    for item in nolocation:
        target = by_id[item["finding_id"]]
        assert item["desc"].startswith(f"{target.num} {items_module.clip_name(target.label)} — ")


def test_review_scope_items_from_a_real_view() -> None:
    store = FakeStore()
    analysis_id = store.put(status="done", job_id="j", result=stored_result())
    row = store.get_analysis(analysis_id)
    assert row is not None
    scope = review_scope(row, row_view(row))
    assert scope is not None
    assert [(t.id, t.num, t.label, t.writable) for t in scope.items] == [
        ("lowconf:0", "R-01", "인식 확인 필요", True),
        ("nolocation:2:income_info", "R-02", "위치 확인 필요", True),
        ("lowconf:2", "R-03", "인식 확인 필요", True),
        ("lowconf:3", "R-04", "인식 확인 필요", True),
        ("lowconf:4", "R-05", "인식 확인 필요", True),
        ("other:5", "R-06", "기타 서류", True),
    ]
