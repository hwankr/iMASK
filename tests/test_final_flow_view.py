# ==========================================================================
#  최종 흐름 결과 → 화면용 결과(final-flow T3, 네트워크 없음 · 합성 값만)
#  - build_view 의 새 키 links·decision·bundle_check 와 검토사항 새 재료(묶음_검증 missing·서류_대조 mismatch·weaklink,
#    link_id) — 고정 응답 다섯(tests/fixtures/final_flow A~E)의 기대값(키·개수·상태·id·종류 순서·글 정확히)
#  - 원문 값(value != masked)이 결과 어디에도 없음, 옛 응답은 빈 값(links []·null·null)이고 items 는 link_id null 만 더해짐
#  - API(TestClient + FakeStore): 조회 응답의 새 키, 새 종류 검토사항의 resolve_item·reopen_item(이력 target)
#  - 경계 강건성: 세 키 각각의 실패 격리, 이상한 쌍(보이지 않음·음수·bool·겹침·기준 자신·모르는 상태)·아주 많은 쌍(선형),
#    masked 가 문자열 아님·아주 긺·서로게이트, 대응표에 없는 field, 묶음 규칙 모양, 로그에 값 없음
# ==========================================================================

from __future__ import annotations

import copy
import functools
import json
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fake_findings import build_findings_response, stored_result
from fake_items import failing_result, merged_result, vdoc, vfinding
from fake_responses import build_response
from fake_reviews import ACTOR
from shared_ctx import ANALYSIS_KEYS, Ctx, ctx, install  # noqa: F401
from view_contract import LINK_KEYS, VIEW_KEYS, assert_items, assert_links, assert_view

