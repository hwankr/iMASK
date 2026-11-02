# ==========================================================================
#  imask_backend.store.SupabaseStore — 진짜 supabase-py(2.33) 위에서 요청 모양을 확인한다.
#  supabase 클라이언트의 httpx 세션 전송층을 MockTransport 로 바꿔 네트워크 없이 본다:
#  조건부 갱신의 쿼리(id·status·upstage_job_id=is.null), 서명 업로드 URL 반환 키,
#  Storage '파일 없음'(HTTP 400 + 본문 statusCode 404) → None, 오류 문구 가림.
# ==========================================================================

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from api_fakes import FAKE_ENV, FAKE_SUPABASE_KEY

from imask_backend.settings import load_settings
from imask_backend.store import StoreError, SupabaseStore

BASE = FAKE_ENV["SUPABASE_URL"]

# supabase-py 2.33 이 내부에서 스스로 deprecated 인자(timeout·verify)를 넘겨 나는 경고 — 우리 코드와 무관
pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning:supabase._sync.client")


class Recorder:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.reply: Any = None  # (status, json) 또는 callable(request) -> Response

    def handle(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.requests.append(request)
        if callable(self.reply):
            return self.reply(request)
        status, body = self.reply if self.reply is not None else (200, [])
        if isinstance(body, bytes):
            return httpx.Response(status, content=body)
        return httpx.Response(status, json=body)


@pytest.fixture
def mocked() -> tuple[SupabaseStore, Recorder]:
    store = SupabaseStore.from_settings(load_settings(FAKE_ENV))
    recorder = Recorder()
    transport = httpx.MockTransport(recorder.handle)
    client = store._client  # noqa: SLF001 — 테스트에서만 전송층을 바꾼다
    client.postgrest.session._transport = transport
    client.storage.session._transport = transport
    return store, recorder


def _query(request: httpx.Request) -> str:
    return httpx.QueryParams(request.url.query).__str__()


def test_claim_is_conditional_patch(mocked: tuple[SupabaseStore, Recorder]) -> None:
    store, rec = mocked
    rec.reply = (200, [{"id": "a1", "status": "running"}])
    assert store.claim_analysis("a1") == {"id": "a1", "status": "running"}
    (req,) = rec.requests
    assert req.method == "PATCH"
    assert req.url.path == "/rest/v1/analyses"
    params = dict(httpx.QueryParams(req.url.query))
    assert params == {"id": "eq.a1", "status": "eq.queued"}
    assert json.loads(req.content) == {"status": "running"}
    assert req.headers["apikey"] == FAKE_SUPABASE_KEY
    assert "return=representation" in req.headers.get("prefer", "")


def test_conditional_update_with_no_rows_is_none(mocked: tuple[SupabaseStore, Recorder]) -> None:
    store, rec = mocked
    rec.reply = (200, [])
    assert store.update_analysis("a1", {"upstage_job_id": "job_1"}, expect_status="running", expect_no_job=True) is None
    params = dict(httpx.QueryParams(rec.requests[0].url.query))
    assert params == {"id": "eq.a1", "status": "eq.running", "upstage_job_id": "is.null"}


def test_get_analysis_embeds_documents_sorted(mocked: tuple[SupabaseStore, Recorder]) -> None:
    store, rec = mocked
    rec.reply = (
        200,
        [
            {
                "id": "a1",
                "status": "queued",
                "documents": [
                    {"id": "d2", "created_at": "2026-11-02T10:00:01+00:00"},
                    {"id": "d1", "created_at": "2026-11-02T10:00:00+00:00"},
                ],
            }
        ],
    )
    row = store.get_analysis("a1")
    assert row is not None
    assert [d["id"] for d in row["documents"]] == ["d1", "d2"]
    params = dict(httpx.QueryParams(rec.requests[0].url.query))
    assert params["id"] == "eq.a1"
    assert "documents(" in params["select"] and "storage_path" in params["select"]


def test_get_analysis_missing_is_none(mocked: tuple[SupabaseStore, Recorder]) -> None:
    store, rec = mocked
    rec.reply = (200, [])
    assert store.get_analysis("a1") is None


def test_insert_and_delete(mocked: tuple[SupabaseStore, Recorder]) -> None:
    store, rec = mocked
    rec.reply = (201, [{"id": "a1", "name": "n", "status": "queued"}])
    assert store.insert_analysis("n")["id"] == "a1"
    assert rec.requests[0].method == "POST"
    assert json.loads(rec.requests[0].content) == {"name": "n", "status": "queued"}
    rec.reply = (200, [])
    store.delete_analysis("a1")
    assert rec.requests[1].method == "DELETE"
    assert dict(httpx.QueryParams(rec.requests[1].url.query)) == {"id": "eq.a1"}


def test_signed_upload_url_keys(mocked: tuple[SupabaseStore, Recorder]) -> None:
    store, rec = mocked
    rec.reply = (200, {"url": "/object/upload/sign/documents/analyses/a1/document.pdf?token=tok123"})
    signed = store.create_signed_upload_url("analyses/a1/document.pdf")
    assert signed["token"] == "tok123"
    assert signed["path"] == "analyses/a1/document.pdf"
    assert signed["signed_url"].startswith(f"{BASE}/storage/v1/object/upload/sign/documents/analyses/a1/document.pdf")
    assert rec.requests[0].url.path == "/storage/v1/object/upload/sign/documents/analyses/a1/document.pdf"


def test_download_returns_bytes_and_none_when_missing(mocked: tuple[SupabaseStore, Recorder]) -> None:
    store, rec = mocked
    rec.reply = (200, b"%PDF-1.7 fake")
    assert store.download("analyses/a1/document.pdf") == b"%PDF-1.7 fake"
    # Storage 는 없는 파일을 HTTP 400 + 본문 statusCode "404" 로 알린다
    rec.reply = (400, {"statusCode": "404", "error": "not_found", "message": "Object not found"})
    assert store.download("analyses/a1/missing.pdf") is None


def test_errors_become_redacted_store_error(mocked: tuple[SupabaseStore, Recorder]) -> None:
    store, rec = mocked
    rec.reply = (500, {"message": f"boom key={FAKE_SUPABASE_KEY}", "code": "XX000", "details": None, "hint": None})
    with pytest.raises(StoreError) as info:
        store.get_analysis("a1")
    assert FAKE_SUPABASE_KEY not in info.value.message
    assert FAKE_SUPABASE_KEY not in repr(info.value)

    rec.reply = (400, {"statusCode": "403", "error": "Unauthorized", "message": f"bad {FAKE_SUPABASE_KEY}"})
    with pytest.raises(StoreError) as info:
        store.download("analyses/a1/document.pdf")
    assert FAKE_SUPABASE_KEY not in info.value.message


def test_connection_error_is_store_error(mocked: tuple[SupabaseStore, Recorder]) -> None:
    store, rec = mocked

    def down(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    rec.reply = down
    with pytest.raises(StoreError):
        store.update_document("d1", {"upstage_file_id": "f"})
    with pytest.raises(StoreError):
        store.create_signed_upload_url("analyses/a1/document.pdf")
