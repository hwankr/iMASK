# ==========================================================================
#  화면 테스트 자료 ↔ 백엔드 계약(review-items F2) — src/services/api/fixtures/done-result.json 과 그 사본
#  items-result.json 이 백엔드가 실제로 내는 결과와 같은 모양·같은 가림 값인지 지킨다. 화면 테스트(매핑·상세·보고서·
#  내보내기)가 이 두 자료를 '백엔드 응답'으로 쓰므로, 자료가 계약·마스킹 규칙과 어긋나면 여기서 먼저 깨진다.
#  - 두 파일 모두: 바이트 모양(BOM·CR 없음·끝 줄바꿈 하나) · 서류 assert_document · 탐지 항목 assert_finding
#    (len(masked) == len(value) 포함) · overall assert_overall, 그리고 탐지 항목의 masked·exposure 가
#    imask_backend.masking 의 masked(value, field_info(field).kind) · exposure(value, kind) 와 정확히 같다.
#    원문과 다른 masked 는 17개.
#  - items-result.json: assert_view 전체(검토사항 items 포함 — items 값이 build_items 와 같은지는
#    test_items_fixture_sync.py 가 지킨다). 지금 서버 모양대로 최종 흐름 키 셋(links []·decision null·bundle_check null)도 있다.
#  - done-result.json: items 키가 없는 옛 결과(화면은 검토사항 0개로 읽는다). items 를 뺀 나머지는 assert_view 와
#    같은 검사(빈 items 로 — 최종 흐름 키 links·decision·bundle_check 도 서버가 옛 결과에 내는 빈 값으로)를 통과한다.
#  - label·mapping_status 는 비교하지 않는다 — 화면 테스트용 값이라 대응표(field_info)와 다른 곳이 있다(이번 범위 밖).
#
#  **실패 출력에 원문·가린 값을 넣지 않는다**(F2-fix1·fix2). 자료(fixture)의 바이트·글·파싱 결과를 만지는 코드는
#  모두 경계 하나를 지난다:
#  - 예외를 잡는 곳은 _attempt 하나 — 예외는 종류 이름만 남기고 메시지·인자·지역 변수는 버린다(pytest 의 긴 traceback 은
#    함수 인자·지역 변수 값을 찍으므로 어떤 예외도 그대로 내보내지 않는다). 실패는 _fail 하나 — 위치(단계 이름·파일
#    이름·항목 순번·필드 id·키 이름·사례 이름)만 담아 pytest.fail(…, pytrace=False) 하고, 늘 _attempt 가 돌아온 뒤
#    (except 블록 밖)에 불러 __context__·__cause__ 가 붙지 않는다.
#  - assert 문을 쓰지 않는다(assert 다시 쓰기가 식의 중간 값 — 객체·비교 양쪽 — 을 해설에 붙인다). 검사는 _need 로
#    bool 을 계산하고 _verify 가 모아 _fail 한다.
#  - 모듈을 읽어 들일 때·수집할 때는 자료를 읽지 않는다. pytest fixture(broken_copy_runs·broken_source_runs)는 준비·
#    하위 실행·결과 수집을 모두 _attempt 안에서 하고, 실패하면 예외 대신 값 없는 오류 결과를 돌려준다(테스트 본문이
#    그것을 _verify 로 실패시킨다). 하위 pytest 의 출력은 메모리에서만 보고 메시지에 넣지 않는다(개수만).
#  회귀(이 파일을 하위 pytest 로 돌려 실패 출력 전체에 값이 없는지 본다 — 원문 값(value ≠ masked)·글자·숫자가 있는 가린
#  값·변조한 칸, 3자 이상, 그대로·repr·JSON escape 꼴. traceback 줄(E·>)·pytest ERROR 도 없어야 한다):
#  - test_broken_copy_*: 일부러 틀린 자료 사본(환경변수 IMASK_SCREEN_FIXTURES_DIR 로 넘김)으로 -q. 이 변수가 있으면
#    두 회귀 모두 건너뛴다(하위 실행이 또 하위 실행을 띄우지 않게).
#  - test_broken_source_*: 저장소 사본(이 파일·view_contract·pytest.ini·자료 — %TEMP%)에서 원본 자료 자체를 깨뜨리고
#    (첫 value 문자열 안에서 잘림·UTF-8 아님·최상위 배열·BOM·value 만 남은 항목) 이 파일 전체를 -q·-vv·--tb=long·
#    --showlocals 로 돌린다. 그 하위 실행은 환경변수 IMASK_SCREEN_SOURCE_CHILD 가 있어 이 회귀만 건너뛴다
#    (test_broken_copy_* 는 깨진 원본으로 그대로 돌아 준비 경로가 값 없이 실패하는지까지 보인다).
# ==========================================================================

