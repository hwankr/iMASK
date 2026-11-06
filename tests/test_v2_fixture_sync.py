# ==========================================================================
#  백엔드 ↔ 화면 공유 자료 잇기(web-v2 T2) — 화면 시험 자료 src/services/api/fixtures/v2-cases.json 이
#  설정 60 고정 응답 tests/fixtures/v2/case_<X>.json → analyses.build_result(설정 "60") → analyses.result_out
#  (조회 응답의 result — 브라우저가 받는 값)과 **바이트까지** 같은지 지킨다. 화면 시험(src/services/api/v2-cases.test.ts)이 이 자료를
#  쓰므로 백엔드 규칙이 바뀌면 여기서 먼저 깨진다.
#    A 판정_상(묶음 · 표 칸 · weaklink · insufficient) · E 판정_중(항목 없음) · L·M 판정_형식(M 표 칸) · N 판정_불일치(내용 모순 — review:mismatch) ·
#    P 판정_누락(판독 불가) · R 판정_대상외(추출 없음) · S 판정_누락(빈 서식) · T 판정_중복(같은 서식 두 건) · U 판정_불일치(서류 간 성명 — unmatched)
#  판정 7갈래를 모두 담는다(상 · 중 · 형식 · 불일치 · 누락 · 대상외 · 중복).
#  관계 칸: 화면 원문 값 바꾸기의 예외(값이 정확히 '본인' · 칸 키 넷)가 fields.py 와 같은지, 관계 칸 임의 값을 판정 글에 복사한 재현의 모양이 백엔드 출력과 같은지 본다.
#  다시 만들기(백엔드 규칙을 바꾼 뒤 — 결과 diff 를 꼭 읽는다):
#    .venv\Scripts\python.exe tests\test_v2_fixture_sync.py
#  값은 모두 가상 값이다(tests/fixtures/v2). 그래도 실패 메시지에는 키 이름 · 위치만 넣는다.
# ==========================================================================

from __future__ import annotations

import json
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if __name__ == "__main__":  # 직접 실행(다시 만들기) — pytest.ini 의 pythonpath 와 같은 자리
    sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

import pytest  # noqa: E402
from view_contract import VIEW_KEYS, assert_view  # noqa: E402

from imask_backend.analyses import build_result, result_out  # noqa: E402
from imask_backend.fields import V2_FIELDS, V2_TABLE_FIELDS  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "v2"
SCREEN = ROOT / "src" / "services" / "api" / "fixtures" / "v2-cases.json"
CONFIG_ID = "60"  # v2_full 의 설정 external id
CASES = ("A", "E", "L", "M", "N", "P", "R", "S", "T", "U")
ANSWERS: dict[str, dict[str, Any]] = json.loads((FIXTURES / "answers.json").read_bytes().decode("utf-8"))

# 화면 시험이 기대하는 모양(src/services/api/v2-cases.test.ts WANT 와 같은 값)
SHAPES: dict[str, dict[str, Any]] = {
    "A": {"kinds": ["lowconf", "weaklink", "lowconf"], "links": [("linked", "confirmed"), ("linked", "confirmed"), ("insufficient", "check")], "verdict": "green", "failed": 0, "stage": "권장_조치"},
    "E": {"kinds": [], "links": [], "verdict": "green", "failed": 0, "stage": "권장_조치"},
    "L": {"kinds": ["format", "lowconf"], "links": [], "verdict": "red", "failed": 1, "stage": "검토_안내"},
    "M": {"kinds": ["format", "lowconf"], "links": [], "verdict": "red", "failed": 1, "stage": "검토_안내"},
    "N": {"kinds": ["lowconf", "mismatch"], "links": [], "verdict": "red", "failed": 1, "stage": "검토_안내"},
    "P": {"kinds": ["unreadable", "missing"], "links": [], "verdict": "red", "failed": 2, "stage": "검토_안내"},
    "R": {"kinds": ["other"], "links": [], "verdict": "red", "failed": 1, "stage": "검토_안내"},
    "S": {"kinds": ["missing", "missing"], "links": [], "verdict": "red", "failed": 2, "stage": "검토_안내"},
    "T": {"kinds": ["duplicate", "lowconf"], "links": [], "verdict": "red", "failed": 1, "stage": "검토_안내"},
    "U": {"kinds": ["mismatch", "lowconf", "mismatch"], "links": [("unmatched", "check"), ("unmatched", "check")], "verdict": "red", "failed": 3, "stage": "검토_안내"},
}


def _load(path: Path) -> Any:
    return json.loads(path.read_bytes().decode("utf-8"))


def screen_result(case: str) -> dict[str, Any]:
    """고정 응답 → 조회 응답의 result(브라우저가 받는 값 그대로)."""
    return result_out(build_result(_load(FIXTURES / f"case_{case}.json"), CONFIG_ID))


