# ==========================================================================
#  scripts/api_e2e.py — 종료 경로 정리(T2-fix1 M4)와 가린 뒤 자르기(m1). 네트워크 없음.
#  가짜 API(MockTransport)와 가짜 Upstage 서버(api_fakes.FakeUpstageServer)로:
#  시간 초과·첫 조회 Ctrl+C·연결 오류·시작 응답 유실 → Upstage DELETE 1회·종료 코드 1,
#  정상 완료 → 서버가 이미 지움(404 = 성공)·종료 코드 0, 정리 실패·정리 중 Ctrl+C → 종료 코드 1.
#  done 확인(T1 findings-api): 화면용 결과(documents·findings·overall)·응답 크기·원본 파일(sha256) 확인,
#  --analysis-id(만들기·시작 없이 조회만), 계약 위반·원본 불일치·stages 섞임 → 종료 코드 1, 원문 값·서명 URL 미출력.
#  done 응답은 손으로 지은 가짜 결과(fake_findings)를 FakeStore 에 넣고 실제 조회 로직(analysis_read_out)으로 만든 것이다.
#  검토 동작 확인(review-actions): POST 를 실제 review_action_out 으로 처리해 — 흐름 전체 통과(단계 21·쓰기 13·analyses 불변),
#  예상과 다른 응답(409 자리에 200·이력 문구 다름·changed 다름) → 종료 코드 1, --no-review → review-actions 요청 없음,
#  --analysis-id → 읽기만(review-actions 요청 없음 · 모양 확인), review null → 종료 코드 1.
# ==========================================================================

from __future__ import annotations

import copy
import importlib.util
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from api_fakes import FAKE_UPSTAGE_KEY, FakeStore, FakeUpstageServer
from fake_findings import VALUES, stored_result
from fake_tokens import fake_jwt
from fastapi.testclient import TestClient

from imask_backend.analyses import ApiError, analysis_out
from imask_backend.reviews import analysis_read_out, parse_action, parse_json, review_action_out
from imask_backend.textsafe import escaped_json_bytes, has_unpaired_surrogates
from imask_backend.upstage import UpstageClient

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_ID = "00000000-0000-4000-8000-0000000000aa"
FILE_ID = "file_e2e1"
BUNDLE = (ROOT / "testdocs" / "iMASK_smoke_bundle.pdf").read_bytes()  # 기본 --file
STORAGE_HOST = "fake-storage.invalid"
DOWNLOAD_TOKEN = "FAKE-DOWNLOAD-TOKEN-7777"
DOWNLOAD_URL = f"https://{STORAGE_HOST}/storage/v1/object/sign/documents/analyses/x/document.pdf?token={DOWNLOAD_TOKEN}"
DONE_RESULT = stored_result()  # format·job·summary·stages·response(가짜 응답 — findings 29·boxes 28)
CREATED_AT = "2026-11-03T06:41:36.66673+00:00"  # done 분석의 시각(검토 동작 시각 = 지금보다 앞)
UPDATED_AT = "2026-11-03T06:42:20.213505+00:00"
REVIEW_PATH = f"/api/py/analyses/{ANALYSIS_ID}/review-actions"
REVIEW_STEPS = 21  # 처음 조회 1 + 동작 19(쓰기 13 · changed false 1 · 거절 5) + 마지막 확인 1
REVIEW_WRITES = 13


