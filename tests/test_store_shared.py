# ==========================================================================
#  imask_backend.store.SupabaseStore — 공유 목록·삭제·started_at(shared-analyses T1) 요청 모양 (네트워크 없음)
#  진짜 supabase-py(2.33)·storage3·postgrest 위에서 httpx 전송층만 MockTransport 로 바꿔 본다(test_api_store 와 같은 방식).
#  - list_analyses: GET 한 번, select = LIST_SELECT(result 열 전체·agent_id·upstage_job_id·storage_path·upstage_file_id 없음),
#    order=created_at.desc,id.desc, limit. 응답이 목록이 아니면 StoreError.
#  - delete_analysis: DELETE ?id=eq.… + Prefer return=minimal,count=exact → Content-Range */N 의 N(지운 행 수).
#  - remove_objects: storage3 remove = DELETE /object/documents {"prefixes": [...]}. 빈 목록은 요청하지 않고, 같은 경로는
#    한 번만. 돌려준 지운 목록에 없는 경로(목록이 아니면 모든 경로)는 info(GET /object/info/…)로 확인 — NoSuchKey(본문
#    statusCode 404 + not_found)면 성공, 아직 있거나(부분 200·오류 객체 200) 확인이 확실하지 않으면 StoreError(T1-fix1 M3).
#    remove 의 StorageApiError(404 꼴 포함)·연결 오류도 StoreError.
#  - 새 메서드의 오류는 값 없이(T1-fix1 M4): 고정 동작 이름 + 예외 종류 + 짧은 코드 + HTTP 상태 — 바깥 message·details·hint 없음.
#  - claim_analysis: status='running' 과 같은 PATCH 에 started_at. update_analysis 의 실행 구분 조건(upstage_job_id·updated_at
#    eq, '+' 는 %2B — T1-fix1 M1·M2).
# ==========================================================================

from __future__ import annotations

import json
import re
from typing import Any

import httpx
import pytest
from api_fakes import FAKE_ENV, FAKE_SUPABASE_KEY

from imask_backend.settings import load_settings
from imask_backend.store import ANALYSIS_COLUMNS, LIST_SELECT, StoreError, SupabaseStore

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning:supabase._sync.client")

# BRIEF §5.2 의 select 문자열 그대로(코디네이터 확정 — 바꾸면 이 시험이 막는다)
BRIEF_SELECT = (
    "id,name,status,error,created_at,updated_at,started_at,risk_level:result->summary->>risk_level,"
    "document_count:result->summary->document_count,documents(id,filename,size_bytes,mime_type,created_at),"
    "analysis_reviews(status)"
)
FORBIDDEN = ("agent_id", "upstage_job_id", "storage_path", "upstage_file_id")


