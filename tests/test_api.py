# ==========================================================================
#  FastAPI 앱(api/index.py) — 접근 코드·만들기·시작·조회 (네트워크 없음)
#  저장소는 메모리 가짜(FakeStore), Upstage 는 진짜 UpstageClient + 가짜 서버(MockTransport).
# ==========================================================================

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from api_fakes import (
    ALL_SECRETS,
    FAKE_ACCESS_CODE,
    FAKE_AGENT_ID,
    FAKE_CONFIG_ID,
    FAKE_ENV,
    FAKE_UPSTAGE_KEY,
    JPEG_BYTES,
    PNG_BYTES,
    FakeStore,
    FakeUpstageServer,
)
from fastapi.testclient import TestClient

from api.index import app, get_store, get_upstage
from imask_backend import analyses as logic
from imask_backend.files import (
    MAX_FILE_BYTES,
    MSG_BAD_EXTENSION,
    MSG_BAD_SIZE,
    MSG_BAD_TYPE,
    MSG_LONG_NAME,
)
from imask_backend.settings import get_settings, load_settings
from imask_backend.upstage import UpstageClient

CODE = {"X-Demo-Code": FAKE_ACCESS_CODE}
ANALYSIS_KEYS = {
    "id",
    "name",
    "status",
    "upstage_job_id",
    "error",
    "result",
    "created_at",
    "updated_at",
    "documents",
    "upstage_status",
    "poll_error",
}
DOCUMENT_KEYS = {"id", "filename", "size_bytes", "mime_type", "upstage_file_id", "created_at"}
LEAKY = f"Authorization: Bearer {FAKE_UPSTAGE_KEY}; bad agent {FAKE_AGENT_ID}"


def leaky(secret: str) -> str:
    """서버 비밀값 하나를 인증 문구·맨 값으로 섞은 바깥 오류 문구(4종을 하나씩 따로 넣는다)."""
    return f"Authorization: Bearer {secret}; leaked {secret}"


@dataclass
class Ctx:
    client: TestClient
    store: FakeStore
    server: FakeUpstageServer
    upstage_made: list[UpstageClient]

    def create(self, **overrides: Any) -> httpx.Response:
        body = {"name": "합성 묶음", "filename": "묶음.pdf", "size": 322053, "mime_type": "application/pdf"}
        body.update(overrides)
        return self.client.post("/api/py/analyses", json=body, headers=CODE)

    def start(self, analysis_id: str) -> httpx.Response:
        return self.client.post(f"/api/py/analyses/{analysis_id}/start", headers=CODE)

    def get(self, analysis_id: str, params: Any = None) -> httpx.Response:
        return self.client.get(f"/api/py/analyses/{analysis_id}", headers=CODE, params=params)


def _install(env: dict[str, str]) -> tuple[FakeStore, FakeUpstageServer, list[UpstageClient]]:
    settings = load_settings(env)
    store = FakeStore()
    server = FakeUpstageServer()
    made: list[UpstageClient] = []

    def upstage_override() -> Iterator[Any]:
        def factory() -> UpstageClient:
            if not made:
                made.append(
                    UpstageClient.from_settings(settings.upstage(), transport=httpx.MockTransport(server.handle))
                )
            return made[0]

        yield factory

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_upstage] = upstage_override
    return store, server, made


@pytest.fixture
def ctx() -> Iterator[Ctx]:
    store, server, made = _install(dict(FAKE_ENV))
    with TestClient(app) as client:
        yield Ctx(client, store, server, made)
    app.dependency_overrides.clear()


def _assert_clean(text: str) -> None:
    for secret in ALL_SECRETS:
        assert secret not in text
    assert "authorization" not in text.lower()
    assert "bearer" not in text.lower()


def _ago(minutes: float) -> str:
    return (datetime.now(UTC) - timedelta(minutes=minutes)).isoformat()


# --- 접근 코드 -----------------------------------------------------------------------