def load_script() -> Any:
    spec = importlib.util.spec_from_file_location("api_e2e", ROOT / "scripts" / "api_e2e.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _json_response(status: int, body: Any) -> httpx.Response:
    """api/index.py 의 _json_out 처럼: 짝 없는 서로게이트가 있으면 ASCII escape JSON, 없으면 보통 JSON."""
    if has_unpaired_surrogates(body):
        return httpx.Response(status, content=escaped_json_bytes(body), headers={"content-type": "application/json"})
    return httpx.Response(status, json=body)


def _row(status: str, *, file_id: str | None = FILE_ID, **extra: Any) -> dict[str, Any]:
    return {
        "id": ANALYSIS_ID,
        "name": "합성",
        "status": status,
        "upstage_job_id": "job_e2e" if status != "queued" else None,
        "error": None,
        "result": None,
        "documents": [{"filename": "iMASK_smoke_bundle.pdf", "upstage_file_id": file_id}],
        "upstage_status": None,
        "poll_error": None,
        **extra,
    }


class FakeApi:
    """백엔드 흉내. start_mode·poll_mode 로 끊김을, start_file·reread_mode 로 정리 경로를 주입한다.

    start_file=False 면 성공한 시작 응답에 file id 가 없다(서버 대체 행에서 빠진 경우와 같은 모양).
    poll_mode 가 interrupt·connect 면 흐름이 첫 GET 에서 끝나므로, 그 뒤의 GET 은 정리 단계의 다시 읽기다.
    reread_mode: file(running + file id) · nofile(running, file id 없음) · connect(연결 오류) · http500
    done 응답과 검토 동작(POST review-actions)은 FakeStore 에 넣은 done 분석으로 **실제 백엔드 로직**
    (analysis_read_out·review_action_out)이 만든다. review_store=False 면 done 응답의 review 가 null(검토 기록을 못 읽음).
    review_override(api, 본문, 몇 번째 POST) 가 응답을 돌려주면 그것을 쓴다(예상과 다른 응답 주입).
    """

    def __init__(
        self,
        *,
        start_mode: str = "ok",
        poll_mode: str = "running",
        start_file: bool = True,
        start_status: str = "running",
        reread_mode: str = "file",
        file_content: bytes = BUNDLE,
        file_status: int = 200,
        tamper: Callable[[dict[str, Any], bool], None] | None = None,
        review_store: bool = True,
        review_override: Callable[[FakeApi, dict[str, Any], int], httpx.Response | None] | None = None,
    ) -> None:
        self.start_mode = start_mode
        self.poll_mode = poll_mode
        self.start_file = start_file
        self.start_status = start_status
        self.reread_mode = reread_mode
        self.file_content = file_content  # 원본 파일 주소로 받을 내용
        self.file_status = file_status
        self.tamper = tamper  # (응답 result, include_stages) 를 고쳐 계약 위반을 주입한다
        self.requests: list[httpx.Request] = []
        self.gets = 0
        self.review_store = review_store
        self.review_override = review_override
        self.review_posts: list[dict[str, Any]] = []
        self.store = FakeStore()
        self.store.analyses[ANALYSIS_ID] = {
            "id": ANALYSIS_ID,
            "name": "합성",
            "status": "done",
            "agent_id": None,
            "upstage_job_id": "job_e2e",
            "result": copy.deepcopy(DONE_RESULT),
            "error": None,
            "created_at": CREATED_AT,
            "updated_at": UPDATED_AT,
        }
        self.store.documents["doc_e2e"] = {
            "id": "doc_e2e",
            "analysis_id": ANALYSIS_ID,
            "filename": "iMASK_smoke_bundle.pdf",
            "storage_path": f"analyses/{ANALYSIS_ID}/document.pdf",
            "size_bytes": len(BUNDLE),
            "mime_type": "application/pdf",
            "upstage_file_id": FILE_ID,
            "created_at": CREATED_AT,
        }

    def read_done(self, include: bool = False) -> dict[str, Any]:
        """실제 조회 응답(analysis_read_out — review 블록 포함). review_store=False 면 review null."""
        row = self.store.get_analysis(ANALYSIS_ID)
        assert row is not None
        if not self.review_store:
            return analysis_out(row, include_stages=include)
        return analysis_read_out(self.store, row, include_stages=include)

    def _done(self, request: httpx.Request) -> httpx.Response:
        """실제 백엔드 로직으로 만든 done 응답(?include=stages 를 따른다)."""
        include = "stages" in request.url.params.get_list("include")
        body = self.read_done(include)
        if self.tamper is not None:
            self.tamper(body["result"], include)
        return _json_response(200, body)

    def _review(self, request: httpx.Request) -> httpx.Response:
        """POST review-actions — 실제 parse_action·review_action_out 으로(오류는 {"detail"})."""
        body = json.loads(request.content)
        self.review_posts.append(body)
        if self.review_override is not None:
            replaced = self.review_override(self, body, len(self.review_posts))
            if replaced is not None:
                return replaced
        try:
            out = review_action_out(self.store, ANALYSIS_ID, parse_action(request.content))
        except ApiError as exc:
            return httpx.Response(exc.status_code, json={"detail": exc.detail})
        return _json_response(200, out)

    def _reread(self) -> httpx.Response:
        if self.reread_mode == "connect":
            raise httpx.ConnectError("down again")
        if self.reread_mode == "http500":
            return httpx.Response(500, text="Internal Server Error")
        if self.reread_mode == "nofile":
            return httpx.Response(200, json=_row("running", file_id=None))
        return httpx.Response(200, json=_row("running"))

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path, method = request.url.path, request.method
        if request.url.host == STORAGE_HOST:  # 서명 다운로드 URL — 사용자 지정 헤더 없이 받는다
            assert "x-demo-code" not in request.headers
            assert request.url.params.get("token") == DOWNLOAD_TOKEN
            return httpx.Response(200, content=self.file_content)
        assert "x-demo-code" not in request.headers  # 접근 코드 없음(2026-11-03 없앰)
        if method == "GET" and path == f"/api/py/analyses/{ANALYSIS_ID}/file":
            if self.file_status != 200:
                return httpx.Response(self.file_status, json={"detail": "원본 파일을 찾을 수 없습니다."})
            body = {"url": DOWNLOAD_URL, "mime_type": "application/pdf", "filename": "iMASK_smoke_bundle.pdf"}
            return httpx.Response(200, json=body, headers={"Cache-Control": "no-store"})
        if method == "POST" and path == REVIEW_PATH:
            return self._review(request)
        if path == "/api/py/health":
            return httpx.Response(200, json={"ok": True, "configured": {}})
        if method == "POST" and path == "/api/py/analyses":
            upload = {"bucket": "documents", "path": f"analyses/{ANALYSIS_ID}/x.pdf", "token": "t", "signed_url": "u"}
            return httpx.Response(201, json={"analysis": _row("queued", file_id=None), "upload": upload})
        if method == "POST" and path.endswith("/start"):
            if self.start_mode == "timeout":
                raise httpx.ReadTimeout("start lost")
            extra = {"error": "Upstage 분석을 시작하지 못했습니다: x"} if self.start_status == "failed" else {}
            row = _row(self.start_status, file_id=FILE_ID if self.start_file else None, **extra)
            return httpx.Response(200, json=row)
        if method == "GET" and path == f"/api/py/analyses/{ANALYSIS_ID}":
            self.gets += 1
            if self.start_mode == "timeout":  # 정리 단계의 다시 읽기
                return httpx.Response(200, json=_row("running"))
            if self.gets > 1 and self.poll_mode in ("interrupt", "connect"):
                return self._reread()
            if self.poll_mode == "interrupt":
                raise KeyboardInterrupt
            if self.poll_mode == "connect":
                raise httpx.ConnectError("down")
            if self.poll_mode == "done":
                return self._done(request)
            return httpx.Response(200, json=_row("running", upstage_status="in_progress"))
        return httpx.Response(404, json={"detail": "요청한 주소를 찾을 수 없습니다."})


@pytest.fixture
def script(monkeypatch: pytest.MonkeyPatch) -> Any:
    module = load_script()
    for name in ("UPSTAGE_API_KEY", "UPSTAGE_PROJECT_ID", "VERCEL_PROTECTION_BYPASS"):
        monkeypatch.delenv(name, raising=False)
    module._SECRETS.clear()
    return module


def _run(
    script: Any, api: FakeApi, upstage: FakeUpstageServer, args: list[str], *, key: bool = True, project: str | None = None
) -> int:
    env: dict[str, str] = {}
    if key:
        env["UPSTAGE_API_KEY"] = FAKE_UPSTAGE_KEY
    if project:
        env["UPSTAGE_PROJECT_ID"] = project

    def client_factory(api_key: str, base_url: str, **kwargs: Any) -> UpstageClient:
        return UpstageClient(api_key, base_url, transport=httpx.MockTransport(upstage.handle), **kwargs)

    with patch.object(script, "_read_env", return_value=env), patch.object(script, "UpstageClient", client_factory):
        return script.main(["--skip-upload", "--interval", "0", *args], transport=httpx.MockTransport(api.handle))


def _deletes(upstage: FakeUpstageServer) -> list[httpx.Request]:
    return upstage.calls("DELETE", "file")


@pytest.mark.parametrize(
    ("poll_mode", "extra_args"),
    [("running", ["--timeout", "0"]), ("interrupt", []), ("connect", [])],
    ids=["timeout", "keyboard_interrupt", "connection_error"],
)
def test_abnormal_exit_deletes_upstage_file(script: Any, capsys: Any, poll_mode: str, extra_args: list[str]) -> None:
    api = FakeApi(poll_mode=poll_mode)
    upstage = FakeUpstageServer()
    upstage.files[FILE_ID] = ("x.pdf", b"")
    code = _run(script, api, upstage, extra_args)
    assert code == 1
    assert len(_deletes(upstage)) == 1
    assert upstage.deleted == [FILE_ID]
    out = capsys.readouterr().out
    assert "정리: Upstage 파일 1개 삭제 요청 완료" in out
    assert FAKE_UPSTAGE_KEY not in out


@pytest.mark.parametrize("project", ["proj_test_FAKE_9", None])
def test_cleanup_sends_project_header_when_set(script: Any, project: str | None) -> None:
    # 서버가 프로젝트 안에 올린 파일은 같은 x-project-id 로만 지울 수 있다
    api = FakeApi(poll_mode="running")
    upstage = FakeUpstageServer()
    upstage.files[FILE_ID] = ("x.pdf", b"")
    assert _run(script, api, upstage, ["--timeout", "0"], project=project) == 1
    (req,) = _deletes(upstage)
    assert req.headers.get("x-project-id") == project
    assert upstage.deleted == [FILE_ID]


def test_lost_start_response_rereads_and_deletes(script: Any, capsys: Any) -> None:
    api = FakeApi(start_mode="timeout")
    upstage = FakeUpstageServer()
    upstage.files[FILE_ID] = ("x.pdf", b"")
    code = _run(script, api, upstage, [])
    assert code == 1
    rereads = [r for r in api.requests if r.method == "GET" and r.url.path.endswith(ANALYSIS_ID)]
    assert len(rereads) == 1
    assert upstage.deleted == [FILE_ID]
    assert "연결 오류: ReadTimeout" in capsys.readouterr().out


def test_normal_done_is_quiet_404_success(script: Any, capsys: Any) -> None:
    api = FakeApi(poll_mode="done")
    upstage = FakeUpstageServer()
    upstage.files[FILE_ID] = ("x.pdf", b"")
    upstage.deleted.append(FILE_ID)  # 서버(조회)가 이미 지웠다
    code = _run(script, api, upstage, [])
    assert code == 0
    assert len(_deletes(upstage)) == 1  # 404 → 성공
    out = capsys.readouterr().out
    assert "지워짐(404)" in out
    assert "정리 못 함" not in out
    assert "결과: 기대대로" in out


# --- done 확인: 화면용 결과·응답 크기·원본 파일(T1 findings-api) ---------------------------


def _fake_values() -> list[str]:
    return [v for page in VALUES.values() for v in page.values()]


def _assert_no_values(out: str) -> None:
    """원문 값·가림 미리보기·서명 URL 은 출력하지 않는다(개수·분포만)."""
    from imask_backend.findings import build_view

    shown = [f["masked"] for f in build_view(DONE_RESULT)["findings"]]
    for text in (*_fake_values(), *shown):
        assert text not in out
    assert DOWNLOAD_TOKEN not in out and DOWNLOAD_URL[:24] not in out


def test_fake_done_result_matches_script_expectations(script: Any) -> None:
    summary = DONE_RESULT["summary"]
    assert (summary["document_count"], summary["extracted_document_count"], summary["risk_level"]) == (6, 5, "상")
    assert script.EXPECTED_FINDINGS == 29 and script.EXPECTED_BOXED == 28


def test_done_checks_view_size_and_original_file(script: Any, capsys: Any) -> None:
    api = FakeApi(poll_mode="done")
    upstage = FakeUpstageServer()
    upstage.deleted.append(FILE_ID)
    upstage.files[FILE_ID] = ("x.pdf", b"")
    assert _run(script, api, upstage, []) == 0
    out = capsys.readouterr().out
    assert "findings: 29 · boxes 있는 항목 28 (기대 29 · 28): 일치" in out
    assert "documents: 6 · kind {'extracted': 5, 'other': 1} · other_guide 있음 1/1 · validation 있음 5/5" in out
    assert "risk 분포: {'unrated': 29}" in out
    assert "overall: level=상 · next_stage=권장_조치" in out
    assert "계약 모양(키·허용 값·id 중복·document_index·boxes 0~1): 맞음" in out
    assert "응답 크기: 기본 GET " in out and "?include=stages GET " in out
    assert "올린 내용과 sha256 일치" in out
    assert "(response·stages 없음: True)" in out
    _assert_no_values(out)
    paths = [(r.method, r.url.path, r.url.query.decode()) for r in api.requests]
    assert ("GET", f"/api/py/analyses/{ANALYSIS_ID}", "include=stages") in paths
    assert ("GET", f"/api/py/analyses/{ANALYSIS_ID}/file", "") in paths
    storage = [r for r in api.requests if r.url.host == STORAGE_HOST]
    assert len(storage) == 1 and "x-demo-code" not in storage[0].headers


def test_analysis_id_mode_only_reads(script: Any, capsys: Any) -> None:
    api = FakeApi(poll_mode="done")
    upstage = FakeUpstageServer()
    assert _run(script, api, upstage, ["--analysis-id", ANALYSIS_ID]) == 0
    assert [r for r in api.requests if r.method != "GET"] == []  # 만들기·시작 없음
    assert upstage.requests == []  # Upstage 를 부르지 않는다(정리도 없음)
    out = capsys.readouterr().out
    assert "기존 분석 확인" in out and "결과: 기대대로 (기존 분석 확인)" in out
    assert "올린 내용과 sha256 일치" in out
    _assert_no_values(out)


def test_analysis_id_mode_not_done_fails(script: Any, capsys: Any) -> None:
    api = FakeApi(poll_mode="running")
    upstage = FakeUpstageServer()
    assert _run(script, api, upstage, ["--analysis-id", ANALYSIS_ID]) == 1
    assert [r for r in api.requests if r.method != "GET"] == []
    assert "상태가 done 이 아님(running)" in capsys.readouterr().out


def test_original_file_mismatch_fails(script: Any, capsys: Any) -> None:
    api = FakeApi(poll_mode="done", file_content=b"%PDF-1.7 other content")
    assert _run(script, api, FakeUpstageServer(), ["--analysis-id", ANALYSIS_ID]) == 1
    assert "올린 내용과 sha256 불일치" in capsys.readouterr().out


def test_original_file_link_error_fails(script: Any, capsys: Any) -> None:
    api = FakeApi(poll_mode="done", file_status=404)
    assert _run(script, api, FakeUpstageServer(), ["--analysis-id", ANALYSIS_ID]) == 1
    assert "원본 파일: HTTP 404 원본 파일을 찾을 수 없습니다." in capsys.readouterr().out


def _drop_key(result: dict[str, Any], _include: bool) -> None:
    result["findings"][0].pop("boxes")


def _duplicate_id(result: dict[str, Any], _include: bool) -> None:
    result["findings"][1]["id"] = result["findings"][0]["id"]
    result["findings"][1]["field"] = result["findings"][0]["field"]


def _bad_box(result: dict[str, Any], _include: bool) -> None:
    result["findings"][0]["boxes"] = [[{"x": 1.5, "y": 0.1}] * 4]


def _bad_risk(result: dict[str, Any], _include: bool) -> None:
    result["findings"][0]["risk"] = "high"  # risk_source 는 null 그대로 — 맞지 않음


def _orphan(result: dict[str, Any], _include: bool) -> None:
    result["findings"][0]["document_index"] = 99
    result["findings"][0]["id"] = "99:" + result["findings"][0]["field"]


def _stages_in_default(result: dict[str, Any], include: bool) -> None:
    if not include:
        result["stages"] = []


def _no_stages_when_asked(result: dict[str, Any], include: bool) -> None:
    if include:
        result.pop("stages")


def _workflow_risk(result: dict[str, Any], _include: bool) -> None:
    result["findings"][0].update(risk="high", risk_source="workflow", risk_reason="가짜")


@pytest.mark.parametrize(
    ("tamper", "message"),
    [
        (_drop_key, "키가 계약과 다름"),
        (_duplicate_id, "finding id 가 겹침"),
        (_bad_box, "boxes 0~1"),
        (_bad_risk, "risk 와 risk_source"),
        (_orphan, "document_index 가 documents 에 없음"),
        (_stages_in_default, "(response·stages 없음: False)"),
        (_no_stages_when_asked, "include=stages 에 stages 있음 False"),
    ],
)
def test_contract_problems_fail(script: Any, capsys: Any, tamper: Any, message: str) -> None:
    api = FakeApi(poll_mode="done", tamper=tamper)
    assert _run(script, api, FakeUpstageServer(), ["--analysis-id", ANALYSIS_ID]) == 1
    out = capsys.readouterr().out
    assert message in out
    assert "결과: 기대와 다름" in out
    _assert_no_values(out)


def test_workflow_risk_is_allowed(script: Any, capsys: Any) -> None:
    # 항목별 등급이 오면(risk_source workflow) unrated 를 강제하지 않는다
    api = FakeApi(poll_mode="done", tamper=_workflow_risk)
    assert _run(script, api, FakeUpstageServer(), ["--analysis-id", ANALYSIS_ID]) == 0
    assert "risk 분포: {'high': 1, 'unrated': 28}" in capsys.readouterr().out


def test_cleanup_failure_makes_exit_1(script: Any, capsys: Any) -> None:
    api = FakeApi(poll_mode="done")
    upstage = FakeUpstageServer()
    upstage.files[FILE_ID] = ("x.pdf", b"")
    upstage.deleted.append(FILE_ID)
    upstage.errors[("DELETE", "file")] = (500, {"error": {"message": f"boom {FAKE_UPSTAGE_KEY}"}})
    code = _run(script, api, upstage, [])
    assert code == 1
    out = capsys.readouterr().out
    assert "정리 못 함" in out
    assert FAKE_UPSTAGE_KEY not in out


def test_keyboard_interrupt_during_cleanup(script: Any, capsys: Any) -> None:
    api = FakeApi(poll_mode="running")
    upstage = FakeUpstageServer()
    upstage.files[FILE_ID] = ("x.pdf", b"")
    upstage.errors[("DELETE", "file")] = KeyboardInterrupt()
    code = _run(script, api, upstage, ["--timeout", "0"])
    assert code == 1
    assert "정리 중 중단됨" in capsys.readouterr().out


def test_no_key_and_unfinished_run_reports_failure(script: Any, capsys: Any) -> None:
    api = FakeApi(poll_mode="running")
    upstage = FakeUpstageServer()
    code = _run(script, api, upstage, ["--timeout", "0"], key=False)
    assert code == 1
    assert "UPSTAGE_API_KEY 가 없어 Upstage 파일 1개를 지우지 못했습니다" in capsys.readouterr().out
    assert upstage.requests == []


def test_no_start_needs_no_cleanup(script: Any) -> None:
    api = FakeApi()
    upstage = FakeUpstageServer()
    assert _run(script, api, upstage, ["--no-start"]) == 0
    assert upstage.requests == []


# --- m1: 가린 뒤 자르기 ---------------------------------------------------------------


def test_upload_error_is_redacted_before_truncation(script: Any, capsys: Any) -> None:
    long_token = "FAKE_LONG_" + "R" * 280
    long_url = "https://storage.invalid/object/upload/sign/documents/probe.pdf?token=" + long_token
    args = script.argparse.Namespace(base_url="http://127.0.0.1:8200")
    run = script.Run(args, {})
    upload = {"bucket": "documents", "path": "analyses/x/document.pdf", "token": long_token, "signed_url": long_url}
    with patch.object(script.httpx, "put", side_effect=RuntimeError(long_url)):
        assert script._upload(run, upload, b"x", "application/pdf") is False
    run.http.close()
    out = capsys.readouterr().out
    assert long_token[:16] not in out
    assert long_url[:24] not in out


@pytest.mark.parametrize("registered", [True, False])
def test_detail_of_non_json_response_is_redacted_before_truncation(script: Any, registered: bool) -> None:
    token = "FAKE_TOK_" + "Z" * 60
    if registered:
        script._hide(token, "<SIGNED_TOKEN>")
        text = "x" * 180 + token  # 등록한 값이 200자 경계에 걸친다
    else:
        text = "x" * 180 + "token=" + token  # 규칙(token=)으로 잡는 값이 경계에 걸친다
    detail = script._detail(httpx.Response(502, text=text))
    assert len(detail) <= 200
    assert token[:12] not in detail


def test_detail_of_json_response_is_redacted(script: Any) -> None:
    jwt = fake_jwt({"fake": "x"}, signature=b"signature-fake")
    detail = script._detail(httpx.Response(400, json={"detail": "x" * 190 + jwt}))
    assert jwt[:9] not in detail  # 자르면 JWT 자리로 9자만 남는다 — 그 9자를 본다(JWT 규칙이 없으면 실패)


# --- R2-M1: 시작 응답에 file id 가 없을 때(fix2) ---------------------------------------


@pytest.mark.parametrize("poll_mode", ["connect", "interrupt"])
def test_start_without_file_id_rereads_and_deletes(script: Any, capsys: Any, poll_mode: str) -> None:
    api = FakeApi(poll_mode=poll_mode, start_file=False, reread_mode="file")
    upstage = FakeUpstageServer()
    upstage.files[FILE_ID] = ("x.pdf", b"")
    code = _run(script, api, upstage, [])
    assert code == 1
    assert api.gets == 2  # 첫 조회(끊김) + 정리의 다시 읽기
    assert upstage.deleted == [FILE_ID]
    assert set(upstage.files) - set(upstage.deleted) == set()
    assert "정리 확인 못 함" not in capsys.readouterr().out


@pytest.mark.parametrize("reread_mode", ["connect", "http500", "nofile"])
def test_start_without_file_id_and_unknown_reread_reports_uncertain(script: Any, capsys: Any, reread_mode: str) -> None:
    api = FakeApi(poll_mode="connect", start_file=False, reread_mode=reread_mode)
    upstage = FakeUpstageServer()
    upstage.files[FILE_ID] = ("x.pdf", b"")
    code = _run(script, api, upstage, [])
    assert code == 1
    assert upstage.requests == []  # 지울 file id 를 모른다
    out = capsys.readouterr().out
    assert "정리 확인 못 함" in out
    assert "정리를 끝내지 못해 실패로 끝냅니다" in out
    assert FAKE_UPSTAGE_KEY not in out


def test_terminal_start_without_file_id_needs_no_reread(script: Any) -> None:
    api = FakeApi(start_file=False, start_status="failed")
    upstage = FakeUpstageServer()
    assert _run(script, api, upstage, ["--expect", "failed"]) == 0
    assert api.gets == 0
    assert upstage.requests == []


# --- 실제 FastAPI 앱 응답을 e2e 전송층에 그대로 연결 ------------------------------------


def _integrated(
    script: Any,
    *,
    fail_final_read: bool,
    lose_start_response: bool = False,
    fail_first_poll: bool = True,
    fail_cleanup_read: bool = False,
):
    """실제 app(TestClient) → e2e. 브라우저 업로드만 FakeStore 에 직접 넣고, Upstage 는 진짜 클라이언트 + 가짜 서버.

    fail_final_read: 시작의 마지막 DB 다시 읽기 실패(서버 대체 행). fail_first_poll: 첫 조회 연결 오류.
    lose_start_response: 서버는 시작을 끝냈지만 e2e 는 응답을 못 받음(그 뒤 GET 은 정리의 다시 읽기).
    fail_cleanup_read: 정리의 다시 읽기도 끊김.
    """
    from api_fakes import FAKE_ENV, FakeStore

    from api.index import app, get_store, get_upstage
    from imask_backend.settings import get_settings, load_settings

    settings = load_settings(FAKE_ENV)
    store = FakeStore()
    if fail_final_read:
        store.fail_get_calls = {2}  # 1: 시작 전 읽기, 2: 시작의 마지막 다시 읽기
    upstage = FakeUpstageServer()
    server_client = UpstageClient.from_settings(
        settings.upstage(), extra_secrets=settings.secrets(), transport=httpx.MockTransport(upstage.handle)
    )
    starts: list[dict[str, Any]] = []
    gets = {"n": 0}
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_upstage] = lambda: lambda: server_client
    try:
        with TestClient(app) as api_client:

            def bridge(request: httpx.Request) -> httpx.Response:
                path = request.url.path
                if request.method == "GET" and path.startswith("/api/py/analyses/"):
                    gets["n"] += 1
                    is_cleanup = lose_start_response or gets["n"] >= 2
                    if is_cleanup and fail_cleanup_read:
                        raise httpx.ConnectError("cleanup read lost")
                    if not is_cleanup and fail_first_poll:
                        raise httpx.ConnectError("first poll lost")
                response = api_client.request(request.method, path, headers=dict(request.headers), content=request.content)
                if path.endswith("/start"):
                    starts.append(response.json())
                    if lose_start_response:
                        raise httpx.ReadTimeout("start response lost")
                return httpx.Response(response.status_code, content=response.content, headers={"content-type": "application/json"})

            def browser_upload(_run: Any, upload: dict[str, str], content: bytes, _mime: str) -> bool:
                store.objects[upload["path"]] = content
                return True

            def cleanup_client(api_key: str, base_url: str, **kwargs: Any) -> UpstageClient:
                return UpstageClient(api_key, base_url, transport=httpx.MockTransport(upstage.handle), **kwargs)

            env = {"UPSTAGE_API_KEY": FAKE_UPSTAGE_KEY}
            with (
                patch.object(script, "_read_env", return_value=env),
                patch.object(script, "_upload", browser_upload),
                patch.object(script, "UpstageClient", cleanup_client),
            ):
                code = script.main(["--interval", "0"], transport=httpx.MockTransport(bridge))
    finally:
        app.dependency_overrides.clear()
        server_client.close()
    return code, store, upstage, starts, gets["n"]