from __future__ import annotations

import copy
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, TypeVar

import pytest
from view_contract import (
    DOCUMENT_KEYS,
    FINDING_KEYS,
    OVERALL_KEYS,
    assert_document,
    assert_finding,
    assert_overall,
    assert_view,
)

from imask_backend.fields import field_info
from imask_backend.masking import exposure, masked

ROOT = Path(__file__).resolve().parents[1]
FIXTURES_REL = Path("src") / "services" / "api" / "fixtures"
REPO_FIXTURES = ROOT / FIXTURES_REL
FIXTURES_ENV = "IMASK_SCREEN_FIXTURES_DIR"
SOURCE_CHILD_ENV = "IMASK_SCREEN_SOURCE_CHILD"
FIXTURES = Path(os.environ[FIXTURES_ENV]) if os.environ.get(FIXTURES_ENV) else REPO_FIXTURES
DONE = "done-result.json"
ITEMS = "items-result.json"
FILES = (DONE, ITEMS)
OLD_RESULT_KEYS = ["format", "job", "summary", "documents", "findings", "overall"]
FINAL_FLOW_KEYS = ["links", "decision", "bundle_check"]  # 서버(build_view)가 늘 내는 최종 흐름 키 셋(final-flow T3 A)
FINDINGS = 19
UNMASKED_DIFFERENT = 17  # value ≠ masked 인 항목 수(화면 테스트의 '원문 값' 목록이 이것에서 나온다)
BOM = b"\xef\xbb\xbf"
SAFE_ID = re.compile(r"\d{1,3}:[a-z0-9_]{1,60}")  # 메시지에 넣어도 되는 꼴의 탐지 id(서류 index:추출 키)
MAX_LISTED = 20
CHILD_TIMEOUT = 300

T = TypeVar("T")


# --- 값 없는 실패 — 예외 경계는 _attempt 하나, 실패는 _fail 하나 ---------------------------------------


def _attempt(fn: Callable[[], T]) -> tuple[T | None, str | None]:
    """fn() → (값, None). 예외면 (None, 예외 종류 이름) — 메시지·인자·지역 변수는 버린다(이 파일에서 예외를 잡는 곳은 여기뿐)."""
    try:
        return fn(), None
    except Exception as exc:  # 손상된 자료의 어떤 예외도 종류 이름만 남긴다
        return None, type(exc).__name__


def _fail(message: str) -> None:
    """위치만 담은 실패(트레이스백 없이). 언제나 _attempt 가 돌아온 뒤 — except 블록 밖에서 불린다."""
    pytest.fail(message, pytrace=False)


def _holds(predicate: Callable[[], object]) -> str | None:
    """predicate() 가 참이면 None, 거짓이면 '', 예외면 예외 종류 이름."""
    value, error = _attempt(predicate)
    if error is not None:
        return error
    return None if value else ""


def _need(problems: list[str], where: str, predicate: Callable[[], object]) -> None:
    """검사 하나 — 통과하지 못하면 위치(와 예외 종류)만 problems 에 더한다."""
    reason = _holds(predicate)
    if reason is not None:
        problems.append(f"{where} ({reason})" if reason else where)


def _contract(problems: list[str], where: str, check: Callable[..., None], *args: Any) -> None:
    """view_contract 검사(실패 메시지에 객체를 담을 수 있다)를 부르고, 실패면 위치와 검사 이름만 남긴다."""

    def run() -> bool:
        check(*args)
        return True

    _need(problems, f"{where} {check.__name__}", run)


def _verify(where: str, body: Callable[[list[str]], None]) -> None:
    """body(problems) 를 돌리고 통과하지 못한 검사가 있으면 위치만 담아 실패(트레이스백 없이)."""
    problems: list[str] = []
    _, error = _attempt(lambda: body(problems))
    if error is not None:
        problems.append(f"검사 중 예외 ({error})")
    if problems:
        more = f" 외 {len(problems) - MAX_LISTED}건" if len(problems) > MAX_LISTED else ""
        _fail(f"{where}: 통과하지 못한 검사 — " + " · ".join(problems[:MAX_LISTED]) + more)