def test_health_needs_no_code_and_shows_only_booleans(ctx: Ctx) -> None:
    response = ctx.client.get("/api/py/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "configured": {"supabase": True, "upstage": True, "access_code": True}}
    _assert_clean(response.text)
    assert FAKE_ENV["SUPABASE_URL"] not in response.text


def test_health_without_env() -> None:
    app.dependency_overrides[get_settings] = lambda: load_settings({})
    try:
        with TestClient(app) as client:
            response = client.get("/api/py/health")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["configured"] == {"supabase": False, "upstage": False, "access_code": False}


@pytest.mark.parametrize("headers", [{}, {"X-Demo-Code": "wrong"}, {"X-Demo-Code": ""}, {"X-Demo-Code": FAKE_ACCESS_CODE + "x"}])
def test_missing_or_wrong_code_is_401(ctx: Ctx, headers: dict[str, str]) -> None:
    body = {"filename": "a.pdf", "size": 10, "mime_type": "application/pdf"}
    for response in (
        ctx.client.post("/api/py/analyses", json=body, headers=headers),
        ctx.client.post(f"/api/py/analyses/{uuid.uuid4()}/start", headers=headers),
        ctx.client.get(f"/api/py/analyses/{uuid.uuid4()}", headers=headers),
    ):
        assert response.status_code == 401
        assert response.json() == {"detail": "접근 코드가 맞지 않습니다."}
    assert ctx.store.calls == []


def test_non_ascii_code_header_is_401_not_500(ctx: Ctx) -> None:
    response = ctx.client.get(f"/api/py/analyses/{uuid.uuid4()}", headers={"X-Demo-Code": "코드".encode()})
    assert response.status_code == 401


def test_401_comes_before_body_check_and_404(ctx: Ctx) -> None:
    bad_json = ctx.client.post("/api/py/analyses", content=b"{not json", headers={"Content-Type": "application/json"})
    assert bad_json.status_code == 401
    assert ctx.client.get("/api/py/analyses/not-a-uuid").status_code == 401
    assert ctx.client.get("/api/py/analyses/x/y/z").status_code == 401
    assert ctx.client.delete(f"/api/py/analyses/{uuid.uuid4()}").status_code == 401
    # 코드가 맞으면 그때 400·404
    assert ctx.client.post("/api/py/analyses", content=b"{not json", headers={**CODE, "Content-Type": "application/json"}).status_code == 400
    assert ctx.client.get("/api/py/analyses/not-a-uuid", headers=CODE).status_code == 404
    unknown = ctx.client.get("/api/py/analyses/x/y/z", headers=CODE)
    assert unknown.status_code == 404
    assert unknown.json() == {"detail": "요청한 주소를 찾을 수 없습니다."}


@pytest.mark.parametrize("code", [None, "", "   "])
def test_server_without_access_code_is_500(code: str | None) -> None:
    env = dict(FAKE_ENV)
    if code is None:
        env.pop("DEMO_ACCESS_CODE")
    else:
        env["DEMO_ACCESS_CODE"] = code
    _install(env)
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/py/analyses/{uuid.uuid4()}", headers={"X-Demo-Code": ""})
            health = client.get("/api/py/health")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 500
    assert response.json() == {"detail": "서버에 접근 코드가 설정되지 않았습니다."}
    assert health.json()["configured"]["access_code"] is False


def test_missing_supabase_env_is_500_with_names_only() -> None:
    env = {k: v for k, v in FAKE_ENV.items() if k not in ("SUPABASE_URL", "SUPABASE_SECRET_KEY")}
    app.dependency_overrides[get_settings] = lambda: load_settings(env)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/py/analyses", json={"filename": "a.pdf", "size": 10, "mime_type": "application/pdf"}, headers=CODE
            )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 500
    assert response.json() == {"detail": "서버 설정이 빠졌습니다: SUPABASE_URL, SUPABASE_SECRET_KEY"}
    _assert_clean(response.text)


# --- 만들기 ------------------------------------------------------------------------


def test_create_returns_analysis_and_signed_upload(ctx: Ctx) -> None:
    response = ctx.create(name="  합성 묶음  ", filename="대출 서류.pdf")
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"analysis", "upload"}
    analysis = body["analysis"]
    assert set(analysis) == ANALYSIS_KEYS
    assert analysis["name"] == "합성 묶음"
    assert analysis["status"] == "queued"
    assert analysis["upstage_job_id"] is None and analysis["error"] is None and analysis["result"] is None
    assert analysis["upstage_status"] is None and analysis["poll_error"] is None
    (doc,) = analysis["documents"]
    assert set(doc) == DOCUMENT_KEYS
    assert doc["filename"] == "대출 서류.pdf"
    assert doc["size_bytes"] == 322053
    assert doc["mime_type"] == "application/pdf"
    assert doc["upstage_file_id"] is None
    assert "agent_id" not in response.text and "storage_path" not in response.text

    upload = body["upload"]
    assert upload["bucket"] == "documents"
    assert upload["path"] == f"analyses/{analysis['id']}/document.pdf"
    assert upload["token"] and upload["signed_url"].startswith("https://")

    stored = ctx.store.analyses[analysis["id"]]
    assert stored["status"] == "queued" and stored["name"] == "합성 묶음"
    (stored_doc,) = ctx.store.docs_of(analysis["id"])
    assert stored_doc["storage_path"] == upload["path"]
    assert stored_doc["filename"] == "대출 서류.pdf"
    assert ctx.server.requests == []


@pytest.mark.parametrize(
    ("filename", "expected"),
    [("iMASK_smoke_bundle.pdf", "iMASK_smoke_bundle.pdf"), ("김 2024 묶음.PDF", "2024.pdf"), ("C:\\tmp\\scan 1.pdf", "scan_1.pdf")],
)
def test_create_storage_path_uses_safe_name(ctx: Ctx, filename: str, expected: str) -> None:
    body = ctx.create(filename=filename).json()
    assert body["upload"]["path"].endswith("/" + expected)
    assert body["analysis"]["documents"][0]["filename"] == filename.split("\\")[-1]


