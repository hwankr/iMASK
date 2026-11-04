# ==========================================================================
#  백엔드 ↔ 화면 공유 자료 잇기(final-flow T5) — 화면 테스트 자료 src/services/api/fixtures/final-flow-<X>.json 이
#  최종 흐름 고정 응답 tests/fixtures/final_flow/<응답>.json → analyses.build_result(설정 "1") → analyses.result_out
#  (조회 응답의 result — documents·findings·overall·items·links·decision·bundle_check 를 서버가 계산한 값)과 **바이트까지**
#  같은지 지킨다. 화면 테스트(src/services/api/final-flow-fixtures.test.ts)가 이 자료를 쓰므로 백엔드 규칙이 바뀌면 여기서 먼저 깨진다.
#    C = C_mismatch(확인서 unmatched → mismatch · 증빙 linked) · D = D_blank_applicant(기준 성명 빔 → weaklink · missing)
#    · E = E_team_forms(팀원 서식 — 연결 2 linked · other)
#  손으로 만든 final-flow-result.json(경계 조합용 — T4)은 그대로 두되, 키·꼴(모든 단계의 키 이름·순서)이 실제 출력과 같아야 한다.
#  다시 만들기(백엔드 규칙을 바꾼 뒤 — 결과 diff 를 꼭 읽는다):
#    .venv\Scripts\python.exe tests\test_final_flow_fixture_sync.py
#  합성 자료만 쓴다(원문 값은 출력·메시지에 옮기지 않는다 — 실패 메시지는 파일·위치·키 이름만).
# ==========================================================================

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if __name__ == "__main__":  # 직접 실행(다시 만들기) — pytest.ini 의 pythonpath 와 같은 자리
    sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

import pytest  # noqa: E402
from view_contract import assert_view  # noqa: E402

from imask_backend.analyses import build_result, result_out  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "final_flow"
SCREEN = ROOT / "src" / "services" / "api" / "fixtures"
HAND = SCREEN / "final-flow-result.json"
CONFIG_ID = "1"  # final_imask_workflow 의 설정 external id
SCREEN_RUNS = {"C": "C_mismatch", "D": "D_blank_applicant", "E": "E_team_forms"}


def _load(path: Path) -> Any:
    return json.loads(path.read_bytes().decode("utf-8"))


def screen_path(key: str) -> Path:
    return SCREEN / f"final-flow-{key}.json"


def screen_result(run: str) -> dict[str, Any]:
    """고정 응답 → 조회 응답의 result(브라우저가 받는 값 그대로)."""
    return result_out(build_result(_load(FIXTURES / f"{run}.json"), CONFIG_ID))


