# ==========================================================================
#  T2-fix1 회귀 — 경쟁·가림 경계·영구 404 (네트워크 없음)
#  M1 만료 처리가 시작 요청에 지면 파일을 지우지 않는다
#  M2 바깥 문자열(poll_error·upstage_status·error·로그)은 서버 비밀값 4종 전체로 가린 뒤 자른다
#  M3 서명 URL·토큰(일반·URL 인코딩·JSON 필드·JWT)도 가린다. 정상 만들기 응답의 upload 값은 그대로
#  m2 Upstage 404 는 job id 저장 뒤 2분이 지났을 때만 failed, 401·403 은 계속 다시 시도
# ==========================================================================

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from api_fakes import (
    ALL_SECRETS,
    FAKE_ENV,
    FAKE_SUPABASE_KEY,
    FakeStore,
    FakeUpstageServer,
)
from fake_tokens import fake_jwt
from fastapi.testclient import TestClient

from api.index import app, get_store, get_upstage
from imask_backend.redaction import SIGNED_URL_PLACEHOLDER
from imask_backend.settings import get_settings, load_settings
from imask_backend.store import SupabaseStore
from imask_backend.upstage import UpstageClient

SECRET_IDS = ["upstage_key", "agent_id", "supabase_key"]
JOB_GONE = "Upstage 작업을 찾을 수 없습니다. 새 분석으로 다시 올려 주세요."

# 가짜 서명 정보(실제 값 아님)
FAKE_TOKEN = "FAKE_SIGNED_" + "Q" * 64
FAKE_JWT = fake_jwt({"fake": "probe"}, signature=b"fake-signature-value")
SIGNED_FORMS = {
    "absolute_url": f"cannot read https://p.supabase.co/storage/v1/object/upload/sign/documents/a.pdf?token={FAKE_TOKEN}",
    "relative_url": f"url=/object/upload/sign/documents/a.pdf?token={FAKE_TOKEN}&x=1",
    "download_url": f"see https://p.supabase.co/storage/v1/object/sign/documents/a.pdf?token={FAKE_TOKEN}.",
    "token_query": f"retry with token={FAKE_TOKEN}",
    "url_encoded": f"next=https%3A%2F%2Fp.supabase.co%2Fx%3Ftoken%3D{FAKE_TOKEN}%26y%3D1",
    "json_field": f'{{"token": "{FAKE_TOKEN}", "path": "a.pdf"}}',
    "json_signed_url": f'{{"signedUrl": "https://p.invalid/a?b={FAKE_TOKEN}"}}',
    "escaped_json": f'{{\\"signed_url\\": \\"https://p.invalid/a?b={FAKE_TOKEN}\\"}}',
    "jwt": f"bad credential {FAKE_JWT} given",
}
SIGNED_NEEDLES = (FAKE_TOKEN, FAKE_JWT, FAKE_TOKEN[:24], FAKE_JWT[:24])


def leaky(secret: str) -> str:
    return f"Authorization: Bearer {secret}; leaked {secret}"


@pytest.fixture
def env() -> Iterator[tuple[TestClient, FakeStore, FakeUpstageServer]]:
    settings = load_settings(FAKE_ENV)
    store = FakeStore()
    server = FakeUpstageServer()

    def upstage_override() -> Iterator[Any]:
        made: list[UpstageClient] = []

        def factory() -> UpstageClient:
            if not made:
                # extra_secrets 없이 — 업무 로직의 가림 경계만으로 막는지 본다(더 엄격한 조건)
                made.append(UpstageClient.from_settings(settings.upstage(), transport=httpx.MockTransport(server.handle)))
            return made[0]

        yield factory

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_upstage] = upstage_override
    with TestClient(app) as client:
        yield client, store, server
    app.dependency_overrides.clear()


def _ago(minutes: float) -> str:
    return (datetime.now(UTC) - timedelta(minutes=minutes)).isoformat()


