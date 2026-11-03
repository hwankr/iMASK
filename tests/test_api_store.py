# ==========================================================================
#  imask_backend.store.SupabaseStore — 진짜 supabase-py(2.33) 위에서 요청 모양을 확인한다.
#  supabase 클라이언트의 httpx 세션 전송층을 MockTransport 로 바꿔 네트워크 없이 본다:
#  조건부 갱신의 쿼리(id·status·upstage_job_id=is.null), 서명 업로드 URL 반환 키,
#  Storage '파일 없음'(HTTP 400 + 본문 statusCode 404) → None, 오류 문구 가림.
#  서명 다운로드 URL(T1 findings-api): 진짜 storage3 의 요청·반환(절대 주소), 가짜 storage 클라이언트로
#  반환 키 변형(signedURL·signedUrl·signed_url)·상대 경로·없는 객체 → None·그 밖 오류 → 가린 StoreError.
#  검토 행(T1 review-actions): get_review(select·analysis_id·limit), insert_review(on_conflict=analysis_id +
#  resolution=ignore-duplicates, 빈 응답 → None), update_review(version 조건, 바뀐 행 없음 → None), 오류 → 가린 StoreError.
# ==========================================================================

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from api_fakes import FAKE_ENV, FAKE_SUPABASE_KEY
from storage3.exceptions import StorageApiError

from imask_backend.settings import load_settings
from imask_backend.store import REVIEW_COLUMNS, StoreError, SupabaseStore

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


# --- 서명 다운로드 URL -----------------------------------------------------------------


def test_signed_download_url_with_real_storage3(mocked: tuple[SupabaseStore, Recorder]) -> None:
    store, rec = mocked
    rec.reply = (200, {"signedURL": "/object/sign/documents/analyses/a1/document.pdf?token=tok123"})
    url = store.create_signed_download_url("analyses/a1/document.pdf", 600)
    # storage3 2.33 은 Storage 기준 주소에 붙인 절대 주소를 돌려준다
    assert url == f"{BASE}/storage/v1/object/sign/documents/analyses/a1/document.pdf?token=tok123"
    (req,) = rec.requests
    assert req.method == "POST"
    assert req.url.path == "/storage/v1/object/sign/documents/analyses/a1/document.pdf"
    assert json.loads(req.content) == {"expiresIn": "600"}


def test_signed_download_url_missing_object_is_none(mocked: tuple[SupabaseStore, Recorder]) -> None:
    store, rec = mocked
    rec.reply = (400, {"statusCode": "404", "error": "not_found", "message": "Object not found"})
    assert store.create_signed_download_url("analyses/a1/missing.pdf", 600) is None


def test_signed_download_url_error_is_redacted(mocked: tuple[SupabaseStore, Recorder]) -> None:
    store, rec = mocked
    rec.reply = (400, {"statusCode": "403", "error": "Unauthorized", "message": f"bad {FAKE_SUPABASE_KEY}"})
    with pytest.raises(StoreError) as info:
        store.create_signed_download_url("analyses/a1/document.pdf", 600)
    assert FAKE_SUPABASE_KEY not in info.value.message


class FakeBucket:
    def __init__(self, reply: Any) -> None:
        self.reply = reply
        self.calls: list[tuple[str, int]] = []

    def create_signed_url(self, path: str, expires_in: int) -> Any:
        self.calls.append((path, expires_in))
        if isinstance(self.reply, BaseException):
            raise self.reply
        return self.reply


class FakeStorage:
    def __init__(self, bucket: FakeBucket) -> None:
        self.bucket = bucket
        self.names: list[str] = []

    def from_(self, name: str) -> FakeBucket:
        self.names.append(name)
        return self.bucket


class FakeClient:
    def __init__(self, reply: Any, storage_url: str | None = "https://fake-project.supabase.co/storage/v1/") -> None:
        self.storage = FakeStorage(FakeBucket(reply))
        if storage_url is not None:
            self.storage_url = storage_url


ABSOLUTE = "https://fake-project.supabase.co/storage/v1/object/sign/documents/a/b.pdf?token=FAKE-download"