@pytest.mark.parametrize("fail_final_read", [False, True], ids=["control", "final_reread_fails"])
def test_real_api_start_then_lost_poll_cleans_up(script: Any, capsys: Any, fail_final_read: bool) -> None:
    code, store, upstage, starts, gets = _integrated(script, fail_final_read=fail_final_read)
    assert code == 1  # 첫 조회 연결 오류
    assert len(upstage.job_bodies) == 1
    (started,) = starts
    assert started["status"] == "running"
    assert started["upstage_job_id"]
    assert [d["upstage_file_id"] for d in started["documents"]] == ["file_fake1"]  # 대체 행에서도 빠지지 않음
    assert [d["upstage_file_id"] for d in store.documents.values()] == ["file_fake1"]
    assert len(upstage.calls("DELETE", "file")) == 1
    assert set(upstage.files) - set(upstage.deleted) == set()  # 남은 파일 0
    assert "정리 확인 못 함" not in capsys.readouterr().out


def test_real_api_lost_start_response_rereads_and_cleans_up(script: Any) -> None:
    code, _, upstage, starts, gets = _integrated(script, fail_final_read=False, lose_start_response=True)
    assert code == 1  # 시작 응답 유실(연결 오류)
    assert starts and starts[0]["status"] == "running"  # 서버는 시작을 끝냈다
    assert gets == 1  # 정리의 다시 읽기 한 번 → 실제 API 가 file id 를 준다
    assert len(upstage.calls("DELETE", "file")) == 1
    assert set(upstage.files) - set(upstage.deleted) == set()


