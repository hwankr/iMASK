# ==========================================================================
#  scripts/api_e2e.py — 종료 경로 정리(T2-fix1 M4)와 가린 뒤 자르기(m1). 네트워크 없음.
#  가짜 API(MockTransport)와 가짜 Upstage 서버(api_fakes.FakeUpstageServer)로:
#  시간 초과·첫 조회 Ctrl+C·연결 오류·시작 응답 유실 → Upstage DELETE 1회·종료 코드 1,
#  정상 완료 → 서버가 이미 지움(404 = 성공)·종료 코드 0, 정리 실패·정리 중 Ctrl+C → 종료 코드 1.
#  done 확인(T1 findings-api): 화면용 결과(documents·findings·overall)·응답 크기·원본 파일(sha256) 확인,
#  --analysis-id(만들기·시작 없이 조회만), 계약 위반·원본 불일치·stages 섞임 → 종료 코드 1, 원문 값·서명 URL 미출력.
#  done 응답은 손으로 지은 가짜 결과(fake_findings)를 실제 analysis_out 으로 만든 것이다.
# ==========================================================================

from __future__ import annotations

import copy
import importlib.util
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from api_fakes import FAKE_UPSTAGE_KEY, FakeUpstageServer
from fake_findings import VALUES, stored_result
from fake_tokens import fake_jwt
from fastapi.testclient import TestClient

from imask_backend.analyses import analysis_out
from imask_backend.upstage import UpstageClient

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_ID = "00000000-0000-4000-8000-0000000000aa"
FILE_ID = "file_e2e1"
BUNDLE = (ROOT / "testdocs" / "iMASK_smoke_bundle.pdf").read_bytes()  # 기본 --file
STORAGE_HOST = "fake-storage.invalid"
DOWNLOAD_TOKEN = "FAKE-DOWNLOAD-TOKEN-7777"
DOWNLOAD_URL = f"https://{STORAGE_HOST}/storage/v1/object/sign/documents/analyses/x/document.pdf?token={DOWNLOAD_TOKEN}"
DONE_RESULT = stored_result()  # format·job·summary·stages·response(가짜 응답 — findings 29·boxes 28)


def load_script() -> Any:
    spec = importlib.util.spec_from_file_location("api_e2e", ROOT / "scripts" / "api_e2e.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


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

    def _done(self, request: httpx.Request) -> httpx.Response:
        """실제 analysis_out 으로 만든 done 응답(?include=stages 를 따른다)."""
        include = "stages" in request.url.params.get_list("include")
        body = analysis_out({**_row("done"), "result": copy.deepcopy(DONE_RESULT)}, include_stages=include)
        if self.tamper is not None:
            self.tamper(body["result"], include)
        return httpx.Response(200, json=body)

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