def _running(store: FakeStore, server: FakeUpstageServer, *, minutes_ago: float = 0) -> str:
    server.files["file_up1"] = ("document.pdf", b"")
    return store.put(status="running", job_id="job_up1", upstage_file_id="file_up1", updated_at=_ago(minutes_ago))


def _count(text: str, needles: tuple[str, ...]) -> int:
    return sum(text.count(n) for n in needles)


def _logs(caplog: pytest.LogCaptureFixture) -> str:
    return "\n".join(r.getMessage() for r in caplog.records)


# --- M1 -----------------------------------------------------------------------------


def test_stale_poll_losing_to_start_keeps_running_job_and_file(env: Any) -> None:
    client, store, server = env
    server.files["file_up1"] = ("document.pdf", b"")
    analysis_id = store.put(status="running", updated_at=_ago(6), upstage_file_id="file_up1")

    def start_saves_job_first(aid: str, _values: Any) -> None:
        # 검증 재현과 같은 순서: 조회가 행을 읽은 뒤, 실패 PATCH 직전에 시작 요청의 job id 저장이 이긴다
        store.update_analysis(aid, {"upstage_job_id": "job_now_running"}, expect_status="running", expect_no_job=True)

    store.before_update = start_saves_job_first
    response = client.get(f"/api/py/analyses/{analysis_id}")
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "running"
    assert body["upstage_job_id"] == "job_now_running"
    assert body["error"] is None
    assert server.calls("DELETE") == []
    assert "file_up1" not in server.deleted


def test_stale_poll_winning_fails_and_deletes(env: Any) -> None:
    client, store, server = env
    server.files["file_up1"] = ("document.pdf", b"")
    analysis_id = store.put(status="running", updated_at=_ago(6), upstage_file_id="file_up1")
    body = client.get(f"/api/py/analyses/{analysis_id}").json()
    assert body["status"] == "failed"
    assert server.deleted == ["file_up1"]


# --- M2: 서버 비밀값 4종을 하나씩, 각 경로에서 --------------------------------------


@pytest.mark.parametrize("secret", ALL_SECRETS, ids=SECRET_IDS)
@pytest.mark.parametrize("path", ["last_failure", "all_failure", "failed_job", "save_failure_log", "delete_failure_log"])
def test_outside_strings_are_redacted_with_all_server_secrets(
    env: Any, caplog: pytest.LogCaptureFixture, secret: str, path: str
) -> None:
    client, store, server = env
    analysis_id = _running(store, server)
    message = leaky(secret)
    if path == "last_failure":
        server.errors[("GET", "response")] = (503, {"error": {"message": message}})
    elif path == "all_failure":
        server.last_status = "completed"
        original = server.handle

        def handle(request: httpx.Request) -> httpx.Response:
            if request.url.query.decode() == "include[]=all":
                return httpx.Response(503, json={"error": {"message": message}})
            return original(request)

        server.handle = handle  # type: ignore[method-assign]
    elif path == "failed_job":
        server.last_status = "failed"
        server.last_extra = {"error": {"message": message}}
    elif path == "save_failure_log":
        server.last_status = "completed"
        store.fail.add("update_analysis")
        store.fail_message = f"분석 갱신: APIError: {message}"
    else:  # delete_failure_log
        server.last_status = "failed"
        server.errors[("DELETE", "file")] = (500, {"error": {"message": message}})

    with caplog.at_level(logging.INFO, logger="imask"):
        response = client.get(f"/api/py/analyses/{analysis_id}")
    assert response.status_code == 200
    body = response.json()
    stored_error = store.analyses[analysis_id]["error"] or ""
    logged = _logs(caplog)
    for text in (response.text, stored_error, logged):
        assert secret not in text
        assert "bearer" not in text.lower()
    if path in ("last_failure", "all_failure"):
        assert body["status"] == "running" and body["poll_error"]
    if path == "save_failure_log":
        assert "분석 상태 저장 실패" in logged  # 로그 경로가 실제로 지나갔다
    if path == "delete_failure_log":
        assert "Upstage 파일 삭제 실패" in logged
        assert body["status"] == "failed"