def test_real_api_cleanup_read_lost_reports_uncertain(script: Any, capsys: Any) -> None:
    code, _, upstage, _, _ = _integrated(script, fail_final_read=False, lose_start_response=True, fail_cleanup_read=True)
    assert code == 1
    assert upstage.calls("DELETE", "file") == []
    out = capsys.readouterr().out
    assert "정리 확인 못 함" in out
    assert FAKE_UPSTAGE_KEY not in out


# --- 검토 동작 확인(review-actions) ----------------------------------------------------------


def _review_types(api: FakeApi) -> list[str]:
    return [str(body.get("type")) for body in api.review_posts]


def _review_requests(api: FakeApi) -> list[httpx.Request]:
    return [r for r in api.requests if r.url.path.endswith("/review-actions")]


def _done_upstage() -> FakeUpstageServer:
    upstage = FakeUpstageServer()
    upstage.files[FILE_ID] = ("x.pdf", b"")
    upstage.deleted.append(FILE_ID)  # 서버(조회)가 이미 지웠다
    return upstage


def test_review_flow_passes_against_real_review_logic(script: Any, capsys: Any) -> None:
    api = FakeApi(poll_mode="done")
    assert _run(script, api, _done_upstage(), []) == 0
    out = capsys.readouterr().out
    assert "[실패]" not in out
    assert f"검토 동작 확인: {REVIEW_STEPS}/{REVIEW_STEPS} 통과 · 쓴 동작 {REVIEW_WRITES}건 — 기대대로" in out
    assert "결과: 기대대로" in out
    # 순서대로 보낸 동작(BRIEF §5.5 의 9종 + 거절 확인)
    assert _review_types(api) == [
        "set_status",
        "set_status",
        "confirm_many",
        "set_status",
        "mark_false_positive",
        "restore",
        "reclassify",
        "reclassify",
        "mark_false_positive",
        "restore",
        "save_finding_memo",
        "save_finding_memo",
        "save_memo",
        "complete_review",
        "set_status",
        "complete_review",
        "reopen_review",
        "delete_everything",
        "save_memo",
    ]
    assert {body.get("actor") for body in api.review_posts} == {"api_e2e"}
    # 저장된 검토 행: 쓰기 13번 = version 13 = 이력 13줄, 다시 연 상태
    saved = api.store.reviews[ANALYSIS_ID]
    assert saved["version"] == REVIEW_WRITES and len(saved["history"]) == REVIEW_WRITES
    assert [line["kind"] for line in saved["history"]] == [
        "confirm",
        "unconfirm",
        "confirm",
        "fp",
        "restore",
        "reclass",
        "fp",
        "restore",
        "fmemo",
        "fmemo",
        "memo",
        "complete",
        "reopen",
    ]
    assert saved["status"] == "needed" and saved["reviewer"] == "api_e2e" and saved["reviewed_at"] is None
    # analyses 행은 쓰지 않는다(분석 시각·걸린 시간 불변)
    row = api.store.analyses[ANALYSIS_ID]
    assert (row["created_at"], row["updated_at"]) == (CREATED_AT, UPDATED_AT)
    assert "update_analysis" not in api.store.calls
    _assert_no_values(out)