def test_create_name_defaults_to_filename(ctx: Ctx) -> None:
    for name in (None, "", "   "):
        body = {"filename": "묶음.pdf", "size": 10, "mime_type": "application/pdf"}
        if name is not None:
            body["name"] = name
        response = ctx.client.post("/api/py/analyses", json=body, headers=CODE)
        assert response.status_code == 201
        assert response.json()["analysis"]["name"] == "묶음.pdf"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"mime_type": "image/gif", "filename": "a.gif"}, MSG_BAD_TYPE),
        ({"mime_type": "application/pdf", "filename": "a.png"}, MSG_BAD_EXTENSION),
        ({"mime_type": "image/jpeg", "filename": "a.png"}, MSG_BAD_EXTENSION),
        ({"size": 0}, MSG_BAD_SIZE),
        ({"size": MAX_FILE_BYTES + 1}, MSG_BAD_SIZE),
        ({"name": "가" * 61}, MSG_LONG_NAME),
        ({"filename": "dir/"}, "파일 이름이 비었습니다."),
        ({"filename": "x" * 197 + ".pdf"}, "파일 이름은 200자 이하여야 합니다."),
    ],
)
def test_create_validation_messages(ctx: Ctx, overrides: dict[str, Any], message: str) -> None:
    response = ctx.create(**overrides)
    assert response.status_code == 400
    assert response.json() == {"detail": message}
    assert ctx.store.analyses == {}


@pytest.mark.parametrize(
    "body",
    [
        {"filename": "a.pdf", "size": "10", "mime_type": "application/pdf"},
        {"filename": "a.pdf", "size": 10.5, "mime_type": "application/pdf"},
        {"filename": "a.pdf", "size": True, "mime_type": "application/pdf"},
        {"filename": 5, "size": 10, "mime_type": "application/pdf"},
        {"filename": "a.pdf", "size": 10},
        {"name": 3, "filename": "a.pdf", "size": 10, "mime_type": "application/pdf"},
        [1, 2],
    ],
)
def test_create_bad_body_shape_is_400(ctx: Ctx, body: Any) -> None:
    response = ctx.client.post("/api/py/analyses", json=body, headers=CODE)
    assert response.status_code == 400
    assert response.json() == {"detail": "요청 형식이 올바르지 않습니다."}


def test_create_accepts_png_jpeg_and_20mb(ctx: Ctx) -> None:
    assert ctx.create(filename="a.png", mime_type="image/png").status_code == 201
    assert ctx.create(filename="a.JPG", mime_type="image/jpeg").status_code == 201
    assert ctx.create(filename="a.jpeg", mime_type="image/jpeg", size=MAX_FILE_BYTES).status_code == 201


@pytest.mark.parametrize("failing", ["insert_document", "create_signed_upload_url"])
def test_create_cleans_up_rows_on_failure(ctx: Ctx, failing: str) -> None:
    ctx.store.fail.add(failing)
    response = ctx.create()
    assert response.status_code == 502
    assert response.json() == {"detail": "분석을 준비하지 못했습니다. 잠시 후 다시 시도해 주세요."}
    assert ctx.store.analyses == {}
    assert ctx.store.documents == {}
    assert "delete_analysis" in ctx.store.calls


def test_create_insert_analysis_failure_is_502(ctx: Ctx) -> None:
    ctx.store.fail.add("insert_analysis")
    response = ctx.create()
    assert response.status_code == 502
    assert ctx.store.analyses == {}


# --- 시작 --------------------------------------------------------------------------


def test_start_uploads_creates_job_and_saves_ids(ctx: Ctx) -> None:
    analysis_id = ctx.store.put(filename="대출 서류.pdf", storage_name="document.pdf")
    response = ctx.start(analysis_id)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == ANALYSIS_KEYS
    assert body["status"] == "running"
    assert body["upstage_job_id"] == "job_fake2"
    assert body["documents"][0]["upstage_file_id"] == "file_fake1"
    assert "agent_id" not in body and FAKE_AGENT_ID not in response.text

    # Upstage: 파일 올리기(안전한 이름, 저장된 내용) → 작업 만들기(config_id·include all)
    (upload,) = ctx.server.calls("POST", "files")
    assert b'filename="document.pdf"' in upload.content
    assert b"%PDF-1.7" in upload.content
    assert b"user_data" in upload.content
    (job_body,) = ctx.server.job_bodies
    assert job_body["model"] == FAKE_AGENT_ID
    assert job_body["config_id"] == FAKE_CONFIG_ID
    assert job_body["include"] == ["all"]
    assert job_body["input"] == [{"role": "user", "content": [{"type": "input_file", "file_id": "file_fake1"}]}]
    assert ctx.server.calls("DELETE") == []
    assert ctx.server.calls("GET") == []  # 완료를 기다리지 않는다

    stored = ctx.store.analyses[analysis_id]
    assert stored["status"] == "running"
    assert stored["agent_id"] == FAKE_AGENT_ID  # DB 에는 저장한다(식별자)
    assert stored["upstage_job_id"] == "job_fake2"
    # 선점(queued 조건) → job id 저장(running·job 없음 조건)
    assert ctx.store.updates[0][2] == {"expect_status": "queued", "expect_no_job": False}
    assert ctx.store.updates[1][2] == {"expect_status": "running", "expect_no_job": True}