def screen_bytes(result: Mapping[str, Any]) -> bytes:
    """저장소 자료의 바이트 — 들여쓰기 2·한글 그대로·LF·끝 줄바꿈 하나(다른 fixtures/*.json 과 같은 꼴)."""
    return (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _first_difference(got: Any, want: Any, where: str = "result") -> str:
    """처음 다른 자리(키 이름·위치만 — 값은 넣지 않는다)."""
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


def _kinds(items: list[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        counts[item["type"]] = counts.get(item["type"], 0) + 1
    return counts


# --- 1. 저장소 자료 = 백엔드 출력(바이트) ------------------------------------------------------


@pytest.mark.parametrize("key", sorted(SCREEN_RUNS))
def test_screen_fixture_equals_backend_output_exactly(key: str) -> None:
    path = screen_path(key)
    assert path.is_file(), f"{path.name} 이 없다 — tests/test_final_flow_fixture_sync.py 를 직접 실행해 만든다"
    want = screen_result(SCREEN_RUNS[key])
    got = _load(path)
    assert got == want, f"{path.name}: {_first_difference(got, want)}"
    assert path.read_bytes() == screen_bytes(want), f"{path.name}: 바이트(키 순서·들여쓰기·줄 끝)가 다르다"
    assert b"\r" not in path.read_bytes()


@pytest.mark.parametrize("key", sorted(SCREEN_RUNS))
def test_screen_fixture_passes_the_view_contract(key: str) -> None:
    result = _load(screen_path(key))
    assert_view({k: result[k] for k in ("documents", "findings", "overall", "items", "links", "decision", "bundle_check")})
    assert "response" not in result and "stages" not in result
    assert result["job"]["config_id"] == CONFIG_ID


# --- 2. 화면 테스트가 기대하는 모양(src/services/api/final-flow-fixtures.test.ts 와 같은 값) ----------------------

SHAPES: dict[str, dict[str, Any]] = {
    "C": {
        "links": [("L-01", "check", "unmatched", "link:0:1"), ("L-02", "confirmed", "linked", "link:0:2")],
        "kinds": {"mismatch": 1},
        "linked_items": {"mismatch:0:1": "link:0:1"},
        "verdict": "yellow",
        "risk": "검토 필요",
    },
    "D": {
        "links": [("L-01", "check", "insufficient", "link:0:1")],
        "kinds": {"missing": 1, "weaklink": 1},
        "linked_items": {"weaklink:0:1": "link:0:1"},
        "verdict": "red",
        "risk": "검토 필요",
    },
    "E": {
        "links": [("L-01", "confirmed", "linked", "link:0:1"), ("L-02", "confirmed", "linked", "link:0:2")],
        "kinds": {"other": 1},
        "linked_items": {},
        "verdict": "yellow",
        "risk": "상",
    },
}


@pytest.mark.parametrize("key", sorted(SCREEN_RUNS))
def test_screen_fixture_shape(key: str) -> None:
    result, shape = _load(screen_path(key)), SHAPES[key]
    links = result["links"]
    assert [(link["number"], link["status"], link["state"], link["id"]) for link in links] == shape["links"]
    items = result["items"]
    final_kinds = {k: n for k, n in _kinds(items).items() if k in ("missing", "mismatch", "weaklink", "other")}
    assert final_kinds == shape["kinds"]
    assert {i["id"]: i["link_id"] for i in items if i["link_id"] is not None} == shape["linked_items"]
    assert result["bundle_check"]["verdict"] == shape["verdict"]
    assert result["decision"]["risk_level"] == shape["risk"] == result["overall"]["level"]
    assert [i["number"] for i in items] == [f"R-{n:02d}" for n in range(1, len(items) + 1)]


@pytest.mark.parametrize("key", sorted(SCREEN_RUNS))
def test_screen_fixture_has_no_raw_value_outside_findings(key: str) -> None:
    # 원문 value(masked 와 다른 값)는 findings[].value 에만 — 연결·검토사항·판정·묶음 검증·요약 어디에도 없다
    result = _load(screen_path(key))
    raws = {f["value"] for f in result["findings"] if isinstance(f["value"], str) and f["value"] != f["masked"] and len(f["value"]) >= 2}
    assert raws, "원문 값이 있는 탐지 항목이 있어야 시험이 뜻이 있다"
    rest = {k: v for k, v in result.items() if k != "findings"}
    text = json.dumps(rest, ensure_ascii=False)
    for finding in result["findings"]:
        text += json.dumps({k: v for k, v in finding.items() if k != "value"}, ensure_ascii=False)
    assert sum(1 for raw in raws if raw in text) == 0


# --- 3. 손으로 만든 자료(final-flow-result.json)의 키·꼴 = 실제 출력 -------------------------------------------


def _key_shape(value: Any) -> Any:
    """값의 키 구조(객체 키 이름·순서, 목록은 항목 키 구조의 합) — 값·개수는 보지 않는다."""
    if isinstance(value, Mapping):
        return {key: _key_shape(v) for key, v in value.items()}
    if isinstance(value, list):
        shapes: list[Any] = []
        for v in value:
            s = _key_shape(v)
            if s not in shapes:
                shapes.append(s)
        return shapes
    return None


def _merged(shapes: list[Any]) -> Any:
    """여러 결과의 키 구조 합(객체는 키마다 — 처음 나온 순서)."""
    if all(isinstance(s, dict) for s in shapes):
        keys: list[str] = []
        for s in shapes:
            keys += [k for k in s if k not in keys]
        return {k: _merged([s[k] for s in shapes if k in s]) for k in keys}
    if all(isinstance(s, list) for s in shapes):
        out: list[Any] = []
        for s in shapes:
            out += [x for x in s if x not in out]
        return [_merged(out)] if out and all(isinstance(x, dict) for x in out) else out
    return None


def _real_shape(part: str) -> Any:
    return _merged([_key_shape(_load(screen_path(key))[part]) for key in sorted(SCREEN_RUNS)])


@pytest.mark.parametrize("part", ["documents", "items", "links", "decision", "bundle_check", "overall"])
def test_hand_fixture_has_the_real_key_shape(part: str) -> None:
    hand = _load(HAND)
    want = _real_shape(part)
    got = _merged([_key_shape(hand[part])])
    assert got == want, f"final-flow-result.json {part}: 키·꼴이 실제 출력과 다르다"


def test_hand_fixture_top_keys_and_findings_keys_are_real() -> None:
    hand, real = _load(HAND), _load(screen_path("C"))
    assert list(hand) == list(real)
    assert all(list(f) == list(real["findings"][0]) for f in hand["findings"])
    # job·summary 는 맨 위 키만(usage·stage_counts 의 안쪽은 실행마다 다른 값이라 꼴이 아니다)
    assert list(hand["job"]) == list(real["job"]) and list(hand["summary"]) == list(real["summary"])
    assert_view({k: hand[k] for k in ("documents", "findings", "overall", "items", "links", "decision", "bundle_check")})


if __name__ == "__main__":  # 다시 만들기
    for name, run in sorted(SCREEN_RUNS.items()):
        target = screen_path(name)
        data = screen_bytes(screen_result(run))
        target.write_bytes(data)
        print(f"{target.relative_to(ROOT)}: {len(data):,} bytes")