def _stages(steps: Sequence[tuple[str, Callable[[], object]]]) -> str | None:
    """단계를 차례로 돌린다 — 처음 실패한 단계 이름과 예외 종류만(값 없음), 모두 되면 None."""
    for stage, step in steps:
        _, error = _attempt(step)
        if error is not None:
            return f"{stage} ({error})"
    return None


def _where(n: int, finding: Any) -> str:
    """탐지 항목 위치 — 꼴이 맞는 id 면 id, 아니면 순번(id 칸이 망가져 값이 들어 있어도 내지 않게)."""
    fid = finding.get("id") if isinstance(finding, Mapping) else None
    return fid if isinstance(fid, str) and SAFE_ID.fullmatch(fid) else f"findings[{n}]"


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_bytes().decode("utf-8"))


def _backend(finding: Mapping[str, Any]) -> tuple[str, str]:
    kind = field_info(finding["field"]).kind
    return masked(finding["value"], kind), exposure(finding["value"], kind)


# --- 두 자료의 계약 ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", FILES)
def test_fixture_bytes_are_utf8_lf_without_bom(name: str) -> None:
    def body(p: list[str]) -> None:
        raw = (FIXTURES / name).read_bytes()
        _need(p, "BOM 없음", lambda: not raw.startswith(BOM))
        _need(p, "CR 없음", lambda: b"\r" not in raw)
        _need(p, "끝 줄바꿈 하나", lambda: raw.endswith(b"\n") and not raw.endswith(b"\n\n"))

    _verify(name, body)


@pytest.mark.parametrize("name", FILES)
def test_documents_pass_the_contract(name: str) -> None:
    def body(p: list[str]) -> None:
        documents = _load(name)["documents"]
        _need(p, "documents 가 비지 않은 목록", lambda: isinstance(documents, list) and len(documents) > 0)
        for n, doc in enumerate(_list(documents)):
            _need(p, f"documents[{n}] 키", lambda: isinstance(doc, Mapping) and set(doc) == DOCUMENT_KEYS)
            _contract(p, f"documents[{n}]", assert_document, doc)

    _verify(name, body)


@pytest.mark.parametrize("name", FILES)
def test_findings_pass_the_contract(name: str) -> None:
    def body(p: list[str]) -> None:
        findings = _load(name)["findings"]
        _need(p, f"findings 가 {FINDINGS}개 목록", lambda: isinstance(findings, list) and len(findings) == FINDINGS)
        for n, finding in enumerate(_list(findings)):
            where = _where(n, finding)
            _need(p, f"{where} 키", lambda: isinstance(finding, Mapping) and set(finding) == FINDING_KEYS)
            _contract(p, where, assert_finding, finding)

    _verify(name, body)


@pytest.mark.parametrize("name", FILES)
def test_findings_masked_and_exposure_equal_the_backend(name: str) -> None:
    def body(p: list[str]) -> None:
        findings = _load(name)["findings"]
        _need(p, "findings 가 목록", lambda: isinstance(findings, list))
        for n, finding in enumerate(_list(findings)):
            where = _where(n, finding)
            _need(p, f"{where} masked = 백엔드 마스킹", lambda: finding["masked"] == _backend(finding)[0])
            _need(p, f"{where} exposure = 백엔드 계산", lambda: finding["exposure"] == _backend(finding)[1])
        _need(
            p,
            f"value ≠ masked 항목 수 {UNMASKED_DIFFERENT}",
            lambda: sum(1 for f in _list(findings) if f["value"] != f["masked"]) == UNMASKED_DIFFERENT,
        )

    _verify(name, body)


@pytest.mark.parametrize("name", FILES)
def test_overall_passes_the_contract(name: str) -> None:
    def body(p: list[str]) -> None:
        overall = _load(name)["overall"]
        _need(p, "overall 키", lambda: isinstance(overall, Mapping) and set(overall) == OVERALL_KEYS)
        _contract(p, "overall", assert_overall, overall)

    _verify(name, body)