def test_start_sends_png_and_jpeg(ctx: Ctx) -> None:
    png = ctx.store.put(mime_type="image/png", storage_name="scan.png", content=PNG_BYTES)
    jpeg = ctx.store.put(mime_type="image/jpeg", storage_name="scan.jpg", content=JPEG_BYTES)
    assert ctx.start(png).json()["status"] == "running"
    assert ctx.start(jpeg).json()["status"] == "running"
    types = [r.content for r in ctx.server.calls("POST", "files")]
    assert b"image/png" in types[0] and b"image/jpeg" in types[1]


@pytest.mark.parametrize("analysis_id", ["not-a-uuid", str(uuid.uuid4())])
def test_start_404(ctx: Ctx, analysis_id: str) -> None:
    response = ctx.start(analysis_id)
    assert response.status_code == 404
    assert response.json() == {"detail": "분석 건을 찾을 수 없습니다."}


@pytest.mark.parametrize("status", ["running", "done", "failed", "partial"])
def test_start_409_when_not_queued(ctx: Ctx, status: str) -> None:
    analysis_id = ctx.store.put(status=status)
    response = ctx.start(analysis_id)
    assert response.status_code == 409
    assert response.json() == {"detail": "이미 시작한 분석입니다."}
    assert ctx.server.requests == []
    assert ctx.store.updates == []


def test_start_409_when_claim_loses_race(ctx: Ctx) -> None:
    analysis_id = ctx.store.put()

    def other_request_claims(aid: str, _values: Any) -> None:
        ctx.store.analyses[aid]["status"] = "running"

    ctx.store.before_update = other_request_claims
    response = ctx.start(analysis_id)
    assert response.status_code == 409
    assert ctx.server.requests == []


def test_start_twice_second_is_409(ctx: Ctx) -> None:
    analysis_id = ctx.store.put()
    assert ctx.start(analysis_id).status_code == 200
    assert ctx.start(analysis_id).status_code == 409
    assert len(ctx.server.job_bodies) == 1


def test_start_without_upstage_config_is_500_and_stays_queued() -> None:
    env = {k: v for k, v in FAKE_ENV.items() if k != "UPSTAGE_CONFIG_ID"}
    store, server, _ = _install(env)
    app.dependency_overrides.pop(get_upstage)  # 진짜 의존성(설정에서 클라이언트를 만든다)
    analysis_id = store.put()
    try:
        with TestClient(app) as client:
            response = client.post(f"/api/py/analyses/{analysis_id}/start", headers=CODE)
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 500
    assert response.json() == {"detail": "서버 설정이 빠졌습니다: UPSTAGE_CONFIG_ID"}
    assert store.analyses[analysis_id]["status"] == "queued"
    assert store.updates == []


def _assert_failed(ctx: Ctx, response: httpx.Response, analysis_id: str, message: str) -> dict[str, Any]:
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"] == message
    assert ctx.store.analyses[analysis_id]["status"] == "failed"
    assert ctx.store.analyses[analysis_id]["error"] == message
    _assert_clean(response.text)
    return body


def test_start_file_missing_fails_without_upstage(ctx: Ctx) -> None:
    analysis_id = ctx.store.put(content=None)
    response = ctx.start(analysis_id)
    _assert_failed(ctx, response, analysis_id, "업로드된 파일을 찾을 수 없습니다. 파일을 다시 올려 주세요.")
    assert ctx.server.requests == []


@pytest.mark.parametrize(
    ("mime", "content"),
    [("application/pdf", b"not a pdf"), ("image/png", JPEG_BYTES), ("image/jpeg", PNG_BYTES), ("application/pdf", b"")],
)
def test_start_content_mismatch_fails_without_upstage(ctx: Ctx, mime: str, content: bytes) -> None:
    analysis_id = ctx.store.put(mime_type=mime, content=content)
    response = ctx.start(analysis_id)
    _assert_failed(ctx, response, analysis_id, "파일 내용이 PDF·PNG·JPEG 형식이 아닙니다.")
    assert ctx.server.requests == []


def test_start_too_large_content_fails(ctx: Ctx) -> None:
    analysis_id = ctx.store.put(content=b"%PDF-" + b"0" * MAX_FILE_BYTES)
    response = ctx.start(analysis_id)
    _assert_failed(ctx, response, analysis_id, "업로드된 파일이 20MB 를 넘습니다.")
    assert ctx.server.requests == []


def test_start_download_error_fails(ctx: Ctx) -> None:
    analysis_id = ctx.store.put()
    ctx.store.fail.add("download")
    response = ctx.start(analysis_id)
    _assert_failed(ctx, response, analysis_id, "업로드된 파일을 읽지 못했습니다. 새 분석으로 다시 올려 주세요.")


