# ==========================================================================
#  실행 구분·겹친 다시 분석·Storage 지우기 확인·값 없는 로그·선점 뒤 클라이언트 (shared-analyses T1-fix1, 네트워크 없음)
#  V-T1-1 의 M1·M2·M3·M4·m1 회귀 테스트.
#  - M1 실행 구분: 옛 조회가 다시 분석의 새 실행을 덮어쓰지 않음(_finish 작업 id 조건), 오래된 시작 만료와 다시 분석이 겹침
#    (updated_at 조건), 만료가 이긴 뒤 다시 읽은 행이 새 실행이면 새 실행의 파일을 지우지 않음, job id 저장이 모호하게 실패한 뒤
#    실패 기록이 져서 최신(running + job) 행 — 작업이 쓰는 파일은 지우지 않음
#  - M2 겹친 다시 분석: 먼저 간 요청이 빨리 failed 로 돌아와도(원본 없음·작업 즉시 실패·job id 저장 실패) 나중 요청은 409,
#    작업 만들기 최대 1회
#  - M3 Storage 지우기 확인: 진짜 storage3 전송층에서 부분 200·오류 객체 200 → 502·행 보존, 다시 누르면 204
#  - M4 값 없는 로그: 바깥 오류 message·details·hint 의 합성 표식이 로그·응답 어디에도 없음(목록·객체 지우기·지우기 확인·
#    행 지우기·Upstage 정리)
#  - m1 선점 뒤 클라이언트: 다시 분석·/start 의 선점 패배·행 없음에서 클라이언트 생성 0회, 생성 실패는 failed 로 기록
# ==========================================================================

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
import pytest
from api_fakes import FAKE_ENV, FAKE_SUPABASE_KEY, PDF_BYTES
from shared_ctx import (  # noqa: F401
    MSG_BUSY,
    MSG_DELETE_FILES,
    MSG_NOT_FOUND,
    MSG_RETRY_CONFLICT,
    MSG_STORE,
    Ctx,
    ctx,
    logic_factory,
)

from api import index as api_index
from imask_backend import manage
from imask_backend.analyses import poll_analysis
from imask_backend.settings import load_settings
from imask_backend.store import StoreError, SupabaseStore

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning:supabase._sync.client")

SETTINGS = load_settings(FAKE_ENV)
MSG_START_INTERNAL = "분석을 시작하는 중 서버 오류가 발생했습니다. 새 분석으로 다시 올려 주세요."
MSG_START_STALE = "분석 시작이 끝나지 않았습니다. 새 분석으로 다시 올려 주세요."
MARKER = "SYNTHETIC_PRIVATE_NAME_AND_ERROR"


def _ago(minutes: float) -> str:
    from datetime import UTC, datetime, timedelta

    return (datetime.now(UTC) - timedelta(minutes=minutes)).isoformat()


def _new_files(ctx: Ctx) -> list[str]:
    return [f for f in ctx.server.files if f.startswith("file_fake")]


# --- M1 실행 구분 ------------------------------------------------------------------------------


def test_old_poll_finishing_after_a_retry_does_not_overwrite_the_new_run(ctx: Ctx) -> None:
    ctx.server.files["old_file"] = ("document.pdf", b"")
    analysis_id = ctx.store.put(status="running", job_id="old_job", upstage_file_id="old_file")
    ctx.server.last_status = "failed"
    seen: dict[str, Any] = {}

    def other_requests(aid: str, _values: Any) -> None:
        # 옛 조회 A 가 실패를 쓰기 직전: 조회 B 가 먼저 실패를 저장하고, 다시 분석이 새 작업을 시작한다
        seen["b"] = poll_analysis(ctx.store, logic_factory(ctx), SETTINGS, aid).row["status"]
        new = manage.retry_analysis(ctx.store, logic_factory(ctx), SETTINGS, aid, "다른 사람")
        seen["new_job"], seen["new_file"] = new["upstage_job_id"], new["documents"][0]["upstage_file_id"]
        ctx.server.last_status = "in_progress"

    ctx.store.before_update = other_requests
    response = ctx.get(analysis_id)
    assert seen["b"] == "failed" and seen["new_job"]
    assert response.status_code == 200
    body = response.json()
    # A 의 쓰기는 졌다: 응답은 새 실행의 최신 행이고, 옛 작업의 Upstage 상태를 붙이지 않는다
    assert body["status"] == "running" and body["upstage_job_id"] == seen["new_job"] and body["upstage_status"] is None
    row = ctx.store.analyses[analysis_id]
    assert (row["status"], row["upstage_job_id"], row["error"]) == ("running", seen["new_job"], None)
    # A 의 쓰기는 job id 조건(old_job)이 붙었다
    lost = [c for _, values, c in ctx.store.updates if values.get("status") == "failed" and c.get("expect_job_id") == "old_job"]
    assert len(lost) == 2  # B(이김)·A(짐)
    # 옛 실행의 파일만 지운다 — 새 실행의 파일은 그대로
    assert "old_file" in ctx.server.deleted and seen["new_file"] not in ctx.server.deleted
    assert len(ctx.server.calls("POST", "responses")) == 1
    # 다음 조회는 새 작업을 조회한다
    polled_before = len(ctx.server.calls("GET", "response"))
    next_body = ctx.get(analysis_id).json()
    assert next_body["status"] == "running" and next_body["upstage_status"] == "in_progress"
    new_polls = ctx.server.calls("GET", "response")[polled_before:]
    assert new_polls and all(seen["new_job"] in r.url.path for r in new_polls)


