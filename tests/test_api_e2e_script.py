# ==========================================================================
#  scripts/api_e2e.py — 종료 경로 정리(T2-fix1 M4)와 가린 뒤 자르기(m1). 네트워크 없음.
#  가짜 API(MockTransport)와 가짜 Upstage 서버(api_fakes.FakeUpstageServer)로:
#  시간 초과·첫 조회 Ctrl+C·연결 오류·시작 응답 유실 → Upstage DELETE 1회·종료 코드 1,
#  정상 완료 → 서버가 이미 지움(404 = 성공)·종료 코드 0, 정리 실패·정리 중 Ctrl+C → 종료 코드 1.
#  done 확인(T1 findings-api): 화면용 결과(documents·findings·overall)·응답 크기·원본 파일(sha256) 확인,
#  --analysis-id(만들기·시작 없이 조회만), 계약 위반·원본 불일치·stages 섞임 → 종료 코드 1, 원문 값·서명 URL 미출력.
#  done 응답은 손으로 지은 가짜 결과(fake_findings)를 FakeStore 에 넣고 실제 조회 로직(analysis_read_out)으로 만든 것이다.
#  검토사항(review-items T3): done 확인의 result.items — 스크립트가 따로 계산한 기대값이 백엔드 build_items 와 여러 모양에서 같음,
#  계약과 다른 items(키·순서·번호·id·쪽·참조·글·개수·종류)·green 아닌 검증(새 모양) → 종료 코드 1(출력은 위치·키 이름만),
#  해결·다시 열기 흐름(본문·이력 H12~H15·해결 기록·잠긴 채 409 둘), 계약과 다른 응답 21가지 → 종료 코드 1, 검토사항 0개면 건너뜀,
#  검증 실패 결과(missing 1개)도 검토 동작 통과, 읽기만 하는 확인의 review.items 모양.
#  수정 1회차(V-T3-1 M1): 검토 동작을 켠 기본 흐름에서 items 모양이 틀리면(번호·id 타입·종류·빈 제목·쪽) 검토사항 POST 0개·
#  받은 값 미출력, 모양은 맞고 값만 다르면(제목·설명·id) 흐름은 그대로 · 받은 값 미출력, review 블록 status·version·findings 키 미출력.
#  검토 동작 확인(review-actions): POST 를 실제 review_action_out 으로 처리해 — 흐름 전체 통과(단계 35·쓰기 18·analyses 불변),
#  예상과 다른 응답(409 자리에 200·이력 문구 다름·changed 다름) → 종료 코드 1, --no-review → review-actions 요청 없음,
#  --analysis-id → 읽기만(review-actions 요청 없음 · 모양 확인), review null → 종료 코드 1.
#  내보내기 기록(log_export, live-report T3): 잠긴 상태에서 CSV·JSON 두 번(본문 6키·이 분석의 이름·그럴듯한 크기, 이력 줄 H13·H14
#  문구·크기 표기)·거절 두 번(이름 아님·size 0 → 400, 쓰기 없음), 계약과 다른 가짜 응답(문구·잠김 409·바뀌면 안 되는 열·거절 자리에
#  200·거절하며 쓰기·다른 400 문구) → 종료 코드 1, 크기 표기(_fmt_size)가 공유 표 tests/fmt_size_cases.json·백엔드 fmt_size 와 같음,
#  파일 이름(_export_name)이 손으로 적은 값·백엔드 expected_file_name 과 같음(자정 경계·Z·해 넘김), created_at 을 못 읽으면 보내지 않음.
#  공유 목록·삭제·다시 분석(shared-analyses): 가짜 API(FakeApi — 목록은 실제 list_out, 삭제는 FakeStore cascade)로 목록 확인·
#  삭제 확인·기본 삭제(정상·비정상 종료·--no-start)·--keep·실패 경로(목록 계약 위반·지워지지 않는 삭제·삭제 502·연결 오류),
#  실제 FastAPI 앱(shared_ctx.install — FakeStore + 가짜 Upstage 서버)으로 --retry-flow(통과·고정 기대값과 따로 판정·옛 이력 순서·
#  틀린 사유·원본 없이 작업을 만든 응답·--keep)·--fail-with-original·기본 흐름 삭제·분석 중 시간 초과 뒤 삭제, 인자 충돌.
# ==========================================================================

from __future__ import annotations

import copy
import importlib.util
import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from api_fakes import FAKE_UPSTAGE_KEY, FakeStore, FakeUpstageServer
from fake_findings import VALUES, build_findings_response, stored_result
from fake_tokens import fake_jwt
from fastapi.testclient import TestClient

from imask_backend.analyses import ApiError, analysis_out
from imask_backend.manage import list_out
from imask_backend.reviews import analysis_read_out, parse_action, parse_json, review_action_out
from imask_backend.store import StoreError
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
REVIEW_STEPS = 35  # 처음 조회 1 + 동작 33(쓰기 18 · changed false 1 · 거절 14) + 마지막 확인 1
REVIEW_WRITES = 18  # 검토 동작 13 + 검토사항 해결·다시 열기·다시 해결 3 + 내보내기 기록 2(log_export CSV·JSON — 잠긴 상태에서)
REVIEW_POSTS = 33  # 보내는 review-actions POST 수
REVIEW_OK_POSTS = 19  # 그중 200(쓰기 18 + changed false 1)
# 내보내기 기록(log_export) 기대값 — 계약대로 손으로 적은 값(ANALYSIS_ID 의 영숫자 앞 4자 '0000', CREATED_AT 06:41 UTC = 서울 11-03)
EXPORT_CODE = "DG-20261103-0000"
EXPORT_CSV = f"iMASK_{EXPORT_CODE}_검토결과_탐지항목.csv"
EXPORT_JSON = f"iMASK_{EXPORT_CODE}_검토결과.json"
EXPORT_WRONG = "iMASK_DG-20261104-0000_검토결과_탐지항목.csv"  # 하루 다른 날짜(이 분석의 이름이 아님)
EXPORT_POSTS = (27, 28, 29, 30)  # log_export POST 순번(CSV · JSON · 이름 아님 400 · size 0 400) — 잠김 409 넷 뒤, 다시 열기 앞
MSG_NOT_FOUND = "분석 건을 찾을 수 없습니다."
REMOVED = "정리: 이번 실행이 만든 분석을 지웠습니다(DELETE 204 · 다시 읽어 404)"  # 끝 정리 — 204 뒤 다시 읽어 없음 확인
# 검토사항 해결·다시 열기(review-items §5.6) — 검토 메모 뒤 · 검토 완료 앞에 보내는 8개(쓰기 3 · 409 둘 · 404 · 400 둘)
ITEM_POST_TYPES = ["resolve_item", "resolve_item", "reopen_item", "reopen_item", "resolve_item", "resolve_item", "reopen_item", "resolve_item"]
ITEM_POSTS = range(14, 22)  # 그 POST 순번(1부터)


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
        delete_mode: str | int = "ok",
        list_override: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None,
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
        # 삭제(shared-analyses): ok = 204 뒤 모든 경로 404 · noop = 204 인데 지우지 않음 · gone = 처음부터 404 · 숫자 = 그 상태
        self.delete_mode = delete_mode
        self.deleted = False
        self.list_override = list_override  # 목록 응답 본문을 고쳐 계약 위반을 주입한다
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

    def _delete(self) -> httpx.Response:
        if self.delete_mode == "connect":
            raise httpx.ConnectError("delete lost")
        if isinstance(self.delete_mode, int):
            return httpx.Response(self.delete_mode, json={"detail": "분석을 지우지 못했습니다. 잠시 후 다시 시도해 주세요."})
        if self.deleted or self.delete_mode == "gone":
            return httpx.Response(404, json={"detail": MSG_NOT_FOUND})
        if self.delete_mode == "ok":
            self.deleted = True
            self.store.delete_analysis(ANALYSIS_ID)  # 문서·검토 행 cascade
        return httpx.Response(204)

    def _list(self) -> httpx.Response:
        """GET /api/py/analyses — FakeStore 에 넣은 분석으로 실제 목록 로직(list_out)이 만든 응답."""
        body = list_out(self.store, 100)
        if self.list_override is not None:
            body = self.list_override(body) or body
        return _json_response(200, body)

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
        if method == "DELETE" and path == f"/api/py/analyses/{ANALYSIS_ID}":
            return self._delete()
        if self.deleted and path.startswith(f"/api/py/analyses/{ANALYSIS_ID}"):
            return httpx.Response(404, json={"detail": MSG_NOT_FOUND})  # 지운 뒤(조회·원본·다시 분석·검토 동작)
        if method == "GET" and path == "/api/py/analyses":
            return self._list()
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
    first_delete = next(i for i, r in enumerate(api.requests) if r.method == "DELETE")
    rereads = [r for r in api.requests[:first_delete] if r.method == "GET" and r.url.path.endswith(ANALYSIS_ID)]
    assert len(rereads) == 1  # 정리의 다시 읽기(그 뒤 GET 은 끝 삭제의 없음 확인)
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
    shape = script._known_shape(6, {"extracted": 5, "other": 1})
    assert shape is not None and (shape["findings"], shape["boxed"]) == (29, 28)


def test_known_shapes_are_exact(script: Any) -> None:
    # 합성 묶음의 알려진 두 모양만 받는다 — 위임장 따로(6·5·29·28) · 위임장 합침(5·4·26·26), 섞인 모양 · 새 모양은 아님
    split = script._known_shape(6, {"extracted": 5, "other": 1})
    merged = script._known_shape(5, {"extracted": 4, "other": 1})
    assert split is not None and (split["findings"], split["boxed"]) == (29, 28)
    assert merged is not None and (merged["findings"], merged["boxed"]) == (26, 26)
    for documents, kinds in [
        (6, {"extracted": 4, "other": 1}),
        (5, {"extracted": 5, "other": 1}),
        (5, {"extracted": 4}),
        (7, {"extracted": 6, "other": 1}),
        (True, {"extracted": 5, "other": 1}),
        ("6", {"extracted": 5, "other": 1}),
    ]:
        assert script._known_shape(documents, kinds) is None, (documents, kinds)
    ok = {"risk_level": "상"}
    assert script._summary_ok({**ok, "document_count": 6, "extracted_document_count": 5})
    assert script._summary_ok({**ok, "document_count": 5, "extracted_document_count": 4})
    assert not script._summary_ok({**ok, "document_count": 6, "extracted_document_count": 4})
    assert not script._summary_ok({**ok, "document_count": 5, "extracted_document_count": 5})
    assert not script._summary_ok({"risk_level": "중", "document_count": 5, "extracted_document_count": 4})


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
    keep: bool = True,
):
    """실제 app(TestClient) → e2e. 브라우저 업로드만 FakeStore 에 직접 넣고, Upstage 는 진짜 클라이언트 + 가짜 서버.

    fail_final_read: 시작의 마지막 DB 다시 읽기 실패(서버 대체 행). fail_first_poll: 첫 조회 연결 오류.
    lose_start_response: 서버는 시작을 끝냈지만 e2e 는 응답을 못 받음(그 뒤 GET 은 정리의 다시 읽기).
    fail_cleanup_read: 정리의 다시 읽기도 끊김.
    keep: True 면 --keep(저장된 행을 테스트가 본다), False 면 기본 — 끝에 그 분석을 DELETE 로 지운다.
    서버 삭제의 Upstage 정리(get_upstage_cleanup)는 따로 둔 가짜 서버(cleanup_server)로 간다(e2e 정리 횟수와 섞이지 않게).
    """
    from api_fakes import FAKE_ENV, FakeStore

    from api.index import app, get_store, get_upstage, get_upstage_cleanup
    from imask_backend.settings import get_settings, load_settings

    settings = load_settings(FAKE_ENV)
    store = FakeStore()
    if fail_final_read:
        store.fail_get_calls = {2}  # 1: 시작 전 읽기, 2: 시작의 마지막 다시 읽기
    upstage = FakeUpstageServer()
    server_client = UpstageClient.from_settings(
        settings.upstage(), extra_secrets=settings.secrets(), transport=httpx.MockTransport(upstage.handle)
    )
    cleanup_server = FakeUpstageServer()
    cleanup_client_of_server = UpstageClient.from_settings(
        settings.upstage(), extra_secrets=settings.secrets(), transport=httpx.MockTransport(cleanup_server.handle)
    )
    starts: list[dict[str, Any]] = []
    gets = {"n": 0}
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_upstage] = lambda: lambda: server_client
    app.dependency_overrides[get_upstage_cleanup] = lambda: lambda: cleanup_client_of_server
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
                code = script.main(["--interval", "0", *(["--keep"] if keep else [])], transport=httpx.MockTransport(bridge))
    finally:
        app.dependency_overrides.clear()
        server_client.close()
        cleanup_client_of_server.close()
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
    assert _run(script, api, _done_upstage(), ["--keep"]) == 0  # 저장된 검토 행을 본다(지우지 않음)
    out = capsys.readouterr().out
    assert "[실패]" not in out
    assert f"검토 동작 확인: {REVIEW_STEPS}/{REVIEW_STEPS} 통과 · 쓴 동작 {REVIEW_WRITES}건 — 기대대로" in out
    assert "결과: 기대대로" in out
    # 순서대로 보낸 동작(BRIEF §5.5 의 9종 + 검토사항 해결·다시 열기 + 내보내기 기록 log_export + 거절 확인)
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
        *ITEM_POST_TYPES,
        "complete_review",
        "set_status",
        "complete_review",
        "resolve_item",
        "reopen_item",
        "log_export",
        "log_export",
        "log_export",
        "log_export",
        "reopen_review",
        "delete_everything",
        "save_memo",
    ]
    assert {body.get("actor") for body in api.review_posts} == {"api_e2e"}
    # log_export 본문: 정확히 6키, 이 분석의 이름·그럴듯한 크기(계약대로 손으로 적은 값)
    exports = [api.review_posts[n - 1] for n in EXPORT_POSTS]
    assert all(set(body) == {"type", "actor", "format", "size", "state", "file_name"} for body in exports)
    assert [(b["format"], b["size"], b["state"], b["file_name"]) for b in exports] == [
        ("csv", 6127, "handed", EXPORT_CSV),
        ("json", 1310720, "saved", EXPORT_JSON),
        ("csv", 6127, "handed", EXPORT_WRONG),
        ("csv", 0, "handed", EXPORT_CSV),
    ]
    # 저장된 검토 행: 쓰기 18번 = version 18 = 이력 18줄, 다시 연 상태
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
        "resolve",
        "reopenItem",
        "resolve",
        "complete",
        "export",
        "export",
        "reopen",
    ]
    # 내보내기 줄 두 개(H16·H17) — 계약 문구(데모 logExport 와 같음), 크기 표기 = 화면 fmtSize(1,310,720 B → 1.3MB 동점 올림)
    assert [{k: line[k] for k in ("id", "actor", "kind", "target", "change", "reason")} for line in saved["history"][15:17]] == [
        {"id": "H16", "actor": "api_e2e", "kind": "export", "target": EXPORT_CSV, "change": "CSV · 6KB · 다운로드 요청", "reason": "민감한 값 마스킹"},
        {"id": "H17", "actor": "api_e2e", "kind": "export", "target": EXPORT_JSON, "change": "JSON · 1.3MB · 저장 완료", "reason": "민감한 값 마스킹"},
    ]
    assert saved["status"] == "needed" and saved["reviewer"] == "api_e2e" and saved["reviewed_at"] is None
    assert "log_export CSV·handed(잠긴 상태 · 6,127 B → 6KB)" in out and "log_export JSON·saved(잠긴 상태 · 1,310,720 B → 1.3MB)" in out
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
    # 잠김 409 자리(23번째 POST — 검토 완료 뒤 set_status)에 다른 409 문구
    if n == 23:
        return httpx.Response(409, json={"detail": "탐지 항목 상태가 바뀌었습니다. 새로 고친 뒤 다시 시도해 주세요."})
    return None