@pytest.mark.parametrize("secret", ALL_SECRETS, ids=["upstage_key", "agent_id", "supabase_key", "access_code"])
def test_start_upload_failure_is_failed_row_with_redacted_reason(ctx: Ctx, secret: str) -> None:
    analysis_id = ctx.store.put()
    ctx.server.errors[("POST", "files")] = (500, {"error": {"message": leaky(secret)}})
    response = ctx.start(analysis_id)
    body = response.json()
    assert response.status_code == 200 and body["status"] == "failed"
    assert body["error"].startswith("Upstage 분석을 시작하지 못했습니다: 파일 올리기: HTTP 500")
    _assert_clean(response.text)
    _assert_clean(ctx.store.analyses[analysis_id]["error"])
    assert ctx.server.job_bodies == []


def test_start_upload_connection_error(ctx: Ctx) -> None:
    analysis_id = ctx.store.put()
    ctx.server.errors[("POST", "files")] = httpx.ConnectError(f"boom {FAKE_UPSTAGE_KEY}")
    body = ctx.start(analysis_id).json()
    assert body["status"] == "failed"
    assert body["error"] == "Upstage 분석을 시작하지 못했습니다: 파일 올리기: Upstage 연결 오류(ConnectError)"


def test_start_create_job_failure_deletes_uploaded_file(ctx: Ctx) -> None:
    analysis_id = ctx.store.put()
    ctx.server.errors[("POST", "responses")] = (400, {"error": {"message": f"bad config for {FAKE_AGENT_ID}"}})
    response = ctx.start(analysis_id)
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"] == "Upstage 분석을 시작하지 못했습니다: 작업 만들기: HTTP 400 — bad config for <UPSTAGE_AGENT_ID>"
    assert ctx.server.deleted == ["file_fake1"]
    assert ctx.store.analyses[analysis_id]["upstage_job_id"] is None


def test_start_job_already_failed_is_failed(ctx: Ctx) -> None:
    analysis_id = ctx.store.put()
    ctx.server.create_status = "failed"
    ctx.server.create_extra = {"error": {"message": "quota exceeded"}}
    body = ctx.start(analysis_id).json()
    assert body["status"] == "failed"
    assert body["error"] == "Upstage 분석을 시작하지 못했습니다: quota exceeded"
    assert ctx.server.deleted == ["file_fake1"]


def test_start_job_already_completed_stays_running(ctx: Ctx) -> None:
    analysis_id = ctx.store.put()
    ctx.server.create_status = "completed"
    body = ctx.start(analysis_id).json()
    assert body["status"] == "running" and body["upstage_job_id"]
    assert ctx.server.deleted == []


def test_start_document_update_failure_deletes_file(ctx: Ctx) -> None:
    analysis_id = ctx.store.put()
    ctx.store.fail.add("update_document")
    body = ctx.start(analysis_id).json()
    assert body["status"] == "failed"
    assert body["error"] == "분석 시작 정보를 저장하지 못했습니다. 새 분석으로 다시 올려 주세요."
    assert ctx.server.deleted == ["file_fake1"]
    assert ctx.server.job_bodies == []


def test_start_failure_that_cannot_be_recorded_is_502(ctx: Ctx) -> None:
    analysis_id = ctx.store.put(content=None)
    # 선점(첫 갱신)은 되고, 그다음 갱신(실패 기록)부터 실패
    ctx.store.before_update = lambda *_: ctx.store.fail.add("update_analysis")
    response = ctx.start(analysis_id)
    assert response.status_code == 502
    assert response.json() == {"detail": "분석 시작 결과를 저장하지 못했습니다. 잠시 후 다시 시도해 주세요."}
    assert ctx.store.analyses[analysis_id]["status"] == "running"  # 5분 뒤 조회가 실패로 바꾼다