def _accept_second_confirm(api: FakeApi, body: dict[str, Any], n: int) -> httpx.Response | None:
    # 4번째 POST(같은 항목 다시 확인 — 409 를 기대하는 자리)에 200 을 돌려준다
    if n == 4:
        return httpx.Response(200, json={"analysis": api.read_done(), "changed": False})
    return None


def _wrong_change_text(api: FakeApi, body: dict[str, Any], n: int) -> httpx.Response | None:
    # 첫 동작은 그대로 저장하되 응답의 새 이력 change 문구만 다르게
    if n != 1:
        return None
    out = review_action_out(api.store, ANALYSIS_ID, parse_action(json.dumps(body).encode()))
    out["analysis"]["review"]["history"][-1]["change"] = "다른 문구"
    return httpx.Response(200, json=out)


def _changed_true_without_write(api: FakeApi, body: dict[str, Any], n: int) -> httpx.Response | None:
    # 같은 값 분류 수정(8번째 POST)에 changed true 로 답한다
    if n == 8:
        return httpx.Response(200, json={"analysis": api.read_done(), "changed": True})
    return None


def _wrong_409_detail(api: FakeApi, body: dict[str, Any], n: int) -> httpx.Response | None:
    # 잠김 409 자리(15번째 POST)에 다른 409 문구
    if n == 15:
        return httpx.Response(409, json={"detail": "탐지 항목 상태가 바뀌었습니다. 새로 고친 뒤 다시 시도해 주세요."})
    return None