class Recorder:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.reply: Any = None  # (status, json) · (status, json, headers) · callable(request) -> Response

    def handle(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.requests.append(request)
        if callable(self.reply):
            return self.reply(request)
        status, body, *rest = self.reply if self.reply is not None else (200, [])
        headers = rest[0] if rest else None
        if body is None:
            return httpx.Response(status, headers=headers)
        return httpx.Response(status, json=body, headers=headers)


@pytest.fixture
def mocked() -> tuple[SupabaseStore, Recorder]:
    store = SupabaseStore.from_settings(load_settings(FAKE_ENV))
    recorder = Recorder()
    transport = httpx.MockTransport(recorder.handle)
    client = store._client  # noqa: SLF001 — 테스트에서만 전송층을 바꾼다
    client.postgrest.session._transport = transport
    client.storage.session._transport = transport
    return store, recorder


def _top_level(select: str) -> list[str]:
    """select 의 최상위 항목(괄호 안 쉼표는 나누지 않는다)."""
    items: list[str] = []
    depth = 0
    current = ""
    for char in select:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            items.append(current)
            current = ""
        else:
            current += char
    items.append(current)
    return items


# --- 목록 select ------------------------------------------------------------------------


def test_list_select_is_the_brief_string() -> None:
    assert LIST_SELECT == BRIEF_SELECT


def test_list_select_has_no_whole_result_or_internal_columns() -> None:
    items = _top_level(LIST_SELECT)
    assert "result" not in items and "*" not in items
    # result 는 JSON 경로(별칭:result->…)로만 — 열 전체(result 단독·별칭:result)로는 읽지 않는다
    for item in items:
        column = item.split(":", 1)[-1]
        assert column != "result" and not column.startswith("result(")
        if "result" in column:
            assert column.startswith("result->summary->")
    assert [i for i in items if "result" in i] == [
        "risk_level:result->summary->>risk_level",
        "document_count:result->summary->document_count",
    ]
    for name in FORBIDDEN:
        assert re.search(rf"\b{name}\b", LIST_SELECT) is None
    # 끼워 넣는 문서 행에도 저장 경로·Upstage file id 가 없다
    assert "documents(id,filename,size_bytes,mime_type,created_at)" in items
    assert "analysis_reviews(status)" in items


def test_analysis_columns_read_started_at(mocked: tuple[SupabaseStore, Recorder]) -> None:
    assert ANALYSIS_COLUMNS.split(",")[-1] == "started_at"
    store, rec = mocked
    rec.reply = (200, [{"id": "a1", "started_at": None, "documents": []}])
    assert store.get_analysis("a1") == {"id": "a1", "started_at": None, "documents": []}
    select = dict(httpx.QueryParams(rec.requests[0].url.query))["select"]
    assert select.startswith(ANALYSIS_COLUMNS + ",documents(")


def test_list_analyses_is_one_get_with_order_and_limit(mocked: tuple[SupabaseStore, Recorder]) -> None:
    store, rec = mocked
    rows = [{"id": "a2", "analysis_reviews": None}, {"id": "a1", "analysis_reviews": {"status": "done"}}]
    rec.reply = (200, rows)
    assert store.list_analyses(7) == rows
    (req,) = rec.requests
    assert (req.method, req.url.path) == ("GET", "/rest/v1/analyses")
    params = dict(httpx.QueryParams(req.url.query))
    assert params == {"select": BRIEF_SELECT, "order": "created_at.desc,id.desc", "limit": "7"}
    assert req.headers["apikey"] == FAKE_SUPABASE_KEY


@pytest.mark.parametrize("body", [{"id": "a1"}, "x", 5])
def test_list_analyses_non_list_reply_is_store_error(mocked: tuple[SupabaseStore, Recorder], body: Any) -> None:
    store, rec = mocked
    rec.reply = (200, body)
    with pytest.raises(StoreError):
        store.list_analyses(100)


def test_list_analyses_errors_are_redacted(mocked: tuple[SupabaseStore, Recorder]) -> None:
    store, rec = mocked
    rec.reply = (500, {"message": f"boom key={FAKE_SUPABASE_KEY}", "code": "XX000", "details": None, "hint": None})
    with pytest.raises(StoreError) as info:
        store.list_analyses(100)
    assert FAKE_SUPABASE_KEY not in info.value.message and info.value.__cause__ is None

    def down(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    rec.reply = down
    with pytest.raises(StoreError):
        store.list_analyses(100)


# --- 행 지우기 --------------------------------------------------------------------------


@pytest.mark.parametrize(("content_range", "count"), [("*/1", 1), ("*/0", 0)])
def test_delete_analysis_returns_the_deleted_row_count(
    mocked: tuple[SupabaseStore, Recorder], content_range: str, count: int
) -> None:
    # PostgREST: DELETE + Prefer count=exact → 204(return=minimal) + Content-Range */N(N = 지운 행 수)
    store, rec = mocked
    rec.reply = (204, None, {"Content-Range": content_range})
    assert store.delete_analysis("a1") == count
    (req,) = rec.requests
    assert (req.method, req.url.path) == ("DELETE", "/rest/v1/analyses")
    assert dict(httpx.QueryParams(req.url.query)) == {"id": "eq.a1"}  # select 없음 — 지운 행을 돌려받지 않는다
    prefer = req.headers.get("prefer", "")
    assert "return=minimal" in prefer and "count=exact" in prefer and "representation" not in prefer


def test_delete_analysis_without_count_header_counts_rows_in_body(mocked: tuple[SupabaseStore, Recorder]) -> None:
    store, rec = mocked
    rec.reply = (200, [{"id": "a1"}])
    assert store.delete_analysis("a1") == 1
    rec.reply = (200, [])
    assert store.delete_analysis("a1") == 0
    rec.reply = (204, None)
    assert store.delete_analysis("a1") == 0


def test_delete_analysis_errors_are_redacted_store_errors(mocked: tuple[SupabaseStore, Recorder]) -> None:
    store, rec = mocked
    rec.reply = (500, {"message": f"boom key={FAKE_SUPABASE_KEY}", "code": "XX000", "details": None, "hint": None})
    with pytest.raises(StoreError) as info:
        store.delete_analysis("a1")
    assert FAKE_SUPABASE_KEY not in info.value.message and info.value.__cause__ is None


# --- 버킷 객체 지우기 ----------------------------------------------------------------------


def test_remove_objects_with_real_storage3(mocked: tuple[SupabaseStore, Recorder]) -> None:
    store, rec = mocked
    names = [{"name": "analyses/a1/document.pdf", "bucket_id": "documents"}, {"name": "analyses/a1/b.png", "bucket_id": "documents"}]
    rec.reply = (200, names)
    store.remove_objects(["analyses/a1/document.pdf", "analyses/a1/document.pdf", "", "analyses/a1/b.png"])
    (req,) = rec.requests  # 모두 지웠다고 돌려주면 확인 조회는 없다
    assert (req.method, req.url.path) == ("DELETE", "/storage/v1/object/documents")
    # 같은 경로는 한 번만, 빈 경로는 보내지 않는다
    assert json.loads(req.content) == {"prefixes": ["analyses/a1/document.pdf", "analyses/a1/b.png"]}
    assert req.headers["apikey"] == FAKE_SUPABASE_KEY


NOT_FOUND_BODY = {"statusCode": "404", "error": "not_found", "message": "Object not found"}


def test_remove_objects_missing_objects_are_success_after_checking(mocked: tuple[SupabaseStore, Recorder]) -> None:
    # Storage 는 없는 경로를 지운 목록에서 뺄 뿐 오류로 알리지 않는다(200 []) — 빠진 경로는 info 로 '없음'을 확인한다
    store, rec = mocked

    def reply(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            return httpx.Response(200, json=[])
        return httpx.Response(400, json=NOT_FOUND_BODY)  # NoSuchKey: HTTP 400 + 본문 statusCode 404

    rec.reply = reply
    store.remove_objects(["analyses/a1/missing.pdf"])
    assert [(r.method, r.url.path) for r in rec.requests] == [
        ("DELETE", "/storage/v1/object/documents"),
        ("GET", "/storage/v1/object/info/documents/analyses/a1/missing.pdf"),
    ]
    assert rec.requests[1].content == b""  # 메타데이터 조회 — 내용을 받지 않는다


def test_remove_objects_with_nothing_to_remove_sends_nothing(mocked: tuple[SupabaseStore, Recorder]) -> None:
    store, rec = mocked
    store.remove_objects([])
    store.remove_objects(["", ""])
    assert rec.requests == []


@pytest.mark.parametrize(
    "reply",
    [
        (400, {"statusCode": "403", "error": "Unauthorized", "message": f"bad {FAKE_SUPABASE_KEY}"}),
        # 버킷 없음 등 404 꼴도 성공으로 보지 않는다(원본이 남았을 수 있으면 행을 지우지 않게)
        (400, {"statusCode": "404", "error": "Bucket not found", "message": "Bucket not found"}),
        (500, {"statusCode": "500", "error": "internal", "message": "boom"}),
    ],
)
def test_remove_objects_failures_are_redacted_store_errors(mocked: tuple[SupabaseStore, Recorder], reply: Any) -> None:
    store, rec = mocked
    rec.reply = reply
    with pytest.raises(StoreError) as info:
        store.remove_objects(["analyses/a1/document.pdf"])
    assert FAKE_SUPABASE_KEY not in info.value.message
    assert info.value.__cause__ is None and info.value.__suppress_context__


def test_remove_objects_connection_error_is_store_error(mocked: tuple[SupabaseStore, Recorder]) -> None:
    store, rec = mocked

    def down(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    rec.reply = down
    with pytest.raises(StoreError):
        store.remove_objects(["analyses/a1/document.pdf"])


# --- 시작 선점의 started_at -------------------------------------------------------------------


def test_claim_puts_the_given_started_at_in_the_same_conditional_patch(mocked: tuple[SupabaseStore, Recorder]) -> None:
    store, rec = mocked
    rec.reply = (200, [{"id": "a1", "status": "running", "started_at": "2026-11-04T01:02:03+00:00"}])
    assert store.claim_analysis("a1", started_at="2026-11-04T01:02:03+00:00")["started_at"] == "2026-11-04T01:02:03+00:00"
    (req,) = rec.requests
    assert req.method == "PATCH"
    assert dict(httpx.QueryParams(req.url.query)) == {"id": "eq.a1", "status": "eq.queued"}
    assert json.loads(req.content) == {"status": "running", "started_at": "2026-11-04T01:02:03+00:00"}
    rec.reply = (200, [])
    assert store.claim_analysis("a1", started_at="2026-11-04T01:02:03+00:00") is None  # 진 요청은 아무것도 바꾸지 못함


def test_insert_analysis_sends_no_started_at(mocked: tuple[SupabaseStore, Recorder]) -> None:
    store, rec = mocked
    rec.reply = (201, [{"id": "a1", "status": "queued", "started_at": None}])
    store.insert_analysis("n")
    assert json.loads(rec.requests[0].content) == {"name": "n", "status": "queued"}


# --- T1-fix1 M3: Storage 지우기 확인 ------------------------------------------------------------


class BucketServer:
    """Storage 흉내(MockTransport 처리기): DELETE /object/documents 와 GET /object/info/documents/{path}.

    objects 에 있는 경로만 '있다'. mode: all(다 지움) · partial(첫 경로만 지움) · error_object(200 + 오류 객체, 안 지움)
    · none(200 [], 안 지움). info 는 있으면 200 메타데이터, 없으면 NoSuchKey(HTTP 400 + 본문 statusCode 404).
    """

    def __init__(self, objects: set[str], mode: str = "all") -> None:
        self.objects = set(objects)
        self.mode = mode
        self.info_reply: Any = None  # (status, body) 로 info 응답을 바꾼다
        self.requests: list[tuple[str, str]] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        request.read()
        prefix = "/storage/v1/object/"
        path = request.url.path[len(prefix):]
        self.requests.append((request.method, path))
        if request.method == "DELETE" and path == "documents":
            paths = json.loads(request.content)["prefixes"]
            if self.mode == "error_object":
                return httpx.Response(200, json={"error": "synthetic"})
            chosen = paths[:1] if self.mode == "partial" else ([] if self.mode == "none" else paths)
            gone = [p for p in chosen if p in self.objects]
            self.objects -= set(gone)
            return httpx.Response(200, json=[{"name": p, "bucket_id": "documents"} for p in gone])
        if request.method == "GET" and path.startswith("info/documents/"):
            if self.info_reply is not None:
                status, body = self.info_reply
                return httpx.Response(status, json=body) if body is not None else httpx.Response(status)
            name = path[len("info/documents/"):]
            if name in self.objects:
                return httpx.Response(200, json={"name": name, "size": 10})
            return httpx.Response(400, json=NOT_FOUND_BODY)
        return httpx.Response(404, json={"statusCode": "404", "error": "not_found", "message": "route"})


def _bucket(mocked: tuple[SupabaseStore, Recorder], objects: set[str], mode: str = "all") -> BucketServer:
    _store, rec = mocked
    server = BucketServer(objects, mode)
    rec.reply = server.handle
    return server


A, B = "analyses/a1/document.pdf", "analyses/a1/second.pdf"


def test_partial_200_is_a_store_error_and_the_rest_stays(mocked: tuple[SupabaseStore, Recorder]) -> None:
    server = _bucket(mocked, {A, B}, "partial")
    with pytest.raises(StoreError) as info:
        mocked[0].remove_objects([A, B])
    assert server.objects == {B}
    assert ("GET", f"info/documents/{B}") in server.requests and ("GET", f"info/documents/{A}") not in server.requests
    assert info.value.message == "원본 파일 지우기: 지우지 못한 객체가 남음"
    # 다시 누르면 이어서 지운다
    server.mode = "all"
    mocked[0].remove_objects([A, B])
    assert server.objects == set()


def test_error_object_200_checks_every_path(mocked: tuple[SupabaseStore, Recorder]) -> None:
    server = _bucket(mocked, {A, B}, "error_object")
    with pytest.raises(StoreError):
        mocked[0].remove_objects([A, B])
    assert server.objects == {A, B}
    # 같은 모양이어도 모든 경로가 정말 없으면 성공
    server.objects.clear()
    mocked[0].remove_objects([A, B])
    assert server.requests[-2:] == [("GET", f"info/documents/{A}"), ("GET", f"info/documents/{B}")]


@pytest.mark.parametrize("result", [[{"name": 5}], [{"bucket_id": "documents"}], ["analyses/a1/document.pdf"], [None]])
def test_unreadable_items_count_as_not_removed(mocked: tuple[SupabaseStore, Recorder], result: Any) -> None:
    store, rec = mocked

    def reply(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            return httpx.Response(200, json=result)
        return httpx.Response(200, json={"name": A})  # 아직 있다

    rec.reply = reply
    with pytest.raises(StoreError):
        store.remove_objects([A])


@pytest.mark.parametrize(
    "info_reply",
    [
        (400, {"statusCode": "403", "error": "Unauthorized", "message": "denied"}),
        (400, {"statusCode": "404", "error": "Bucket not found", "message": "Bucket not found"}),
        (404, None),  # 본문 없는 404 — storage3 가 본문을 못 읽어 InternalError
        (500, {"statusCode": "500", "error": "internal", "message": "boom"}),
    ],
    ids=["forbidden", "bucket_not_found", "bodyless_404", "server_error"],
)
def test_uncertain_checks_are_store_errors(mocked: tuple[SupabaseStore, Recorder], info_reply: Any) -> None:
    server = _bucket(mocked, {A}, "none")
    server.info_reply = info_reply
    with pytest.raises(StoreError) as info:
        mocked[0].remove_objects([A])
    assert info.value.message.startswith("원본 파일 지우기 확인: StorageApiError")


def test_check_connection_error_is_a_store_error(mocked: tuple[SupabaseStore, Recorder]) -> None:
    store, rec = mocked

    def reply(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            return httpx.Response(200, json=[])
        raise httpx.ConnectError("down")

    rec.reply = reply
    with pytest.raises(StoreError) as info:
        store.remove_objects([A])
    assert info.value.message == "원본 파일 지우기 확인: ConnectError"


def test_returned_names_need_no_check(mocked: tuple[SupabaseStore, Recorder]) -> None:
    server = _bucket(mocked, {A, B})
    mocked[0].remove_objects([A, B])
    assert server.requests == [("DELETE", "documents")]


# --- T1-fix1 M4: 새 Store 메서드의 값 없는 오류 ----------------------------------------------------

MARKER = "SYNTHETIC_PRIVATE_NAME_AND_ERROR"


def _postgrest_error(_request: httpx.Request) -> httpx.Response:
    body = {"message": f"{MARKER} m {FAKE_SUPABASE_KEY}", "code": "XX000", "details": f"{MARKER} d", "hint": f"{MARKER} h"}
    return httpx.Response(500, json=body)


@pytest.mark.parametrize(
    ("call", "expected"),
    [
        (lambda s: s.list_analyses(100), "분석 목록 읽기: APIError (XX000)"),
        (lambda s: s.delete_analysis("a1"), "분석 행 지우기: APIError (XX000)"),
    ],
    ids=["list_analyses", "delete_analysis"],
)
def test_postgrest_errors_carry_no_outside_text(
    mocked: tuple[SupabaseStore, Recorder], caplog: pytest.LogCaptureFixture, call: Any, expected: str
) -> None:
    store, rec = mocked
    rec.reply = _postgrest_error
    with caplog.at_level("DEBUG", logger="imask"), pytest.raises(StoreError) as info:
        call(store)
    assert info.value.message == expected
    logged = "\n".join(r.getMessage() for r in caplog.records)
    for text in (info.value.message, repr(info.value), logged):
        assert MARKER not in text and FAKE_SUPABASE_KEY not in text
    assert info.value.__cause__ is None and info.value.__suppress_context__


@pytest.mark.parametrize("step", ["remove", "check"])
def test_storage_errors_carry_no_outside_text(
    mocked: tuple[SupabaseStore, Recorder], caplog: pytest.LogCaptureFixture, step: str
) -> None:
    store, rec = mocked

    def reply(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE" and step == "check":
            return httpx.Response(200, json=[])
        return httpx.Response(403, json={"message": f"{MARKER} {FAKE_SUPABASE_KEY}", "error": "Denied", "statusCode": 403})

    rec.reply = reply
    with caplog.at_level("DEBUG", logger="imask"), pytest.raises(StoreError) as info:
        store.remove_objects([A])
    action = "원본 파일 지우기" if step == "remove" else "원본 파일 지우기 확인"
    assert info.value.message == f"{action}: StorageApiError (Denied) HTTP 403"
    logged = "\n".join(r.getMessage() for r in caplog.records)
    for text in (info.value.message, logged):
        assert MARKER not in text and FAKE_SUPABASE_KEY not in text


def test_quiet_error_keeps_only_short_codes_and_statuses() -> None:
    class Odd(Exception):
        code = "has space"
        status = "4040"
        message = MARKER

    error = SupabaseStore._quiet_error("동작", Odd(MARKER))  # noqa: SLF001
    assert error.message == "동작: Odd"


# --- T1-fix1 M1·M2: 실행 구분 조건 -------------------------------------------------------------------


def test_update_with_job_and_updated_at_conditions(mocked: tuple[SupabaseStore, Recorder]) -> None:
    store, rec = mocked
    rec.reply = (200, [])
    stamp = "2026-11-04T01:02:03.456789+00:00"
    assert store.update_analysis("a1", {"status": "failed"}, expect_status="running", expect_job_id="job_1", expect_updated_at=stamp) is None
    (req,) = rec.requests
    params = dict(httpx.QueryParams(req.url.query))
    assert params == {"id": "eq.a1", "status": "eq.running", "upstage_job_id": "eq.job_1", "updated_at": f"eq.{stamp}"}
    # '+' 는 %2B 로 간다(그대로 보내면 PostgREST 가 공백으로 읽는다)
    raw = req.url.query.decode()
    assert "%2B00" in raw and "+" not in raw


# --- T1-fix2 R1·R2: 문서 file id 비교 후 교환 · 읽은 실행만 지우기 ---------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "condition"),
    [
        ({"expect_no_file": True}, {"upstage_file_id": "is.null"}),
        ({"expect_file_id": "file_old"}, {"upstage_file_id": "eq.file_old"}),
        ({}, {}),
    ],
    ids=["is_null", "eq_read_value", "unconditional"],
)
def test_update_document_compare_and_swap(mocked: tuple[SupabaseStore, Recorder], kwargs: dict[str, Any], condition: dict[str, str]) -> None:
    store, rec = mocked
    rec.reply = (200, [{"id": "d1"}])
    assert store.update_document("d1", {"upstage_file_id": "file_new"}, **kwargs) is True
    (req,) = rec.requests
    assert (req.method, req.url.path) == ("PATCH", "/rest/v1/documents")
    assert dict(httpx.QueryParams(req.url.query)) == {"id": "eq.d1", **condition, "select": "id"}
    assert "return=representation" in req.headers.get("prefer", "")
    assert json.loads(req.content) == {"upstage_file_id": "file_new"}
    # 바뀐 행이 없으면(다른 실행이 먼저 썼거나 행이 지워짐) False
    rec.reply = (200, [])
    assert store.update_document("d1", {"upstage_file_id": "file_new"}, **kwargs) is False


def test_update_document_error_is_a_store_error(mocked: tuple[SupabaseStore, Recorder]) -> None:
    store, rec = mocked
    rec.reply = (500, {"message": f"boom {FAKE_SUPABASE_KEY}", "code": "XX000", "details": None, "hint": None})
    with pytest.raises(StoreError) as info:
        store.update_document("d1", {"upstage_file_id": "f"}, expect_no_file=True)
    assert FAKE_SUPABASE_KEY not in info.value.message


def test_delete_with_the_read_updated_at(mocked: tuple[SupabaseStore, Recorder]) -> None:
    store, rec = mocked
    stamp = "2026-11-04T01:02:03.456789+00:00"
    rec.reply = (204, None, {"Content-Range": "*/0"})
    assert store.delete_analysis("a1", expect_updated_at=stamp) == 0
    (req,) = rec.requests
    assert req.method == "DELETE"
    assert dict(httpx.QueryParams(req.url.query)) == {"id": "eq.a1", "updated_at": f"eq.{stamp}"}
    assert "%2B00" in req.url.query.decode()