def _fake_store(reply: Any, **kw: Any) -> tuple[SupabaseStore, FakeClient]:
    client = FakeClient(reply, **kw)
    return SupabaseStore(client, {FAKE_SUPABASE_KEY: "<SUPABASE_SECRET_KEY>"}), client


@pytest.mark.parametrize(
    "reply",
    [
        {"signedURL": ABSOLUTE, "signedUrl": ABSOLUTE},
        {"signedURL": None, "signedUrl": ABSOLUTE},
        {"signedUrl": ABSOLUTE},
        {"signed_url": ABSOLUTE},
        {"signedURL": f"  {ABSOLUTE}  "},
    ],
)
def test_signed_download_url_key_variants(reply: Any) -> None:
    store, client = _fake_store(reply)
    assert store.create_signed_download_url("a/b.pdf", 600) == ABSOLUTE
    assert client.storage.bucket.calls == [("a/b.pdf", 600)]
    assert client.storage.names == ["documents"]


@pytest.mark.parametrize("relative", ["/object/sign/documents/a/b.pdf?token=FAKE-download", "object/sign/documents/a/b.pdf?token=FAKE-download"])
def test_signed_download_url_relative_becomes_absolute(relative: str) -> None:
    store, _ = _fake_store({"signedURL": relative})
    assert store.create_signed_download_url("a/b.pdf", 600) == ABSOLUTE


def test_signed_download_url_relative_without_base_is_error() -> None:
    store, _ = _fake_store({"signedURL": "/object/sign/x?token=FAKE"}, storage_url=None)
    with pytest.raises(StoreError):
        store.create_signed_download_url("a/b.pdf", 600)


@pytest.mark.parametrize("reply", [{}, {"signedURL": None, "signedUrl": None}, {"signedURL": ""}, {"signedURL": 5}, "x", None, []])
def test_signed_download_url_without_url_is_error(reply: Any) -> None:
    store, _ = _fake_store(reply)
    with pytest.raises(StoreError):
        store.create_signed_download_url("a/b.pdf", 600)


@pytest.mark.parametrize(
    "exc",
    [
        StorageApiError("Object not found", "not_found", "404"),
        StorageApiError("Object not found", "InvalidKey", 400),
        StorageApiError("missing", "NoSuchKey", 400),
    ],
)
def test_signed_download_url_not_found_is_none(exc: BaseException) -> None:
    store, _ = _fake_store(exc)
    assert store.create_signed_download_url("a/b.pdf", 600) is None


@pytest.mark.parametrize(
    "exc",
    [
        StorageApiError(f"denied {FAKE_SUPABASE_KEY}", "Unauthorized", "403"),
        RuntimeError(f"boom {FAKE_SUPABASE_KEY} {ABSOLUTE}"),
        httpx.ConnectError("down"),
    ],
)
def test_signed_download_url_other_errors_are_redacted_store_errors(exc: BaseException) -> None:
    store, _ = _fake_store(exc)
    with pytest.raises(StoreError) as info:
        store.create_signed_download_url("a/b.pdf", 600)
    assert FAKE_SUPABASE_KEY not in info.value.message
    assert "FAKE-download" not in info.value.message  # 서명 URL 의 token 값도 가린다
    assert info.value.__cause__ is None and info.value.__suppress_context__


# --- 검토 행(analysis_reviews) — T1 review-actions -----------------------------------------------------


def test_get_review_reads_one_row_by_analysis_id(mocked: tuple[SupabaseStore, Recorder]) -> None:
    store, rec = mocked
    rec.reply = (200, [{"analysis_id": "a1", "version": 2}])
    assert store.get_review("a1") == {"analysis_id": "a1", "version": 2}
    (req,) = rec.requests
    assert (req.method, req.url.path) == ("GET", "/rest/v1/analysis_reviews")
    params = dict(httpx.QueryParams(req.url.query))
    assert params == {"select": REVIEW_COLUMNS, "analysis_id": "eq.a1", "limit": "1"}
    assert req.headers["apikey"] == FAKE_SUPABASE_KEY
    rec.reply = (200, [])
    assert store.get_review("a1") is None