@pytest.mark.parametrize(
    ("override", "message"),
    [
        (_accept_second_confirm, "HTTP 200"),
        (_wrong_change_text, "새 이력 change: '다른 문구'"),
        (_changed_true_without_write, "changed True(기대 false)"),
        (_wrong_409_detail, "HTTP 409 탐지 항목 상태가 바뀌었습니다."),
    ],
    ids=["409_became_200", "history_text_differs", "changed_differs", "wrong_409_detail"],
)
def test_unexpected_review_response_fails(script: Any, capsys: Any, override: Any, message: str) -> None:
    api = FakeApi(poll_mode="done", review_override=override)
    assert _run(script, api, _done_upstage(), []) == 1
    out = capsys.readouterr().out
    assert "[실패]" in out
    assert message in out
    assert "검토 동작 확인: " in out and "— 기대와 다름" in out
    assert "결과: 기대와 다름" in out


def test_no_review_sends_no_review_actions(script: Any, capsys: Any) -> None:
    api = FakeApi(poll_mode="done")
    assert _run(script, api, _done_upstage(), ["--no-review"]) == 0
    assert _review_requests(api) == []
    assert api.store.reviews == {}
    out = capsys.readouterr().out
    assert "검토 동작 확인 건너뜀(--no-review)" in out
    assert "결과: 기대대로" in out


def test_analysis_id_mode_reads_review_shape_only(script: Any, capsys: Any) -> None:
    api = FakeApi(poll_mode="done")
    assert _run(script, api, FakeUpstageServer(), ["--analysis-id", ANALYSIS_ID]) == 0
    assert _review_requests(api) == []
    assert [r for r in api.requests if r.method != "GET"] == []
    assert api.store.reviews == {}
    out = capsys.readouterr().out
    assert (
        "검토 기록 모양(읽기만, 동작 보내지 않음): status=needed · findings 0개 · 이력 2줄(S1·S2 포함) · version 0"
        " · 기본값(검토 행 없음) True: 맞음"
    ) in out
    assert "결과: 기대대로 (기존 분석 확인)" in out


def test_analysis_id_mode_accepts_reviewed_analysis(script: Any, capsys: Any) -> None:
    # 이미 검토한 기존 분석도 모양만 본다(기본값을 강제하지 않음) — 그래도 동작은 보내지 않는다
    api = FakeApi(poll_mode="done")
    finding_id = api.read_done()["result"]["findings"][0]["id"]
    body = {"type": "set_status", "actor": "검토자", "finding_id": finding_id, "status": "confirmed", "reason": ""}
    review_action_out(api.store, ANALYSIS_ID, parse_action(json.dumps(body).encode()))
    assert _run(script, api, FakeUpstageServer(), ["--analysis-id", ANALYSIS_ID]) == 0
    assert _review_requests(api) == []
    assert api.store.reviews[ANALYSIS_ID]["version"] == 1
    out = capsys.readouterr().out
    assert "status=needed · findings 1개 · 이력 3줄(S1·S2 포함) · version 1 · 기본값(검토 행 없음) False: 맞음" in out


def test_analysis_id_mode_no_review_skips_shape(script: Any, capsys: Any) -> None:
    api = FakeApi(poll_mode="done", review_store=False)
    assert _run(script, api, FakeUpstageServer(), ["--analysis-id", ANALYSIS_ID, "--no-review"]) == 0
    assert "검토 기록 모양 확인 건너뜀(--no-review)" in capsys.readouterr().out


@pytest.mark.parametrize("existing", [False, True], ids=["new_analysis", "analysis_id"])
def test_review_null_fails(script: Any, capsys: Any, existing: bool) -> None:
    # 검토 기록을 읽지 못한 응답(review null)이면 실패 — 새 분석이어도 동작을 보내지 않는다
    api = FakeApi(poll_mode="done", review_store=False)
    args = ["--analysis-id", ANALYSIS_ID] if existing else []
    assert _run(script, api, _done_upstage(), args) == 1
    assert _review_requests(api) == []
    assert "review 가 객체가 아님" in capsys.readouterr().out


def _run_through_real_app(script: Any, api: FakeApi) -> tuple[int, list[dict[str, Any]], list[str]]:
    """조회·검토 동작을 실제 FastAPI 앱(TestClient)으로 — api/index.py 경로·본문 읽기(65,536 바이트 한도·413)·_json_out·
    오류 모양까지 지난다. 만들기·시작·파일은 FakeApi 그대로. → (종료 코드, 검토 POST 마다 {type, bytes, status}, Upstage 생성 기록)"""
    from api_fakes import FAKE_ENV

    from api.index import app, get_store, get_upstage
    from imask_backend.settings import get_settings, load_settings

    built: list[str] = []
    posts: list[dict[str, Any]] = []

    def no_upstage() -> UpstageClient:
        built.append("upstage")
        raise AssertionError("done 조회·검토 동작은 Upstage 를 부르지 않는다")

    settings = load_settings(FAKE_ENV)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_store] = lambda: api.store
    app.dependency_overrides[get_upstage] = lambda: no_upstage
    analysis_path = f"/api/py/analyses/{ANALYSIS_ID}"
    try:
        with TestClient(app) as client:

            def handle(request: httpx.Request) -> httpx.Response:
                path = request.url.path
                if not (path == REVIEW_PATH or (request.method == "GET" and path == analysis_path)):
                    return api.handle(request)  # 만들기·시작·파일 등은 FakeApi 그대로
                api.requests.append(request)
                if request.method == "POST":
                    assert request.headers["content-type"] == "application/json"
                    assert int(request.headers["content-length"]) == len(request.content)
                    api.review_posts.append(parse_json(request.content))  # 서버와 같은 파서(같은 키 두 번·UTF-8 검사)
                response = client.request(
                    request.method, path, params=request.url.params, headers=dict(request.headers), content=request.content
                )
                if request.method == "POST":
                    posts.append({"type": api.review_posts[-1].get("type"), "bytes": len(request.content), "status": response.status_code})
                return httpx.Response(response.status_code, content=response.content, headers={"content-type": "application/json"})

            env = {"UPSTAGE_API_KEY": FAKE_UPSTAGE_KEY}
            upstage = _done_upstage()

            def client_factory(api_key: str, base_url: str, **kwargs: Any) -> UpstageClient:
                return UpstageClient(api_key, base_url, transport=httpx.MockTransport(upstage.handle), **kwargs)

            with patch.object(script, "_read_env", return_value=env), patch.object(script, "UpstageClient", client_factory):
                code = script.main(["--skip-upload", "--interval", "0"], transport=httpx.MockTransport(handle))
    finally:
        app.dependency_overrides.clear()
    return code, posts, built


