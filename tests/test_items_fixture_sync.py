# ==========================================================================
#  백엔드 ↔ 화면 공유 자료 잇기(review-items T3) — 화면 테스트 자료 src/services/api/fixtures/items-result.json 의
#  result.items 가 백엔드 imask_backend.items.build_items 가 같은 documents·findings + 서류 index 1 의 실패한 필수 항목
#  규칙으로 만든 값과 **정확히** 같은지(키 순서 포함) 지킨다. 화면 매핑 테스트(item-mapping·detailModel.items·
#  reportModel.items)가 이 자료를 쓰므로, 백엔드 규칙이 바뀌면 여기서 먼저 깨진다. 자료는 읽기만 한다(고치지 않는다).
#  - 서류 index 1: validation 'red' + checks 에 applicant_name_detected 실패(left.field applicant_name, left.value 정수 0
#    — 지금 워크플로우의 필수항목_검증 모양). 그 밖 서류는 검증 checks 없음(None).
#  - tests/view_contract.py 의 items 검사(assert_items)도 통과해야 한다.
#  합성 자료만 쓴다(원문 값은 출력·메시지에 옮기지 않는다 — 실패 메시지는 위치·키 이름만).
# ==========================================================================

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fake_items import NAME_RULE, rule
from view_contract import EVIDENCE_KEYS, ITEM_KEYS, assert_items

from imask_backend.items import build_items

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "src" / "services" / "api" / "fixtures"
ITEMS_FIXTURE = FIXTURES / "items-result.json"
DONE_FIXTURE = FIXTURES / "done-result.json"
FAILED_INDEX = 1  # 필수 항목 검증에 실패한 서류


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_bytes().decode("utf-8"))


def _failing_checks() -> list[dict[str, Any]]:
    """서류 index 1 의 검증 checks — 신청인 성명 규칙 하나가 실패(값 길이 0)."""
    check = rule()
    assert check["name"] == NAME_RULE == "applicant_name_detected"
    assert check["passed"] is False
    left = check["conditions"]["left"]
    assert left["field"] == "applicant_name" and type(left["value"]) is int and left["value"] == 0
    return [check]


def _checks_for(documents: list[dict[str, Any]]) -> list[Any]:
    """documents 와 같은 위치의 checks 원래 값(build_items 입력) — 서류 index 1 만 실패 규칙, 나머지 None."""
    return [_failing_checks() if doc.get("index") == FAILED_INDEX else None for doc in documents]


def _backend_items(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    return build_items(fixture["documents"], fixture["findings"], _checks_for(fixture["documents"]))


def _first_difference(got: list[dict[str, Any]], want: list[Any]) -> str:
    """처음 다른 자리(항목 번호·키 이름만 — 값은 넣지 않는다)."""
    if len(got) != len(want):
        return f"개수 {len(got)} ≠ {len(want)}"
    for n, (a, b) in enumerate(zip(got, want, strict=True)):
        if not isinstance(b, dict) or list(a) != list(b):
            return f"items[{n}] 키 순서"
        for key in a:
            if a[key] != b[key]:
                return f"items[{n}].{key}"
            if key == "evidence" and any(list(x) != list(y) for x, y in zip(a[key], b[key], strict=True)):
                return f"items[{n}].evidence 키 순서"
    return "같음"


def test_fixture_items_equal_backend_build_items_exactly() -> None:
    fixture = _load(ITEMS_FIXTURE)
    got = _backend_items(fixture)
    want = fixture["items"]
    assert got == want, _first_difference(got, want)
    # 키 순서까지(파이썬 dict 비교는 순서를 보지 않는다) — 같은 바이트로 직렬화되는지
    assert json.dumps(got, ensure_ascii=False) == json.dumps(want, ensure_ascii=False), _first_difference(got, want)
    for item in want:
        assert list(item) == list(ITEM_KEYS)
        assert all(list(evidence) == list(EVIDENCE_KEYS) for evidence in item["evidence"])


def test_fixture_items_pass_the_view_contract_items_check() -> None:
    fixture = _load(ITEMS_FIXTURE)
    assert_items(fixture["items"], fixture["documents"], fixture["findings"])


def test_fixture_shape_is_what_the_screen_tests_expect() -> None:
    # 화면 테스트가 기대하는 모양: 8개 — 종류 lowconf 4 · missing 1 · nolocation 2 · other 1, 실패 서류는 validation 'red'
    fixture = _load(ITEMS_FIXTURE)
    items = fixture["items"]
    assert [i["number"] for i in items] == [f"R-{n:02d}" for n in range(1, 9)]
    counts: dict[str, int] = {}
    for item in items:
        counts[item["type"]] = counts.get(item["type"], 0) + 1
    assert counts == {"lowconf": 4, "missing": 1, "nolocation": 2, "other": 1}
    (missing,) = [i for i in items if i["type"] == "missing"]
    assert missing["id"] == f"missing:{FAILED_INDEX}:{NAME_RULE}"
    assert missing["title"] == "신청인 성명이 없습니다"
    validations = {d["index"]: d["validation"] for d in fixture["documents"]}
    assert validations[FAILED_INDEX] == "red"
    assert all(v in ("green", None) for i, v in validations.items() if i != FAILED_INDEX)


def test_fixture_is_the_done_result_copy_plus_the_failed_document() -> None:
    # items-result.json = done-result.json 사본 + 서류 index 1 의 validation 'red' + items — findings·overall 등은 같다
    items_fixture, done_fixture = _load(ITEMS_FIXTURE), _load(DONE_FIXTURE)
    assert "items" not in done_fixture  # 옛 결과(검토사항 0개) 자료는 그대로
    assert set(items_fixture) == set(done_fixture) | {"items", "links", "decision", "bundle_check"}
    for key in done_fixture:
        if key != "documents":
            assert items_fixture[key] == done_fixture[key], key
    changed = [
        a["index"] for a, b in zip(items_fixture["documents"], done_fixture["documents"], strict=True) if a != b
    ]
    assert changed == [FAILED_INDEX]
    # checks 를 볼 수 없으면(verdict 'red' 만) 규칙 항목 대신 1′ verdict 항목이 같은 자리에 온다 — 나머지는 같은 순서
    without = build_items(items_fixture["documents"], items_fixture["findings"], None)
    want_ids = [f"verdict:{FAILED_INDEX}" if i["type"] == "missing" else i["id"] for i in items_fixture["items"]]
    assert [i["id"] for i in without] == want_ids