def test_items_fixture_passes_the_whole_view_contract() -> None:
    def body(p: list[str]) -> None:
        fixture = _load(ITEMS)
        _need(p, "최상위 키 = 옛 결과 6개 + items + 최종 흐름 3개", lambda: list(fixture) == [*OLD_RESULT_KEYS, "items", *FINAL_FLOW_KEYS])
        _need(p, "items 가 비지 않은 목록", lambda: isinstance(fixture["items"], list) and len(fixture["items"]) > 0)
        _contract(p, "결과 전체", assert_view, fixture)

    _verify(ITEMS, body)


def test_done_fixture_is_an_old_result_without_items() -> None:
    def body(p: list[str]) -> None:
        fixture = _load(DONE)
        _need(p, "items 키 없음", lambda: "items" not in fixture)
        _need(p, "최상위 키 = 옛 결과 6개", lambda: list(fixture) == OLD_RESULT_KEYS)
        # items 만 없을 뿐 나머지(서류 순서·id 겹침·서류 참조)는 새 결과와 같은 검사를 통과한다
        # (최종 흐름 키 셋은 옛 결과를 지금 계약으로 읽을 때 서버 build_view 가 내는 빈 값으로 — final-flow T3 A.4)
        old_view = {**fixture, "items": [], "links": [], "decision": None, "bundle_check": None}
        _contract(p, "결과 전체(+ 빈 items·links·decision·bundle_check)", assert_view, old_view)

    _verify(DONE, body)


# --- 회귀 공통: 하위 pytest 와 그 출력 검사(값 없이 — 개수·이름만) ------------------------------------------


def _forms(text: str) -> set[str]:
    """출력에서 찾을 꼴 — 그대로 · repr escape · JSON ASCII escape."""
    return {text, repr(text)[1:-1], json.dumps(text, ensure_ascii=True)[1:-1]}


def _sensitive(datas: list[Any], written: list[str]) -> list[set[str]]:
    """자료의 원문 값(value ≠ masked)·가린 값(글자·숫자가 있는 것)·변조한 칸 — 3자 이상만."""
    texts: set[str] = set(written)
    for data in datas:
        for f in _list(data.get("findings") if isinstance(data, Mapping) else None):
            if not isinstance(f, Mapping):
                continue
            value, mask = f.get("value"), f.get("masked")
            if isinstance(value, str) and value != mask:
                texts.add(value)
            if isinstance(mask, str) and any(ch.isalnum() for ch in mask):
                texts.add(mask)
    return [_forms(t) for t in texts if len(t) >= 3]


def _hits(output: str, sensitive: list[set[str]]) -> int:
    return sum(1 for forms in sensitive if any(s in output for s in forms))


def _read_originals() -> tuple[dict[str, bytes], list[Any]]:
    """저장소 원본 자료 두 개 — 바이트와 파싱 결과(값 찾기 재료). 늘 _attempt·_stages 안에서 부른다."""
    originals = {name: (REPO_FIXTURES / name).read_bytes() for name in FILES}
    return originals, [json.loads(raw.decode("utf-8")) for raw in originals.values()]


def _child_pytest(cwd: Path, args: Sequence[str], env_extra: Mapping[str, str], basetemp: Path, target: str) -> tuple[int, str]:
    """하위 pytest 하나 → (종료 코드, 출력 글). 출력은 돌려받는 쪽이 메모리에서만 본다."""
    env = {k: v for k, v in os.environ.items() if k not in (FIXTURES_ENV, SOURCE_CHILD_ENV)}
    env.update({"PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1", **env_extra})
    command = [sys.executable, "-X", "utf8", "-m", "pytest", *args, "-p", "no:cacheprovider", "--basetemp", str(basetemp), target]
    proc = subprocess.run(command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=CHILD_TIMEOUT)
    return proc.returncode, proc.stdout.decode("utf-8", errors="replace")