def test_review_flow_through_real_app_never_builds_upstage(script: Any, capsys: Any) -> None:
    # 실제 FastAPI 앱을 지나도 흐름 통과, Upstage 클라이언트는 만들지 않는다
    api = FakeApi(poll_mode="done")
    code, posts, built = _run_through_real_app(script, api)
    out = capsys.readouterr().out
    assert code == 0, out[-3000:]
    assert f"검토 동작 확인: {REVIEW_STEPS}/{REVIEW_STEPS} 통과" in out
    assert built == []
    assert len(api.review_posts) == 19
    assert [p["status"] for p in posts].count(200) == 14
    assert api.store.reviews[ANALYSIS_ID]["version"] == REVIEW_WRITES
    row = api.store.analyses[ANALYSIS_ID]
    assert (row["created_at"], row["updated_at"]) == (CREATED_AT, UPDATED_AT)


# --- 특수한 추출 키(표시 이름·이력 target 경계, V-T3-1 m1·m2) -----------------------------------
# 글자는 모두 chr() 로 만든다(소스에 보이지 않는 글자를 넣지 않게). 가짜 결과의 첫 추출 키(applicant_name — D1-01)를
# 바꿔 실제 build_view·검토 로직·FakeStore 로 응답을 만든다. 표에 없는 키라 label 도 그 키다.

FIRST_KEY = "applicant_name"
NUL, FFFD, ELLIPSIS = chr(0), chr(0xFFFD), chr(0x2026)


def _rename_key(value: Any, new_key: str) -> Any:
    """저장 형식 결과 안의 추출 키 FIRST_KEY 를 new_key 로 — dict 키와 JSON 문자열 안까지(build_view 가 읽는 경로)."""
    if isinstance(value, dict):
        return {(new_key if k == FIRST_KEY else k): _rename_key(v, new_key) for k, v in value.items()}
    if isinstance(value, list):
        return [_rename_key(v, new_key) for v in value]
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (ValueError, TypeError):
            return value
        if isinstance(decoded, (dict, list)):
            return json.dumps(_rename_key(decoded, new_key), ensure_ascii=True)
    return value


def _api_with_first_key(new_key: str, **kwargs: Any) -> FakeApi:
    api = FakeApi(poll_mode="done", **kwargs)
    row = api.store.analyses[ANALYSIS_ID]
    row["result"] = _rename_key(row["result"], new_key)
    first = api.read_done()["result"]["findings"][0]
    assert (first["field"], first["document_index"]) == (new_key, 0)  # D1-01 이 그 키
    return api


# (이름, 추출 키, 이름 기반 이력 target 의 저장 모양 — 계약대로 손으로 적은 기대값)
SPECIAL_KEYS = [
    ("FEFF_trimmed", chr(0xFEFF) + "probe" + chr(0xFEFF), "D1-01 probe"),
    ("NEL_kept", chr(0x85) + "probe" + chr(0x85), "D1-01 " + chr(0x85) + "probe" + chr(0x85)),
    *[(f"U+{c:04X}_kept", chr(c) + "probe" + chr(c), "D1-01 " + chr(c) + "probe" + chr(c)) for c in range(0x1C, 0x20)],
    ("JS_spaces_trimmed", chr(0x3000) + chr(0x2028) + "probe" + chr(0x202F) + chr(0xA0), "D1-01 probe"),
    ("only_FEFF_unnamed", chr(0xFEFF), "D1-01 이름 없는 항목"),
    ("target_200_kept", "q" * 194, "D1-01 " + "q" * 194),
    ("target_201_cut", "q" * 195, "D1-01 " + "q" * 193 + ELLIPSIS),
    ("long_210_cut", "p" * 210, "D1-01 " + "p" * 193 + ELLIPSIS),
    ("NUL_replaced", "probe" + NUL, "D1-01 probe" + FFFD),
    ("lone_surrogate_replaced", "probe" + chr(0xD800), "D1-01 probe" + FFFD),
    ("astral_kept", "probe" + chr(0x1F600), "D1-01 probe" + chr(0x1F600)),
]


@pytest.mark.parametrize(("new_key", "stored_target"), [c[1:] for c in SPECIAL_KEYS], ids=[c[0] for c in SPECIAL_KEYS])
def test_special_extraction_keys_pass_review_checks(script: Any, capsys: Any, new_key: str, stored_target: str) -> None:
    api = _api_with_first_key(new_key)
    code = _run(script, api, _done_upstage(), [])
    out = capsys.readouterr().out
    assert "[실패]" not in out, out[-3000:]
    assert f"검토 동작 확인: {REVIEW_STEPS}/{REVIEW_STEPS} 통과 · 쓴 동작 {REVIEW_WRITES}건 — 기대대로" in out
    assert code == 0
    saved = api.store.reviews[ANALYSIS_ID]
    assert saved["version"] == REVIEW_WRITES
    # 이름 기반 이력 줄(fp·restore·reclass·fp·restore)의 저장된 target = 계약대로 손으로 적은 값
    named = [line["target"] for line in saved["history"] if line["kind"] in ("fp", "restore", "reclass")]
    assert named == [stored_target] * 5
    assert len(stored_target) <= 200


def _unsafe_target(raw_target: str) -> Callable[[FakeApi, dict[str, Any], int], httpx.Response | None]:
    """첫 오탐 표시(5번째 POST)의 응답에서 새 이력 target 을 안전화하지 않은 원래 이름으로 바꾼다(저장은 정상)."""

    def override(api: FakeApi, body: dict[str, Any], n: int) -> httpx.Response | None:
        if n != 5:
            return None
        assert body["type"] == "mark_false_positive"
        out = review_action_out(api.store, ANALYSIS_ID, parse_action(json.dumps(body, ensure_ascii=True).encode()))
        out["analysis"]["review"]["history"][-1]["target"] = raw_target
        return _json_response(200, out)

    return override


@pytest.mark.parametrize(
    ("new_key", "raw_target"),
    [
        ("probe" + NUL, "D1-01 probe" + NUL),  # NUL 그대로
        ("probe" + chr(0xDC00), "D1-01 probe" + chr(0xDC00)),  # 짝 없는 서로게이트 그대로
        ("p" * 210, "D1-01 " + "p" * 210),  # 자르지 않음
        ("q" * 195, "D1-01 " + "q" * 195),  # 201자 그대로
        ("q" * 195, "D1-01 " + "q" * 194 + ELLIPSIS),  # 200자를 넘는 자르기(앞 199 + … 가 아님)
    ],
    ids=["NUL_raw", "surrogate_raw", "untruncated_210", "untruncated_201", "wrong_cut"],
)
def test_unsafe_target_in_response_fails(script: Any, capsys: Any, new_key: str, raw_target: str) -> None:
    api = _api_with_first_key(new_key, review_override=_unsafe_target(raw_target))
    assert _run(script, api, _done_upstage(), []) == 1
    out = capsys.readouterr().out
    assert "[실패] 06. mark_false_positive(D1-01)" in out
    assert "새 이력 target:" in out
    assert "— 기대와 다름" in out


def test_js_trim_set_is_ecmascript_whitespace_and_line_terminators(script: Any) -> None:
    import unicodedata

    zs = {c for c in range(0x110000) if unicodedata.category(chr(c)) == "Zs"}
    expected = zs | {0x09, 0x0B, 0x0C, 0x20, 0xA0, 0xFEFF} | {0x0A, 0x0D, 0x2028, 0x2029}
    assert {ord(c) for c in script.JS_TRIM_CHARS} == expected
    for kept in (0x85, 0x1C, 0x1D, 0x1E, 0x1F, 0x180E, 0x200B, 0x0):  # Python strip() 이나 다른 곳과 다른 글자
        assert chr(kept) not in script.JS_TRIM_CHARS
    assert script._js_trim(chr(0xFEFF) + " a " + chr(0x3000)) == "a"
    assert script._js_trim(chr(0x85) + "a" + chr(0x1F)) == chr(0x85) + "a" + chr(0x1F)