def test_old_poll_losing_to_the_same_runs_other_poll_keeps_its_status(ctx: Ctx) -> None:
    # 같은 실행의 다른 조회가 먼저 저장한 경우(작업 id 같음)는 지금처럼 승자의 행 + 이 조회가 본 Upstage 상태
    analysis_id = ctx.store.put(status="running", job_id="job_1")
    ctx.server.last_status = "failed"
    ctx.store.before_update = lambda aid, _values: ctx.store.analyses[aid].update(status="failed", error="승자")
    body = ctx.get(analysis_id).json()
    assert body["status"] == "failed" and body["error"] == "승자" and body["upstage_status"] == "failed"


def test_stale_start_expiry_overlapping_a_full_retry_loses(ctx: Ctx) -> None:
    ctx.server.files["old_file"] = ("document.pdf", b"")
    analysis_id = ctx.store.put(status="running", updated_at=_ago(10), upstage_file_id="old_file")
    seen: dict[str, Any] = {}

    def other_requests(aid: str, _values: Any) -> None:
        seen["b"] = poll_analysis(ctx.store, logic_factory(ctx), SETTINGS, aid).row["status"]  # 다른 조회가 먼저 만료
        new = manage.retry_analysis(ctx.store, logic_factory(ctx), SETTINGS, aid, "다른 사람")
        seen["new_job"], seen["new_file"] = new["upstage_job_id"], new["documents"][0]["upstage_file_id"]

    ctx.store.before_update = other_requests
    body = ctx.get(analysis_id).json()
    assert seen["b"] == "failed"
    assert body["status"] == "running" and body["upstage_job_id"] == seen["new_job"]
    assert ctx.store.analyses[analysis_id]["status"] == "running"
    assert seen["new_file"] not in ctx.server.deleted and ctx.server.deleted == ["old_file"]


def test_stale_start_expiry_overlapping_a_fresh_claim_without_job_loses(ctx: Ctx) -> None:
    # 다시 분석이 선점까지만 한 상태(running·job 없음): status·job 조건만으로는 맞지만 updated_at 이 달라 져야 한다
    stale = _ago(10)
    analysis_id = ctx.store.put(status="running", updated_at=stale)

    def other_requests(aid: str, _values: Any) -> None:
        row = ctx.store.analyses[aid]
        row.update(status="failed", error=MSG_START_STALE)  # 다른 조회가 만료
        row["updated_at"] = _ago(1)
        reverted = ctx.store.update_analysis(aid, {"status": "queued", "error": None}, expect_status="failed")
        assert reverted is not None
        assert ctx.store.claim_analysis(aid) is not None  # 새 실행 선점(작업은 아직)

    ctx.store.before_update = other_requests
    body = ctx.get(analysis_id).json()
    row = ctx.store.analyses[analysis_id]
    assert (row["status"], row["error"], row["upstage_job_id"]) == ("running", None, None)
    assert body["status"] == "running" and body["error"] is None
    stale_writes = [c for _, v, c in ctx.store.updates if v.get("error") == MSG_START_STALE]
    assert stale_writes == [{"expect_status": "running", "expect_no_job": True, "expect_updated_at": stale}]