def test_start_unexpected_error_becomes_failed_row(ctx: Ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    analysis_id = ctx.store.put()

    def broken(_path: str) -> bytes:
        raise RuntimeError(f"unexpected {FAKE_UPSTAGE_KEY}")

    monkeypatch.setattr(ctx.store, "download", broken)
    response = ctx.start(analysis_id)
    _assert_failed(ctx, response, analysis_id, "분석을 시작하는 중 서버 오류가 발생했습니다. 새 분석으로 다시 올려 주세요.")


def test_start_job_save_skipped_when_row_changed(ctx: Ctx) -> None:
    analysis_id = ctx.store.put()
    calls = {"n": 0}
    # 두 번째 갱신(job id 저장) 직전에 다른 조회가 이 분석을 실패로 바꾼 경우
    original = ctx.store.update_analysis

    def update(aid: str, values: Any, **kw: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 2:
            ctx.store.analyses[aid].update(status="failed", error="분석 시작이 끝나지 않았습니다. 새 분석으로 다시 올려 주세요.")
        return original(aid, values, **kw)

    ctx.store.update_analysis = update  # type: ignore[method-assign]
    body = ctx.start(analysis_id).json()
    assert body["status"] == "failed"
    assert ctx.store.analyses[analysis_id]["upstage_job_id"] is None
    assert ctx.server.deleted == ["file_fake1"]


# --- 조회 --------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["queued", "done", "failed", "partial"])
def test_get_non_running_returns_stored_without_upstage(ctx: Ctx, status: str) -> None:
    stored_result = {"format": "imask-upstage-v1", "summary": {"risk_level": "상"}, "stages": [], "response": {"big": 1}}
    analysis_id = ctx.store.put(status=status, job_id="job_x" if status != "queued" else None, result=stored_result)
    response = ctx.get(analysis_id)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == ANALYSIS_KEYS
    assert body["status"] == status
    assert body["upstage_status"] is None and body["poll_error"] is None
    # 응답 모양이 바뀜(T1 findings-api): stages·response 는 빼고 화면용 documents·findings·overall 을 더한다.
    # 원본(response)에 단계가 없으므로 셋 다 빈 값이다(저장된 summary 는 그대로 옮긴다).
    assert body["result"] == {
        "format": "imask-upstage-v1",
        "summary": {"risk_level": "상"},
        "documents": [],
        "findings": [],
        "overall": {"level": None, "text": "", "next_stage": None, "next_text": ""},
    }
    # ?include=stages 면 저장된 stages 를 그대로 넣는다
    with_stages = ctx.get(analysis_id, params={"include": "stages"}).json()["result"]
    assert with_stages["stages"] == []
    assert "response" not in with_stages
    assert ctx.server.requests == []
    assert ctx.upstage_made == []  # 클라이언트도 만들지 않는다
    assert ctx.store.updates == []


@pytest.mark.parametrize("analysis_id", ["not-a-uuid", str(uuid.uuid4())])
def test_get_404(ctx: Ctx, analysis_id: str) -> None:
    response = ctx.get(analysis_id)
    assert response.status_code == 404
    assert response.json() == {"detail": "분석 건을 찾을 수 없습니다."}


def _running(ctx: Ctx, **kw: Any) -> str:
    ctx.server.files["file_up1"] = ("document.pdf", b"")
    return ctx.store.put(status="running", job_id="job_up1", upstage_file_id="file_up1", **kw)


@pytest.mark.parametrize("status", ["queued", "in_progress"])
def test_get_in_progress_keeps_row(ctx: Ctx, status: str) -> None:
    analysis_id = _running(ctx)
    before = dict(ctx.store.analyses[analysis_id])
    ctx.server.last_status = status
    body = ctx.get(analysis_id).json()
    assert body["status"] == "running"
    assert body["upstage_status"] == status
    assert body["poll_error"] is None
    assert ctx.store.updates == []
    assert ctx.store.analyses[analysis_id] == before  # updated_at 도 그대로
    (poll,) = ctx.server.calls("GET", "response")
    assert poll.url.query.decode() == "include[]=last"
    assert ctx.server.deleted == []


def test_get_completed_saves_result_and_deletes_file(ctx: Ctx, caplog: pytest.LogCaptureFixture) -> None:
    analysis_id = _running(ctx)
    ctx.server.last_status = "completed"
    with caplog.at_level(logging.INFO, logger="imask"):
        response = ctx.get(analysis_id)
    body = response.json()
    assert body["status"] == "done"
    assert body["error"] is None
    assert body["upstage_status"] == "completed"
    # API 응답: response(원본)·stages 없음, 화면용 documents·findings·overall 있음(T1 findings-api)
    result = body["result"]
    assert set(result) == {"format", "job", "summary", "documents", "findings", "overall"}
    assert result["format"] == "imask-upstage-v1"
    assert result["job"]["id"] == "job_up1"
    assert result["job"]["config_id"] == FAKE_CONFIG_ID
    summary = result["summary"]
    assert summary["document_count"] == 6
    assert summary["extracted_document_count"] == 5
    assert summary["risk_level"] == "상"
    assert summary["final_stage"] == "권장_조치"
    assert summary["other_document_count"] == 1
    assert [d["type"] for d in result["documents"]] == summary["document_types"]
    assert result["overall"]["level"] == "상" and result["overall"]["next_stage"] == "권장_조치"
    _assert_clean(response.text)
    # 단계별 결과는 ?include=stages 일 때만(이미 done 이라 Upstage 를 다시 부르지 않는다)
    staged = ctx.get(analysis_id, params={"include": "stages"}).json()["result"]
    assert staged["stages"] and staged["stages"][0]["name"] == "step_1_parse"
    assert "response" not in staged

    # DB: response 저장, 최상위 model(에이전트 id) 없음
    stored = ctx.store.analyses[analysis_id]
    assert stored["status"] == "done"
    assert set(stored["result"]) == {"format", "job", "summary", "stages", "response"}
    assert "model" not in stored["result"]["response"]
    assert stored["result"]["response"]["output"]
    assert FAKE_AGENT_ID not in json.dumps(stored["result"], ensure_ascii=False)
    assert ctx.store.updates[-1][2] == {"expect_status": "running", "expect_no_job": False}

    # Upstage: last → all → 파일 삭제
    polls = [r.url.query.decode() for r in ctx.server.calls("GET", "response")]
    assert polls == ["include[]=last", "include[]=all"]
    assert ctx.server.deleted == ["file_up1"]

    # 로그: 단계 이름만
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "Instruct - 위험도_판정" in logged
    _assert_clean(logged)

    # 다음 조회는 Upstage 를 부르지 않는다
    count = len(ctx.server.requests)
    assert ctx.get(analysis_id).json()["status"] == "done"
    assert len(ctx.server.requests) == count


def test_get_completed_with_odd_shape_is_still_done(ctx: Ctx) -> None:
    analysis_id = _running(ctx)
    ctx.server.last_status = "completed"
    ctx.server.full_response = {"object": "response", "status": "completed", "output": [{"weird": True}]}
    body = ctx.get(analysis_id).json()
    assert body["status"] == "done"
    assert body["result"]["summary"]["document_count"] is None
    assert body["result"]["summary"]["risk_level"] is None


def test_get_completed_result_with_secret_is_redacted(ctx: Ctx) -> None:
    analysis_id = _running(ctx)
    ctx.server.last_status = "completed"
    ctx.server.full_response = {
        **ctx.server.full_response,
        "metadata": {"source": f"agent {FAKE_AGENT_ID} key {FAKE_UPSTAGE_KEY}"},
    }
    ctx.get(analysis_id)
    stored = json.dumps(ctx.store.analyses[analysis_id]["result"], ensure_ascii=False)
    for secret in ALL_SECRETS:
        assert secret not in stored
    assert ctx.store.analyses[analysis_id]["result"]["summary"]["document_count"] == 6


@pytest.mark.parametrize(
    ("status", "extra", "message"),
    [
        ("failed", {"error": {"message": "document unreadable"}}, "Upstage 분석이 실패했습니다: document unreadable"),
        ("failed", {"error": {"code": "server_error"}}, "Upstage 분석이 실패했습니다: server_error"),
        ("incomplete", {"incomplete_details": {"reason": "max_output_tokens"}}, "Upstage 분석이 실패했습니다: max_output_tokens"),
        ("cancelled", {}, "Upstage 분석이 실패했습니다: cancelled"),
        ("failed", {}, "Upstage 분석이 실패했습니다: failed"),
        ("weird_status", {}, "Upstage 분석이 실패했습니다: weird_status"),
    ],
)
def test_get_failed_job_marks_failed_and_deletes_file(ctx: Ctx, status: str, extra: dict[str, Any], message: str) -> None:
    analysis_id = _running(ctx)
    ctx.server.last_status = status
    ctx.server.last_extra = extra
    body = ctx.get(analysis_id).json()
    assert body["status"] == "failed"
    assert body["error"] == message
    assert body["upstage_status"] == status
    assert ctx.store.analyses[analysis_id]["error"] == message
    assert ctx.server.deleted == ["file_up1"]
    assert [r.url.query.decode() for r in ctx.server.calls("GET", "response")] == ["include[]=last"]


@pytest.mark.parametrize("secret", ALL_SECRETS, ids=["upstage_key", "agent_id", "supabase_key", "access_code"])
def test_get_failed_job_reason_is_redacted(ctx: Ctx, secret: str) -> None:
    analysis_id = _running(ctx)
    ctx.server.last_status = "failed"
    ctx.server.last_extra = {"error": {"message": leaky(secret)}}
    response = ctx.get(analysis_id)
    assert response.json()["status"] == "failed"
    _assert_clean(response.text)
    _assert_clean(ctx.store.analyses[analysis_id]["error"])


@pytest.mark.parametrize(
    "error",
    [
        (503, {"error": {"message": "busy"}}),
        (429, {"error": {"message": "slow down"}}),
        (401, {"error": {"message": LEAKY}}),
        (403, {"error": {"message": "forbidden"}}),
        (404, {"error": {"message": "job not found yet"}}),  # job id 저장 직후(2분 전)의 404 는 다시 시도
        httpx.ConnectError("down"),
        httpx.ReadTimeout("slow"),
    ],
)
def test_get_poll_error_keeps_state(ctx: Ctx, error: Any) -> None:
    analysis_id = _running(ctx)
    before = dict(ctx.store.analyses[analysis_id])
    ctx.server.errors[("GET", "response")] = error
    response = ctx.get(analysis_id)
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "running"
    assert body["upstage_status"] is None
    assert body["poll_error"].startswith("Upstage 상태를 확인하지 못했습니다: 작업 조회")
    _assert_clean(response.text)
    assert ctx.store.analyses[analysis_id] == before
    assert ctx.server.deleted == []


def test_get_full_result_fetch_error_keeps_state(ctx: Ctx) -> None:
    analysis_id = _running(ctx)
    ctx.server.last_status = "completed"
    original = ctx.server.handle

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.query.decode() == "include[]=all":
            return httpx.Response(502, json={"error": {"message": "gateway"}})
        return original(request)

    ctx.server.handle = handle  # type: ignore[method-assign]
    # 이미 만든 클라이언트가 없으므로 새 처리기가 쓰인다
    body = ctx.get(analysis_id).json()
    assert body["status"] == "running"
    assert body["upstage_status"] == "completed"
    assert body["poll_error"] == "Upstage 결과를 받지 못했습니다: 작업 조회: HTTP 502 — gateway"
    assert ctx.store.updates == []
    assert ctx.server.deleted == []


def test_get_missing_status_is_poll_error(ctx: Ctx) -> None:
    analysis_id = _running(ctx)
    ctx.server.last_status = None
    body = ctx.get(analysis_id).json()
    assert body["status"] == "running"
    assert body["poll_error"] == "Upstage 응답에 상태가 없습니다."
    assert ctx.store.updates == []


def test_get_save_failure_is_poll_error(ctx: Ctx) -> None:
    analysis_id = _running(ctx)
    ctx.server.last_status = "completed"
    ctx.store.fail.add("update_analysis")
    body = ctx.get(analysis_id).json()
    assert body["status"] == "running"
    assert body["poll_error"] == "분석 상태를 저장하지 못했습니다. 다음 조회에서 다시 시도합니다."
    assert ctx.server.deleted == []  # 다음 조회에서 다시 처리한다


def test_get_conditional_update_lost_returns_reread_row(ctx: Ctx) -> None:
    analysis_id = _running(ctx)
    ctx.server.last_status = "completed"
    winner = {"format": "imask-upstage-v1", "summary": {"risk_level": "상"}, "stages": ["first"], "response": {}}

    def other_poll_finishes_first(aid: str, _values: Any) -> None:
        ctx.store.analyses[aid].update(status="done", result=winner)
        ctx.server.deleted.append("file_up1")  # 다른 조회가 이미 지움 → 이번 삭제는 404

    ctx.store.before_update = other_poll_finishes_first
    response = ctx.get(analysis_id)
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "done"
    assert body["result"]["summary"] == {"risk_level": "상"}  # 먼저 반영된 결과 그대로
    assert ctx.get(analysis_id, params={"include": "stages"}).json()["result"]["stages"] == ["first"]
    assert ctx.store.analyses[analysis_id]["result"] == winner
    assert ctx.server.calls("DELETE")  # 두 번째 삭제는 404 → 성공으로 본다


def test_get_running_without_job_recent_is_unchanged(ctx: Ctx) -> None:
    analysis_id = ctx.store.put(status="running", updated_at=_ago(4))
    body = ctx.get(analysis_id).json()
    assert body["status"] == "running"
    assert ctx.store.updates == []
    assert ctx.server.requests == []


def test_get_running_without_job_stale_fails_and_cleans_up(ctx: Ctx) -> None:
    ctx.server.files["file_orphan"] = ("document.pdf", b"")
    analysis_id = ctx.store.put(status="running", updated_at=_ago(6), upstage_file_id="file_orphan")
    body = ctx.get(analysis_id).json()
    assert body["status"] == "failed"
    assert body["error"] == "분석 시작이 끝나지 않았습니다. 새 분석으로 다시 올려 주세요."
    assert ctx.store.updates[-1][2] == {"expect_status": "running", "expect_no_job": True}
    assert ctx.server.calls("GET") == []
    assert ctx.server.deleted == ["file_orphan"]


def test_get_store_read_failure_is_502(ctx: Ctx) -> None:
    analysis_id = _running(ctx)
    ctx.store.fail.add("get_analysis")
    response = ctx.get(analysis_id)
    assert response.status_code == 502
    assert response.json() == {"detail": "데이터 저장소에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요."}


def test_unexpected_error_is_500_json_and_log_is_redacted(ctx: Ctx, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    def broken(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError(f"broken with {FAKE_UPSTAGE_KEY} and {FAKE_ACCESS_CODE}")

    monkeypatch.setattr(logic, "_load", broken)
    with caplog.at_level(logging.ERROR, logger="imask"):
        response = ctx.get(str(uuid.uuid4()))
    assert response.status_code == 500
    assert response.json() == {"detail": "서버 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."}
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "RuntimeError" in logged
    _assert_clean(logged)


# --- 끝까지 한 번 -------------------------------------------------------------------


def test_full_flow_queued_running_done(ctx: Ctx) -> None:
    created = ctx.create(filename="iMASK_smoke_bundle.pdf").json()
    analysis_id = created["analysis"]["id"]
    ctx.store.objects[created["upload"]["path"]] = b"%PDF-1.7 synthetic"  # 브라우저가 서명 URL 로 올린 것
    assert ctx.start(analysis_id).json()["status"] == "running"
    ctx.server.last_status = "in_progress"
    assert ctx.get(analysis_id).json()["upstage_status"] == "in_progress"
    ctx.server.last_status = "completed"
    done = ctx.get(analysis_id).json()
    assert done["status"] == "done"
    assert done["result"]["summary"]["document_count"] == 6
    assert ctx.server.deleted == [done["documents"][0]["upstage_file_id"]]