def _inspect(exit_code: int, output: str, sensitive: list[set[str]]) -> dict[str, Any]:
    """하위 실행 출력 → 값 없는 요약(종료 코드·실패한 테스트 이름·ERROR 수·traceback 줄 수·값 일치 수)."""
    return {
        "exit": exit_code,
        "failed": set(re.findall(r"^FAILED \S+::(\S+)", output, re.M)),
        "errors": len(re.findall(r"^ERROR ", output, re.M)),
        "tracebacks": len(re.findall(r"^(?:E |>)", output, re.M)),  # pytest traceback 의 오류 줄·소스 줄
        "passed_line": bool(re.search(r"\d+ passed", output)),
        "hits": _hits(output, sensitive),
        # 찾는 값이 원문 값 수 이상이고, 각 값을 글 속에 심으면 찾아낸다(빈 목록·잘못된 꼴로 0건이 되지 않게)
        "detector_ok": len(sensitive) >= UNMASKED_DIFFERENT
        and all(_hits("앞 " + sorted(forms)[0] + " 뒤", [forms]) == 1 for forms in sensitive),
    }


def _parallel_runs(
    cases: Sequence[tuple[Any, ...]],
    run_one: Callable[[tuple[Any, ...], Path], dict[str, Any]],
    factory: pytest.TempPathFactory,
    name: str,
    workers: int,
) -> dict[str, dict[str, Any]]:
    """사례마다 run_one(사례, 폴더)을 동시에 — 사례 하나가 예외를 내도 그 사례만 값 없는 오류 결과로."""
    base = factory.mktemp(name)

    def safe(case: tuple[Any, ...]) -> dict[str, Any]:
        result, error = _attempt(lambda: run_one(case, base))
        return result if error is None and isinstance(result, dict) else {"error": f"사례 실행 ({error or '결과 없음'})"}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(safe, cases))
    return {case[0]: result for case, result in zip(cases, results, strict=True)}