from imask_backend import final_flow
from imask_backend import findings as findings_module
from imask_backend import items as items_module
from imask_backend.findings import build_view, empty_view
from imask_backend.items import (
    MAX_CHECKS,
    MAX_LINK_FIELDS,
    BundleCheck,
    DocBundle,
    LinkPair,
    build_items,
    build_links,
    bundle_parts,
    link_pairs,
    with_particle,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "final_flow"
RUNS = ("A_smoke", "B_blank_autotransfer", "C_mismatch", "D_blank_applicant", "E_team_forms")
NAMES = {code: name for code, (name, _group) in final_flow.FINAL_DOC_TYPES.items()}
TIME_LIMIT = 2.0

LINKED_BASIS = ["두 서류의 신청인 성명이 같습니다."]
LINKED_CHECK = "두 서류를 함께 보관·전달할 때 열람 권한을 확인해 주세요."
CHECK_ORIGINAL = "같은 고객의 서류인지 원본에서 확인해 주세요."
NOTHING = "비교할 신청인 성명이 없습니다."
DIFFERENT = "두 서류의 신청인 성명이 다릅니다."
MISSING_TEXT = ("필수 항목 검증을 통과하지 못했습니다.", "원본에서 직접 확인해 주세요.")
VERDICT_TEXT = ("필수 항목 검증을 통과하지 못했습니다", "통과하지 못한 항목을 결과에서 찾지 못했습니다.", "원본에서 필수 항목을 직접 확인해 주세요.")
ABSENT_TEXT = ("필수 서류가 묶음에 없습니다.", "빠진 서류가 있는지 원본에서 확인해 주세요.")
MISMATCH_DESC = "서류 대조에서 같은 고객으로 확인되지 않았습니다."


@functools.cache
def _raw(name: str) -> str:
    return (FIXTURES / f"{name}.json").read_bytes().decode("utf-8")


def load(name: str) -> dict[str, Any]:
    return json.loads(_raw(name))


def view_of(source: str | dict[str, Any]) -> dict[str, Any]:
    return build_view({"response": load(source) if isinstance(source, str) else source})


def ids(items: list[dict[str, Any]]) -> list[str]:
    return [i["id"] for i in items]


def change_bundle(response: dict[str, Any], change: Any) -> None:
    """묶음_검증 content[0].additional_values(JSON 문자열)를 풀어 고친 뒤 다시 문자열로."""
    entry = next(i for i in response["output"] if i["model"] == "Validate - 묶음_검증")
    additional = json.loads(entry["content"][0]["additional_values"])
    change(additional)
    entry["content"][0]["additional_values"] = json.dumps(additional, ensure_ascii=False)


def set_check(additional: dict[str, Any], name: str, **changes: Any) -> None:
    check = next(c for c in additional["checks"] if c["name"] == name)
    for key, value in changes.items():
        if key == "value":
            check["conditions"]["left"]["value"] = value
        else:
            check[key] = value


@contextmanager
def imask_log() -> Iterator[list[str]]:
    """'imask' 로거(propagate=False)에 직접 붙인 핸들러로 모든 로그 글을 모은다(test_items 와 같은 방식)."""
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


# --- 다섯 고정 응답의 기대값 ---------------------------------------------------------------------------------

LINKS = {
    "A_smoke": [
        ("link:0:1", "linked", "대출신청서 · 동의서"),
        ("link:0:2", "linked", "대출신청서 · 소득 증빙"),
        ("link:0:4", "linked", "대출신청서 · 채무내역"),
        ("link:0:3", "linked", "대출신청서 · 위임장"),
    ],
    "B_blank_autotransfer": [("link:0:1", "insufficient", "자동이체 신청서 · 위임장")],
    "C_mismatch": [("link:0:1", "unmatched", "대출신청서 · 동의서"), ("link:0:2", "linked", "대출신청서 · 소득 증빙")],
    "D_blank_applicant": [("link:0:1", "insufficient", "대출신청서 · 동의서")],
    "E_team_forms": [
        ("link:0:1", "linked", "체크카드 가입신청서 · FATCA/CRS 본인확인서"),
        ("link:0:2", "linked", "체크카드 가입신청서 · 위임장"),
    ],
}

ITEMS = {
    "A_smoke": [
        ("lowconf:0", "lowconf", "인식 신뢰도가 낮은 항목 4건"),
        ("nolocation:2:income_info", "nolocation", "원문 위치가 없는 탐지 항목"),
        ("lowconf:2", "lowconf", "인식 신뢰도가 낮은 항목 2건"),
        ("lowconf:3", "lowconf", "인식 신뢰도가 낮은 항목 1건"),
        ("lowconf:4", "lowconf", "인식 신뢰도가 낮은 항목 3건"),
        ("other:5", "other", "기타 서류로 분류된 문서"),
    ],
    "B_blank_autotransfer": [
        ("missing:0:신청서_신청인_성명", "missing", "신청인 성명이 없습니다"),
        ("missing:1:위임장_위임인_성명", "missing", "신청인 성명이 없습니다"),
        ("missing:1:위임장_대리인_성명", "missing", "제3자 성명이 없습니다"),
        ("weaklink:0:1", "weaklink", "연결 근거가 부족합니다"),
    ],
    "C_mismatch": [
        ("lowconf:0", "lowconf", "인식 신뢰도가 낮은 항목 2건"),
        ("mismatch:0:1", "mismatch", "대출신청서와 신청인 성명이 다릅니다"),
        ("lowconf:2", "lowconf", "인식 신뢰도가 낮은 항목 1건"),
    ],
    "D_blank_applicant": [
        ("missing:0:신청서_신청인_성명", "missing", "신청인 성명이 없습니다"),
        ("lowconf:0", "lowconf", "인식 신뢰도가 낮은 항목 2건"),
        ("weaklink:0:1", "weaklink", "연결 근거가 부족합니다"),
    ],
    "E_team_forms": [
        ("lowconf:0", "lowconf", "인식 신뢰도가 낮은 항목 2건"),
        ("other:3", "other", "기타 서류로 분류된 문서"),
    ],
}

# (risk_level, document_types 수, sensitive_categories 수, review_reasons)
DECISIONS = {
    "A_smoke": ("상", 5, 5, []),
    "B_blank_autotransfer": ("검토 필요", 2, 0, ["필수 항목 누락"]),
    "C_mismatch": ("검토 필요", 3, 4, ["서류 간 불일치"]),
    "D_blank_applicant": ("검토 필요", 2, 3, ["필수 항목 누락"]),
    "E_team_forms": ("상", 3, 4, []),
}

RULES = ("신청서_신청인_성명", "확인서_신청인_성명", "증빙_신청인_성명", "위임장_위임인_성명", "위임장_대리인_성명")
BUNDLES = {
    "A_smoke": ("green", ("pass", "pass", "pass", "pass", "pass")),
    "B_blank_autotransfer": ("red", ("fail", "absent", "absent", "fail", "fail")),
    "C_mismatch": ("yellow", ("pass", "pass", "pass", "absent", "absent")),
    "D_blank_applicant": ("red", ("fail", "pass", "absent", "absent", "absent")),
    "E_team_forms": ("yellow", ("pass", "pass", "absent", "pass", "pass")),
}


@pytest.mark.parametrize("name", RUNS)
def test_fixture_view_has_the_new_keys_and_keeps_the_contract(name: str) -> None:
    view = view_of(name)
    assert tuple(view) == VIEW_KEYS
    assert_view(view)


@pytest.mark.parametrize("name", RUNS)
def test_fixture_links(name: str) -> None:
    links = view_of(name)["links"]
    assert [(link["id"], link["state"], link["title"]) for link in links] == LINKS[name]
    assert [link["number"] for link in links] == [f"L-{n:02d}" for n in range(1, len(links) + 1)]
    for link in links:
        assert tuple(link) == LINK_KEYS
        assert (link["field"], link["label"]) == ("applicant_name", "신청인 성명")
        if link["state"] == "linked":
            assert (link["status"], link["basis"], link["missing"], link["check"]) == ("confirmed", LINKED_BASIS, "", LINKED_CHECK)
        elif link["state"] == "unmatched":
            assert (link["status"], link["basis"], link["missing"], link["check"]) == ("check", [], DIFFERENT, CHECK_ORIGINAL)
        else:
            assert (link["status"], link["basis"], link["missing"], link["check"]) == ("check", [], NOTHING, CHECK_ORIGINAL)
        assert [d["document_index"] for d in link["docs"]] == [0, int(link["id"].rsplit(":", 1)[1])]


@pytest.mark.parametrize("name", RUNS)
def test_fixture_items(name: str) -> None:
    view = view_of(name)
    items = view["items"]
    assert [(i["id"], i["type"], i["title"]) for i in items] == ITEMS[name]
    assert [i["number"] for i in items] == [f"R-{n:02d}" for n in range(1, len(items) + 1)]
    links = {link["id"]: link for link in view["links"]}
    texts = {"mismatch": (MISMATCH_DESC, CHECK_ORIGINAL), "weaklink": (NOTHING, CHECK_ORIGINAL), "missing": MISSING_TEXT}
    for item in items:
        if item["type"] in texts:
            assert (item["desc"], item["next"]) == texts[item["type"]], item["id"]
        if item["type"] in ("mismatch", "weaklink"):
            anchor, target = item["id"].split(":")[1:]
            assert item["link_id"] == f"link:{anchor}:{target}" and item["link_id"] in links
            assert links[item["link_id"]]["state"] == ("unmatched" if item["type"] == "mismatch" else "insufficient")
        else:
            assert item["link_id"] is None
    assert_items(items, view["documents"], view["findings"], view["links"])


@pytest.mark.parametrize("name", RUNS)
def test_fixture_decision(name: str) -> None:
    decision = view_of(name)["decision"]
    level, types, categories, reasons = DECISIONS[name]
    assert list(decision) == ["risk_level", "document_types", "sensitive_categories", "review_reasons", "reason"]
    assert decision["risk_level"] == level
    assert (len(decision["document_types"]), len(decision["sensitive_categories"])) == (types, categories)
    assert decision["review_reasons"] == reasons
    assert isinstance(decision["reason"], str) and decision["reason"]
    assert decision == final_flow.read_decision(load(name))  # read_decision 그대로


@pytest.mark.parametrize("name", RUNS)
def test_fixture_bundle_check(name: str) -> None:
    bundle = view_of(name)["bundle_check"]
    verdict, statuses = BUNDLES[name]
    assert list(bundle) == ["verdict", "checks"] and bundle["verdict"] == verdict
    assert [(c["id"], c["name"], c["status"]) for c in bundle["checks"]] == [(r, r, s) for r, s in zip(RULES, statuses)]
    for check in bundle["checks"]:
        assert list(check) == ["id", "name", "severity", "status", "field", "label", "group"]
        assert check["severity"] == ("error" if check["name"].startswith("신청서") else "warning")
        assert check["group"] == check["name"].split("_")[0]
        assert (check["field"], check["label"]) == (
            ("other_person_name", "제3자 성명") if check["name"] == "위임장_대리인_성명" else ("applicant_name", "신청인 성명")
        )
    assert "documents" not in json.dumps(bundle, ensure_ascii=False)  # 규칙의 서류별 결과는 넣지 않는다


@pytest.mark.parametrize("name", RUNS)
def test_fixture_view_holds_no_raw_values(name: str) -> None:
    # 원문 value 는 findings[].value 에만 있다(계약). 원문과 masked 가 같은 값은 원래 가려진 값이라 찾지 않는다
    view = view_of(name)
    raws = {f["value"] for f in view["findings"] if f["value"] != f["masked"]}
    rest = {**view, "findings": [{k: v for k, v in f.items() if k != "value"} for f in view["findings"]]}
    dumped = json.dumps(rest, ensure_ascii=False)
    assert [len(v) for v in raws if v in dumped] == [], "원문 값이 결과에 들어 있다(길이만 표시)"
    # 새 키·검토사항만 따로 봐도 같다(더 짧은 글 — 검증 reason·conditions 의 값도 없다)
    new = json.dumps([view["links"], view["decision"], view["bundle_check"], view["items"]], ensure_ascii=False)
    assert [len(v) for v in raws if v in new] == []
    assert "gte" not in new and "nodeType" not in new and "conditions" not in new


def test_mismatch_item_of_c_exactly() -> None:
    view = view_of("C_mismatch")
    item = next(i for i in view["items"] if i["type"] == "mismatch")
    assert item == {
        "id": "mismatch:0:1",
        "number": "R-02",
        "type": "mismatch",
        "document_index": 1,
        "page": 2,
        "finding_id": None,
        "title": "대출신청서와 신청인 성명이 다릅니다",
        "desc": MISMATCH_DESC,
        "next": CHECK_ORIGINAL,
        "evidence": [{"label": "1쪽 값 보기", "page": 2, "finding_ids": ["1:applicant_name"], "finding_id": None}],
        "link_id": "link:0:1",
    }


def test_weaklink_and_bundle_missing_items_of_b_exactly() -> None:
    items = view_of("B_blank_autotransfer")["items"]
    first_page = {"finding_ids": [], "finding_id": None, "label": "1쪽 열기"}
    assert items[0] == {
        "id": "missing:0:신청서_신청인_성명",
        "number": "R-01",
        "type": "missing",
        "document_index": 0,
        "page": 1,
        "finding_id": None,
        "title": "신청인 성명이 없습니다",
        "desc": MISSING_TEXT[0],
        "next": MISSING_TEXT[1],
        "evidence": [{**first_page, "page": 1}],
        "link_id": None,
    }
    assert items[3] == {
        "id": "weaklink:0:1",
        "number": "R-04",
        "type": "weaklink",
        "document_index": 1,
        "page": 2,
        "finding_id": None,
        "title": "연결 근거가 부족합니다",
        "desc": NOTHING,
        "next": CHECK_ORIGINAL,
        "evidence": [{"label": "1쪽 열기", "page": 2, "finding_ids": [], "finding_id": None}],
        "link_id": "link:0:1",
    }


def test_link_rows_of_c_and_d_exactly() -> None:
    view = view_of("C_mismatch")
    masked = {f["id"]: f["masked"] for f in view["findings"]}
    assert view["links"][0] == {
        "id": "link:0:1",
        "number": "L-01",
        "status": "check",
        "state": "unmatched",
        "title": "대출신청서 · 동의서",
        "field": "applicant_name",
        "label": "신청인 성명",
        "docs": [
            {"document_index": 0, "page": 1, "fields": f"신청인 성명 {masked['0:applicant_name']}", "finding_ids": ["0:applicant_name"]},
            {"document_index": 1, "page": 2, "fields": f"신청인 성명 {masked['1:applicant_name']}", "finding_ids": ["1:applicant_name"]},
        ],
        "basis": [],
        "missing": DIFFERENT,
        "check": CHECK_ORIGINAL,
    }
    view = view_of("D_blank_applicant")
    masked = {f["id"]: f["masked"] for f in view["findings"]}
    # 기준 서류(신청서)의 신청인 성명이 비어 탐지 항목이 없다 — '값 없음'·서류 첫 쪽·id 없음
    assert view["links"][0]["docs"] == [
        {"document_index": 0, "page": 1, "fields": "신청인 성명 값 없음", "finding_ids": []},
        {"document_index": 1, "page": 2, "fields": f"신청인 성명 {masked['1:applicant_name']}", "finding_ids": ["1:applicant_name"]},
    ]
    assert (view["links"][0]["missing"], view["links"][0]["check"]) == (NOTHING, CHECK_ORIGINAL)


def test_final_flow_constants_match_items_constants() -> None:
    # items 는 순환 import 를 피해 같은 글자를 따로 둔다
    assert (items_module.LINK_LINKED, items_module.LINK_UNMATCHED, items_module.LINK_INSUFFICIENT) == (
        final_flow.LINK_LINKED,
        final_flow.LINK_UNMATCHED,
        final_flow.LINK_INSUFFICIENT,
    )
    assert (items_module.CHECK_FAIL, items_module.CHECK_ABSENT) == (final_flow.CHECK_FAIL, final_flow.CHECK_ABSENT)
    assert items_module.SEVERITY_ERROR in final_flow.SEVERITIES
    assert items_module.MAX_CHECKS == final_flow.MAX_CHECKS


# --- 묶음 규칙의 다른 모양(고정 응답을 고쳐서) --------------------------------------------------------------------


def _b_variant() -> dict[str, Any]:
    """B 를 고친 것: 확인서 규칙을 error 로(absent:) · 위임인 규칙 값 목록 길이가 서류 수와 다름(bundle:)."""
    response = load("B_blank_autotransfer")

    def change(additional: dict[str, Any]) -> None:
        set_check(additional, "확인서_신청인_성명", severity="error")
        set_check(additional, "위임장_위임인_성명", value=[0, 0])

    change_bundle(response, change)
    return response


def test_absent_error_and_bundle_level_failure_items() -> None:
    view = view_of(_b_variant())
    assert_view(view)
    assert [(i["number"], i["id"], i["document_index"], i["title"]) for i in view["items"]] == [
        ("R-01", "missing:0:신청서_신청인_성명", 0, "신청인 성명이 없습니다"),
        ("R-02", "absent:확인서_신청인_성명", 0, "확인서가 없습니다"),
        ("R-03", "bundle:위임장_위임인_성명", 0, VERDICT_TEXT[0]),
        ("R-04", "missing:1:위임장_대리인_성명", 1, "제3자 성명이 없습니다"),
        ("R-05", "weaklink:0:1", 1, "연결 근거가 부족합니다"),
    ]
    absent, bundle = view["items"][1], view["items"][2]
    assert (absent["desc"], absent["next"], absent["page"]) == (*ABSENT_TEXT, 1)
    assert absent["evidence"] == [{"label": "1쪽 열기", "page": 1, "finding_ids": [], "finding_id": None}]
    assert (bundle["desc"], bundle["next"]) == VERDICT_TEXT[1:]
    assert bundle["evidence"] == absent["evidence"]


# --- 옛 응답: 새 키는 빈 값, items 는 link_id null 만 더해짐 ---------------------------------------------------------


OLD_RESULTS = {
    "action": lambda: {"response": build_response()},
    "review": lambda: {"response": build_response(types=("loan_application",), risk="검토 필요", final="검토_안내")},
    "findings-fake": lambda: {"response": build_findings_response()},
    "stored": stored_result,
    "stages-only": lambda: stored_result(keep_response=False),
    "merged": merged_result,
    "failing": failing_result,
}


@pytest.mark.parametrize("make", list(OLD_RESULTS.values()), ids=list(OLD_RESULTS))
def test_old_workflow_results_have_empty_new_keys(make: Any) -> None:
    view = build_view(make())
    assert_view(view)
    assert (view["links"], view["decision"], view["bundle_check"]) == ([], None, None)
    assert all(item["link_id"] is None for item in view["items"])
    assert all(item["type"] not in ("mismatch", "weaklink") for item in view["items"])
    assert not any(item["id"].startswith(("bundle:", "absent:")) for item in view["items"])


def test_old_items_equal_the_items_without_bundle_materials() -> None:
    # 옛 응답은 묶음 재료가 없다 — bundle 없이 만든 검토사항과 같다
    for make in OLD_RESULTS.values():
        view = build_view(make())
        assert view["items"] == build_items(view["documents"], view["findings"], _checks_of(make()))


def _checks_of(result: Any) -> list[Any]:
    stages = findings_module.view_stages(result)
    docs, count = findings_module._documents(stages)
    findings_module._attach_extracts(stages, docs, count)
    findings_module._attach_checks(stages, docs)
    return [d.checks for d in sorted(docs, key=lambda d: d.index)]


def test_empty_view_has_the_new_keys() -> None:
    assert tuple(empty_view()) == VIEW_KEYS
    assert (empty_view()["links"], empty_view()["decision"], empty_view()["bundle_check"]) == ([], None, None)
    assert build_view(None) == empty_view() and build_view({}) == empty_view()


# --- 실패 격리 -------------------------------------------------------------------------------------------------

SECRET = "값센티널Q7"


def _boom(*_a: Any, **_k: Any) -> Any:
    raise RuntimeError(SECRET)


@pytest.mark.parametrize(
    ("target", "key", "empty"),
    [("build_links", "links", []), ("_decision_view", "decision", None), ("_bundle_check_view", "bundle_check", None)],
)
def test_one_new_key_failing_empties_only_that_key(monkeypatch: pytest.MonkeyPatch, target: str, key: str, empty: Any) -> None:
    reference = view_of("C_mismatch")
    monkeypatch.setattr(findings_module, target, _boom)
    with imask_log() as log:
        view = view_of("C_mismatch")
    assert view[key] == empty
    assert {k: v for k, v in view.items() if k != key} == {k: v for k, v in reference.items() if k != key}
    text = "\n".join(log)
    assert "RuntimeError" in text and key in text and SECRET not in text


def test_link_pairs_failing_drops_links_and_link_items_only(monkeypatch: pytest.MonkeyPatch) -> None:
    reference = view_of("C_mismatch")
    monkeypatch.setattr(findings_module, "link_pairs", _boom)
    view = view_of("C_mismatch")
    assert view["links"] == [] and ids(view["items"]) == ["lowconf:0", "lowconf:2"]
    for key in ("documents", "findings", "overall", "decision", "bundle_check"):
        assert view[key] == reference[key]


def test_bundle_parts_failing_drops_only_the_bundle_materials(monkeypatch: pytest.MonkeyPatch) -> None:
    reference = view_of("B_blank_autotransfer")
    monkeypatch.setattr(findings_module, "bundle_parts", _boom)
    view = view_of("B_blank_autotransfer")
    assert view["items"] == [] and view["links"] == reference["links"] and view["bundle_check"] == reference["bundle_check"]


@pytest.mark.parametrize(("reader", "key", "empty"), [("read_links", "links", []), ("read_decision", "decision", None), ("read_bundle_checks", "bundle_check", None)])
def test_a_reader_raising_empties_only_its_values(monkeypatch: pytest.MonkeyPatch, reader: str, key: str, empty: Any) -> None:
    reference = view_of("C_mismatch")
    monkeypatch.setattr(final_flow, reader, _boom)
    with imask_log() as log:
        view = view_of("C_mismatch")
    assert view[key] == empty
    for other in ("documents", "findings", "overall"):
        assert view[other] == reference[other]
    assert SECRET not in "\n".join(log)


def test_each_reader_runs_once_per_view(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, int] = {}
    for name in ("read_links", "read_bundle_checks", "read_decision"):
        original = getattr(final_flow, name)

        def counted(stages: Any, _name: str = name, _original: Any = original) -> Any:
            calls[_name] = calls.get(_name, 0) + 1
            return _original(stages)

        monkeypatch.setattr(final_flow, name, counted)
    view_of("C_mismatch")
    assert calls == {"read_links": 1, "read_bundle_checks": 1, "read_decision": 1}


def test_one_link_row_failing_keeps_the_others_numbered(monkeypatch: pytest.MonkeyPatch) -> None:
    original = items_module.link_view

    def flaky(pair: LinkPair, number: int) -> Any:
        if pair.id == "link:0:2":
            raise ValueError(SECRET)
        return original(pair, number)

    monkeypatch.setattr(items_module, "link_view", flaky)
    with imask_log() as log:
        links = view_of("A_smoke")["links"]
    assert [(link["id"], link["number"]) for link in links] == [("link:0:1", "L-01"), ("link:0:4", "L-02"), ("link:0:3", "L-03")]
    assert SECRET not in "\n".join(log) and "ValueError" in "\n".join(log)


def test_one_bundle_candidate_failing_drops_only_it(monkeypatch: pytest.MonkeyPatch) -> None:
    original = items_module._bundle_item

    def flaky(ctx: Any, part: BundleCheck) -> Any:
        if part.name == "위임장_위임인_성명":
            raise KeyError(SECRET)
        return original(ctx, part)

    monkeypatch.setattr(items_module, "_bundle_item", flaky)
    with imask_log() as log:
        items = view_of("B_blank_autotransfer")["items"]
    assert ids(items) == ["missing:0:신청서_신청인_성명", "missing:1:위임장_대리인_성명", "weaklink:0:1"]
    assert SECRET not in "\n".join(log)


# --- link_pairs·build_links 경계 ---------------------------------------------------------------------------------


def _docs(n: int) -> list[dict[str, Any]]:
    return [vdoc(i) for i in range(n)]


def _name_finding(index: int, masked: Any = "김*늘", **kw: Any) -> dict[str, Any]:
    finding = vfinding(index, "applicant_name", **kw)
    finding["masked"] = masked
    return finding


def _links(pairs: list[Any], *, anchor: Any = 0, field_name: Any = "applicant_name") -> dict[str, Any]:
    return {"field": field_name, "anchor_index": anchor, "pairs": pairs}


def _pair(target: Any, status: Any = "unmatched") -> dict[str, Any]:
    return {"id": f"link:0:{target}", "target_index": target, "group": "확인서", "status": status}


@pytest.mark.parametrize(
    "links",
    [None, "x", {}, _links([_pair(1)], anchor=None), _links(None), _links("x"), _links([_pair(1)], field_name=None), _links([_pair(1)], field_name=""), _links([_pair(1)], anchor=True), _links([_pair(1)], anchor=9)],
    ids=["None", "문자열", "빈객체", "기준없음", "쌍None", "쌍문자열", "field없음", "field빈", "기준bool", "기준보이지않음"],
)
def test_link_pairs_without_an_anchor_or_pairs_are_empty(links: Any) -> None:
    assert link_pairs(_docs(3), [], links, NAMES) == []


def test_odd_pairs_are_skipped_and_numbers_continue() -> None:
    docs = [*_docs(3), {**vdoc(5), "page_start": None}]  # 서류 5 는 쪽이 없어 보이지 않는다
    pairs = [
        "쌍 아님",
        _pair(7),  # 없는 서류
        _pair(-1),
        _pair(True),
        _pair(5),  # 보이지 않는 서류
        _pair(0),  # 기준 자신
        _pair(1, "모르는상태"),
        _pair(1, None),
        _pair(1),
        _pair(1, "linked"),  # 같은 대상 두 번 — 첫 쌍만
        _pair(2, "insufficient"),
    ]
    result = link_pairs(docs, [], _links(pairs), NAMES)
    assert [(p.id, p.state) for p in result] == [("link:0:1", "unmatched"), ("link:0:2", "insufficient")]
    rows = build_links(result)
    assert [(r["id"], r["number"]) for r in rows] == [("link:0:1", "L-01"), ("link:0:2", "L-02")]
    assert_links(rows, docs, [])


def test_link_sides_use_the_first_same_field_finding_and_masked_only() -> None:
    docs = [vdoc(0, 1, 2), vdoc(1, 3, 4)]
    finds = [
        vfinding(0, "applicant_phone"),
        _name_finding(0, "첫*값", page=2),
        _name_finding(0, "둘*값", fid="0:applicant_name#2"),
        {**_name_finding(1, "아이디 없음"), "id": 5},  # id 가 문자열이 아니면 대조 항목이 아니다
        _name_finding(1, "대*상", page=99),  # 범위 밖 쪽 → 서류 page_start
    ]
    rows = build_links(link_pairs(docs, finds, _links([_pair(1)]), NAMES))
    assert rows[0]["docs"] == [
        {"document_index": 0, "page": 2, "fields": "신청인 성명 첫*값", "finding_ids": ["0:applicant_name"]},
        {"document_index": 1, "page": 3, "fields": "신청인 성명 대*상", "finding_ids": ["1:applicant_name"]},
    ]
    assert "합성값" not in json.dumps(rows, ensure_ascii=False)  # 원문 value 는 쓰지 않는다


@pytest.mark.parametrize("masked", [None, 5, ["김*늘"], {"x": 1}, True])
def test_masked_that_is_not_text_shows_only_the_label(masked: Any) -> None:
    rows = build_links(link_pairs(_docs(2), [_name_finding(1, masked)], _links([_pair(1)]), NAMES))
    assert rows[0]["docs"][1] == {"document_index": 1, "page": 2, "fields": "신청인 성명", "finding_ids": ["1:applicant_name"]}


def test_long_and_surrogate_masked_are_clipped_and_replaced() -> None:
    long_masked = "*" * 100_000
    rows = build_links(link_pairs(_docs(3), [_name_finding(1, long_masked), _name_finding(2, "김\ud800*\x00늘")], _links([_pair(1), _pair(2)]), NAMES))
    fields = rows[0]["docs"][1]["fields"]
    assert len(fields) == MAX_LINK_FIELDS and fields.endswith("…") and fields.startswith("신청인 성명 ***")
    assert rows[1]["docs"][1]["fields"] == "신청인 성명 김�*�늘"
    json.dumps(rows, ensure_ascii=False).encode("utf-8")  # 인코딩할 수 있다


def test_field_outside_the_table_uses_the_field_itself() -> None:
    rows = build_links(link_pairs(_docs(2), [], _links([_pair(1, "insufficient")], field_name="custom_key"), NAMES))
    assert (rows[0]["field"], rows[0]["label"]) == ("custom_key", "custom_key")
    assert rows[0]["docs"][0]["fields"] == "custom_key 값 없음"
    assert rows[0]["missing"] == "비교할 custom_key이(가) 없습니다."
    items = build_items(_docs(2), [], None, bundle_parts(_docs(2), None, link_pairs(_docs(2), [], _links([_pair(1)], field_name="custom_key"), NAMES)))
    assert items[0]["title"] == "대출신청서와 custom_key이(가) 다릅니다"


def test_surrogate_field_and_long_label_are_safe_in_text() -> None:
    field_name = "키\ud800" + "가" * 60
    rows = build_links(link_pairs(_docs(2), [], _links([_pair(1, "linked")], field_name=field_name), NAMES))
    text = rows[0]["basis"][0]
    assert "\ud800" not in text and "�" in text and "…" in text
    assert rows[0]["label"] == field_name  # 대응표에 없는 키는 그대로(응답 경계가 escape 한다)


def test_document_names_come_from_the_final_doc_types_or_the_code() -> None:
    docs = [vdoc(0), {**vdoc(1), "type": "new_form_code"}, {**vdoc(2), "type": None}, {**vdoc(3), "type": "income_proof"}]
    rows = build_links(link_pairs(docs, [], _links([_pair(1), _pair(2), _pair(3, "linked")]), NAMES))
    assert [r["title"] for r in rows] == ["대출신청서 · new_form_code", "대출신청서 · ", "대출신청서 · 소득 증빙"]


def test_surrogate_and_long_document_codes_are_safe_in_titles() -> None:
    docs = [{**vdoc(0), "type": "코드\ud800"}, {**vdoc(1), "type": "x" * 100}]
    pairs = link_pairs(docs, [], _links([_pair(1)]), NAMES)
    rows = build_links(pairs)
    assert rows[0]["title"] == "코드� · " + "x" * 39 + "…"
    items = build_items(docs, [], None, bundle_parts(docs, None, pairs))
    assert items[0]["title"] == "코드�와(과) 신청인 성명이 다릅니다"
    json.dumps([rows, items], ensure_ascii=False).encode("utf-8")


@pytest.mark.parametrize(("name", "particle"), [("대출신청서", "와"), ("소득 증빙", "과"), ("위임장", "과"), ("FATCA", "와(과)"), ("", "와(과)"), ("기타…", "와(과)"), ("ㄱ", "와(과)")])
def test_with_particle(name: str, particle: str) -> None:
    assert with_particle(name) == particle


def test_many_pairs_are_linear() -> None:
    docs = _docs(500)
    finds = [_name_finding(i % 500) for i in range(10_000)]
    pairs = [_pair(i % 600, ("linked", "unmatched", "insufficient")[i % 3]) for i in range(100_000)]
    started = time.perf_counter()
    result = link_pairs(docs, finds, _links(pairs), NAMES)
    rows = build_links(result)
    items = build_items(docs, finds, None, bundle_parts(docs, None, result))
    assert time.perf_counter() - started < TIME_LIMIT
    assert len(rows) == 499 and rows[-1]["number"] == "L-499"  # 대상 서류마다 한 줄(기준 자신 빼고)
    assert len([i for i in items if i["type"] in ("mismatch", "weaklink")]) == len([r for r in rows if r["state"] != "linked"])


# --- bundle_parts 경계 ----------------------------------------------------------------------------------------------


def _check(name: Any = "규칙", status: Any = "fail", *, severity: Any = "warning", field_name: Any = "applicant_name", group: Any = "확인서", documents: Any = None) -> dict[str, Any]:
    return {"id": name, "name": name, "severity": severity, "passed": status == "pass", "field": field_name, "group": group, "status": status, "documents": documents}


def _bundle(*checks: Any, verdict: Any = "red") -> dict[str, Any]:
    return {"verdict": verdict, "checks": list(checks)}


def _items_for(bundle: Any, docs: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    docs = docs if docs is not None else _docs(3)
    return build_items(docs, [], None, bundle_parts(docs, bundle))


def test_fail_with_documents_marks_only_visible_not_ok_documents() -> None:
    documents = [
        {"index": 0, "ok": False},
        {"index": 1, "ok": True},
        {"index": 2, "ok": "false"},
        {"index": 9, "ok": False},  # 보이지 않는 서류
        {"index": True, "ok": False},
        "서류 아님",
        {"index": 0, "ok": False},  # 같은 서류 두 번 — 같은 계약 id 라 처음 것만
    ]
    items = _items_for(_bundle(_check(documents=documents)))
    assert [(i["id"], i["document_index"], i["title"]) for i in items] == [("missing:0:규칙", 0, "신청인 성명이 없습니다")]


@pytest.mark.parametrize("documents", ["x", 5, {"index": 0}], ids=["문자열", "숫자", "객체"])
def test_fail_with_odd_documents_makes_nothing(documents: Any) -> None:
    assert _items_for(_bundle(_check(documents=documents))) == []


def test_fail_without_documents_points_to_the_first_visible_document() -> None:
    docs = [{**vdoc(0), "page_start": None}, vdoc(2, 3, 4), vdoc(1, 2, 2)]  # 0 은 보이지 않음 → 첫 보이는 서류는 1
    items = _items_for(_bundle(_check(documents=None)), docs)
    assert [(i["id"], i["document_index"], i["page"], i["title"]) for i in items] == [("bundle:규칙", 1, 2, VERDICT_TEXT[0])]


def test_absent_only_for_error_severity_and_group_falls_back_to_the_rule_name() -> None:
    items = _items_for(
        _bundle(
            _check("a", "absent", severity="error", group="신청서"),
            _check("b", "absent", severity="warning"),
            _check("c", "absent", severity=None),
            _check("d", "absent", severity="error", group=None),
            _check("e", "absent", severity="error", group="  "),
            _check("f", "pass", severity="error"),
            _check("g", "unknown", severity="error"),
        )
    )
    assert [(i["id"], i["title"]) for i in items] == [("absent:a", "신청서가 없습니다"), ("absent:d", "d이(가) 없습니다"), ("absent:e", "e이(가) 없습니다")]


def test_surrogate_and_long_groups_are_clipped_and_replaced() -> None:
    items = _items_for(_bundle(_check("a", "absent", severity="error", group="묶음\ud800"), _check("b", "absent", severity="error", group="가" * 50)))
    assert [i["title"] for i in items] == ["묶음�이(가) 없습니다", "가" * 39 + "…이(가) 없습니다"]


def test_unreadable_bundle_checks_are_an_empty_list() -> None:
    response = load("B_blank_autotransfer")
    change_bundle(response, lambda a: a.update(checks="목록 아님"))
    view = view_of(response)
    assert view["bundle_check"] == {"verdict": "red", "checks": []}
    assert ids(view["items"]) == ["weaklink:0:1"]  # 묶음 missing 은 없고 연결 재료는 그대로
    assert_view(view)


@pytest.mark.parametrize("name", [None, 5, "", "   ", "가" * 101, "이름\x00", "이름\ud800"], ids=["None", "숫자", "빈", "공백", "101자", "NUL", "서로게이트"])
def test_bad_rule_names_make_no_bundle_item(name: Any) -> None:
    assert _items_for(_bundle(_check(name, documents=None))) == []


def test_rule_names_are_js_trimmed_and_labels_follow_the_table() -> None:
    items = _items_for(
        _bundle(
            _check("  앞뒤 공백 ", documents=[{"index": 0, "ok": False}]),
            _check("rule_x", field_name="모르는키", documents=[{"index": 1, "ok": False}]),
            _check("필드없음", field_name=None, documents=[{"index": 2, "ok": False}]),
        )
    )
    assert [(i["id"], i["title"]) for i in items] == [
        ("missing:0:앞뒤 공백", "신청인 성명이 없습니다"),
        ("missing:1:rule_x", "rule_x이(가) 없습니다"),
        ("missing:2:필드없음", "필드없음이 없습니다"),
    ]


@pytest.mark.parametrize("bundle", [None, "x", {}, {"checks": None}, {"checks": "x"}, {"checks": [None, 5, "규칙"]}])
def test_odd_bundle_values_make_nothing(bundle: Any) -> None:
    assert bundle_parts(_docs(2), bundle) == {}


def test_only_the_first_checks_are_read() -> None:
    passed = [_check(f"r{n}", "pass") for n in range(MAX_CHECKS)]
    assert _items_for(_bundle(*passed, _check("늦은", documents=None))) == []
    assert ids(_items_for(_bundle(*passed[:-1], _check("마지막", documents=None)))) == ["bundle:마지막"]


def test_no_visible_documents_no_parts() -> None:
    assert bundle_parts([], _bundle(_check(documents=None))) == {}
    assert bundle_parts([{**vdoc(0), "index": -1}], _bundle(_check(documents=None))) == {}


def test_bundle_failure_with_the_same_id_as_a_document_check_is_kept_once() -> None:
    docs = _docs(1)
    check = {"name": "규칙", "passed": False, "conditions": {"left": {"field": "applicant_name", "value": 0}}}
    items = build_items(docs, [], [[check]], bundle_parts(docs, _bundle(_check(documents=[{"index": 0, "ok": False}]))))
    assert ids(items) == ["missing:0:규칙"]


def test_kind_order_inside_one_document() -> None:
    # 서류 하나에 모든 재료: checks → bundle_checks → links → nolocation → lowconf → other
    docs = [vdoc(0), vdoc(1, kind="other", validation="red")]
    finds = [vfinding(1, "a", boxes=[]), vfinding(1, "b", confidence="low")]
    pairs = link_pairs(docs, finds, _links([_pair(1, "insufficient")]), NAMES)
    bundle = bundle_parts(docs, _bundle(_check("묶음", documents=[{"index": 1, "ok": False}])), pairs)
    check = {"name": "서류규칙", "passed": False, "conditions": {"left": {"field": "applicant_name", "value": 0}}}
    items = build_items(docs, finds, [None, [check]], bundle)
    assert [(i["id"], i["type"]) for i in items] == [
        ("missing:1:서류규칙", "missing"),
        ("missing:1:묶음", "missing"),
        ("weaklink:0:1", "weaklink"),
        ("nolocation:1:a", "nolocation"),
        ("lowconf:1", "lowconf"),
        ("other:1", "other"),
    ]


def test_build_items_keeps_old_calls_and_ignores_odd_bundle_values() -> None:
    docs, finds = _docs(1), [vfinding(0, "a", boxes=[])]
    expected = ids(build_items(docs, finds))
    assert ids(build_items(docs, finds, None)) == expected == ["nolocation:0:a"]
    for odd in ("x", {0: "x"}, {0: None}, {"0": DocBundle()}, [DocBundle()]):
        assert ids(build_items(docs, finds, None, odd)) == expected


def test_link_material_only_for_its_target_document() -> None:
    # 다른 서류에 잘못 놓인 쌍은 만들지 않는다(근거가 그 서류 안만 가리키게)
    docs = _docs(3)
    pair = link_pairs(docs, [], _links([_pair(1)]), NAMES)[0]
    assert build_items(docs, [], None, {2: DocBundle(links=(pair,))}) == []


def test_large_bundle_inputs_are_linear() -> None:
    docs = _docs(1000)
    documents = [{"index": i, "ok": i % 2 == 0} for i in range(1000)]
    checks = [_check(f"r{n}", documents=documents) for n in range(MAX_CHECKS)]
    started = time.perf_counter()
    items = _items_for(_bundle(*checks), docs)
    assert time.perf_counter() - started < TIME_LIMIT
    assert len(items) == MAX_CHECKS * 500


# --- API: 조회 응답과 새 종류의 해결·다시 열기 ----------------------------------------------------------------------


def _done(ctx: Ctx, response: dict[str, Any]) -> str:  # noqa: F811
    return ctx.store.put(status="done", job_id="job_done", result=stored_result(response))


def test_get_returns_the_new_keys(ctx: Ctx) -> None:  # noqa: F811
    analysis_id = _done(ctx, load("C_mismatch"))
    body = ctx.get(analysis_id).json()
    assert set(body) == ANALYSIS_KEYS
    result = body["result"]
    assert {"links", "decision", "bundle_check", "items"} <= set(result) and "response" not in result
    assert [link["id"] for link in result["links"]] == ["link:0:1", "link:0:2"]
    assert result["decision"]["risk_level"] == "검토 필요" and result["bundle_check"]["verdict"] == "yellow"
    assert ids(result["items"]) == ["lowconf:0", "mismatch:0:1", "lowconf:2"]
    assert result["items"][1]["link_id"] == "link:0:1"
    assert body["review"]["history"][1]["change"].endswith("검토사항 3건")
    ctx.no_upstage()


@pytest.mark.parametrize(
    ("source", "item_id", "target"),
    [
        ("C_mismatch", "mismatch:0:1", "R-02 값 불일치"),
        ("B_blank_autotransfer", "weaklink:0:1", "R-04 연결 근거 부족"),
        ("B_blank_autotransfer", "missing:1:위임장_대리인_성명", "R-03 필수 항목 없음"),
        ("B_variant", "absent:확인서_신청인_성명", "R-02 필수 항목 없음"),
        ("B_variant", "bundle:위임장_위임인_성명", "R-03 필수 항목 없음"),
    ],
)
def test_resolve_and_reopen_new_kinds_over_http(ctx: Ctx, source: str, item_id: str, target: str) -> None:  # noqa: F811
    analysis_id = _done(ctx, _b_variant() if source == "B_variant" else load(source))
    response = ctx.act(analysis_id, "resolve_item", item_id=item_id, note="원본 확인")
    assert response.status_code == 200, response.text
    review = response.json()["analysis"]["review"]
    value = review["items"][item_id]
    assert (value["resolved"], value["note"], value["resolved_by"]) == (True, "원본 확인", ACTOR)
    last = review["history"][-1]
    assert (last["kind"], last["target"], last["change"], last["reason"]) == ("resolve", target, "미해결 → 해결", "원본 확인")
    response = ctx.act(analysis_id, "reopen_item", item_id=item_id)
    assert response.status_code == 200, response.text
    review = response.json()["analysis"]["review"]
    assert review["items"][item_id]["resolved"] is False and review["items"][item_id]["note"] == "원본 확인"
    last = review["history"][-1]
    assert (last["kind"], last["target"], last["change"], last["reason"]) == ("reopenItem", target, "해결 → 미해결", "")
    ctx.no_upstage()


def test_unknown_link_item_is_404(ctx: Ctx) -> None:  # noqa: F811
    analysis_id = _done(ctx, load("A_smoke"))  # 모두 linked — mismatch·weaklink 없음
    response = ctx.act(analysis_id, "resolve_item", item_id="mismatch:0:1", note="")
    assert (response.status_code, response.json()["detail"]) == (404, "검토사항을 찾을 수 없습니다.")