def screen_bytes(cases: Mapping[str, Any]) -> bytes:
    """저장소 자료의 바이트 — 들여쓰기 2 · 한글 그대로 · LF · 끝 줄바꿈 하나(다른 fixtures/*.json 과 같은 꼴)."""
    return (json.dumps(cases, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _first_difference(got: Any, want: Any, where: str = "cases") -> str:
    """처음 다른 자리(키 이름 · 위치만 — 값은 넣지 않는다)."""
    if type(got) is not type(want):
        return f"{where}: 타입"
    if isinstance(got, Mapping):
        if list(got) != list(want):
            return f"{where}: 키·순서"
        for key in got:
            found = _first_difference(got[key], want[key], f"{where}.{key}")
            if found:
                return found
        return ""
    if isinstance(got, list):
        if len(got) != len(want):
            return f"{where}: 개수 {len(got)} ≠ {len(want)}"
        for n, (a, b) in enumerate(zip(got, want, strict=True)):
            found = _first_difference(a, b, f"{where}[{n}]")
            if found:
                return found
        return ""
    return "" if got == want else f"{where}: 값"


def test_screen_fixture_equals_backend_output_exactly() -> None:
    assert SCREEN.is_file(), f"{SCREEN.name} 이 없다 — tests/test_v2_fixture_sync.py 를 직접 실행해 만든다"
    want = {case: screen_result(case) for case in CASES}
    got = _load(SCREEN)
    assert got == want, f"{SCREEN.name}: {_first_difference(got, want)}"
    raw = SCREEN.read_bytes()
    assert raw == screen_bytes(want), f"{SCREEN.name}: 바이트(키 순서·들여쓰기·줄 끝)가 다르다"
    assert b"\r" not in raw


@pytest.mark.parametrize("case", CASES)
def test_screen_fixture_passes_the_view_contract(case: str) -> None:
    result = _load(SCREEN)[case]
    assert_view({k: result[k] for k in VIEW_KEYS})
    assert "response" not in result and "stages" not in result
    assert result["job"]["config_id"] == CONFIG_ID


@pytest.mark.parametrize("case", CASES)
def test_screen_fixture_decision_is_the_answer_sheet(case: str) -> None:
    # 화면 판정 표의 재료 = 정답지 8키(목록은 차례 무관 — 응답 차례를 그대로 둔다, tests/test_v2_flow.py same_answer 와 같은 기준)
    decision = _load(SCREEN)[case]["decision"]
    assert list(decision) == list(ANSWERS[case])
    for key, want in ANSWERS[case].items():
        got = decision[key]
        assert (sorted(got) == sorted(want)) if isinstance(want, list) else got == want, f"{case}: decision.{key}"


@pytest.mark.parametrize("case", CASES)
def test_screen_fixture_shape(case: str) -> None:
    result, shape = _load(SCREEN)[case], SHAPES[case]
    assert [i["type"] for i in result["items"]] == shape["kinds"]
    assert [(link["state"], link["status"]) for link in result["links"]] == shape["links"]
    bundle = result["bundle_check"]
    assert bundle["verdict"] == shape["verdict"]
    assert sum(1 for c in bundle["checks"] if c["status"] == "fail") == shape["failed"]
    assert result["overall"]["next_stage"] == shape["stage"]
    assert result["overall"]["level"] == result["decision"]["risk_level"]
    assert result["overall"]["next_text"] == result["decision"]["recommended_action"]


def test_screen_fixture_covers_seven_branches_and_new_kinds() -> None:
    cases = _load(SCREEN)
    kinds = {i["type"] for r in cases.values() for i in r["items"]}
    assert {"format", "duplicate", "unreadable", "mismatch", "weaklink", "missing", "lowconf", "other"} <= kinds
    ids = {i["id"] for r in cases.values() for i in r["items"]}
    assert any(i.startswith("review:") for i in ids)
    # 표 칸 탐지 항목 id 에 [ ] . 이 있다
    table = [f["id"] for r in cases.values() for f in r["findings"] if "[" in f["id"]]
    assert table and all("]." in i for i in table)
    # finding_ids 가 여러 개인 근거가 있다
    assert any(len(e["finding_ids"]) > 1 for r in cases.values() for i in r["items"] for e in i["evidence"])


@pytest.mark.parametrize("case", CASES)
def test_screen_fixture_has_no_raw_value_outside_findings(case: str) -> None:
    # 원문 value(masked 와 다른 값)는 findings[].value 에만 — 연결 · 검토사항 · 판정 · 묶음 검증 · 요약 어디에도 없다. 관계 칸 값도 같다.
    # 다른 칸의 masked 는 보지 않는다 — 짧은 값이 다른 칸 표시값의 안 가린 앞부분과 같을 수 있다(그 값 자체가 가린 표시다).
    result = _load(SCREEN)[case]
    raws = {f["value"] for f in result["findings"] if isinstance(f["value"], str) and f["value"] != f["masked"] and len(f["value"]) >= 2}
    rest = {k: v for k, v in result.items() if k != "findings"}
    text = json.dumps(rest, ensure_ascii=False)
    for finding in result["findings"]:
        text += json.dumps({k: v for k, v in finding.items() if k not in ("value", "masked")}, ensure_ascii=False)
    assert sum(1 for raw in raws if raw in text) == 0


# --- 관계 칸 — 화면 원문 값 바꾸기(src/services/raw-mask.ts)의 예외가 백엔드 칸 표 · 출력과 맞는지 ------------------------------------------


def test_relation_keys_on_the_screen_are_the_backend_relation_keys() -> None:
    # 예외 칸 키 넷 = fields.py 의 관계 칸 전부(새 관계 칸이 생기면 여기서 깨져 예외에 넣을지 정한다)
    source = (ROOT / "src" / "services" / "raw-mask.ts").read_bytes().decode("utf-8")
    found = re.search(r"RELATION_KEYS[^=]*=\s*new Set\(\[([^\]]*)\]\)", source)
    assert found, "raw-mask.ts 에 RELATION_KEYS 가 없다"
    screen = re.findall(r"'([^']+)'", found.group(1))
    backend = {key for key in V2_FIELDS if key.endswith("관계")} | {cell for _, cell in V2_TABLE_FIELDS if cell.endswith("관계")}
    assert sorted(screen) == sorted(backend) == sorted(["중_관계", "중_대리인_관계", "중_법정대리인_관계", "중_가족관계"])


def _with_relation(case: str, row: str, table: str | None, value: str, *, copy_to_decision: bool) -> dict[str, Any]:
    """고정 응답의 관계 칸 값을 바꾸고(copy_to_decision 이면 판정 reason · recommended_action 에도) 백엔드에 넣은 result."""
    source = _load(FIXTURES / f"case_{case}.json")
    changed = 0
    for step in source["output"]:
        text = step.get("content", [{}])[0].get("text") if step.get("content") else None
        if not isinstance(text, str) or not text.startswith("{"):
            continue
        model = step.get("model", "").split(" - ")[-1]
        payload = json.loads(text)
        if model.startswith("판정_"):
            if copy_to_decision:
                payload["reason"] = value
                payload["recommended_action"] = value
                changed += 1
        elif table is None and payload.get(row):  # 값이 있는 칸만(다른 서식의 빈 같은 키는 탐지 항목이 아니다)
            payload[row] = value
            changed += 1
        elif table is not None and isinstance(payload.get(table), list) and payload[table] and payload[table][0].get(row):
            payload[table][0][row] = value
            changed += 1
        step["content"][0]["text"] = json.dumps(payload, ensure_ascii=False)
    assert changed == (2 if copy_to_decision else 1)
    return result_out(build_result(source, CONFIG_ID))


@pytest.mark.parametrize(
    ("case", "field", "table", "row"),
    [
        ("U", "세대구성원[0].중_관계", "세대구성원", "중_관계"),
        ("M", "세대구성원[0].중_관계", "세대구성원", "중_관계"),
        ("A", "중_대리인_관계", None, "중_대리인_관계"),
    ],
)
def test_relation_value_copied_to_the_decision_has_the_shape_the_screen_test_uses(case: str, field: str, table: str | None, row: str) -> None:
    # v2-cases.test.ts 의 재현(관계 칸 + 판정 글에 같은 임의 값)이 백엔드 출력과 같은 모양인지 — 값은 코드로 만든다
    value = "".join(chr(0xac10 + 2 * 31 + i) for i in range(10))
    result = _with_relation(case, row, table, value, copy_to_decision=True)
    cell = next(f for f in result["findings"] if f["field"] == field)
    assert cell["value"] == value and cell["risk_source"] == "workflow" and cell["risk_reason"] is None
    assert cell["masked"] == value[0] + "*" * 9  # 화면 시험의 maskedOf
    assert result["decision"]["reason"] == value and result["decision"]["recommended_action"] == value
    assert result["overall"]["text"] == value and result["overall"]["next_text"] == value
    # 판정 글 밖의 서버 글에는 들어가지 않는다(화면이 가릴 자리는 판정 글 · overall 뿐)
    assert not any(value in json.dumps(result[key], ensure_ascii=False) for key in ("items", "links", "bundle_check", "summary", "documents"))


@pytest.mark.parametrize("case", ["U", "M"])
def test_self_relation_value_and_the_fixed_text_it_overlaps(case: str) -> None:
    # 값이 정확히 '본인' 인 관계 칸 — 표시값과, 겹치는 고정 글 · 토큰이 실제로 있는지(화면 시험의 전제)
    result = _with_relation(case, "중_관계", "세대구성원", "본인", copy_to_decision=False)
    cell = next(f for f in result["findings"] if f["field"] == "세대구성원[0].중_관계")
    assert cell["value"] == "본인" and cell["masked"] == "본*" and cell["risk_source"] == "workflow"
    decision = result["decision"]
    tokens = decision["high_risk_items"] + decision["medium_risk_items"] + decision["low_risk_items"]
    assert "외국인_세대구성원_확인서.본인_성명" in tokens
    if case == "U":
        assert all(link["label"] == "본인 성명" and "본인 성명" in link["missing"] for link in result["links"])


if __name__ == "__main__":  # 다시 만들기
    data = screen_bytes({case: screen_result(case) for case in CASES})
    SCREEN.write_bytes(data)
    print(f"{SCREEN.relative_to(ROOT)}: {len(data):,} bytes")