def _prepared(factory: pytest.TempPathFactory, prepare: Callable[[pytest.TempPathFactory], dict[str, dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    """fixture 준비 전체를 경계 안에서 — 실패하면 모든 사례가 받을 값 없는 오류 결과('' 키)."""
    runs, error = _attempt(lambda: prepare(factory))
    return runs if error is None and isinstance(runs, dict) else {"": {"error": f"회귀 준비 ({error or '결과 없음'})"}}


def _run_for(runs: Mapping[str, dict[str, Any]], label: str) -> dict[str, Any]:
    return runs.get(label) or runs.get("") or {"error": "결과 없음"}


# --- 회귀 1: 틀린 사본의 실패 출력에 값이 없다 ---------------------------------------------------------
#  (이름, 바꿀 파일, 변조 종류, 실패해야 하는 테스트 — 적어도 이것들). 'control' 은 바꾸지 않은 사본(모두 통과해야 함).

MUTATIONS: tuple[tuple[str, str | None, str, tuple[str, ...]], ...] = (
    ("control", None, "none", ()),
    ("done-value-only", DONE, "finding_value_only", (
        f"test_findings_pass_the_contract[{DONE}]",
        f"test_findings_masked_and_exposure_equal_the_backend[{DONE}]",
        "test_done_fixture_is_an_old_result_without_items",
    )),
    ("items-value-only", ITEMS, "finding_value_only", (
        f"test_findings_pass_the_contract[{ITEMS}]",
        f"test_findings_masked_and_exposure_equal_the_backend[{ITEMS}]",
        "test_items_fixture_passes_the_whole_view_contract",
    )),
    ("done-finding-key", DONE, "finding_key_removed", (f"test_findings_pass_the_contract[{DONE}]",)),
    ("items-id-is-value", ITEMS, "finding_id_is_value", (f"test_findings_pass_the_contract[{ITEMS}]",)),
    ("done-masked-shorter", DONE, "masked_shorter", (
        f"test_findings_pass_the_contract[{DONE}]",
        f"test_findings_masked_and_exposure_equal_the_backend[{DONE}]",
    )),
    ("items-masked-differs", ITEMS, "masked_differs", (f"test_findings_masked_and_exposure_equal_the_backend[{ITEMS}]",)),
    ("done-exposure-differs", DONE, "exposure_differs", (f"test_findings_masked_and_exposure_equal_the_backend[{DONE}]",)),
    ("items-value-changed", ITEMS, "value_changed", (f"test_findings_masked_and_exposure_equal_the_backend[{ITEMS}]",)),
    ("items-document-key", ITEMS, "document_key_removed", (f"test_documents_pass_the_contract[{ITEMS}]",)),
    ("done-overall-key", DONE, "overall_key_removed", (f"test_overall_passes_the_contract[{DONE}]",)),
    ("items-items-changed", ITEMS, "items_changed", ("test_items_fixture_passes_the_whole_view_contract",)),
    ("done-has-items", DONE, "done_has_items", ("test_done_fixture_is_an_old_result_without_items",)),
    ("items-bom", ITEMS, "bom", (f"test_fixture_bytes_are_utf8_lf_without_bom[{ITEMS}]",)),
)
TARGET = "0:applicant_email"  # 값을 바꾸는 변조가 쓰는 항목(value ≠ masked)


def _mutate(data: dict[str, Any], kind: str) -> list[str]:
    """data 를 kind 대로 틀리게 바꾸고, 새로 써 넣은 글자(출력에 나오면 안 되는 것)를 돌려준다."""
    findings = data["findings"]
    target = next(f for f in findings if f["id"] == TARGET)
    if kind == "finding_value_only":  # 검증 V-F2-1 의 재현 — 첫 항목을 value 하나만 남긴다
        findings[0] = {"value": findings[0]["value"]}
        return []
    if kind == "finding_key_removed":
        target.pop("risk_source")
        return []
    if kind == "finding_id_is_value":  # id 칸에 원문 값 — 위치에 id 대신 순번이 나와야 한다
        target["id"] = target["value"]
        return []
    if kind == "masked_shorter":
        target["masked"] = target["masked"][:-1]
        return [target["masked"]]
    if kind == "masked_differs":  # 길이는 같고 글자가 다르다
        target["masked"] = "~" + target["masked"][1:]
        return [target["masked"]]
    if kind == "exposure_differs":
        target["exposure"] = "마스킹됨" if target["exposure"] != "마스킹됨" else "전체 노출"
        return []
    if kind == "value_changed":  # 원문 값을 바꾼다(masked 는 옛 값 기준이라 백엔드 값과 달라진다)
        target["value"] = target["value"][::-1]
        return [target["value"]]
    if kind == "document_key_removed":
        data["documents"][0].pop("other_guide")
        return []
    if kind == "overall_key_removed":
        data["overall"].pop("next_text")
        return []
    if kind == "items_changed":  # 쪽을 계약 밖으로 + id 칸에 원문 값(view_contract 메시지가 id 를 담는다)
        data["items"][0]["page"] = 0
        data["items"][0]["id"] = target["value"]
        return []
    if kind == "done_has_items":
        data["items"] = []
        return []
    raise ValueError(kind)


def _run_case(case: tuple[str, str | None, str, tuple[str, ...]], base: Path) -> dict[str, Any]:
    """사본을 만들고 이 파일을 하위 pytest -q 로 돌린다 → 값 없는 요약. 단계마다 실패하면 단계 이름·예외 종류만."""
    label, target_file, kind, _expected = case
    s: dict[str, Any] = {"written": []}

    def folder() -> None:
        s["folder"] = base / label
        s["copies"] = s["folder"] / "fixtures"
        s["copies"].mkdir(parents=True)

    def read() -> None:
        s["originals"], s["datas"] = _read_originals()

    def make() -> None:
        for name, raw in s["originals"].items():
            if name == target_file and kind == "bom":
                raw = BOM + raw
            elif name == target_file:
                data = copy.deepcopy(json.loads(raw.decode("utf-8")))
                s["written"] = _mutate(data, kind)
                s["datas"].append(data)
                raw = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            (s["copies"] / name).write_bytes(raw)

    def child() -> None:
        target = str(Path(__file__).relative_to(ROOT))
        s["exit"], s["output"] = _child_pytest(ROOT, ["-q"], {FIXTURES_ENV: str(s["copies"])}, s["folder"] / "pytest", target)

    def inspect() -> None:
        s["result"] = _inspect(s["exit"], s["output"], _sensitive(s["datas"], s["written"]))

    error = _stages((("사본 폴더", folder), ("원본 읽기", read), ("사본 만들기", make), ("하위 실행", child), ("출력 검사", inspect)))
    s.pop("output", None)  # 원문이 들어 있을 수 있는 출력은 바로 버린다
    return {"error": error} if error is not None else s["result"]


@pytest.fixture(scope="module")
def broken_copy_runs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, dict[str, Any]]:
    if os.environ.get(FIXTURES_ENV):  # 하위 실행 안에서는 띄우지 않는다(아래 skipif 와 같은 이중 방어)
        pytest.skip("하위 실행")
    return _prepared(tmp_path_factory, lambda factory: _parallel_runs(MUTATIONS, _run_case, factory, "broken-copies", 8))


@pytest.mark.skipif(bool(os.environ.get(FIXTURES_ENV)), reason="하위 실행 안에서는 회귀 테스트를 돌리지 않는다")
@pytest.mark.parametrize("case", MUTATIONS, ids=[case[0] for case in MUTATIONS])
def test_broken_copy_fails_without_fixture_values_in_output(
    case: tuple[str, str | None, str, tuple[str, ...]], broken_copy_runs: dict[str, dict[str, Any]]
) -> None:
    label, _file, _kind, expected = case

    def body(p: list[str]) -> None:
        run = _run_for(broken_copy_runs, label)
        if "error" in run:
            p.append(f"준비·실행 실패 — {run['error']}")
            return
        if label == "control":
            _need(p, "바꾸지 않은 사본은 모두 통과(종료 코드 0)", lambda: run["exit"] == 0 and not run["failed"])
            _need(p, "통과 줄이 있음(사본을 실제로 읽음)", lambda: run["passed_line"])
        else:
            _need(p, "틀린 사본은 실패(종료 코드 1)", lambda: run["exit"] == 1)
            missing = [name for name in expected if name not in run["failed"]]
            _need(p, f"실패해야 하는 테스트가 실패 {missing}", lambda: not missing)
        _need(p, f"출력 전체에 사본의 원문·가린 값·변조한 칸 없음(일치 {run['hits']}건)", lambda: run["hits"] == 0)
        _need(p, f"traceback 줄 없음({run['tracebacks']}줄) · pytest ERROR 없음({run['errors']}건)",
              lambda: run["tracebacks"] == 0 and run["errors"] == 0)
        _need(p, "값 찾기 자체 확인", lambda: run["detector_ok"])

    _verify(f"사본 {label}", body)


# --- 회귀 2: 원본 자료 자체가 깨진 저장소 사본 — 이 파일 전체의 출력에 값이 없다 ---------------------------------
#  (이름, 깨뜨릴 파일, 깨뜨리는 법) × 출력 옵션. 깨진 원본으로는 회귀 1 의 준비(원본 읽기·변조)도 실패하므로
#  그 경로(fixture 준비)가 값 없이 끝나는지까지 본다.

SOURCE_BREAKS: tuple[tuple[str, str], ...] = (
    ("truncated-value", DONE),  # 첫 value 문자열 안에서 끊김(닫는 따옴표 앞 — 그 값 글자는 모두 남는다)
    ("invalid-utf8", ITEMS),  # 첫 value 바로 뒤에 UTF-8 이 아닌 바이트
    ("top-level-array", DONE),  # 최상위가 배열
    ("bom", ITEMS),  # 앞에 BOM
    ("value-only", DONE),  # 첫 탐지 항목이 value 하나만(읽히는 JSON — 회귀 1 의 하위 실행까지 간다)
)
OUTPUT_MODES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("q", ("-q",)),
    ("vv", ("-vv",)),
    ("long", ("-q", "--tb=long")),
    ("showlocals", ("-q", "--showlocals")),
)
SOURCE_CASES: tuple[tuple[str, str, str, tuple[str, ...]], ...] = tuple(
    (f"{kind}-{mode}", name, kind, args) for kind, name in SOURCE_BREAKS for mode, args in OUTPUT_MODES
)
VALUE_TOKEN = re.compile(rb'"value"\s*:\s*"((?:\\.|[^"\\])*)"')


def _break_source(raw: bytes, kind: str) -> bytes:
    """원본 자료 바이트를 kind 대로 깨뜨린다."""
    if kind in ("truncated-value", "invalid-utf8"):
        token = VALUE_TOKEN.search(raw)
        if token is None:
            raise ValueError(kind)
        if kind == "truncated-value":
            return raw[: token.end(1)]
        return raw[: token.end()] + b"\xff" + raw[token.end():]
    if kind == "bom":
        return BOM + raw
    data = json.loads(raw.decode("utf-8"))
    if kind == "top-level-array":
        data = [data]
    elif kind == "value-only":
        data["findings"][0] = {"value": data["findings"][0]["value"]}
    else:
        raise ValueError(kind)
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _run_source_case(case: tuple[str, str, str, tuple[str, ...]], base: Path) -> dict[str, Any]:
    """저장소 사본(이 파일·view_contract·pytest.ini·자료 — 하나는 깨뜨림)에서 이 파일 전체를 하위 실행 → 값 없는 요약."""
    label, broken_file, kind, args = case
    s: dict[str, Any] = {}

    def folder() -> None:
        s["folder"] = base / label
        s["repo"] = s["folder"] / "repo"
        (s["repo"] / "tests").mkdir(parents=True)
        (s["repo"] / FIXTURES_REL).mkdir(parents=True)

    def read() -> None:
        s["originals"], s["datas"] = _read_originals()

    def make() -> None:
        repo = s["repo"]
        for name, raw in s["originals"].items():
            (repo / FIXTURES_REL / name).write_bytes(_break_source(raw, kind) if name == broken_file else raw)
        here = Path(__file__).resolve()
        (repo / "tests" / here.name).write_bytes(here.read_bytes())
        (repo / "tests" / "view_contract.py").write_bytes((here.parent / "view_contract.py").read_bytes())
        (repo / "pytest.ini").write_bytes((ROOT / "pytest.ini").read_bytes())

    def child() -> None:
        # imask_backend 는 진짜 저장소에서(PYTHONPATH), 테스트·계약 도우미·자료는 사본에서
        path = os.pathsep.join(p for p in (str(ROOT), os.environ.get("PYTHONPATH", "")) if p)
        target = str(Path("tests") / Path(__file__).name)
        extra = {SOURCE_CHILD_ENV: "1", "PYTHONPATH": path}
        s["exit"], s["output"] = _child_pytest(s["repo"], args, extra, s["folder"] / "pytest", target)

    def inspect() -> None:
        s["result"] = _inspect(s["exit"], s["output"], _sensitive(s["datas"], []))

    error = _stages((("저장소 사본 폴더", folder), ("원본 읽기", read), ("저장소 사본 만들기", make), ("하위 실행", child), ("출력 검사", inspect)))
    s.pop("output", None)
    return {"error": error} if error is not None else s["result"]


def _source_children_skipped() -> bool:
    return bool(os.environ.get(FIXTURES_ENV) or os.environ.get(SOURCE_CHILD_ENV))


@pytest.fixture(scope="module")
def broken_source_runs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, dict[str, Any]]:
    if _source_children_skipped():  # 하위 실행 안에서는 띄우지 않는다(아래 skipif 와 같은 이중 방어)
        pytest.skip("하위 실행")
    return _prepared(tmp_path_factory, lambda factory: _parallel_runs(SOURCE_CASES, _run_source_case, factory, "broken-sources", 5))