def test_stored_target_boundaries(script: Any) -> None:
    assert script._stored_target("x" * 200) == "x" * 200
    assert script._stored_target("x" * 201) == "x" * 199 + ELLIPSIS
    assert len(script._stored_target("x" * 5000)) == 200
    assert script._stored_target("a" + NUL + chr(0xD83D) + chr(0xDE00) + "b") == "a" + FFFD * 3 + "b"  # 따로 든 서로게이트는 각각
    assert script._stored_target(chr(0x1F600) * 200) == chr(0x1F600) * 200  # 보충 평면 글자는 한 코드 포인트
    assert script._stored_target(NUL * 201) == FFFD * 199 + ELLIPSIS


# --- 검토 POST 본문 직렬화(V-T3-2 m3): httpx json= 과 같은 UTF-8, 짝 없는 서로게이트만 escape ---------------------

BACKSLASH = chr(92)
SERIALIZE_CASES = [
    ("plain_ascii", {"type": "set_status", "actor": "api_e2e", "finding_id": "0:applicant_name", "status": "open", "reason": ""}),
    ("korean", {"type": "save_memo", "actor": "이지은", "text": "검토 메모 " + "한" * 300}),
    ("quotes_backslash_control", {"type": "save_memo", "actor": "a", "text": 'q"' + BACKSLASH + chr(0x1F) + chr(0x7F) + NUL}),
    ("astral", {"type": "save_finding_memo", "actor": "a", "finding_id": "0:" + chr(0x1F600), "text": chr(0x10FFFF)}),
    ("high_surrogate", {"type": "set_status", "actor": "a", "finding_id": "0:probe" + chr(0xD800), "status": "open", "reason": ""}),
    ("low_surrogate_in_list", {"type": "confirm_many", "actor": "a", "finding_ids": ["0:" + chr(0xDFFF), "1:x" + chr(0xDC00) + "y"]}),
    ("separated_surrogates", {"type": "save_memo", "actor": "a", "text": chr(0xD83D) + "-" + chr(0xDE00)}),
]


@pytest.mark.parametrize("value", [c[1] for c in SERIALIZE_CASES], ids=[c[0] for c in SERIALIZE_CASES])
def test_json_body_round_trips_through_server_parser(script: Any, value: dict[str, Any]) -> None:
    body = script._json_body(value)
    text = body.decode("utf-8")  # 늘 유효한 UTF-8
    assert parse_json(body) == value  # 서버 본문 파서(같은 키 두 번·NaN·UTF-8 엄격)가 읽으면 넘긴 객체와 정확히 같다
    assert json.loads(text) == value
    surrogates = [c for c in json.dumps(value, ensure_ascii=False) if 0xD800 <= ord(c) <= 0xDFFF]
    escapes = [BACKSLASH + "u" + f"{ord(c):04x}" for c in surrogates]
    assert all(e in text for e in escapes)
    if not surrogates:
        # 서로게이트가 없으면 httpx json= 과 바이트까지 같다(같은 크기 — 서버 본문 한도 기준이 바뀌지 않음)
        assert body == json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        assert body == httpx.Request("POST", "http://local.invalid/", json=value).content
    else:
        # 서로게이트 말고는 escape 하지 않는다(한글·보충 평면 글자는 UTF-8 그대로)
        plain = {k: v for k, v in value.items() if k in ("type", "actor")}
        assert script._json_body(plain) == httpx.Request("POST", "http://local.invalid/", json=plain).content
        assert text.count(BACKSLASH + "u") == len(surrogates)


def test_json_body_keeps_korean_size_like_httpx(script: Any) -> None:
    value = {"type": "set_status", "actor": "api_e2e", "finding_id": "0:" + "한" * 11000, "status": "confirmed", "reason": ""}
    body = script._json_body(value)
    assert len(body) == len(httpx.Request("POST", "http://local.invalid/", json=value).content)
    assert 33_000 < len(body) < 65_536  # 예전 ASCII escape(약 66,000 바이트 — 413)와 달리 한도 안


def test_review_post_body_sends_lone_surrogate_id(script: Any) -> None:
    # 짝 없는 서로게이트가 든 계약 id 도 보낸다 — 그 글자만 escape, 본문은 UTF-8 JSON
    api = _api_with_first_key("probe" + chr(0xD800))
    assert _run(script, api, _done_upstage(), []) == 0
    posts = _review_requests(api)
    assert len(posts) == 19
    for request in posts:
        request.content.decode("utf-8")
        assert request.headers["content-type"] == "application/json"
    assert parse_json(posts[0].content)["finding_id"] == "0:probe" + chr(0xD800)
    assert (BACKSLASH + "ud800").encode() in posts[0].content
    assert ("가" * 501).encode("utf-8") in posts[-1].content  # 마지막(501자 글) — 한글은 escape 없이 UTF-8 그대로


@pytest.mark.parametrize(
    "new_key",
    ["한" * 11000, "probe" + chr(0xD800), "probe" + chr(0xDC00) + "한" * 100],
    ids=["korean_11000", "lone_high_surrogate", "lone_low_surrogate_korean"],
)
def test_real_app_body_limit_accepts_long_korean_and_surrogate_ids(script: Any, capsys: Any, new_key: str) -> None:
    # 실제 FastAPI 앱의 본문 읽기(65,536 바이트 한도)를 지난다 — 한글 11,000자 id 는 첫 요청 약 33KB 로 한도 안
    api = _api_with_first_key(new_key)
    code, posts, built = _run_through_real_app(script, api)
    out = capsys.readouterr().out
    assert "[실패]" not in out, out[-3000:]
    assert f"검토 동작 확인: {REVIEW_STEPS}/{REVIEW_STEPS} 통과 · 쓴 동작 {REVIEW_WRITES}건 — 기대대로" in out
    assert code == 0
    assert built == []
    assert len(posts) == 19 and 413 not in [p["status"] for p in posts]
    assert max(p["bytes"] for p in posts) < 65_536
    if new_key.startswith("한"):
        assert posts[0]["bytes"] > 33_000  # UTF-8 그대로(한 글자 3바이트) — 예전 ASCII escape 면 약 66KB 로 413
    assert api.store.reviews[ANALYSIS_ID]["version"] == REVIEW_WRITES


def test_real_app_body_over_limit_is_still_413(script: Any, capsys: Any) -> None:
    # 실제 본문이 65,536 바이트를 넘는 id(한글 23,000자 ≈ 69KB)는 서버가 413 — 검증기는 실패(종료 코드 1)로 끝난다
    api = _api_with_first_key("한" * 23000)
    code, posts, built = _run_through_real_app(script, api)
    out = capsys.readouterr().out
    assert code == 1
    assert built == []
    over = [p for p in posts if p["bytes"] > 65_536]
    assert over and all(p["status"] == 413 for p in over)
    assert all(p["status"] != 413 for p in posts if p["bytes"] <= 65_536)
    assert "HTTP 413 요청 본문이 너무 큽니다." in out
    assert "— 기대와 다름" in out
    assert api.store.reviews.get(ANALYSIS_ID, {}).get("version", 0) < REVIEW_WRITES