# 가림 전 절단(300자 경계)은 tests/test_api_truncation.py 가 실제 get_upstage 의존성으로 모든 위치를 확인한다(fix2).


def test_upstage_status_is_scrubbed(env: Any) -> None:
    client, store, server = env
    analysis_id = _running(store, server)
    server.last_status = f"weird_{FAKE_SUPABASE_KEY}"
    body = client.get(f"/api/py/analyses/{analysis_id}").json()
    assert FAKE_SUPABASE_KEY not in (body["upstage_status"] or "")
    assert FAKE_SUPABASE_KEY not in (body["error"] or "")


def test_real_upstage_dependency_knows_all_server_secrets() -> None:
    settings = load_settings(FAKE_ENV)
    generator = get_upstage(settings)
    factory = next(generator)
    try:
        client = factory()
        for secret in ALL_SECRETS:
            assert secret not in client.redact(f"x {secret} y", limit=None)
    finally:
        generator.close()


# --- M3: 서명 URL·토큰 ----------------------------------------------------------------


@pytest.mark.parametrize("form", list(SIGNED_FORMS), ids=list(SIGNED_FORMS))
def test_signed_url_and_tokens_in_failed_job_are_redacted(env: Any, caplog: pytest.LogCaptureFixture, form: str) -> None:
    client, store, server = env
    analysis_id = _running(store, server)
    server.last_status = "failed"
    server.last_extra = {"error": {"message": SIGNED_FORMS[form]}}
    server.errors[("DELETE", "file")] = (500, {"error": {"message": SIGNED_FORMS[form]}})  # 로그 경로도
    with caplog.at_level(logging.INFO, logger="imask"):
        response = client.get(f"/api/py/analyses/{analysis_id}")
    assert response.json()["status"] == "failed"
    for text in (response.text, store.analyses[analysis_id]["error"], _logs(caplog)):
        assert _count(text, SIGNED_NEEDLES) == 0


@pytest.mark.parametrize("form", list(SIGNED_FORMS), ids=list(SIGNED_FORMS))
def test_signed_url_in_poll_error_is_redacted(env: Any, form: str) -> None:
    client, store, server = env
    analysis_id = _running(store, server)
    server.errors[("GET", "response")] = (502, {"error": {"message": SIGNED_FORMS[form]}})
    response = client.get(f"/api/py/analyses/{analysis_id}")
    assert response.json()["poll_error"]
    assert _count(response.text, SIGNED_NEEDLES) == 0


@pytest.mark.parametrize("form", list(SIGNED_FORMS), ids=list(SIGNED_FORMS))
def test_signed_url_in_store_exception_is_redacted(caplog: pytest.LogCaptureFixture, form: str) -> None:
    store = SupabaseStore(object(), load_settings(FAKE_ENV).secrets())
    with caplog.at_level(logging.INFO, logger="imask"):
        wrapped = store._error("서명 업로드 URL 만들기", RuntimeError(SIGNED_FORMS[form]))  # noqa: SLF001
    assert _count(wrapped.message, SIGNED_NEEDLES) == 0
    assert _count(repr(wrapped), SIGNED_NEEDLES) == 0
    assert _count(_logs(caplog), SIGNED_NEEDLES) == 0


def test_start_failure_with_signed_url_is_redacted(env: Any) -> None:
    client, store, server = env
    analysis_id = store.put()
    server.errors[("POST", "files")] = (500, {"error": {"message": SIGNED_FORMS["absolute_url"]}})
    response = client.post(f"/api/py/analyses/{analysis_id}/start")
    assert response.json()["status"] == "failed"
    assert SIGNED_URL_PLACEHOLDER in response.json()["error"]
    assert _count(response.text, SIGNED_NEEDLES) == 0