@pytest.mark.skipif(_source_children_skipped(), reason="하위 실행 안에서는 원본 깨뜨리기 회귀를 돌리지 않는다")
@pytest.mark.parametrize("case", SOURCE_CASES, ids=[case[0] for case in SOURCE_CASES])
def test_broken_source_fixture_fails_without_fixture_values_in_output(
    case: tuple[str, str, str, tuple[str, ...]], broken_source_runs: dict[str, dict[str, Any]]
) -> None:
    label, broken_file, _kind, _args = case
    expected = (
        f"test_findings_pass_the_contract[{broken_file}]",
        f"test_findings_masked_and_exposure_equal_the_backend[{broken_file}]",
        "test_broken_copy_fails_without_fixture_values_in_output[control]",
    )

    def body(p: list[str]) -> None:
        run = _run_for(broken_source_runs, label)
        if "error" in run:
            p.append(f"준비·실행 실패 — {run['error']}")
            return
        _need(p, "깨진 원본으로는 실패(종료 코드 1)", lambda: run["exit"] == 1)
        missing = [name for name in expected if name not in run["failed"]]
        _need(p, f"실패해야 하는 테스트가 실패 {missing}", lambda: not missing)
        _need(p, f"출력 전체에 원문·가린 값 없음(일치 {run['hits']}건)", lambda: run["hits"] == 0)
        _need(p, f"traceback 줄 없음({run['tracebacks']}줄) · pytest ERROR 없음({run['errors']}건)",
              lambda: run["tracebacks"] == 0 and run["errors"] == 0)
        _need(p, "값 찾기 자체 확인", lambda: run["detector_ok"])

    _verify(f"원본 깨짐 {label}", body)