def test_stale_expiry_that_won_does_not_delete_a_new_runs_file(ctx: Ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx.server.files["old_file"] = ("document.pdf", b"")
    analysis_id = ctx.store.put(status="running", updated_at=_ago(10), upstage_file_id="old_file")
    original = ctx.store.get_analysis
    state = {"calls": 0, "inside": False}
    seen: dict[str, Any] = {}

    def get_analysis(aid: str) -> Any:
        state["calls"] += 1
        if state["calls"] == 2 and not state["inside"]:
            # 만료가 이긴 직후 다시 읽기 전에 다시 분석이 새 실행을 시작한다(새 파일)
            state["inside"] = True
            new = manage.retry_analysis(ctx.store, logic_factory(ctx), SETTINGS, aid, "다른 사람")
            seen["new_file"] = new["documents"][0]["upstage_file_id"]
        return original(aid)

    monkeypatch.setattr(ctx.store, "get_analysis", get_analysis)
    assert ctx.get(analysis_id).status_code == 200
    assert seen["new_file"] and seen["new_file"] not in ctx.server.deleted
    assert ctx.server.deleted == ["old_file"]
    assert ctx.store.analyses[analysis_id]["status"] == "running"


@pytest.mark.parametrize("route", ["start", "retry"])
def test_ambiguous_job_save_then_lost_failure_record_returns_the_running_row(ctx: Ctx, monkeypatch: pytest.MonkeyPatch, route: str) -> None:
    analysis_id = ctx.store.put(status="queued" if route == "start" else "failed", error=None if route == "start" else "e")
    original = ctx.store.update_analysis

    def update(aid: str, values: Any, **kw: Any) -> Any:
        result = original(aid, values, **kw)
        if "upstage_job_id" in values and values["upstage_job_id"]:
            raise StoreError("job id 저장: 응답을 받지 못함(가짜 — 실제로는 저장됨)")
        return result

    monkeypatch.setattr(ctx.store, "update_analysis", update)
    response = ctx.start(analysis_id) if route == "start" else ctx.retry(analysis_id)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running" and body["upstage_job_id"] == "job_fake2" and body["error"] is None
    row = ctx.store.analyses[analysis_id]
    assert (row["status"], row["upstage_job_id"]) == ("running", "job_fake2")
    # 실패 기록은 선점이 돌려준 updated_at 조건이라 졌다
    record = [c for _, v, c in ctx.store.updates if v.get("status") == "failed"]
    assert len(record) == 1 and "expect_updated_at" in record[0]
    assert ctx.server.deleted == []  # 작업이 쓰는 파일은 지우지 않는다(끝난 뒤 조회가 지운다)


def test_job_save_lost_to_a_delete_still_cleans_its_upload(ctx: Ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    analysis_id = ctx.store.put()
    original = ctx.store.update_analysis

    def update(aid: str, values: Any, **kw: Any) -> Any:
        if "upstage_job_id" in values:
            ctx.store.analyses.pop(aid)
        return original(aid, values, **kw)

    monkeypatch.setattr(ctx.store, "update_analysis", update)
    response = ctx.start(analysis_id)
    assert (response.status_code, response.json()) == (404, {"detail": MSG_NOT_FOUND})
    assert ctx.server.deleted == ["file_fake1"]


# --- M2 겹친 다시 분석 ------------------------------------------------------------------------------


@pytest.mark.parametrize("fast_fail", ["missing_original", "job_fails_immediately", "job_save_fails"])
def test_overlapping_retry_after_a_fast_failing_retry_is_409(ctx: Ctx, monkeypatch: pytest.MonkeyPatch, fast_fail: str) -> None:
    analysis_id = ctx.store.put(status="failed", error="처음 실패", content=None if fast_fail == "missing_original" else PDF_BYTES)
    if fast_fail == "job_fails_immediately":
        ctx.server.create_status = "failed"
    if fast_fail == "job_save_fails":
        original = ctx.store.update_analysis

        def update(aid: str, values: Any, **kw: Any) -> Any:
            if values.get("upstage_job_id"):  # job id 저장만(되돌리기는 None 을 쓴다)
                raise StoreError("job id 저장 실패(가짜)")
            return original(aid, values, **kw)

        monkeypatch.setattr(ctx.store, "update_analysis", update)
    inner: list[str] = []

    def other_retry(aid: str, _values: Any) -> None:
        # A 가 되돌리기 직전: B 가 한 바퀴(되돌리기 → 시작 → 빠른 실패) 돌아 다시 failed 로 만든다
        inner.append(manage.retry_analysis(ctx.store, logic_factory(ctx), SETTINGS, aid, "다른 사람")["status"])

    ctx.store.before_update = other_retry
    response = ctx.retry(analysis_id)
    assert inner == ["failed"]
    assert (response.status_code, response.json()) == (409, {"detail": MSG_RETRY_CONFLICT})
    assert len(ctx.server.calls("POST", "responses")) <= 1
    assert len(ctx.server.calls("POST", "files")) <= 1
    assert len(ctx.store.reviews[analysis_id]["history"]) == 1  # B 의 이력만
    assert ctx.store.analyses[analysis_id]["status"] == "failed"


def test_overlapping_retries_first_job_immediately_fails(ctx: Ctx) -> None:
    # V-T1-1 probe_races 의 사례 그대로
    analysis_id = ctx.store.put(status="failed", job_id="old_job", error="synthetic")
    ctx.server.create_status = "failed"
    seen: list[str] = []

    def other_retry(aid: str, _values: Any) -> None:
        seen.append(manage.retry_analysis(ctx.store, logic_factory(ctx), SETTINGS, aid, "다른 사람")["status"])
        ctx.server.create_status = "in_progress"

    ctx.store.before_update = other_retry
    response = ctx.retry(analysis_id)
    assert seen == ["failed"] and response.status_code == 409
    assert (len(ctx.server.calls("POST", "files")), len(ctx.server.calls("POST", "responses"))) == (1, 1)


def test_retry_of_a_row_without_updated_at_still_works(ctx: Ctx) -> None:
    analysis_id = ctx.store.put(status="failed")
    ctx.store.analyses[analysis_id]["updated_at"] = None  # 조건 없이(옛 동작) — 실제 열은 not null
    assert ctx.retry(analysis_id).status_code == 200


# --- m1 선점 뒤 클라이언트 ---------------------------------------------------------------------------


@pytest.mark.parametrize("route", ["retry", "start"])
@pytest.mark.parametrize("mode", ["lost_claim", "deleted_before_claim"])
def test_losing_the_claim_makes_no_upstage_client(ctx: Ctx, monkeypatch: pytest.MonkeyPatch, route: str, mode: str) -> None:
    analysis_id = ctx.store.put(status="failed" if route == "retry" else "queued")

    def lose(aid: str, **_kw: Any) -> None:
        if mode == "deleted_before_claim":
            ctx.store.delete_analysis(aid)

    monkeypatch.setattr(ctx.store, "claim_analysis", lose)
    response = ctx.retry(analysis_id) if route == "retry" else ctx.start(analysis_id)
    if route == "retry":
        expected = (404, MSG_NOT_FOUND) if mode == "deleted_before_claim" else (409, MSG_BUSY)
    else:
        expected = (409, "이미 시작한 분석입니다.")  # /start 는 지금처럼(선점에 지면 409)
    assert (response.status_code, response.json()["detail"]) == expected
    assert ctx.made == [] and ctx.server.requests == []


def test_client_creation_failure_after_the_claim_is_recorded_as_failed(ctx: Ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    class Broken:
        @classmethod
        def from_settings(cls, *_args: Any, **_kw: Any) -> Any:
            raise RuntimeError("client boom")

    monkeypatch.setattr(api_index, "UpstageClient", Broken)
    analysis_id = ctx.store.put()
    response = ctx.start(analysis_id)
    assert response.status_code == 200
    body = response.json()
    assert (body["status"], body["error"]) == ("failed", MSG_START_INTERNAL)
    assert ctx.store.analyses[analysis_id]["status"] == "failed"  # running 으로 남지 않는다


# --- M3 Storage 지우기 확인(진짜 storage3 전송층) ---------------------------------------------------


class BucketOverStore:
    """ctx.store.objects 를 버킷으로 쓰는 Storage 흉내 — 진짜 SupabaseStore.remove_objects 가 이 전송층으로 간다."""

    def __init__(self, ctx: Ctx, mode: str) -> None:
        self.ctx = ctx
        self.mode = mode
        self.requests: list[tuple[str, str]] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        request.read()
        path = request.url.path[len("/storage/v1/object/"):]
        self.requests.append((request.method, path))
        objects = self.ctx.store.objects
        if request.method == "DELETE":
            paths = json.loads(request.content)["prefixes"]
            if self.mode == "error_object":
                return httpx.Response(200, json={"error": "synthetic"})
            chosen = paths[:1] if self.mode == "partial" else paths
            gone = [p for p in chosen if objects.pop(p, None) is not None]
            return httpx.Response(200, json=[{"name": p, "bucket_id": "documents"} for p in gone])
        name = path[len("info/documents/"):]
        if name in objects:
            return httpx.Response(200, json={"name": name})
        return httpx.Response(400, json={"statusCode": "404", "error": "not_found", "message": "Object not found"})


def _real_storage(ctx: Ctx, monkeypatch: pytest.MonkeyPatch, handler: Any) -> SupabaseStore:
    real = SupabaseStore.from_settings(load_settings(FAKE_ENV))
    transport = httpx.MockTransport(handler)
    real._client.storage.session._transport = transport  # noqa: SLF001
    real._client.postgrest.session._transport = transport  # noqa: SLF001
    return real


def _two_objects(ctx: Ctx) -> str:
    analysis_id = ctx.store.put(status="done", job_id="j")
    doc = ctx.store.docs_of(analysis_id)[0]
    second = {**doc, "id": "00000000-0000-4000-8000-0000000000aa", "storage_path": doc["storage_path"] + ".second"}
    ctx.store.documents[second["id"]] = second
    ctx.store.objects[second["storage_path"]] = PDF_BYTES
    return analysis_id


@pytest.mark.parametrize("mode", ["partial", "error_object"])
def test_partial_storage_delete_keeps_the_row_then_retry_finishes(ctx: Ctx, monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    analysis_id = _two_objects(ctx)
    bucket = BucketOverStore(ctx, mode)
    real = _real_storage(ctx, monkeypatch, bucket.handle)
    monkeypatch.setattr(ctx.store, "remove_objects", real.remove_objects)
    response = ctx.delete(analysis_id)
    assert (response.status_code, response.json()) == (502, {"detail": MSG_DELETE_FILES})
    assert analysis_id in ctx.store.analyses and ctx.store.docs_of(analysis_id)
    assert len([p for p in ctx.store.objects if analysis_id in p]) == (1 if mode == "partial" else 2)
    assert "delete_analysis" not in ctx.store.calls
    ctx.no_upstage()
    # 다시 누르면 이어서 지워진다
    bucket.mode = "all"
    assert ctx.delete(analysis_id).status_code == 204
    assert analysis_id not in ctx.store.analyses and not [p for p in ctx.store.objects if analysis_id in p]


def test_normal_empty_200_for_missing_objects_is_204_after_checking(ctx: Ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    analysis_id = ctx.store.put(status="failed", content=None)  # 원본을 올리지 않은 분석
    bucket = BucketOverStore(ctx, "all")
    real = _real_storage(ctx, monkeypatch, bucket.handle)
    monkeypatch.setattr(ctx.store, "remove_objects", real.remove_objects)
    assert ctx.delete(analysis_id).status_code == 204
    assert [m for m, _ in bucket.requests] == ["DELETE", "GET"]


# --- M4 값 없는 로그 ------------------------------------------------------------------------------


def _marker_reply(kind: str) -> Any:
    def reply(request: httpx.Request) -> httpx.Response:
        if "/storage/" in request.url.path:
            if kind == "check" and request.method == "DELETE":
                return httpx.Response(200, json=[])
            return httpx.Response(403 if kind == "remove" else 500, json={"message": f"{MARKER} {FAKE_SUPABASE_KEY}", "error": "Denied", "statusCode": "403"})
        body = {"message": f"{MARKER} m {FAKE_SUPABASE_KEY}", "code": "XX000", "details": f"{MARKER} d", "hint": f"{MARKER} h"}
        return httpx.Response(500, json=body)

    return reply


@pytest.mark.parametrize("kind", ["list_analyses", "remove", "check", "delete_analysis"])
def test_external_error_text_never_reaches_logs_or_responses(
    ctx: Ctx, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, kind: str
) -> None:
    analysis_id = ctx.store.put(status="failed")
    real = _real_storage(ctx, monkeypatch, _marker_reply(kind))
    method = {"list_analyses": "list_analyses", "remove": "remove_objects", "check": "remove_objects", "delete_analysis": "delete_analysis"}[kind]
    monkeypatch.setattr(ctx.store, method, getattr(real, method))
    with caplog.at_level(logging.DEBUG, logger="imask"):
        response = ctx.list() if kind == "list_analyses" else ctx.delete(analysis_id)
    assert response.status_code == 502
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert logged  # 경고는 남긴다(값 없이)
    for text in (logged, response.text):
        assert MARKER not in text and FAKE_SUPABASE_KEY not in text


def test_upstage_cleanup_error_text_never_reaches_logs(ctx: Ctx, caplog: pytest.LogCaptureFixture) -> None:
    analysis_id = ctx.store.put(status="failed", upstage_file_id="file_up_1")
    ctx.server.errors[("DELETE", "file")] = (500, {"error": {"message": MARKER}})
    with caplog.at_level(logging.DEBUG, logger="imask"):
        assert ctx.delete(analysis_id).status_code == 204
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "file_up_1" in logged and "UpstageError HTTP 500" in logged
    assert MARKER not in logged