def test_create_response_keeps_signed_upload_values(env: Any) -> None:
    client, store, _ = env
    response = client.post(
        "/api/py/analyses",
        json={"filename": "a.pdf", "size": 10, "mime_type": "application/pdf"},
    )
    assert response.status_code == 201
    upload = response.json()["upload"]
    (signed,) = store.signed_uploads
    assert upload["token"] == signed["token"]  # JWT 꼴이어도 가리지 않는다(브라우저 업로드 계약)
    assert upload["signed_url"] == signed["signed_url"]
    assert upload["token"].startswith("eyJ")


# --- m2: 영구 404 정책 ----------------------------------------------------------------


def test_404_within_grace_keeps_running(env: Any) -> None:
    client, store, server = env
    analysis_id = _running(store, server, minutes_ago=1)
    server.errors[("GET", "response")] = (404, {"error": {"message": "not found"}})
    body = client.get(f"/api/py/analyses/{analysis_id}").json()
    assert body["status"] == "running"
    assert body["poll_error"].startswith("Upstage 상태를 확인하지 못했습니다")
    assert store.updates == []
    assert server.deleted == []


def test_404_after_grace_fails_and_deletes(env: Any) -> None:
    client, store, server = env
    analysis_id = _running(store, server, minutes_ago=3)
    server.errors[("GET", "response")] = (404, {"error": {"message": "not found"}})
    body = client.get(f"/api/py/analyses/{analysis_id}").json()
    assert body["status"] == "failed"
    assert body["error"] == JOB_GONE
    assert body["poll_error"] is None
    assert store.analyses[analysis_id]["error"] == JOB_GONE
    assert store.updates[-1][2] == {"expect_status": "running", "expect_no_job": False}
    assert server.deleted == ["file_up1"]


def test_404_on_full_result_after_grace_fails(env: Any) -> None:
    client, store, server = env
    analysis_id = _running(store, server, minutes_ago=3)
    server.last_status = "completed"
    original = server.handle

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.query.decode() == "include[]=all":
            return httpx.Response(404, json={"error": {"message": "gone"}})
        return original(request)

    server.handle = handle  # type: ignore[method-assign]
    body = client.get(f"/api/py/analyses/{analysis_id}").json()
    assert body["status"] == "failed"
    assert body["error"] == JOB_GONE
    assert server.deleted == ["file_up1"]


def test_404_on_full_result_within_grace_keeps_running(env: Any) -> None:
    client, store, server = env
    analysis_id = _running(store, server, minutes_ago=1)
    server.last_status = "completed"
    original = server.handle

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.query.decode() == "include[]=all":
            return httpx.Response(404, json={"error": {"message": "gone"}})
        return original(request)

    server.handle = handle  # type: ignore[method-assign]
    body = client.get(f"/api/py/analyses/{analysis_id}").json()
    assert body["status"] == "running"
    assert body["poll_error"].startswith("Upstage 결과를 받지 못했습니다")
    assert server.deleted == []


@pytest.mark.parametrize("status_code", [401, 403, 429, 500, 503])
def test_other_errors_after_grace_keep_retrying(env: Any, status_code: int) -> None:
    client, store, server = env
    analysis_id = _running(store, server, minutes_ago=30)
    server.errors[("GET", "response")] = (status_code, {"error": {"message": "nope"}})
    body = client.get(f"/api/py/analyses/{analysis_id}").json()
    assert body["status"] == "running"
    assert body["poll_error"]
    assert store.updates == []
    assert server.deleted == []


def test_404_after_grace_save_failure_keeps_file(env: Any) -> None:
    client, store, server = env
    analysis_id = _running(store, server, minutes_ago=3)
    server.errors[("GET", "response")] = (404, {"error": {"message": "not found"}})
    store.fail.add("update_analysis")
    body = client.get(f"/api/py/analyses/{analysis_id}").json()
    assert body["status"] == "running"
    assert body["poll_error"] == "분석 상태를 저장하지 못했습니다. 다음 조회에서 다시 시도합니다."
    assert server.deleted == []
