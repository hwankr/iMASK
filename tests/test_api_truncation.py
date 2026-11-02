# ==========================================================================
#  T2-fix2 R2-m1 — 가림은 자르기 **전에**(실제 get_upstage 의존성으로 확인)
#  get_upstage 는 바꾸지 않고, 그 안의 UpstageClient 만 MockTransport 를 쓰는 하위 클래스로 바꾼다 —
#  그래서 실제 의존성의 extra_secrets=settings.secrets() 전달을 그대로 시험한다(빼면 이 테스트가 실패).
#  서버 비밀값 4종을 하나씩, 앞·중간·끝과 300자 절단 지점에 걸치는 모든 위치(1 ~ len-1 자가 앞에 남는
#  자리)로 옮겨 가며: 출력이 기대한 가린 문구와 **정확히** 같고, 가짜 값의 4자 이상 부분 문자열이 없다.
# ==========================================================================

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from api_fakes import (
    ALL_SECRETS,
    FAKE_ACCESS_CODE,
    FAKE_ENV,
    FakeStore,
    FakeUpstageServer,
)
from fastapi.testclient import TestClient

import api.index as api_index
from api.index import app, get_store
from imask_backend.analyses import (
    MSG_POLL_FAILED,
    MSG_RESULT_FETCH_FAILED,
    MSG_UPSTAGE_FAILED,
    MSG_UPSTAGE_START,
)
from imask_backend.redaction import redact
from imask_backend.settings import get_settings, load_settings
from imask_backend.upstage import MAX_MESSAGE, UpstageClient, job_failure_message

CODE = {"X-Demo-Code": FAKE_ACCESS_CODE}
SECRET_IDS = ["upstage_key", "agent_id", "supabase_key", "access_code"]
SETTINGS = load_settings(FAKE_ENV)
SECRETS = SETTINGS.secrets()
OUTER_LIMIT = 500  # analyses.MAX_ERROR_LENGTH

# 경로별 (Upstage 오류 문구 앞부분, 화면 문장 틀)
ACTIONS = {
    "last": ("작업 조회: HTTP 503 — ", MSG_POLL_FAILED),
    "all": ("작업 조회: HTTP 503 — ", MSG_RESULT_FETCH_FAILED),
    "start": ("파일 올리기: HTTP 500 — ", MSG_UPSTAGE_START),
}


@pytest.fixture
def real_dep(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, FakeStore, FakeUpstageServer]]:
    store = FakeStore()
    server = FakeUpstageServer()

    class MockedClient(UpstageClient):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs["transport"] = httpx.MockTransport(server.handle)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(api_index, "UpstageClient", MockedClient)
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    app.dependency_overrides[get_store] = lambda: store
    # get_upstage 는 바꾸지 않는다(실제 의존성)
    with TestClient(app) as client:
        yield client, store, server
    app.dependency_overrides.clear()


def _positions(prefix: str, secret: str) -> list[int]:
    """비밀값 앞에 둘 'x' 개수: 앞·중간, 절단 지점(limit-1)에 걸치는 모든 자리, 절단 뒤."""
    cut = MAX_MESSAGE - 1
    first = cut - len(prefix) - len(secret) + 1  # 비밀값 앞 len-1 자가 절단 앞에 남는 자리
    straddle = list(range(max(first, 0), cut - len(prefix)))  # 1 ~ len-1 자가 앞에 남는 자리 모두
    return [0, 60, 150, *straddle, cut - len(prefix) + 5]


def _assert_no_fragment(text: str, secret: str) -> None:
    # 자리표시자 낱말(예: <UPSTAGE_AGENT_ID> 의 AGENT)과 겹치는 조각은 빼고 센다 — 자리표시자가 잘려도
    # ('<UPSTAGE_AGE…') 비밀값 조각이 아니기 때문
    placeholders = set(SECRETS.values())
    pieces = {secret[i : i + 4] for i in range(len(secret) - 3)}
    pieces = {p for p in pieces if not any(p in ph for ph in placeholders)}
    assert pieces, "검사할 조각이 없다"
    assert not [p for p in pieces if p in text], "가짜 비밀값 조각이 남았다"


def _expected(path: str, message: str) -> str:
    prefix, template = ACTIONS[path]
    reason = redact(prefix + message, SECRETS, limit=MAX_MESSAGE)  # 전체 사전으로 가린 뒤 300자
    return redact(template.format(reason=reason), SECRETS, limit=OUTER_LIMIT)


def _arrange(path: str, store: FakeStore, server: FakeUpstageServer, message: str) -> tuple[str, str]:
    """경로 하나를 준비하고 (HTTP 메서드, 주소) 를 돌려준다."""
    if path == "start":
        analysis_id = store.put()
        server.errors[("POST", "files")] = (500, {"error": {"message": message}})
        return "POST", f"/api/py/analyses/{analysis_id}/start"
    server.files["file_up1"] = ("document.pdf", b"")
    analysis_id = store.put(status="running", job_id="job_up1", upstage_file_id="file_up1")
    if path == "last":
        server.errors[("GET", "response")] = (503, {"error": {"message": message}})
    else:
        server.errors.pop(("GET", "response"), None)
        server.last_status = "completed"
        server.full_error = message
    return "GET", f"/api/py/analyses/{analysis_id}"


@pytest.mark.parametrize("secret", ALL_SECRETS, ids=SECRET_IDS)
@pytest.mark.parametrize("path", list(ACTIONS))
def test_upstage_errors_are_redacted_with_all_secrets_before_truncation(real_dep: Any, path: str, secret: str) -> None:
    client, store, server = real_dep
    original = server.handle

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.query.decode() == "include[]=all" and getattr(server, "full_error", None):
            return httpx.Response(503, json={"error": {"message": server.full_error}})
        return original(request)

    server.handle = handle  # type: ignore[method-assign]
    prefix, _ = ACTIONS[path]
    checked = 0
    for pad in _positions(prefix, secret):
        message = "x" * pad + secret + " tail"
        method, url = _arrange(path, store, server, message)
        body = client.request(method, url, headers=CODE).json()
        shown = body["error"] if path == "start" else body["poll_error"]
        assert shown == _expected(path, message), f"pad={pad}"
        _assert_no_fragment(shown, secret)
        checked += 1
    assert checked >= len(secret) + 2  # 절단 지점의 모든 자리를 지났다


@pytest.mark.parametrize("secret", ALL_SECRETS, ids=SECRET_IDS)
def test_failed_job_reason_is_redacted_with_all_secrets_before_truncation(real_dep: Any, secret: str) -> None:
    client, store, server = real_dep
    server.last_status = "failed"
    for pad in _positions("", secret):
        message = "x" * pad + secret + " tail"
        server.files["file_up1"] = ("document.pdf", b"")
        analysis_id = store.put(status="running", job_id="job_up1", upstage_file_id="file_up1")
        server.last_extra = {"error": {"message": message}}
        body = client.get(f"/api/py/analyses/{analysis_id}", headers=CODE).json()
        reason = job_failure_message({"status": "failed", "error": {"message": message}}, SECRETS)
        expected = redact(MSG_UPSTAGE_FAILED.format(reason=reason), SECRETS, limit=OUTER_LIMIT)
        assert body["error"] == expected, f"pad={pad}"
        assert store.analyses[analysis_id]["error"] == expected
        _assert_no_fragment(body["error"], secret)