@pytest.mark.parametrize(
    ("override", "message"),
    [
        (_accept_second_confirm, "HTTP 200"),
        (_wrong_change_text, "새 이력 change: 계약과 다름"),
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
    assert _run(script, api, _done_upstage(), ["--no-review", "--keep"]) == 0
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
        "검토 기록 모양(읽기만, 동작 보내지 않음): status=needed · findings 0개 · 검토사항 해결 기록 0개 · 이력 2줄(S1·S2 포함) · version 0"
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
    assert "status=needed · findings 1개 · 검토사항 해결 기록 0개 · 이력 3줄(S1·S2 포함) · version 1 · 기본값(검토 행 없음) False: 맞음" in out


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
    오류 모양까지 지난다. 만들기·시작·파일은 FakeApi 그대로. --keep 으로 돌린다(저장된 검토 행을 본다). → (종료 코드, 검토 POST 마다 {type, bytes, status}, Upstage 생성 기록)"""
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
                code = script.main(["--skip-upload", "--interval", "0", "--keep"], transport=httpx.MockTransport(handle))
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
    assert len(api.review_posts) == REVIEW_POSTS
    assert [p["status"] for p in posts].count(200) == REVIEW_OK_POSTS
    assert api.store.reviews[ANALYSIS_ID]["version"] == REVIEW_WRITES
    row = api.store.analyses[ANALYSIS_ID]
    assert (row["created_at"], row["updated_at"]) == (CREATED_AT, UPDATED_AT)
    # 내보내기 기록은 실제 경로에서도 잠긴 상태에서 200 두 번 · 거절 400 두 번
    assert [posts[n - 1]["type"] for n in EXPORT_POSTS] == ["log_export"] * 4
    assert [posts[n - 1]["status"] for n in EXPORT_POSTS] == [200, 200, 400, 400]


# --- 내보내기 기록(log_export) — 계약과 다른 응답이면 실패(live-report T3) ------------------------------
# 기대값(파일 이름·크기 표기·문구)은 스크립트가 계약대로 따로 만든다. 여기서는 손으로 적은 값·공유 크기 표와 맞는지,
# 그리고 가짜 서버가 계약과 다르게 답하면(문구·잠김·바뀌면 안 되는 열·거절) 검증기가 실패하는지 본다. 네트워크 없음.


def _export_out(api: FakeApi, body: dict[str, Any]) -> dict[str, Any]:
    """그 본문을 실제 검토 로직으로 처리한 응답(저장은 정상)."""
    return review_action_out(api.store, ANALYSIS_ID, parse_action(json.dumps(body).encode()))


def _export_line(n_post: int, key: str, value: str) -> Callable[[FakeApi, dict[str, Any], int], httpx.Response | None]:
    """n번째 POST(log_export)의 저장·응답 이력 줄 key 를 value 로 바꾼다(저장과 응답이 같아 다시 읽기는 맞는다)."""

    def override(api: FakeApi, body: dict[str, Any], n: int) -> httpx.Response | None:
        if n != n_post:
            return None
        assert body["type"] == "log_export"
        _export_out(api, body)
        api.store.reviews[ANALYSIS_ID]["history"][-1][key] = value
        return _json_response(200, {"analysis": api.read_done(), "changed": True})

    return override


def _export_locked(api: FakeApi, body: dict[str, Any], n: int) -> httpx.Response | None:
    # 잠긴 상태의 내보내기 기록을 다른 동작처럼 409 로 거절하는 서버
    if body.get("type") == "log_export" and n == EXPORT_POSTS[0]:
        return httpx.Response(409, json={"detail": "검토를 완료한 분석은 바꿀 수 없습니다."})
    return None


def _export_moves(column: str, value: Any) -> Callable[[FakeApi, dict[str, Any], int], httpx.Response | None]:
    """첫 log_export 를 정상 저장한 뒤 검토 행의 다른 열도 바꾸는 서버(저장·응답·다시 읽기가 모두 같다)."""

    def override(api: FakeApi, body: dict[str, Any], n: int) -> httpx.Response | None:
        if n != EXPORT_POSTS[0]:
            return None
        _export_out(api, body)
        api.store.reviews[ANALYSIS_ID][column] = value
        return _json_response(200, {"analysis": api.read_done(), "changed": True})

    return override


def _export_refusal_accepted(n_post: int) -> Callable[[FakeApi, dict[str, Any], int], httpx.Response | None]:
    """거절해야 할 log_export(이름 아님·size 0)에 200 changed false 로 답하는 서버(쓰기 없음)."""

    def override(api: FakeApi, body: dict[str, Any], n: int) -> httpx.Response | None:
        if n != n_post:
            return None
        return _json_response(200, {"analysis": api.read_done(), "changed": False})

    return override


def _export_refusal_writes(api: FakeApi, body: dict[str, Any], n: int) -> httpx.Response | None:
    # 이름이 아닌 요청에 400 으로 답하면서 이력은 써 버리는 서버(맞는 이름으로 저장)
    if n != EXPORT_POSTS[2]:
        return None
    _export_out(api, {**body, "file_name": EXPORT_CSV})
    return httpx.Response(400, json={"detail": "요청 형식이 올바르지 않습니다."})


def _export_wrong_400_detail(api: FakeApi, body: dict[str, Any], n: int) -> httpx.Response | None:
    # size 0 자리에 다른 400 문구
    if n == EXPORT_POSTS[3]:
        return httpx.Response(400, json={"detail": "처리자 이름이 올바르지 않습니다."})
    return None


@pytest.mark.parametrize(
    ("override", "message"),
    [
        (_export_line(EXPORT_POSTS[1], "change", "JSON · 1.2MB · 저장 완료"), "새 이력 change: 계약과 다름"),
        (_export_line(EXPORT_POSTS[0], "change", "CSV · 6KB · 저장 완료"), "새 이력 change: 계약과 다름"),
        (_export_line(EXPORT_POSTS[0], "reason", ""), "새 이력 reason: 계약과 다름"),
        (_export_line(EXPORT_POSTS[0], "kind", "memo"), "새 이력 kind: 계약과 다름"),
        (_export_line(EXPORT_POSTS[0], "target", EXPORT_WRONG), "새 이력 target:"),
        (_export_line(EXPORT_POSTS[1], "actor", "다른 처리자"), "새 이력 actor: 계약과 다름"),
        (_export_locked, "HTTP 409 검토를 완료한 분석은 바꿀 수 없습니다.(기대 200"),
        (_export_moves("status", "needed"), "review status 가 바뀜"),
        (_export_moves("reviewer", "다른 검토자"), "review reviewer 가 바뀜"),
        (_export_moves("completion_note", ""), "review completion_note 가 바뀜"),
        (_export_moves("memo", "다른 메모"), "review memo 가 바뀜"),
        (_export_moves("reviewed_at", None), "review reviewed_at 가 바뀜"),
        (_export_moves("findings", {}), "review findings 가 바뀜"),
        (_export_refusal_accepted(EXPORT_POSTS[2]), "HTTP 200"),
        (_export_refusal_accepted(EXPORT_POSTS[3]), "HTTP 200"),
        (_export_refusal_writes, "다시 읽은 review 가 바뀜(쓰기가 있었음)"),
        (_export_wrong_400_detail, "HTTP 400 처리자 이름이 올바르지 않습니다.(기대 400 요청 형식이 올바르지 않습니다.)"),
    ],
    ids=[
        "python_round_size_text",
        "state_text_differs",
        "reason_differs",
        "kind_differs",
        "target_differs",
        "actor_differs",
        "locked_409",
        "status_unlocked",
        "reviewer_changed",
        "completion_note_changed",
        "memo_changed",
        "reviewed_at_changed",
        "findings_changed",
        "wrong_name_accepted",
        "size_zero_accepted",
        "refusal_still_writes",
        "wrong_400_detail",
    ],
)
def test_unexpected_export_response_fails(script: Any, capsys: Any, override: Any, message: str) -> None:
    api = FakeApi(poll_mode="done", review_override=override)
    assert _run(script, api, _done_upstage(), []) == 1
    out = capsys.readouterr().out
    assert "[실패]" in out
    assert message in out
    failed = [line for line in out.splitlines() if "[실패]" in line]
    assert any("log_export" in line or "마지막 —" in line for line in failed), failed
    assert "검토 동작 확인: " in out and "— 기대와 다름" in out
    assert "결과: 기대와 다름" in out


def test_mismatch_output_has_no_values(script: Any, capsys: Any) -> None:
    # 서버가 이력 줄에 원문 같은 값을 잘못 담아 돌려줘도 진단 출력에는 필드 이름과 '계약과 다름'만 나온다
    sentinel = "원문센티널-RAW-7Q2"
    api = FakeApi(poll_mode="done", review_override=_export_line(EXPORT_POSTS[0], "reason", sentinel))
    assert _run(script, api, _done_upstage(), []) == 1
    out = capsys.readouterr().out
    assert "새 이력 reason: 계약과 다름" in out
    assert sentinel not in out


def test_export_steps_are_numbered_after_lock_checks(script: Any, capsys: Any) -> None:
    # 단계 번호: 잠김 409(24)·이미 완료 409(25)·잠긴 검토사항 409 둘(26·27) 다음 28~31 이 내보내기 기록, 32 가 다시 열기
    api = FakeApi(poll_mode="done")
    assert _run(script, api, _done_upstage(), ["--keep"]) == 0
    out = capsys.readouterr().out
    assert "[통과] 25. 이미 완료 — complete_review → 409" in out
    assert "[통과] 27. 잠김 — reopen_item(R-01) → 409 — HTTP 409 · 쓰기 없음" in out
    assert "[통과] 28. log_export CSV·handed(잠긴 상태 · 6,127 B → 6KB) — 이력 18줄 · version 16" in out
    assert "[통과] 29. log_export JSON·saved(잠긴 상태 · 1,310,720 B → 1.3MB) — 이력 19줄 · version 17" in out
    assert "[통과] 30. log_export 이 분석의 이름이 아님(서울 날짜 하루 다름) → 400 — HTTP 400 · 쓰기 없음" in out
    assert "[통과] 31. log_export size 0 → 400 — HTTP 400 · 쓰기 없음" in out
    assert "[통과] 32. reopen_review" in out
    assert f"[통과] {REVIEW_STEPS:02d}. 마지막 —" in out
    # 저장 행: 내보내기 줄 at 이 검토 완료 줄 at 보다 앞서지 않는다
    history = api.store.reviews[ANALYSIS_ID]["history"]
    stamps = [datetime.fromisoformat(line["at"]) for line in history]
    assert stamps == sorted(stamps)


def test_fmt_size_matches_shared_table(script: Any) -> None:
    # 스크립트의 크기 표기(계약대로 따로 만든 것)가 화면·백엔드와 같이 쓰는 표(tests/fmt_size_cases.json)와 모두 같다
    cases = json.loads((ROOT / "tests" / "fmt_size_cases.json").read_text(encoding="utf-8"))
    assert cases and all(isinstance(b, int) and isinstance(t, str) for b, t in cases)
    assert [[b, script._fmt_size(b)] for b, _ in cases] == cases
    # 동점에서 파이썬 round()·format 과 다르다(JS '절반은 올림')
    assert script._fmt_size(2560) == "3KB" and round(2560 / 1024) == 2
    assert script._fmt_size(1310720) == "1.3MB" and f"{1310720 / 1048576:.1f}" == "1.2"
    assert script._fmt_size(script.EXPORT_CSV_SIZE) == "6KB" and script._fmt_size(script.EXPORT_JSON_SIZE) == "1.3MB"


def test_fmt_size_agrees_with_backend_on_a_sweep(script: Any) -> None:
    # 같은 계약을 따로 구현한 백엔드 fmt_size 와 경계 근처를 훑어 비교(스크립트는 백엔드를 import 하지 않는다)
    from imask_backend.exports import fmt_size

    kb_ties = {(2 * k + 1) * 512 + d for k in range(1024) for d in (-1, 0, 1)}  # b/1024 = n + 0.5
    mb_ties = {(2 * j + 1) * 262_144 + d for j in range(200) for d in (-1, 0, 1)}  # 10b/1048576 = m + 0.5
    sizes = {*range(0, 6000), *range(1_048_000, 1_049_200), *kb_ties, *mb_ties, 104_857_599, 104_857_600}
    assert [s for s in sorted(sizes) if script._fmt_size(s) != fmt_size(s)] == []


@pytest.mark.parametrize(
    ("analysis_id", "created_at", "code"),
    [
        (ANALYSIS_ID, CREATED_AT, "DG-20261103-0000"),  # 소수 초 5자리
        ("7b944f1e-1234-4abc-8def-0123456789ab", "2026-11-04T15:00:00+00:00", "DG-20261105-7B94"),  # 서울 자정(다음 날)
        ("7b944f1e-1234-4abc-8def-0123456789ab", "2026-11-04T14:59:59.999999+00:00", "DG-20261104-7B94"),  # 자정 바로 앞
        ("7b944f1e-1234-4abc-8def-0123456789ab", "2026-11-04T15:00:00Z", "DG-20261105-7B94"),  # Z
        ("7b944f1e-1234-4abc-8def-0123456789ab", "2026-12-31T15:00:00.123456+00:00", "DG-20270101-7B94"),  # 해 넘김
        ("ab-c1-2345-6789", "2026-11-04T05:06:07.123456+00:00", "DG-20261104-ABC1"),  # 하이픈 건너뜀
    ],
    ids=["fraction5", "seoul_midnight", "before_midnight", "zulu", "new_year", "hyphens"],
)
def test_export_name_follows_the_contract(script: Any, analysis_id: str, created_at: str, code: str) -> None:
    row = {"id": analysis_id, "created_at": created_at}
    assert script._export_name(row, "csv") == f"iMASK_{code}_검토결과_탐지항목.csv"
    assert script._export_name(row, "json") == f"iMASK_{code}_검토결과.json"
    # 백엔드가 받는 이 분석의 이름과 같다(따로 만든 두 구현 비교)
    from imask_backend.exports import expected_file_name

    assert expected_file_name(row, "csv") == script._export_name(row, "csv")
    assert expected_file_name(row, "json") == script._export_name(row, "json")
    shifted = script._export_name(row, "csv", shift_days=1)
    assert shifted is not None and shifted != script._export_name(row, "csv") and len(shifted) == len(script._export_name(row, "csv"))


@pytest.mark.parametrize("created_at", [None, "", "2026-11-04T15:00:00", "not a time", 20261104])
def test_export_name_needs_a_readable_created_at(script: Any, created_at: Any) -> None:
    assert script._export_name({"id": ANALYSIS_ID, "created_at": created_at}, "csv") is None


def test_unreadable_created_at_fails_the_export_step(script: Any, capsys: Any) -> None:
    # 처음 조회의 created_at 을 읽지 못하면 log_export 를 보내지 않고 그 단계를 실패로 적는다(이름을 추측하지 않음)
    api = FakeApi(poll_mode="done")
    real_read = api.read_done
    unreadable = "2026-11-03 06:41"  # 시간대 없음 — _when 이 읽지 않는다

    def read_done(include: bool = False) -> dict[str, Any]:
        body = real_read(include)
        body["created_at"] = unreadable
        if isinstance(body.get("review"), dict):
            body["review"]["history"][0]["at"] = unreadable  # S1 은 created_at 그대로(처음 조회 확인은 지나게)
        return body

    api.read_done = read_done  # type: ignore[method-assign]
    assert _run(script, api, _done_upstage(), []) == 1
    out = capsys.readouterr().out
    assert "[실패] 28. log_export — 이 분석의 파일 이름" in out
    assert "log_export" not in _review_types(api)


def test_analysis_id_mode_sends_no_export_log(script: Any, capsys: Any) -> None:
    # --analysis-id(읽기 전용)에서는 log_export 를 보내지 않는다(기존 분석에 이력이 써지지 않게)
    api = FakeApi(poll_mode="done")
    assert _run(script, api, FakeUpstageServer(), ["--analysis-id", ANALYSIS_ID]) == 0
    assert _review_requests(api) == [] and api.review_posts == []
    assert api.store.reviews == {}
    assert "log_export" not in capsys.readouterr().out


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
    code = _run(script, api, _done_upstage(), ["--keep"])
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
    assert len(posts) == REVIEW_POSTS
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
    assert len(posts) == REVIEW_POSTS and 413 not in [p["status"] for p in posts]
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


# --- 공유 목록·삭제·다시 분석(shared-analyses) — 가짜 API ------------------------------------------


def _methods(api: FakeApi, method: str, suffix: str = "") -> list[httpx.Request]:
    return [r for r in api.requests if r.method == method and r.url.path.endswith(f"/api/py/analyses{suffix}")]


def _api_deletes(api: FakeApi) -> list[httpx.Request]:
    return [r for r in api.requests if r.method == "DELETE"]


def test_default_done_flow_checks_list_then_deletes(script: Any, capsys: Any) -> None:
    api = FakeApi(poll_mode="done")
    assert _run(script, api, _done_upstage(), []) == 0
    out = capsys.readouterr().out
    assert "[실패]" not in out, out[-3000:]
    assert "목록 확인(완료 분석): GET /api/py/analyses HTTP 200 · 1건 · " in out
    assert "· result 키 있는 항목 0 · 이 분석 status=done review=needed risk_level=상 문서 1개: 통과" in out
    assert "삭제 확인: 6/6 통과 — 기대대로" in out
    assert "  [새] 목록: 통과" in out and "  [새] 삭제: 통과" in out
    assert "새 확인(목록·다시 분석·삭제): 2/2 통과 — 기대대로" in out
    assert "정리: 이번 실행이 만든 분석은 삭제 확인에서 지웠습니다(없음 확인)" in out
    # 마지막 검토 POST 뒤: 목록 확인(조회 + 목록) → 삭제 확인(DELETE → GET → /file → 목록 → retry → DELETE)
    last_review = max(i for i, r in enumerate(api.requests) if r.url.path == REVIEW_PATH)
    tail = [(r.method, r.url.path.replace(f"/api/py/analyses/{ANALYSIS_ID}", "{id}")) for r in api.requests[last_review + 1 :]]
    assert tail == [
        ("GET", "{id}"),  # 마지막 거절(501자 글)의 다시 읽기
        ("GET", "{id}"),  # 검토 동작 확인의 마지막 조회
        ("GET", "{id}"),  # 목록 기대값을 만들 조회
        ("GET", "/api/py/analyses"),
        ("DELETE", "{id}"),
        ("GET", "{id}"),
        ("GET", "{id}/file"),
        ("GET", "/api/py/analyses"),
        ("POST", "{id}/retry"),
        ("DELETE", "{id}"),
    ]
    assert api.store.analyses == {} and api.store.documents == {} and api.store.reviews == {}  # cascade


def test_keep_leaves_the_analysis(script: Any, capsys: Any) -> None:
    api = FakeApi(poll_mode="done")
    assert _run(script, api, _done_upstage(), ["--keep"]) == 0
    assert _api_deletes(api) == []
    assert ANALYSIS_ID in api.store.analyses
    out = capsys.readouterr().out
    assert "삭제 확인 건너뜀(--keep — 이번 실행이 만든 분석을 남김)" in out
    assert f"정리: 이번 실행이 만든 분석을 남깁니다: {ANALYSIS_ID}" in out
    assert "새 확인(목록·다시 분석·삭제): 1/1 통과 — 기대대로" in out


def _item(body: dict[str, Any]) -> dict[str, Any] | None:
    """목록 안의 이 분석(지운 뒤의 목록이면 None — 삭제 확인의 목록 조회에는 손대지 않는다)."""
    found = [i for i in body["analyses"] if i["id"] == ANALYSIS_ID]
    return found[0] if found else None


def _list_missing(body: dict[str, Any]) -> dict[str, Any]:
    return {"analyses": []}


def _list_with_result(body: dict[str, Any]) -> dict[str, Any]:
    if (item := _item(body)) is not None:
        item["result"] = {"summary": {}}
    return body


def _list_wrong_review(body: dict[str, Any]) -> dict[str, Any]:
    if (item := _item(body)) is not None:
        item["review"] = "done"
    return body


def _list_wrong_risk(body: dict[str, Any]) -> dict[str, Any]:
    if (item := _item(body)) is not None:
        item["risk_level"] = None
    return body


def _list_doc_extra_key(body: dict[str, Any]) -> dict[str, Any]:
    if (item := _item(body)) is not None:
        item["documents"][0]["storage_path"] = "analyses/x/document.pdf"
    return body


def _list_twice(body: dict[str, Any]) -> dict[str, Any]:
    if (item := _item(body)) is not None:
        body["analyses"].append(copy.deepcopy(item))
    return body


def _list_out_of_order(body: dict[str, Any]) -> dict[str, Any]:
    if (item := _item(body)) is not None:
        older = {**copy.deepcopy(item), "id": "00000000-0000-4000-8000-0000000000ab", "created_at": "2026-01-01T00:00:00+00:00"}
        body["analyses"].insert(0, older)
    return body


def _list_envelope(body: dict[str, Any]) -> dict[str, Any]:
    return {**body, "next": None}


@pytest.mark.parametrize(
    ("override", "message"),
    [
        (_list_missing, "이 분석이 목록에 0번 있음(기대 1번)"),
        (_list_with_result, "result 키가 있는 항목 1개"),
        (_list_wrong_review, "이 분석의 항목이 조회 응답과 다름 ['review']"),
        (_list_wrong_risk, "이 분석의 항목이 조회 응답과 다름 ['risk_level']"),
        (_list_doc_extra_key, "문서 키가 계약(filename·size_bytes·mime_type)과 다른 항목 1개"),
        (_list_twice, "이 분석이 목록에 2번 있음(기대 1번)"),
        (_list_out_of_order, "created_at desc, id desc 순서가 아님"),
        (_list_envelope, '응답 모양이 {"analyses": [...]} 가 아님'),
    ],
    ids=["missing", "result_key", "review", "risk_level", "doc_key", "twice", "order", "envelope"],
)
def test_list_contract_problems_fail_separately(script: Any, capsys: Any, override: Any, message: str) -> None:
    api = FakeApi(poll_mode="done", list_override=override)
    assert _run(script, api, _done_upstage(), []) == 1
    out = capsys.readouterr().out
    assert message in out
    assert out.split("목록 확인(완료 분석):", 1)[1].split("\n", 1)[0].endswith(": 실패")
    # 고정 기대값·검토 동작 확인은 그대로 통과 — 새 확인만 따로 실패로 보인다
    assert "  done 확인(요약·화면용 결과 고정 기대값·검토사항·응답 크기): 통과" in out
    assert "  검토 동작: 통과" in out
    assert "  [새] 목록: 실패" in out
    assert "새 확인(목록·다시 분석·삭제): " in out and "— 기대와 다름" in out
    assert "결과: 기대와 다름" in out
    assert "예상 못 한 오류" not in out


def test_delete_that_does_not_delete_fails(script: Any, capsys: Any) -> None:
    # V-T3-1 m3 · M1: 204 인데 지우지 않음 → 없음 확인 실패 → 다시 분석 · 두 번째 DELETE 를 보내지 않고, 완료 표식도 달지 않아
    # finally 가 다시 지우고 확인한다 — 그래도 남으면 정리 실패 + 분석 id(종료 1)
    api = FakeApi(poll_mode="done", delete_mode="noop")
    assert _run(script, api, _done_upstage(), []) == 1
    out = capsys.readouterr().out
    assert "  [통과] 01. DELETE → 204(본문 없음)" in out
    assert "  [실패] 02. GET → 404" in out
    assert "  [실패] 03. GET …/file → 404" in out
    assert "  [실패] 04. 목록에 없음" in out and "목록에 아직 있음" in out
    deletion = out.split("삭제 확인(이번 실행이 만든 분석):", 1)[1]
    assert "] 05." not in deletion and "] 06." not in deletion
    assert _methods(api, "POST", f"/{ANALYSIS_ID}/retry") == []
    assert "  [새] 삭제: 실패" in out
    assert "삭제 확인에서 지웠습니다" not in out
    assert f"정리 못 함: DELETE 204 를 받았지만 분석이 아직 있습니다(GET HTTP 200): {ANALYSIS_ID}" in out
    assert "정리를 끝내지 못해 실패로 끝냅니다" in out
    assert len(_api_deletes(api)) == 2 and ANALYSIS_ID in api.store.analyses


def test_delete_502_is_retried_at_the_end_and_fails(script: Any, capsys: Any) -> None:
    api = FakeApi(poll_mode="done", delete_mode=502)
    assert _run(script, api, _done_upstage(), []) == 1
    out = capsys.readouterr().out
    assert "  [실패] 01. DELETE → 204(본문 없음)" in out
    assert "지워지지 않아 나머지 확인(다시 분석 404 등)을 보내지 않습니다" in out
    assert _methods(api, "POST", f"/{ANALYSIS_ID}/retry") == []  # V-T3-1 M1 — 남은 분석에 다시 분석을 보내지 않는다
    # finally 에서 한 번 더 지우려 하고, 못 지우면 정리 실패(종료 코드 1)
    assert "정리 못 함: 이번 실행이 만든 분석을 지우지 못했습니다(HTTP 502 분석을 지우지 못했습니다." in out
    assert "정리를 끝내지 못해 실패로 끝냅니다" in out
    assert len(_api_deletes(api)) == 2  # 삭제 확인의 첫 DELETE + 정리(두 번째 DELETE 확인은 보내지 않음)


@pytest.mark.parametrize(
    ("mode", "args", "code", "message", "deletes"),
    [
        ("ok", [], 0, REMOVED, 1),
        ("gone", [], 0, "정리: 이번 실행이 만든 분석이 이미 없습니다(DELETE 404)", 1),
        (502, [], 1, "정리 못 함: 이번 실행이 만든 분석을 지우지 못했습니다(HTTP 502", 1),
        ("connect", [], 1, "정리 못 함: 이번 실행이 만든 분석을 지우지 못했습니다(ConnectError)", 1),
        ("ok", ["--keep"], 0, "정리: 이번 실행이 만든 분석을 남깁니다", 0),
    ],
    ids=["deleted", "already_gone", "http_502", "connect_error", "keep"],
)
def test_no_start_run_is_deleted_at_the_end(
    script: Any, capsys: Any, mode: str | int, args: list[str], code: int, message: str, deletes: int
) -> None:
    api = FakeApi(delete_mode=mode)
    upstage = FakeUpstageServer()
    assert _run(script, api, upstage, ["--no-start", *args]) == code
    assert len(_api_deletes(api)) == deletes
    assert upstage.requests == []
    out = capsys.readouterr().out
    assert message in out
    assert ("정리를 끝내지 못해 실패로 끝냅니다" in out) == (code == 1)


@pytest.mark.parametrize(
    ("poll_mode", "extra_args"),
    [("running", ["--timeout", "0"]), ("interrupt", []), ("connect", [])],
    ids=["timeout", "keyboard_interrupt", "connection_error"],
)
def test_abnormal_exit_also_deletes_the_created_analysis(script: Any, capsys: Any, poll_mode: str, extra_args: list[str]) -> None:
    api = FakeApi(poll_mode=poll_mode)
    upstage = FakeUpstageServer()
    upstage.files[FILE_ID] = ("x.pdf", b"")
    assert _run(script, api, upstage, extra_args) == 1
    assert upstage.deleted == [FILE_ID]  # Upstage 파일 정리 뒤
    assert len(_api_deletes(api)) == 1  # 그 분석을 지운다
    out = capsys.readouterr().out
    assert out.index("정리: Upstage 파일 1개 삭제 요청 완료") < out.index(REMOVED)


def test_ctrl_c_during_cleanup_does_not_delete(script: Any, capsys: Any) -> None:
    api = FakeApi(poll_mode="running")
    upstage = FakeUpstageServer()
    upstage.files[FILE_ID] = ("x.pdf", b"")
    upstage.errors[("DELETE", "file")] = KeyboardInterrupt()
    assert _run(script, api, upstage, ["--timeout", "0"]) == 1
    assert _api_deletes(api) == []
    assert f"정리 중 중단돼 이번 실행이 만든 분석을 지우지 않았습니다: {ANALYSIS_ID}" in capsys.readouterr().out


def test_analysis_id_mode_never_deletes(script: Any) -> None:
    api = FakeApi(poll_mode="done")
    assert _run(script, api, FakeUpstageServer(), ["--analysis-id", ANALYSIS_ID]) == 0
    assert _api_deletes(api) == [] and _methods(api, "GET") == []  # 목록도 부르지 않는다(기존 동작 그대로)


# --- 계약 기대값(백엔드 함수를 쓰지 않고 따로 만든 것) ------------------------------------------


def _detail_row(**overrides: Any) -> dict[str, Any]:
    stamp = "2026-11-04T00:00:00+00:00"
    base = {
        "id": "a",
        "name": "n",
        "status": "done",
        "error": None,
        "created_at": stamp,
        "updated_at": "2026-11-04T00:01:00+00:00",
        "started_at": "2026-11-04T00:00:01+00:00",
        "result": {"summary": {"risk_level": "중", "document_count": 2}},
        "documents": [
            {"id": "d2", "filename": "b.pdf", "size_bytes": 2, "mime_type": "application/pdf", "upstage_file_id": "f", "created_at": stamp},
            {"id": "d1", "filename": "a.png", "size_bytes": 1, "mime_type": "image/png", "upstage_file_id": None, "created_at": stamp},
        ],
        "review": {"status": "needed"},
    }
    return {**base, **overrides}


@pytest.mark.parametrize(
    ("overrides", "risk", "review"),
    [
        ({}, "중", "needed"),
        ({"review": {"status": "done"}}, "중", "done"),
        ({"review": None}, "중", "needed"),  # 검토 기록을 못 읽은 상세 — 목록은 서류 수로 needed
        ({"result": {"summary": {"risk_level": "상", "document_count": 0}}}, "상", "none"),
        ({"result": {"summary": {"risk_level": 3, "document_count": True}}}, None, "none"),
        ({"result": {"summary": {"document_count": 1.0}}}, None, "none"),
        ({"status": "failed", "result": None, "review": None}, None, "none"),
        ({"status": "running", "result": None}, None, "none"),
        ({"status": "partial"}, "중", "none"),
    ],
    ids=["done_needed", "done_done", "review_null", "count_0", "bool_count", "float_count", "failed", "running", "partial"],
)
def test_list_expected_follows_the_contract(script: Any, overrides: dict[str, Any], risk: Any, review: str) -> None:
    item = script._list_expected(_detail_row(**overrides))
    assert set(item) == script.LIST_ITEM_KEYS
    assert (item["risk_level"], item["review"]) == (risk, review)
    # 문서는 만든 순(created_at, 같으면 id) · 키 셋만
    assert item["documents"] == [
        {"filename": "a.png", "size_bytes": 1, "mime_type": "image/png"},
        {"filename": "b.pdf", "size_bytes": 2, "mime_type": "application/pdf"},
    ]


def test_stored_reason_limit(script: Any) -> None:
    assert script._stored_text("x" * 500, 500) == "x" * 500
    assert script._stored_text("x" * 501, 500) == "x" * 499 + ELLIPSIS
    assert script._stored_text("a" + NUL + chr(0xDC00), 500) == "a" + FFFD * 2


# --- 실제 FastAPI 앱 + FakeStore + 가짜 Upstage 서버(shared_ctx) ------------------------------------

SUPABASE_HOST = "fake-project.supabase.co"  # FakeStore 서명 다운로드 주소의 호스트
SIGN_PREFIX = "/storage/v1/object/sign/documents/"


def _app_run(
    script: Any,
    monkeypatch: pytest.MonkeyPatch,
    args: list[str],
    *,
    response: dict[str, Any] | None = None,
    complete: bool = True,
    tamper: Callable[[httpx.Request, int, Any], Any] | None = None,
    configure: Callable[[Any], None] | None = None,
    intercept: Callable[[httpx.Request], httpx.Response | None] | None = None,
) -> tuple[int, Any, list[tuple[str, str, int]]]:
    """e2e → 실제 app(TestClient). 저장소는 FakeStore, Upstage 는 진짜 클라이언트 + 가짜 서버(삭제 정리 포함 — 네트워크 없음).

    브라우저 업로드는 FakeStore 객체에 넣고, 서명 다운로드 주소는 그 객체를 준다. complete=True 면 조회가 곧바로 완료를 본다.
    tamper(요청, 상태, 본문) 가 값을 돌려주면 그 본문으로 바꿔 e2e 에 준다(예상과 다른 응답 주입 — 예외를 던지면 응답 유실).
    configure(ctx) 는 TestClient 를 열기 전에 저장소·가짜 Upstage 를 고친다. intercept(요청) 가 응답을 돌려주면(또는 예외를 던지면)
    앱에 보내지 않고 그것을 쓴다(서버까지 가지 않은 실패·지워지지 않는 204 흉내).
    다시 분석·검토 POST 앞에는 20ms 쉰다 — Windows 시계 해상도에서도 started_at·이력 at 이 앞 시각과 같아지지 않게."""
    from shared_ctx import install

    from api.index import app

    ctx = install(monkeypatch)
    if response is not None:
        ctx.server.full_response = response
    if complete:
        ctx.server.last_status = "completed"
    if configure is not None:
        configure(ctx)
    seen: list[tuple[str, str, int]] = []
    try:
        with TestClient(app) as client:
            ctx.client = client

            def bridge(request: httpx.Request) -> httpx.Response:
                if request.url.host == SUPABASE_HOST:  # 서명 다운로드(사용자 지정 헤더 없이)
                    data = ctx.store.objects.get(request.url.path.split(SIGN_PREFIX, 1)[1])
                    return httpx.Response(200 if data is not None else 404, content=data or b"")
                if request.method == "POST" and request.url.path.endswith(("/retry", "/review-actions")):
                    time.sleep(0.02)
                if intercept is not None:
                    stubbed = intercept(request)
                    if stubbed is not None:
                        seen.append((request.method, request.url.path, stubbed.status_code))
                        return stubbed
                answer = client.request(
                    request.method, request.url.path, params=request.url.params, headers=dict(request.headers), content=request.content
                )
                seen.append((request.method, request.url.path, answer.status_code))
                content = answer.content
                if tamper is not None and content:
                    changed = tamper(request, answer.status_code, json.loads(content))
                    if changed is not None:
                        content = json.dumps(changed, ensure_ascii=False).encode("utf-8")
                headers = {"content-type": answer.headers.get("content-type", "application/json")}
                if "cache-control" in answer.headers:
                    headers["cache-control"] = answer.headers["cache-control"]
                return httpx.Response(answer.status_code, content=content, headers=headers)

            def browser_upload(_run: Any, upload: dict[str, str], content: bytes, _mime: str) -> bool:
                ctx.store.objects[upload["path"]] = content
                return True

            def script_upstage(api_key: str, base_url: str, **kwargs: Any) -> UpstageClient:
                return UpstageClient(api_key, base_url, transport=httpx.MockTransport(ctx.server.handle), **kwargs)

            env = {"UPSTAGE_API_KEY": FAKE_UPSTAGE_KEY}
            with (
                patch.object(script, "_read_env", return_value=env),
                patch.object(script, "_upload", browser_upload),
                patch.object(script, "UpstageClient", script_upstage),
            ):
                code = script.main(["--interval", "0", *args], transport=httpx.MockTransport(bridge))
    finally:
        app.dependency_overrides.clear()
    return code, ctx, seen


def _retry_posts(seen: list[tuple[str, str, int]]) -> list[int]:
    return [status for method, path, status in seen if method == "POST" and path.endswith("/retry")]


def test_retry_flow_through_real_app_passes_and_deletes(script: Any, monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    code, ctx, seen = _app_run(script, monkeypatch, ["--retry-flow"], response=build_findings_response())
    out = capsys.readouterr().out
    assert "[실패]" not in out, out[-4000:]
    assert code == 0
    # Upstage: 원본 없이 시작·다시 분석은 0번, 올린 뒤 다시 분석에서 올리기 1 · 작업 만들기 1
    assert len(ctx.server.job_bodies) == 1
    assert len(ctx.server.calls("POST", "files")) == 1
    # 다시 분석 POST: 원본 없음(200 failed) → 올린 뒤(200 running) → 분석 중(409) → 지운 뒤(404)
    assert _retry_posts(seen) == [200, 200, 409, 404]
    assert "다시 분석 확인: " in out and " 통과 — 기대대로" in out
    assert "검토 이력 — [S1, 다시 분석 2줄(사유 = 앞 실패 이유), S2] · at 이 줄지 않음 — 이력 4줄 · version 2" in out
    assert "검토 동작 뒤 이력 — ['S1', 'H1', 'H2', 'S2', 'H3'] · at 이 줄지 않음" in out
    assert "목록 확인(실패 분석): " in out and "이 분석 status=failed review=none risk_level=None 문서 1개: 통과" in out
    assert "목록 확인(다시 분석한 완료 분석): " in out and "이 분석 status=done review=needed risk_level=상 문서 1개: 통과" in out
    assert "새 확인(목록·다시 분석·삭제): 4/4 통과 — 기대대로" in out
    assert "  done 확인(요약·화면용 결과 고정 기대값·검토사항·응답 크기): 통과" in out
    assert ctx.store.analyses == {} and ctx.store.objects == {} and ctx.store.reviews == {}  # 지움(원본·검토 행 포함)


def test_retry_flow_keep_stores_retry_lines_with_previous_reasons(script: Any, monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    code, ctx, seen = _app_run(script, monkeypatch, ["--retry-flow", "--keep"], response=build_findings_response())
    out = capsys.readouterr().out
    assert code == 0, out[-4000:]
    assert [m for m, _, _ in seen if m == "DELETE"] == []
    (row,) = ctx.store.analyses.values()
    assert row["status"] == "done" and row["started_at"] > row["created_at"]
    history = ctx.store.reviews[row["id"]]["history"]
    assert [line["kind"] for line in history] == ["retry", "retry", "confirm"]
    assert [line["reason"] for line in history[:2]] == [script.MSG_FILE_MISSING] * 2
    assert {line["change"] for line in history[:2]} == {"같은 파일로 다시 분석 요청"}
    assert "삭제 확인 건너뜀(--keep" in out


def test_retry_flow_judges_fixed_expectations_separately(script: Any, monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    # 가짜 서버의 기본 응답(서류 6 · 추출 키 하나)은 알려진 모양(탐지 29 · 26 등)과 다르다 — 새 확인은 따로 통과로 보인다
    code, ctx, _ = _app_run(script, monkeypatch, ["--retry-flow"])
    out = capsys.readouterr().out
    assert code == 1
    assert "  done 확인(요약·화면용 결과 고정 기대값·검토사항·응답 크기): 실패" in out
    assert "  [새] 다시 분석: 통과" in out and "  [새] 삭제: 통과" in out
    assert "새 확인(목록·다시 분석·삭제): 4/4 통과 — 기대대로" in out
    assert ctx.store.analyses == {}


def _old_history_order(request: httpx.Request, status: int, body: Any) -> Any:
    # 예전 순서 [S1, S2, 저장된 줄…] 로 돌려준다(retry 줄이 S2 뒤)
    review = body.get("review") if isinstance(body, dict) else None
    if request.method == "GET" and isinstance(review, dict) and len(review["history"]) >= 4:
        lines = review["history"]
        system = [line for line in lines if line["id"] in ("S1", "S2")]
        review["history"] = system + [line for line in lines if line["id"] not in ("S1", "S2")]
        return body
    return None


def _wrong_retry_reason(request: httpx.Request, status: int, body: Any) -> Any:
    review = body.get("review") if isinstance(body, dict) else None
    if request.method == "GET" and isinstance(review, dict) and len(review["history"]) == 4:
        review["history"][1]["reason"] = "다른 이유"
        return body
    return None


def _job_without_original(request: httpx.Request, status: int, body: Any) -> Any:
    # 원본 없이 다시 분석한 응답이 작업을 만든 것처럼(running · job id)
    if request.url.path.endswith("/retry") and status == 200 and body.get("status") == "failed":
        return {**body, "status": "running", "error": None, "upstage_job_id": "job_unexpected"}
    return None


@pytest.mark.parametrize(
    ("tamper", "message"),
    [
        (_old_history_order, "H1 id: 계약과 다름"),
        (_wrong_retry_reason, "H1 reason: 계약과 다름"),
        (_job_without_original, "upstage_job_id 가 있음(Upstage 작업을 만듦)"),
    ],
    ids=["old_history_order", "wrong_reason", "job_without_original"],
)
def test_retry_flow_problems_fail(script: Any, monkeypatch: pytest.MonkeyPatch, capsys: Any, tamper: Any, message: str) -> None:
    code, ctx, _ = _app_run(script, monkeypatch, ["--retry-flow"], response=build_findings_response(), tamper=tamper)
    out = capsys.readouterr().out
    assert code == 1
    assert message in out, out[-4000:]
    assert "  [새] 다시 분석: 실패" in out
    assert "다시 분석 확인: " in out and "— 기대와 다름" in out
    assert ctx.store.analyses == {}  # 실패해도 끝에 지운다


def test_retry_flow_output_has_no_signed_token(script: Any, monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    tokens: list[str] = []

    def record(request: httpx.Request, status: int, body: Any) -> Any:
        if request.method == "POST" and request.url.path == "/api/py/analyses" and status == 201:
            tokens.append(body["upload"]["token"])
        return None

    _app_run(script, monkeypatch, ["--retry-flow"], response=build_findings_response(), tamper=record)
    out = capsys.readouterr().out
    assert tokens and tokens[0][:24] not in out
    assert FAKE_UPSTAGE_KEY not in out


def test_fail_with_original_leaves_a_retryable_failed_analysis(script: Any, monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    code, ctx, seen = _app_run(script, monkeypatch, ["--fail-with-original"])
    out = capsys.readouterr().out
    assert "[실패]" not in out, out[-3000:]
    assert code == 0
    assert ctx.server.requests == [] and ctx.server.job_bodies == []  # Upstage 0번
    assert [m for m, _, _ in seen if m == "DELETE"] == [] and _retry_posts(seen) == []
    (row,) = ctx.store.analyses.values()
    assert (row["status"], row["error"], row["upstage_job_id"]) == ("failed", script.MSG_FILE_MISSING, None)
    (doc,) = ctx.store.docs_of(row["id"])
    assert ctx.store.objects[doc["storage_path"]] == BUNDLE  # 같은 서명 주소로 올린 원본
    assert f"분석 id: {row['id']}" in out and "남김: 화면에서 다시 분석할 실패 분석입니다" in out
    assert "올린 내용과 sha256 일치" in out


def test_default_flow_through_real_app_lists_and_deletes(script: Any, monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    code, ctx, seen = _app_run(script, monkeypatch, [], response=build_findings_response())
    out = capsys.readouterr().out
    assert "[실패]" not in out, out[-3000:]
    assert code == 0
    assert len(ctx.server.job_bodies) == 1
    assert [s for m, _, s in seen if m == "DELETE"] == [204, 404]
    assert "새 확인(목록·다시 분석·삭제): 2/2 통과 — 기대대로" in out
    assert ctx.store.analyses == {} and ctx.store.objects == {} and ctx.store.reviews == {}


def test_running_analysis_is_deleted_after_a_timeout(script: Any, monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    # 분석 중에 끝나도(시간 초과) 그 분석을 지운다 — 삭제는 상태와 상관없다
    code, ctx, seen = _app_run(script, monkeypatch, ["--timeout", "0"], complete=False)
    out = capsys.readouterr().out
    assert code == 1
    assert len(ctx.server.job_bodies) == 1
    assert [s for m, _, s in seen if m == "DELETE"] == [204]
    assert ctx.store.analyses == {} and ctx.store.objects == {}
    assert REMOVED in out


@pytest.mark.parametrize(
    "args",
    [
        ["--retry-flow", "--fail-with-original"],
        ["--retry-flow", "--analysis-id", ANALYSIS_ID],
        ["--retry-flow", "--no-start"],
        ["--fail-with-original", "--content-file", "x.bin"],
        ["--retry-flow", "--expect", "failed"],
    ],
    ids=["both_modes", "analysis_id", "no_start", "content_file", "expect_failed"],
)
def test_conflicting_flags_are_rejected(script: Any, capsys: Any, args: list[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        script.main(args)
    assert exc.value.code == 2
    assert "함께 쓸 수 없습니다" in capsys.readouterr().err


# --- V-T3-1 수정(T3-fix1): 삭제 실패 뒤 다시 분석 금지 · 다시 분석 응답 유실 정리 · 완료 시각 판정 · documents 모양 ---------


def _first_job_fails(ctx: Any) -> None:
    """첫 작업 만들기만 503 — 원본이 버킷에 있는 failed 분석을 만든다(다시 분석하면 실제로 작업이 생기는 상태)."""
    original = ctx.server.handle
    calls = [0]

    def handle(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/responses"):
            calls[0] += 1
            if calls[0] == 1:
                request.read()
                ctx.server.requests.append(request)
                return httpx.Response(503, json={"error": {"message": "synthetic transient failure"}})
        return original(request)

    ctx.server.handle = handle


def _broken_remove(ctx: Any) -> None:
    _first_job_fails(ctx)

    def fail(paths: Any) -> None:
        raise StoreError("synthetic remove failure")

    ctx.store.remove_objects = fail


def _row_never_deleted(ctx: Any) -> None:
    # 행 지우기가 매번 0행이고 행이 바뀐 것처럼 보여(3번 모두 짐) 409. 원본도 남겨 둔다(다시 분석하면 작업이 생기는 상태).
    _first_job_fails(ctx)
    ctx.store.remove_objects = lambda paths: None

    def never(analysis_id: str, *, expect_updated_at: str | None = None) -> int:
        row = ctx.store.analyses[analysis_id]
        row["updated_at"] = datetime.now(UTC).isoformat()
        return 0

    ctx.store.delete_analysis = never


def _delete_connect_error(request: httpx.Request) -> httpx.Response | None:
    if request.method == "DELETE":
        raise httpx.ConnectError("synthetic delete lost")
    return None


def _delete_noop_204(request: httpx.Request) -> httpx.Response | None:
    return httpx.Response(204) if request.method == "DELETE" else None


@pytest.mark.parametrize(
    ("configure", "intercept", "first_status"),
    [
        (_broken_remove, None, 502),
        (_row_never_deleted, None, 409),
        (_first_job_fails, _delete_connect_error, None),
        (_first_job_fails, _delete_noop_204, 204),
    ],
    ids=["delete_502", "delete_409", "delete_connect_error", "delete_204_not_deleted"],
)
def test_unconfirmed_delete_sends_no_retry(
    script: Any, monkeypatch: pytest.MonkeyPatch, capsys: Any, configure: Any, intercept: Any, first_status: int | None
) -> None:
    # V-T3-1 M1: 원본이 있는 failed 분석에서 지운 것이 확인되지 않으면 '지운 분석 다시 분석' 을 보내지 않는다(작업 0)
    code, ctx, seen = _app_run(script, monkeypatch, ["--expect", "failed"], complete=False, configure=configure, intercept=intercept)
    out = capsys.readouterr().out
    assert code == 1
    assert "최종 상태: failed" in out
    (row,) = ctx.store.analyses.values()  # 지워지지 않았다
    (doc,) = ctx.store.docs_of(row["id"])
    assert doc["storage_path"] in ctx.store.objects  # 원본이 남았다(다시 분석하면 실제로 작업이 생기는 상태)
    assert _retry_posts(seen) == []
    assert len(ctx.server.calls("POST", "responses")) == 1  # 처음의 실패한 작업 만들기뿐
    assert len(ctx.server.calls("POST", "files")) == 1
    assert set(ctx.server.files) - set(ctx.server.deleted) == set()
    assert "  [새] 삭제: 실패" in out and "삭제 확인에서 지웠습니다" not in out
    assert "정리를 끝내지 못해 실패로 끝냅니다" in out and row["id"] in out.split("정리 못 함:", 1)[1]
    if first_status is not None:
        assert [s for m, _, s in seen if m == "DELETE"] == [first_status, first_status]  # 삭제 확인 + 정리(두 번째 DELETE 확인 없음)


def _lose_second_retry(kind: str) -> Callable[[httpx.Request, int, Any], Any]:
    count = [0]

    def tamper(request: httpx.Request, status: int, body: Any) -> Any:
        if request.method == "POST" and request.url.path.endswith("/retry") and status == 200:
            count[0] += 1
            if count[0] == 2:  # 원본을 올린 뒤의 다시 분석 — 서버는 작업을 만들었고 응답만 잃는다
                if kind == "interrupt":
                    raise KeyboardInterrupt
                raise (httpx.ReadTimeout if kind == "timeout" else httpx.ConnectError)("synthetic lost retry response")
        return None

    return tamper


@pytest.mark.parametrize("kind", ["timeout", "connect", "interrupt"])
def test_lost_retry_response_still_cleans_upstage_files(script: Any, monkeypatch: pytest.MonkeyPatch, capsys: Any, kind: str) -> None:
    # V-T3-1 M2: 앞의 원본 없는 실패(끝남)를 믿지 않고 정리 단계가 다시 읽어 새 file id 를 지운다(--keep 이라 분석은 남음)
    code, ctx, seen = _app_run(
        script, monkeypatch, ["--retry-flow", "--keep"], response=build_findings_response(), complete=False, tamper=_lose_second_retry(kind)
    )
    out = capsys.readouterr().out
    assert code == 1
    assert len(ctx.server.job_bodies) == 1 and len(ctx.server.calls("POST", "files")) == 1
    assert set(ctx.server.files) - set(ctx.server.deleted) == set(), out[-2000:]
    assert "정리: Upstage 파일 1개 삭제 요청 완료" in out and "정리 확인 못 함" not in out
    (row,) = ctx.store.analyses.values()
    assert row["status"] == "running"  # --keep — 분석·원본은 남긴다
    assert "정리: 이번 실행이 만든 분석을 남깁니다" in out
    # 정리의 다시 읽기는 응답을 잃은 다시 분석 뒤에 있다
    last_retry = max(i for i, (m, p, _) in enumerate(seen) if m == "POST" and p.endswith("/retry"))
    assert any(m == "GET" and p == f"/api/py/analyses/{row['id']}" for m, p, _ in seen[last_retry + 1 :])


def test_lost_retry_response_without_keep_cleans_files_then_deletes(script: Any, monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    code, ctx, _ = _app_run(
        script, monkeypatch, ["--retry-flow"], response=build_findings_response(), complete=False, tamper=_lose_second_retry("timeout")
    )
    out = capsys.readouterr().out
    assert code == 1
    assert set(ctx.server.files) - set(ctx.server.deleted) == set()
    assert ctx.store.analyses == {} and ctx.store.objects == {}
    assert REMOVED in out


def test_settle_start_keeps_pending_unless_observed_or_refused(script: Any) -> None:
    run = script.Run(script.argparse.Namespace(base_url="http://127.0.0.1:8200"), {})
    try:
        run.observe({"status": "failed", "documents": []})
        assert run.terminal
        run.begin_start()
        assert run.start_requested and run.start_pending
        for status in (500, 502, 503):
            run.settle_start(status, {"detail": "x"})
            assert run.start_pending  # 서버가 작업을 만들었을 수 있다
        run.settle_start(200, ["not", "an", "object"])
        assert run.start_pending
        for status in (400, 404, 409, 413):
            run.begin_start()
            run.settle_start(status, {"detail": "x"})
            assert not run.start_pending  # 작업을 만들지 않는 거절
        run.begin_start()
        run.settle_start(200, {"status": "running", "documents": [{"upstage_file_id": "file_new"}]})
        assert not run.start_pending and not run.terminal and list(run.file_ids) == ["file_new"]
    finally:
        run.http.close()


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("started_at", "완료 행의 started_at 이 마지막 다시 분석 때 값과 다름"),
        ("created_at", "완료 행의 created_at 이 처음과 다름"),
    ],
)
def test_changed_times_at_completion_fail_the_retry_check(
    script: Any, monkeypatch: pytest.MonkeyPatch, capsys: Any, field: str, message: str
) -> None:
    # V-T3-1 m1: 분석 중 확인은 그대로 통과하고, 완료된 응답들에서만 시각이 바뀌면 '다시 분석' 확인 실패 · 종료 1
    done_reads = [0]

    def change(request: httpx.Request, status: int, body: Any) -> Any:
        if isinstance(body, dict) and body.get("status") == "done" and "id" in body:
            done_reads[0] += 1
            if done_reads[0] == 1:  # 분석 중 다시 분석 409 뒤의 다시 읽기 — 분석 중 그대로 보이게
                return {**body, "status": "running", "result": None, "review": None}
            return {**body, field: "2020-01-01T00:00:00+00:00"}
        return None

    code, ctx, _ = _app_run(script, monkeypatch, ["--retry-flow"], response=build_findings_response(), tamper=change)
    out = capsys.readouterr().out
    assert code == 1
    assert "  [통과] 05. 분석 중에 다시 분석" in out
    assert message in out
    assert "  [새] 다시 분석: 실패" in out
    assert ctx.store.analyses == {}


BAD_DOCUMENTS = [7, "x", {"filename": "a.pdf"}, None, [7, {"filename": "a.pdf"}]]
BAD_IDS = ["number", "string", "object", "null", "bad_item"]


@pytest.mark.parametrize("documents", BAD_DOCUMENTS, ids=BAD_IDS)
def test_malformed_list_documents_fail_without_exception(
    script: Any, monkeypatch: pytest.MonkeyPatch, capsys: Any, documents: Any
) -> None:
    def tamper(request: httpx.Request, status: int, body: Any) -> Any:
        if request.method == "GET" and request.url.path == "/api/py/analyses" and body["analyses"]:
            body["analyses"][0]["documents"] = documents
            return body
        return None

    code, ctx, _ = _app_run(script, monkeypatch, [], response=build_findings_response(), tamper=tamper)
    out = capsys.readouterr().out
    assert "예상 못 한 오류" not in out, out[-2000:]
    assert code == 1
    assert "확인 요약:" in out and "  [새] 목록: 실패" in out and "  [새] 삭제: 통과" in out
    assert ctx.store.analyses == {}


@pytest.mark.parametrize("documents", BAD_DOCUMENTS, ids=BAD_IDS)
def test_malformed_retry_documents_fail_without_exception(
    script: Any, monkeypatch: pytest.MonkeyPatch, capsys: Any, documents: Any
) -> None:
    def tamper(request: httpx.Request, status: int, body: Any) -> Any:
        if request.method == "POST" and request.url.path.endswith("/retry") and status == 200:
            return {**body, "documents": documents}
        return None

    code, ctx, _ = _app_run(script, monkeypatch, ["--retry-flow"], response=build_findings_response(), tamper=tamper)
    out = capsys.readouterr().out
    assert "예상 못 한 오류" not in out, out[-2000:]
    assert code == 1
    assert "확인 요약:" in out and "  [새] 다시 분석: 실패" in out
    assert "documents 가 목록이 아님" in out or "documents 에 객체가 아닌 항목" in out
    assert set(ctx.server.files) - set(ctx.server.deleted) == set()
    assert ctx.store.analyses == {}


@pytest.mark.parametrize("documents", [7, [7]], ids=["number", "bad_item"])
def test_malformed_read_documents_fail_without_exception(
    script: Any, monkeypatch: pytest.MonkeyPatch, capsys: Any, documents: Any
) -> None:
    def tamper(request: httpx.Request, status: int, body: Any) -> Any:
        if request.method == "GET" and request.url.path.count("/") == 4 and status == 200 and isinstance(body, dict) and "status" in body:
            return {**body, "documents": documents}  # GET /api/py/analyses/{id}
        return None

    code, ctx, _ = _app_run(script, monkeypatch, ["--retry-flow"], response=build_findings_response(), tamper=tamper)
    out = capsys.readouterr().out
    assert "예상 못 한 오류" not in out, out[-2000:]
    assert code == 1
    assert "확인 요약:" in out and "  [새] 다시 분석: 실패" in out and "  [새] 목록: 실패" in out
    assert set(ctx.server.files) - set(ctx.server.deleted) == set()
    assert ctx.store.analyses == {}


def test_observe_keeps_valid_file_ids_from_malformed_documents(script: Any) -> None:
    run = script.Run(script.argparse.Namespace(base_url="http://127.0.0.1:8200"), {})
    try:
        for documents in (7, "x", {"upstage_file_id": "file_obj"}, None):
            run.observe({"status": "running", "documents": documents})
        assert list(run.file_ids) == []
        run.observe({"status": "running", "documents": [7, None, {"upstage_file_id": ""}, {"upstage_file_id": "file_ok"}]})
        assert list(run.file_ids) == ["file_ok"] and not run.terminal
        assert script._documents({"documents": 7}) == [] and script._documents("x") == []
        assert script._documents_problems({"documents": 7}) == ["documents 가 목록이 아님(int)"]
        assert script._documents_problems({"documents": [7, {}]}) == ["documents 에 객체가 아닌 항목 1개"]
        assert script._documents_problems({"documents": []}) == []
    finally:
        run.http.close()


# --- 검토사항(review-items T3): done 확인의 result.items · 해결·다시 열기 흐름 ------------------------------------
# done 확인: 스크립트가 documents·findings 로 따로 계산한 기대값(_expected_items)이 백엔드 build_items 와 여러 모양에서 같고,
# 계약과 다른 items(키·순서·번호·id·쪽·참조·글·개수·종류)·green 아닌 검증(새 모양)은 실패 — 출력에는 위치·키 이름만.
# 검토 동작: 첫 검토사항 해결 → 다시 해결 409 → 다시 열기 → 다시 열기 409 → 다시 해결 → 없는 id 404 → 400 둘 → 완료 문구의
# 미해결 검토사항 수 → 잠긴 채 409 둘. 계약과 다른 응답이면 실패, 검토사항 0개면 건너뜀, 검증 실패 결과(missing 1개)도 통과.

ITEM_TEXT = "api_e2e 검토사항 해결"
ITEM_TEXT_AGAIN = "api_e2e 검토사항 다시 해결"
SENTINEL = "원문센티널-ITEM-5Z"


def _item_view(*docs: dict[str, Any], findings: list[dict[str, Any]]) -> dict[str, Any]:
    return {"documents": list(docs), "findings": findings}


def _tricky_item_views() -> list[dict[str, Any]]:
    """스크립트 기대값 ↔ 백엔드 build_items 비교용 화면 결과(검증 green·null 만 — missing 은 checks 가 있어야 하므로)."""
    from fake_items import BOX, vdoc, vfinding

    many_low = [vfinding(0, f"low{n}", confidence="low", page=1 + n % 3) for n in range(8)]  # 8건 → '외 3건'
    spread = [vfinding(1, f"p{n}", confidence="low", page=10 + n) for n in range(25)]  # 25쪽 → 근거 앞 20쪽
    nul, sur = chr(0), chr(0xD800)
    odd = [
        vfinding(2, "long", page=None, boxes=[], label="가" * 100),  # 위치 없음 · 이름 40자 자르기
        vfinding(2, "nul", page=40, boxes=[], label="a" + nul + "b"),  # 범위 안 쪽 · 상자 없음 · NUL
        vfinding(2, "sur", page=99, boxes=BOX, label="x" + sur),  # 범위 밖 쪽 → 서류 첫 쪽 · 위치 없음 · 서로게이트
        vfinding(2, "ws", label=chr(0x3000) + " " + chr(0xFEFF)),  # label 이 JS 공백뿐 → field
        vfinding(2, "", label="", fid="2:"),  # 이름 없음
        vfinding(2, "lowloc", confidence="low", page=41),  # low · 위치 있음(41쪽)
        vfinding(2, "lownoloc", confidence="low", page=None, boxes=[]),  # low · 위치 없음(n 에만)
        vfinding(2, "bool", page=True, boxes=BOX),  # bool 쪽 → 위치 없음
    ]
    return [
        _item_view(vdoc(0, 1, 3), vdoc(1, 10, 40), vdoc(2, 40, 41), vdoc(3, 42, 42, kind="other"), findings=[*many_low, *spread, *odd]),
        _item_view(
            vdoc(5, 7, 6, validation="Green "),  # page_end < page_start → [7, 7]
            {**vdoc(4), "page_start": None},  # 보이지 않는 서류
            vdoc(1, 2, 2, kind="other", validation=None),
            vdoc(1, 3, 3),  # 같은 index 두 번 → 처음 것
            {**vdoc(0), "index": True},  # bool index → 보이지 않음
            findings=[vfinding(5, "a", page=7, confidence="low"), vfinding(4, "b", confidence="low"), vfinding(1, "c", page=None, boxes=[])],
        ),
        _item_view(findings=[]),
    ]


def test_expected_items_agree_with_the_backend_on_many_shapes(script: Any) -> None:
    # 계약을 따로 구현한 두 쪽(스크립트 _expected_items · 백엔드 build_items)이 같은 값을 낸다(스크립트는 백엔드를 import 하지 않는다)
    from fake_items import merged_result

    from imask_backend.findings import build_view
    from imask_backend.items import build_items

    views = [build_view(stored_result()), build_view(merged_result()), *_tricky_item_views()]
    for n, view in enumerate(views):
        want, reason = script._expected_items(view)
        assert want is not None, (n, reason)
        backend = build_items(view["documents"], view["findings"])
        assert json.dumps(want, ensure_ascii=True) == json.dumps(backend, ensure_ascii=True), n  # 키 순서까지
        assert script._items_shape_problems(backend, view) == [], n
        assert script._items_compare(backend, want) == [], n
    tricky = script._expected_items(views[2])[0]
    assert tricky is not None
    lows = [i for i in tricky if i["type"] == "lowconf"]
    assert lows[0]["desc"].endswith(" 외 3건의 값이 틀렸을 수 있습니다.") and len(lows[1]["evidence"]) == 20


@pytest.mark.parametrize(
    ("validation", "green"),
    [(None, True), ("", True), ("green", True), (" Green ", True), ("GREEN" + chr(0x3000), True), ("red", False), ("yellow", False), (1, False)],
)
def test_validation_green(script: Any, validation: Any, green: bool) -> None:
    assert script._validation_green(validation) is green


def test_done_items_check_passes_and_prints_counts_only(script: Any, capsys: Any) -> None:
    api = FakeApi(poll_mode="done")
    assert _run(script, api, _done_upstage(), ["--no-review", "--keep"]) == 0
    out = capsys.readouterr().out
    assert "검토사항(result.items):\n  6개 · 종류 {'lowconf': 4, 'nolocation': 1, 'other': 1} · 근거 6개" in out
    assert "  계약 모양(키·순서·타입·R-nn 연속·id 중복 없음·서류·쪽·탐지 항목 참조): 맞음" in out
    assert "nolocation·lowconf·other, 검증 모두 green·null → missing 0): 6개 · 종류 {'lowconf': 4, 'nolocation': 1, 'other': 1}: 일치" in out
    assert "  done 확인(요약·화면용 결과 고정 기대값·검토사항·응답 크기): 통과" in out
    # 검토사항 글·id 는 출력하지 않는다(개수·종류만)
    for item in api.read_done()["result"]["items"]:
        assert item["title"] not in out and item["desc"] not in out and item["id"] not in out
    _assert_no_values(out)


def _drop_items(result: dict[str, Any], _include: bool) -> None:
    del result["items"]


def _swap_keys(result: dict[str, Any], _include: bool) -> None:
    first = result["items"][0]
    first["page"] = first.pop("page")  # page 를 끝으로(키 순서가 계약과 다름)


def _number_gap(result: dict[str, Any], _include: bool) -> None:
    result["items"][1]["number"] = "R-03"


def _duplicate_item_id(result: dict[str, Any], _include: bool) -> None:
    result["items"][1]["id"] = result["items"][0]["id"]


def _evidence_page_out(result: dict[str, Any], _include: bool) -> None:
    result["items"][0]["evidence"][0]["page"] = 99


def _title_sentinel(result: dict[str, Any], _include: bool) -> None:
    result["items"][0]["title"] = SENTINEL


def _extra_item(result: dict[str, Any], _include: bool) -> None:
    extra = copy.deepcopy(result["items"][-1])
    extra.update(id="other:9", number="R-07")
    result["items"].append(extra)


def _missing_item(result: dict[str, Any], _include: bool) -> None:
    items = result["items"]
    del items[0]
    for n, item in enumerate(items, 1):
        item["number"] = f"R-{n:02d}"


def _unknown_type(result: dict[str, Any], _include: bool) -> None:
    result["items"][0]["type"] = "riskhigh"


def _foreign_finding(result: dict[str, Any], _include: bool) -> None:
    result["items"][0]["evidence"][0]["finding_ids"].append("4:card_number")  # 다른 서류의 탐지 항목


def _nolocation_without_finding(result: dict[str, Any], _include: bool) -> None:
    (item,) = [i for i in result["items"] if i["type"] == "nolocation"]
    item["finding_id"] = None


def _red_validation(result: dict[str, Any], _include: bool) -> None:
    result["documents"][1]["validation"] = "red"


def _wrong_nums(result: dict[str, Any], _include: bool) -> None:
    result["items"][0]["desc"] = result["items"][0]["desc"].replace("D1-", "D2-")


@pytest.mark.parametrize(
    ("tamper", "messages"),
    [
        (_drop_items, ["result.items 가 목록이 아님", "개수 0(기대 6)"]),
        (_swap_keys, ["items[0]: 키·순서가 계약과 다름"]),
        (_number_gap, ["number 가 R-01 부터 이어지지 않음", "items[1].number: 기대값과 다름"]),
        (_duplicate_item_id, ["id 가 겹침", "items[1].id: 기대값과 다름"]),
        (_evidence_page_out, ["items[0].evidence[0].page(서류 쪽 범위)", "items[0].evidence[0].page: 기대값과 다름"]),
        (_title_sentinel, ["items[0].title: 기대값과 다름"]),
        (_extra_item, ["개수 7(기대 6)", "종류 {'lowconf': 4, 'nolocation': 1, 'other': 2}"]),
        (_missing_item, ["개수 5(기대 6)", "items[0].id: 기대값과 다름"]),
        (_unknown_type, ["items[0].type", "'계약 밖': 1"]),
        (_foreign_finding, ["items[0].evidence[0].finding_ids(그 서류의 탐지 항목)"]),
        (_nolocation_without_finding, ["finding_id(nolocation 만 있음)", ".finding_id: 기대값과 다름"]),
        (_wrong_nums, ["items[0].desc: 기대값과 다름"]),
        (_red_validation, ["계산할 수 없음 — 새 모양 — 검증 결과가 green 이 아닌 서류 1개"]),
    ],
    ids=[
        "no_items",
        "key_order",
        "number_gap",
        "duplicate_id",
        "evidence_page",
        "title",
        "extra",
        "missing",
        "unknown_type",
        "foreign_finding",
        "nolocation_finding_id",
        "nums",
        "red_validation_new_shape",
    ],
)
def test_done_items_problems_fail(script: Any, capsys: Any, tamper: Any, messages: list[str]) -> None:
    api = FakeApi(poll_mode="done", tamper=tamper)
    assert _run(script, api, _done_upstage(), ["--no-review", "--keep"]) == 1
    out = capsys.readouterr().out
    for message in messages:
        assert message in out, message
    assert "  done 확인(요약·화면용 결과 고정 기대값·검토사항·응답 크기): 실패" in out
    assert "결과: 기대와 다름" in out
    assert SENTINEL not in out and "riskhigh" not in out  # 받은 값은 출력하지 않는다
    _assert_no_values(out)


def test_analysis_id_mode_checks_items_without_writing(script: Any, capsys: Any) -> None:
    # 읽기만 하는 확인에서도 result.items 를 본다(쓰기 없음)
    api = FakeApi(poll_mode="done", tamper=_number_gap)
    assert _run(script, api, FakeUpstageServer(), ["--analysis-id", ANALYSIS_ID]) == 1
    assert [r for r in api.requests if r.method != "GET"] == []
    assert "number 가 R-01 부터 이어지지 않음" in capsys.readouterr().out


def test_item_actions_store_the_contract_values(script: Any, capsys: Any) -> None:
    api = FakeApi(poll_mode="done")
    assert _run(script, api, _done_upstage(), ["--keep"]) == 0
    out = capsys.readouterr().out
    assert "[실패]" not in out
    items = api.read_done()["result"]["items"]
    assert (items[0]["id"], items[0]["number"], items[0]["type"]) == ("lowconf:0", "R-01", "lowconf")
    # 보낸 본문(정확한 필드) — 해결·다시 해결 409·다시 열기·다시 열기 409·다시 해결·없는 id·note 붙은 다시 열기·501자
    bodies = [api.review_posts[n - 1] for n in ITEM_POSTS]
    assert [body["type"] for body in bodies] == ITEM_POST_TYPES
    resolve = {"type": "resolve_item", "actor": "api_e2e", "item_id": "lowconf:0"}
    reopen = {"type": "reopen_item", "actor": "api_e2e", "item_id": "lowconf:0"}
    assert bodies[0] == bodies[1] == {**resolve, "note": ITEM_TEXT}
    assert bodies[2] == bodies[3] == reopen
    assert bodies[4] == {**resolve, "note": ITEM_TEXT_AGAIN}
    assert bodies[5]["item_id"] not in {i["id"] for i in items} and bodies[5]["type"] == "resolve_item"
    assert bodies[6] == {**reopen, "note": ""} and bodies[7] == {**resolve, "note": "가" * 501}
    # 잠긴 채 보낸 두 동작: 해결하지 않은 다른 검토사항(R-02) 해결 · 해결한 R-01 다시 열기
    assert api.review_posts[24:26] == [
        {"type": "resolve_item", "actor": "api_e2e", "item_id": "nolocation:2:income_info", "note": ITEM_TEXT},
        reopen,
    ]
    # 저장된 이력(H12~H15)·해결 기록
    saved = api.store.reviews[ANALYSIS_ID]
    lines = [{k: line[k] for k in ("id", "kind", "target", "change", "reason")} for line in saved["history"][11:15]]
    assert lines == [
        {"id": "H12", "kind": "resolve", "target": "R-01 인식 확인 필요", "change": "미해결 → 해결", "reason": ITEM_TEXT},
        {"id": "H13", "kind": "reopenItem", "target": "R-01 인식 확인 필요", "change": "해결 → 미해결", "reason": ""},
        {"id": "H14", "kind": "resolve", "target": "R-01 인식 확인 필요", "change": "미해결 → 해결", "reason": ITEM_TEXT_AGAIN},
        {
            "id": "H15",
            "kind": "complete",
            "target": "분석 건",
            "change": "검토 필요 → 검토 완료 (남은 항목: 미확인 탐지 26건, 미해결 검토사항 5건)",
            "reason": "api_e2e 검토 완료",
        },
    ]
    assert saved["items"] == {
        "lowconf:0": {"resolved": True, "note": ITEM_TEXT_AGAIN, "resolved_at": saved["history"][13]["at"], "resolved_by": "api_e2e"}
    }
    assert "[통과] 15. resolve_item(R-01) — 이력 14줄 · version 12" in out
    assert "[통과] 22. resolve_item 501자 처리 내용 → 400(R-01) — HTTP 400 · 쓰기 없음" in out
    assert "[통과] 23. complete_review(남은 미확인 26건 · 미해결 검토사항 5건)" in out
    assert ITEM_TEXT not in out  # 처리 내용(합성 문구)도 출력하지 않는다
    row = api.store.analyses[ANALYSIS_ID]
    assert (row["created_at"], row["updated_at"]) == (CREATED_AT, UPDATED_AT) and "update_analysis" not in api.store.calls


def _handled(api: FakeApi, body: dict[str, Any]) -> None:
    """그 본문을 실제 검토 로직으로 처리한다(저장은 정상)."""
    review_action_out(api.store, ANALYSIS_ID, parse_action(json.dumps(body, ensure_ascii=True).encode()))


Change = Callable[[FakeApi, dict[str, Any]], "dict[str, Any] | None"]


def _after_post(n_post: int, change: Change) -> Callable[[FakeApi, dict[str, Any], int], httpx.Response | None]:
    """n번째 POST 를 정상 처리한 뒤 change(api, 응답) 로 저장 행이나 응답을 바꾼다(None 이면 바뀐 저장 행으로 다시 만든 응답)."""

    def override(api: FakeApi, body: dict[str, Any], n: int) -> httpx.Response | None:
        if n != n_post:
            return None
        _handled(api, body)
        replaced = change(api, {"analysis": api.read_done(), "changed": True})
        return _json_response(200, replaced if replaced is not None else {"analysis": api.read_done(), "changed": True})

    return override


def _answer(n_post: int, status: int, detail: str | None = None) -> Callable[[FakeApi, dict[str, Any], int], httpx.Response | None]:
    """n번째 POST 에 쓰기 없이 status 로 답한다(200 이면 지금 분석 · changed false)."""

    def override(api: FakeApi, body: dict[str, Any], n: int) -> httpx.Response | None:
        if n != n_post:
            return None
        if status == 200:
            return _json_response(200, {"analysis": api.read_done(), "changed": False})
        return httpx.Response(status, json={"detail": detail})

    return override


def _saved_item(**values: Any) -> Change:
    def change(api: FakeApi, _out: dict[str, Any]) -> None:
        api.store.reviews[ANALYSIS_ID]["items"]["lowconf:0"].update(values)

    return change


def _last_line(key: str, value: str) -> Change:
    def change(api: FakeApi, _out: dict[str, Any]) -> None:
        api.store.reviews[ANALYSIS_ID]["history"][-1][key] = value

    return change


def _review_row(**values: Any) -> Change:
    def change(api: FakeApi, _out: dict[str, Any]) -> None:
        api.store.reviews[ANALYSIS_ID].update(values)

    return change


def _other_item_written(api: FakeApi, _out: dict[str, Any]) -> None:
    api.store.reviews[ANALYSIS_ID]["items"]["other:5"] = {"resolved": True, "note": "", "resolved_at": None, "resolved_by": ""}


def _started_at_in_response(_api: FakeApi, out: dict[str, Any]) -> dict[str, Any]:
    out["analysis"]["started_at"] = "2026-11-03T06:41:40+00:00"
    return out


STATE_409 = "검토사항 상태가 바뀌었습니다. 새로 고친 뒤 다시 시도해 주세요."


@pytest.mark.parametrize(
    ("override", "message"),
    [
        (_after_post(14, _saved_item(resolved_at="2026-11-03T00:00:00+00:00")), "R-01 resolved_at: 계약과 다름"),
        (_after_post(14, _saved_item(resolved_by="다른 처리자")), "R-01 resolved_by: 계약과 다름"),
        (_after_post(14, _last_line("target", "lowconf:0 인식 확인 필요")), "새 이력 target: 계약과 다름"),
        (_after_post(14, _last_line("kind", "confirm")), "새 이력 kind: 계약과 다름"),
        (_answer(15, 200), "HTTP 200"),
        (_answer(15, 409, "검토를 완료한 분석은 바꿀 수 없습니다."), f"(기대 409 {STATE_409})"),
        (_after_post(16, _saved_item(note="")), "R-01 note: 계약과 다름"),
        (_after_post(16, _saved_item(resolved_at=None)), "R-01 resolved_at 이 남지 않음"),
        (_after_post(16, _last_line("change", "해결 → 미확인")), "새 이력 change: 계약과 다름"),
        (_after_post(16, _last_line("reason", ITEM_TEXT)), "새 이력 reason: 계약과 다름"),
        (_answer(17, 200), "HTTP 200"),
        (_after_post(18, _saved_item(note=ITEM_TEXT)), "R-01 note: 계약과 다름"),
        (_answer(19, 409, STATE_409), "(기대 404 검토사항을 찾을 수 없습니다.)"),
        (_answer(20, 200), "HTTP 200"),
        (_answer(21, 400, "메모·사유에 쓸 수 없는 문자가 있습니다."), "(기대 400 메모·사유는 500자 이하로 적어 주세요.)"),
        (_after_post(22, _last_line("change", "검토 필요 → 검토 완료 (남은 항목: 미확인 탐지 26건)")), "새 이력 change: 계약과 다름"),
        (_answer(25, 409, STATE_409), "(기대 409 검토를 완료한 분석은 바꿀 수 없습니다.)"),
        (_answer(26, 200), "HTTP 200"),
        (_after_post(31, _review_row(items={})), "review items 가 바뀜"),
        (_after_post(14, _other_item_written), "다른 검토사항의 저장 값이 바뀜"),
        (_after_post(14, _started_at_in_response), "분석 started_at 가 바뀜"),
    ],
    ids=[
        "resolve_time_not_history_time",
        "resolve_actor",
        "resolve_target_uses_id",
        "resolve_kind",
        "second_resolve_accepted",
        "second_resolve_wrong_409",
        "reopen_clears_note",
        "reopen_clears_time",
        "reopen_change_text",
        "reopen_reason",
        "second_reopen_accepted",
        "resolve_again_keeps_old_note",
        "unknown_id_409",
        "reopen_with_note_accepted",
        "long_note_wrong_400",
        "complete_without_open_items",
        "locked_resolve_wrong_409",
        "locked_reopen_accepted",
        "reopen_review_wipes_items",
        "other_item_changed",
        "started_at_changed",
    ],
)
def test_unexpected_item_responses_fail(script: Any, capsys: Any, override: Any, message: str) -> None:
    api = FakeApi(poll_mode="done", review_override=override)
    assert _run(script, api, _done_upstage(), []) == 1
    out = capsys.readouterr().out
    assert message in out, out[-2500:]
    assert "검토 동작 확인: " in out and "— 기대와 다름" in out
    assert "결과: 기대와 다름" in out
    assert ITEM_TEXT not in out and "다른 처리자" not in out


def _api_with_result(result: dict[str, Any]) -> FakeApi:
    api = FakeApi(poll_mode="done")
    api.store.analyses[ANALYSIS_ID]["result"] = result
    return api


def test_zero_items_skips_the_item_actions(script: Any, capsys: Any) -> None:
    # 모두 신뢰도 high · 위치 있음 · 기타 서류 없음 → 검토사항 0개: 해결·다시 열기·잠긴 채 검토사항 동작을 보내지 않는다
    from fake_items import Spec, bundle_result, merged_specs

    specs = [Spec(s.code, s.pages, {k: (v, p, "high") for k, (v, p, _c) in s.fields.items()}) for s in merged_specs() if s.validate]
    api = _api_with_result(bundle_result(specs))
    assert api.read_done()["result"]["items"] == []
    _run(script, api, _done_upstage(), ["--keep"])  # done 고정 기대값(알려진 모양)은 다르다 — 검토 동작 확인만 본다
    out = capsys.readouterr().out
    assert "  검토사항 해결·다시 열기 확인 건너뜀(검토사항 0개)" in out
    assert "검토 동작 확인: 25/25 통과 · 쓴 동작 15건 — 기대대로" in out
    assert not {"resolve_item", "reopen_item"} & set(_review_types(api))
    assert "0개 · 종류 {} · 근거 0개" in out and "0개 · 종류 {}: 일치" in out
    (complete,) = [line for line in api.store.reviews[ANALYSIS_ID]["history"] if line["kind"] == "complete"]
    assert "미해결 검토사항" not in complete["change"]


def test_failed_validation_result_resolves_the_missing_item(script: Any, capsys: Any) -> None:
    # 검증 실패 결과(서류 1 신청인 성명 규칙 실패 · verdict red) — done 확인은 '새 모양'으로 실패를 알리고(missing 을 계산할 수 없음),
    # 검토 동작은 그 missing 검토사항 하나로 그대로 통과한다(완료 문구에 미해결 검토사항 없음)
    from fake_items import failing_result

    api = _api_with_result(failing_result())
    (item,) = api.read_done()["result"]["items"]
    assert (item["id"], item["type"], item["title"]) == ("missing:1:applicant_name_detected", "missing", "신청인 성명이 없습니다")
    assert _run(script, api, _done_upstage(), ["--keep"]) == 1
    out = capsys.readouterr().out
    assert "계산할 수 없음 — 새 모양 — 검증 결과가 green 이 아닌 서류 1개" in out
    assert f"검토 동작 확인: {REVIEW_STEPS}/{REVIEW_STEPS} 통과 · 쓴 동작 {REVIEW_WRITES}건 — 기대대로" in out
    saved = api.store.reviews[ANALYSIS_ID]
    assert {line["target"] for line in saved["history"] if line["kind"] in ("resolve", "reopenItem")} == {"R-01 필수 항목 없음"}
    (complete,) = [line for line in saved["history"] if line["kind"] == "complete"]
    assert "미해결 검토사항" not in complete["change"]
    assert "[통과] 26. 잠김 — resolve_item(R-01) → 409" in out  # 다른 검토사항이 없으면 해결한 것으로


def _review_read(api: FakeApi, mutate: Callable[[dict[str, Any]], None]) -> None:
    real = api.read_done

    def read_done(include: bool = False) -> dict[str, Any]:
        body = real(include)
        if isinstance(body.get("review"), dict):
            mutate(body["review"])
        return body

    api.read_done = read_done  # type: ignore[method-assign]


def _items_not_object(review: dict[str, Any]) -> None:
    review["items"] = []


def _stranger_item(review: dict[str, Any]) -> None:
    review["items"]["x:1"] = {"resolved": True, "note": "", "resolved_at": None, "resolved_by": ""}


def _resolved_text(review: dict[str, Any]) -> None:
    review["items"]["lowconf:0"] = {"resolved": "true", "note": "", "resolved_at": None, "resolved_by": ""}


def _item_missing_keys(review: dict[str, Any]) -> None:
    review["items"]["lowconf:0"] = {"resolved": True}


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (_items_not_object, "items 가 객체가 아님"),
        (_stranger_item, "지금 결과의 검토사항이 아닌 id 1개"),
        (_resolved_text, "값 모양"),
        (_item_missing_keys, "값 모양"),
    ],
    ids=["not_object", "stranger_id", "resolved_text", "missing_keys"],
)
def test_review_items_shape_problems_fail_read_only(script: Any, capsys: Any, mutate: Any, message: str) -> None:
    api = FakeApi(poll_mode="done")
    _review_read(api, mutate)
    assert _run(script, api, FakeUpstageServer(), ["--analysis-id", ANALYSIS_ID]) == 1
    out = capsys.readouterr().out
    assert message in out and "x:1" not in out
    assert _review_requests(api) == []


def test_read_only_mode_accepts_a_resolved_item(script: Any, capsys: Any) -> None:
    api = FakeApi(poll_mode="done")
    _handled(api, {"type": "resolve_item", "actor": "검토자", "item_id": "other:5", "note": "합성 처리 내용"})
    assert _run(script, api, FakeUpstageServer(), ["--analysis-id", ANALYSIS_ID]) == 0
    out = capsys.readouterr().out
    assert "findings 0개 · 검토사항 해결 기록 1개 · 이력 3줄(S1·S2 포함) · version 1 · 기본값(검토 행 없음) False: 맞음" in out
    assert _review_requests(api) == []


def test_first_read_needs_empty_review_items(script: Any, capsys: Any) -> None:
    # 새 분석의 처음 조회는 review.items {} — 이미 해결 기록이 있으면 처음 조회 실패로 동작을 보내지 않는다
    api = FakeApi(poll_mode="done")
    _handled(api, {"type": "resolve_item", "actor": "검토자", "item_id": "other:5", "note": ""})
    assert _run(script, api, _done_upstage(), []) == 1
    out = capsys.readouterr().out
    assert "[실패] 01. 처음 조회" in out and "items: 계약과 다름" in out
    assert api.review_posts == []


# --- 수정 1회차(V-T3-1 M1): 검토 동작을 켠 기본 흐름에서도 받은 표시 번호·id·글을 출력하지 않는다 ------------------------
# 검토사항 동작을 보내기 전에 result.items 전체의 계약 모양을 먼저 본다 — 틀리면 값 없는 실패 위치만 적고 검토사항 POST 0개.
# 모양은 맞고 done 기대값만 다르면(글·id 가 다름) 검토 흐름은 그대로 돌되, 출력의 번호는 스크립트가 만든 순번이다.

ITEM_ACTIONS = ("resolve_item", "reopen_item")


def _item_posts(api: FakeApi) -> list[dict[str, Any]]:
    return [body for body in api.review_posts if body.get("type") in ITEM_ACTIONS]


def _set_item(n: int, key: str, value: Any) -> Callable[[dict[str, Any], bool], None]:
    def tamper(result: dict[str, Any], _include: bool) -> None:
        result["items"][n][key] = value

    return tamper


SHAPE_BREAKS = [
    ("number_sentinel", _set_item(0, "number", SENTINEL), ["number 가 R-01 부터 이어지지 않음"]),
    ("second_number_sentinel", _set_item(1, "number", SENTINEL), ["number 가 R-01 부터 이어지지 않음"]),
    ("id_wrong_type", _set_item(1, "id", {"x": SENTINEL}), ["items[1].id"]),
    ("type_sentinel", _set_item(0, "type", SENTINEL), ["items[0].type"]),
    ("empty_title", _set_item(0, "title", ""), ["items[0].title·desc·next"]),
    ("page_text", _set_item(0, "page", SENTINEL), ["items[0].page(서류 쪽 범위)"]),
]


@pytest.mark.parametrize(("tamper", "messages"), [c[1:] for c in SHAPE_BREAKS], ids=[c[0] for c in SHAPE_BREAKS])
def test_bad_item_shape_sends_no_item_actions_and_prints_no_received_value(script: Any, capsys: Any, tamper: Any, messages: list[str]) -> None:
    api = FakeApi(poll_mode="done", tamper=tamper)
    assert _run(script, api, _done_upstage(), []) == 1  # 검토 동작 켬(기본)
    out = capsys.readouterr().out
    assert SENTINEL not in out
    assert _item_posts(api) == []
    assert "[실패]" in out and "검토사항 모양 — 계약과 달라 해결·다시 열기를 보내지 않음" in out
    for message in messages:
        assert message in out, message
    assert "검토 동작 확인: " in out and "— 기대와 다름" in out and "결과: 기대와 다름" in out
    _assert_no_values(out)


@pytest.mark.parametrize(("key", "value"), [("title", SENTINEL), ("desc", SENTINEL), ("id", SENTINEL)], ids=["title", "desc", "id"])
def test_good_shape_with_wrong_values_keeps_the_flow_without_printing_them(script: Any, capsys: Any, key: str, value: Any) -> None:
    # 모양은 맞고 값만 다르면(검증 실패 서류처럼 done 기대값만 다른 경우와 같은 흐름) 검토사항 동작은 그대로 보내고,
    # 출력에는 받은 글·id 가 없다(번호는 스크립트 순번 R-01). id 가 다르면 서버가 404 로 거절하는 것이 실패로 남는다.
    api = FakeApi(poll_mode="done", tamper=_set_item(0, key, value))
    assert _run(script, api, _done_upstage(), []) == 1
    out = capsys.readouterr().out
    assert SENTINEL not in out
    assert f"items[0].{key}: 기대값과 다름" in out
    assert "검토사항 모양 — 계약과 달라" not in out
    assert len(_item_posts(api)) == 10
    assert "resolve_item(R-01)" in out
    if key == "id":
        assert _item_posts(api)[0]["item_id"] == SENTINEL  # 본문에는 받은 계약 id 그대로(출력에는 없음)
        assert "HTTP 404 검토사항을 찾을 수 없습니다.(기대 200" in out


def test_item_target_uses_the_local_number_only_when_it_matches(script: Any) -> None:
    item = {"id": "lowconf:0", "number": "R-02", "type": "lowconf"}
    assert script._item_target(item, 2) == {"id": "lowconf:0", "num": "R-02", "target": "R-02 인식 확인 필요"}
    assert script._item_target(item, 1) is None  # 받은 번호가 순번과 다르면 대상이 아니다
    for bad in ({**item, "number": SENTINEL}, {**item, "number": 2}, {**item, "id": 7}, {**item, "id": ""}, {**item, "type": SENTINEL}, "x", None):
        assert script._item_target(bad, 2) is None


def test_shown_renders_received_values_without_text(script: Any) -> None:
    assert script._shown(True) == "True" and script._shown(None) == "None" and script._shown(3) == "3"
    assert script._shown(SENTINEL) == "<str>" and script._shown({"a": 1}) == "<dict>" and script._shown(1.5) == "<float>"
    assert script._shown("done", script.REVIEW_STATUSES) == "'done'" and script._shown("done") == "<str>"
    assert script._plain("needed", script.REVIEW_STATUSES) == "needed" and script._plain(SENTINEL, script.REVIEW_STATUSES) == "<str>"


def test_readme_result_example_is_a_consistent_response(script: Any) -> None:
    # 수정 1회차(V-T3-1 m1): README 'API 응답의 result' 의 JSON 을 그대로 읽어 — 스크립트의 items 모양 검사·따로 계산한 기대값,
    # 백엔드 build_items, 공통 계약 검사(view_contract.assert_view)를 모두 지난다(예시의 items 가 같은 응답의 findings 를 가리킴)
    import re

    from view_contract import assert_view

    from imask_backend.items import build_items

    text = (ROOT / "README.md").read_text(encoding="utf-8")
    section = text.split("### API 응답의 `result`", 1)[1]
    match = re.search(r"```json\n(.*?)\n```", section, re.DOTALL)
    assert match, "README 에 result 예시 JSON 이 없다"
    example = json.loads(match.group(1))
    assert script._items_shape_problems(example["items"], example) == []
    want, reason = script._expected_items(example)
    assert want is not None, reason
    assert script._items_compare(example["items"], want) == []
    assert json.dumps(build_items(example["documents"], example["findings"]), ensure_ascii=False) == json.dumps(example["items"], ensure_ascii=False)
    assert_view({key: example[key] for key in ("documents", "findings", "overall", "items")})
    assert [i["type"] for i in example["items"]] == ["lowconf"]


def _status_sentinel(review: dict[str, Any]) -> None:
    review["status"] = SENTINEL


def _findings_key_sentinel(review: dict[str, Any]) -> None:
    review["findings"][SENTINEL] = {"status": SENTINEL}


def _version_sentinel(review: dict[str, Any]) -> None:
    review["version"] = SENTINEL


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (_status_sentinel, "status <str>"),
        (_findings_key_sentinel, "findings: 검토 가능 항목이 아닌 id 1개"),
        (_version_sentinel, "version 이 0 이상 정수가 아님"),
    ],
    ids=["status", "findings_key", "version"],
)
def test_review_block_values_are_not_printed(script: Any, capsys: Any, mutate: Any, message: str) -> None:
    # 읽기만 하는 확인 · 기본 흐름의 처음 조회 모두 review 블록의 받은 글자를 출력하지 않는다
    for args in (["--analysis-id", ANALYSIS_ID], []):
        api = FakeApi(poll_mode="done")
        _review_read(api, mutate)
        assert _run(script, api, _done_upstage(), args) == 1
        out = capsys.readouterr().out
        assert SENTINEL not in out, args
        assert message in out, args
        assert api.review_posts == []