def test_insert_review_is_insert_on_conflict_do_nothing(mocked: tuple[SupabaseStore, Recorder]) -> None:
    store, rec = mocked
    # 저장 키는 ASCII escape(storage_key) — 진짜 서로게이트는 보내지 않는다(아래 시험)
    values = {"analysis_id": "a1", "status": "needed", "findings": {"0:\\ud800": {"status": "open"}}, "history": [], "version": 1}
    rec.reply = (201, [{**values, "created_at": "t", "updated_at": "t"}])
    assert store.insert_review(values) == {**values, "created_at": "t", "updated_at": "t"}
    (req,) = rec.requests
    assert (req.method, req.url.path) == ("POST", "/rest/v1/analysis_reviews")
    assert dict(httpx.QueryParams(req.url.query)) == {"on_conflict": "analysis_id"}
    prefer = req.headers.get("prefer", "")
    assert "resolution=ignore-duplicates" in prefer and "return=representation" in prefer
    assert "merge-duplicates" not in prefer
    assert json.loads(req.content) == values
    # 이미 행이 있으면 PostgREST 는 빈 목록 → None(다른 요청이 먼저 만들었다)
    rec.reply = (201, [])
    assert store.insert_review(values) is None


def test_real_surrogate_in_review_values_cannot_be_sent(mocked: tuple[SupabaseStore, Recorder]) -> None:
    # 그래서 저장 키는 storage_key(ASCII escape)이고 사용자 글은 400 으로 막는다 — 보내면 가린 StoreError(502)
    store, rec = mocked
    with pytest.raises(StoreError):
        store.insert_review({"analysis_id": "a1", "findings": {"0:" + "\ud800": {}}, "version": 1})
    assert rec.requests == []


def test_update_review_is_conditional_on_version(mocked: tuple[SupabaseStore, Recorder]) -> None:
    store, rec = mocked
    rec.reply = (200, [{"analysis_id": "a1", "version": 4}])
    assert store.update_review("a1", {"memo": "m", "version": 4}, expect_version=3) == {"analysis_id": "a1", "version": 4}
    (req,) = rec.requests
    assert (req.method, req.url.path) == ("PATCH", "/rest/v1/analysis_reviews")
    assert dict(httpx.QueryParams(req.url.query)) == {"analysis_id": "eq.a1", "version": "eq.3"}
    assert "return=representation" in req.headers.get("prefer", "")
    assert json.loads(req.content) == {"memo": "m", "version": 4}
    rec.reply = (200, [])
    assert store.update_review("a1", {"version": 4}, expect_version=3) is None


def test_review_methods_never_touch_the_analyses_table(mocked: tuple[SupabaseStore, Recorder]) -> None:
    store, rec = mocked
    rec.reply = (200, [])
    store.get_review("a1")
    store.insert_review({"analysis_id": "a1", "version": 1})
    store.update_review("a1", {"version": 2}, expect_version=1)
    assert {r.url.path for r in rec.requests} == {"/rest/v1/analysis_reviews"}


@pytest.mark.parametrize("call", ["get", "insert", "update"])
def test_review_errors_become_redacted_store_errors(mocked: tuple[SupabaseStore, Recorder], call: str) -> None:
    store, rec = mocked
    rec.reply = (500, {"message": f"boom key={FAKE_SUPABASE_KEY}", "code": "XX000", "details": None, "hint": None})
    actions = {
        "get": lambda: store.get_review("a1"),
        "insert": lambda: store.insert_review({"analysis_id": "a1", "version": 1}),
        "update": lambda: store.update_review("a1", {"version": 2}, expect_version=1),
    }
    with pytest.raises(StoreError) as info:
        actions[call]()
    assert FAKE_SUPABASE_KEY not in info.value.message and FAKE_SUPABASE_KEY not in repr(info.value)
    assert info.value.__cause__ is None and info.value.__suppress_context__

    def down(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    rec.reply = down
    with pytest.raises(StoreError):
        actions[call]()


def test_missing_review_table_is_a_store_error(mocked: tuple[SupabaseStore, Recorder]) -> None:
    # 마이그레이션 전 배포: PostgREST 가 없는 테이블을 404 PGRST205 로 알린다 → StoreError(조회는 review: null)
    store, rec = mocked
    rec.reply = (404, {"code": "PGRST205", "message": "Could not find the table 'public.analysis_reviews' in the schema cache", "details": None, "hint": None})
    with pytest.raises(StoreError):
        store.get_review("a1")
