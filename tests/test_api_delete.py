# ==========================================================================
#  DELETE /api/py/analyses/{id} — 원본 파일·검토 기록과 함께 지우기 (shared-analyses BRIEF §5.3·5.6, 네트워크 없음)
#  - 순서 Storage → 행 → Upstage(최선), Storage 실패 → 502·행 남음·Upstage 안 부름·다시 누르면 이어서 204
#  - 없는 객체 성공, 지운 행 0 → 404, 두 번째 삭제 404, 겹친 삭제(훅) 500 없음
#  - Upstage 실패·설정 없음·시간 초과 → 204 + 값 없는 경고, file id 없으면 클라이언트를 만들지 않음, 짧은 시간 제한 클라이언트
#  - 모든 상태 삭제·cascade(문서·검토 행), uuid 아님 404, 행 갱신 없음, 본문 무시, 저장소 오류 502
# ==========================================================================

from __future__ import annotations

import copy
import logging
from typing import Any

import httpx
import pytest
from api_fakes import FAKE_ENV, FAKE_UPSTAGE_KEY
from fake_reviews import SMALL, custom_result
from fastapi.testclient import TestClient
from shared_ctx import MSG_DELETE_FILES, MSG_DELETE_ROW, MSG_NOT_FOUND, MSG_STORE, Ctx, ctx, install, logic_factory  # noqa: F401

from api.index import app
from imask_backend import manage
from imask_backend.settings import load_settings
from imask_backend.upstage import CLEANUP_TIMEOUT


def _assert_gone(ctx: Ctx, analysis_id: str) -> None:
    assert analysis_id not in ctx.store.analyses
    assert ctx.store.docs_of(analysis_id) == []
    assert analysis_id not in ctx.store.reviews
    assert not [path for path in ctx.store.objects if analysis_id in path]
    assert ctx.get(analysis_id).status_code == 404


def test_delete_goes_storage_then_row_then_upstage(ctx: Ctx) -> None:
    analysis_id = ctx.store.put(status="done", job_id="job_1", upstage_file_id="file_up_1", result=custom_result(SMALL))
    ctx.store.put_review(analysis_id, status="done")
    path = ctx.store.docs_of(analysis_id)[0]["storage_path"]
    seen: list[tuple[bool, bool]] = []
    original = ctx.server.handle

    def handle(request: httpx.Request) -> httpx.Response:
        # Upstage 를 부를 때는 이미 원본·행이 없다
        seen.append((path in ctx.store.objects, analysis_id in ctx.store.analyses))
        return original(request)

    ctx.server.handle = handle  # type: ignore[method-assign]
    response = ctx.delete(analysis_id)
    assert response.status_code == 204 and response.content == b""
    assert ctx.store.calls == ["get_analysis", "remove_objects", "delete_analysis"]
    assert ctx.store.removed == [[path]]
    assert [r.url.path for r in ctx.server.calls("DELETE", "file")] == ["/v2/files/file_up_1"]
    assert seen == [(False, False)]
    _assert_gone(ctx, analysis_id)


def test_storage_failure_is_502_keeps_the_row_and_calls_no_upstage_then_retry_finishes(ctx: Ctx) -> None:
    analysis_id = ctx.store.put(status="failed", upstage_file_id="file_up_1")
    ctx.store.put_review(analysis_id)
    ctx.store.fail.add("remove_objects")
    response = ctx.delete(analysis_id)
    assert (response.status_code, response.json()) == (502, {"detail": MSG_DELETE_FILES})
    assert analysis_id in ctx.store.analyses and ctx.store.docs_of(analysis_id) and analysis_id in ctx.store.reviews
    assert "delete_analysis" not in ctx.store.calls
    ctx.no_upstage()
    # 다시 누르면 이어서 지워진다
    ctx.store.fail.clear()
    assert ctx.delete(analysis_id).status_code == 204
    _assert_gone(ctx, analysis_id)
    assert len(ctx.server.calls("DELETE", "file")) == 1


def test_row_delete_failure_is_502_after_removing_files_then_retry_finishes(ctx: Ctx) -> None:
    analysis_id = ctx.store.put(status="failed")
    ctx.store.fail.add("delete_analysis")
    response = ctx.delete(analysis_id)
    assert (response.status_code, response.json()) == (502, {"detail": MSG_DELETE_ROW})
    assert analysis_id in ctx.store.analyses and not [p for p in ctx.store.objects if analysis_id in p]
    ctx.no_upstage()
    ctx.store.fail.clear()
    assert ctx.delete(analysis_id).status_code == 204  # 원본은 이미 없다(없는 객체 = 성공)
    _assert_gone(ctx, analysis_id)


def test_missing_objects_count_as_removed(ctx: Ctx) -> None:
    analysis_id = ctx.store.put(status="failed", content=None)  # 원본을 올리지 않은 분석
    assert ctx.delete(analysis_id).status_code == 204
    _assert_gone(ctx, analysis_id)


def test_analysis_without_documents_skips_storage(ctx: Ctx) -> None:
    analysis_id = ctx.store.put(status="failed", with_document=False)
    assert ctx.delete(analysis_id).status_code == 204
    assert ctx.store.calls == ["get_analysis", "delete_analysis"]
    _assert_gone(ctx, analysis_id)


def test_paths_and_file_ids_are_deduplicated_and_blank_ones_skipped(ctx: Ctx) -> None:
    analysis_id = ctx.store.put(status="failed", upstage_file_id="file_same")
    (doc,) = ctx.store.docs_of(analysis_id)
    for i, (path, file_id) in enumerate([(doc["storage_path"], "file_same"), ("", ""), (None, None), (5, 7)]):
        doc_id = f"00000000-0000-4000-8000-00000000000{i}"
        ctx.store.documents[doc_id] = {**doc, "id": doc_id, "storage_path": path, "upstage_file_id": file_id}
    assert ctx.delete(analysis_id).status_code == 204
    assert ctx.store.removed == [[doc["storage_path"]]]
    assert [r.url.path for r in ctx.server.calls("DELETE", "file")] == ["/v2/files/file_same"]


def test_deleted_row_count_zero_is_404_without_upstage(ctx: Ctx) -> None:
    analysis_id = ctx.store.put(status="failed", upstage_file_id="file_up_1")
    ctx.store.before_delete = lambda aid: ctx.store.analyses.pop(aid)  # 그 사이 다른 요청이 행을 지움
    response = ctx.delete(analysis_id)
    assert (response.status_code, response.json()) == (404, {"detail": MSG_NOT_FOUND})
    assert ctx.store.deleted_counts == [0]
    ctx.no_upstage()


def test_second_delete_is_404(ctx: Ctx) -> None:
    analysis_id = ctx.store.put(status="done", job_id="j")
    assert ctx.delete(analysis_id).status_code == 204
    response = ctx.delete(analysis_id)
    assert (response.status_code, response.json()) == (404, {"detail": MSG_NOT_FOUND})


@pytest.mark.parametrize("hook", ["before_remove", "before_delete"])
def test_two_deletes_at_once_are_204_and_404_never_500(ctx: Ctx, hook: str) -> None:
    analysis_id = ctx.store.put(status="done", job_id="j", upstage_file_id="file_up_1")
    settings = load_settings(FAKE_ENV)
    inner: list[Any] = []

    def other_request(*_args: Any) -> None:
        inner.append(manage.delete_analysis(ctx.store, logic_factory(ctx), settings, analysis_id))

    setattr(ctx.store, hook, other_request)
    response = ctx.delete(analysis_id)
    assert inner == [None]  # 끼어든 요청은 끝까지 지웠다(204)
    assert (response.status_code, response.json()) == (404, {"detail": MSG_NOT_FOUND})
    _assert_gone(ctx, analysis_id)
    # Upstage 파일 지우기는 행을 실제로 지운 쪽만
    assert len(ctx.server.calls("DELETE", "file")) == 1


@pytest.mark.parametrize(
    "injected",
    [
        (500, {"error": {"message": "boom"}}),
        (401, {"error": {"message": f"bad key {FAKE_UPSTAGE_KEY}"}}),
        httpx.ReadTimeout("slow"),
        httpx.ConnectTimeout("slow"),
        httpx.ConnectError("down"),
    ],
    ids=["500", "401", "read_timeout", "connect_timeout", "connect_error"],
)
def test_upstage_failures_still_204_with_a_value_free_warning(ctx: Ctx, injected: Any, caplog: pytest.LogCaptureFixture) -> None:
    analysis_id = ctx.store.put(status="failed", upstage_file_id="file_up_1")
    ctx.store.analyses[analysis_id]["name"] = "비밀이름-표식"
    ctx.store.analyses[analysis_id]["error"] = "오류원문-표식"
    ctx.server.errors[("DELETE", "file")] = injected
    with caplog.at_level(logging.DEBUG, logger="imask"):
        response = ctx.delete(analysis_id)
    assert response.status_code == 204
    _assert_gone(ctx, analysis_id)
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "Upstage 파일 삭제 실패" in logged and "file_up_1" in logged
    for value in ("비밀이름", "오류원문", FAKE_UPSTAGE_KEY, "Bearer"):
        assert value not in logged


def test_missing_upstage_settings_still_204(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    env = {k: v for k, v in FAKE_ENV.items() if not k.startswith("UPSTAGE_")}
    context = install(monkeypatch, env)
    try:
        with TestClient(app) as client:
            context.client = client
            analysis_id = context.store.put(status="failed", upstage_file_id="file_up_1")
            with caplog.at_level(logging.DEBUG, logger="imask"):
                response = context.delete(analysis_id)
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 204 and analysis_id not in context.store.analyses
    context.no_upstage()
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "Upstage 설정이 없어" in logged and "UPSTAGE_API_KEY" not in logged


def test_unexpected_cleanup_error_still_204(ctx: Ctx, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    analysis_id = ctx.store.put(status="failed", upstage_file_id="file_up_1")

    def boom(*_args: Any, **_kw: Any) -> None:
        raise RuntimeError("unexpected secret detail")

    monkeypatch.setattr(manage, "_delete_files_quietly", boom)
    with caplog.at_level(logging.DEBUG, logger="imask"):
        assert ctx.delete(analysis_id).status_code == 204
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "RuntimeError" in logged and "secret detail" not in logged


def test_without_file_ids_no_upstage_client_is_made(ctx: Ctx) -> None:
    analysis_id = ctx.store.put(status="done", job_id="j", upstage_file_id=None)
    assert ctx.delete(analysis_id).status_code == 204
    ctx.no_upstage()


def test_cleanup_uses_the_short_timeout_client(ctx: Ctx) -> None:
    analysis_id = ctx.store.put(status="failed", upstage_file_id="file_up_1")
    assert ctx.delete(analysis_id).status_code == 204
    assert ctx.made == [CLEANUP_TIMEOUT]
    timeout = ctx.clients[0]._client.timeout  # noqa: SLF001
    assert (timeout.connect, timeout.read, timeout.write, timeout.pool) == (5.0, 10.0, 10.0, 10.0)
    # 시작·조회 경로의 클라이언트는 기본 시간 제한 그대로(생성자에 timeout 을 넘기지 않음)
    other = ctx.store.put()
    assert ctx.start(other).status_code == 200
    assert ctx.made[-1] is None


@pytest.mark.parametrize("status", ["queued", "running", "done", "failed", "partial", "weird"])
def test_every_status_is_deleted_with_documents_and_review_rows(ctx: Ctx, status: str) -> None:
    analysis_id = ctx.store.put(status=status, job_id="job_1" if status in ("running", "done") else None, result=custom_result(SMALL))
    ctx.store.put_review(analysis_id, status="done", memo="메모")
    assert ctx.delete(analysis_id).status_code == 204
    _assert_gone(ctx, analysis_id)


def test_running_analysis_is_deleted_and_its_job_result_is_dropped(ctx: Ctx) -> None:
    analysis_id = ctx.store.put()
    assert ctx.start(analysis_id).status_code == 200  # 작업이 돌고 있다(취소 API 없음)
    assert ctx.delete(analysis_id).status_code == 204
    assert ctx.get(analysis_id).status_code == 404  # 그 뒤 조회는 404 — Upstage 결과는 버린다
    assert ctx.server.calls("GET", "response") == []


@pytest.mark.parametrize("analysis_id", ["not-a-uuid", "123", "00000000-0000-4000-8000-000000000000"])
def test_unknown_or_bad_ids_are_404(ctx: Ctx, analysis_id: str) -> None:
    response = ctx.delete(analysis_id)
    assert (response.status_code, response.json()) == (404, {"detail": MSG_NOT_FOUND})
    assert "remove_objects" not in ctx.store.calls and "delete_analysis" not in ctx.store.calls


def test_delete_never_updates_any_row(ctx: Ctx) -> None:
    analysis_id = ctx.store.put(status="done", job_id="j", result=custom_result(SMALL))
    ctx.store.put_review(analysis_id)
    before = copy.deepcopy(ctx.store.analyses[analysis_id])
    review_before = copy.deepcopy(ctx.store.reviews[analysis_id])
    at_delete: list[Any] = []
    ctx.store.before_delete = lambda aid: at_delete.append((copy.deepcopy(ctx.store.analyses[aid]), copy.deepcopy(ctx.store.reviews[aid])))
    assert ctx.delete(analysis_id).status_code == 204
    assert at_delete == [(before, review_before)]  # 지우기 직전까지 행(updated_at 포함)은 그대로
    assert ctx.store.updates == [] and ctx.store.review_writes == []
    assert not {"update_analysis", "update_document", "update_review", "insert_review", "claim_analysis"} & set(ctx.store.calls)


def test_request_body_is_ignored(ctx: Ctx) -> None:
    analysis_id = ctx.store.put(status="failed")
    assert ctx.delete(analysis_id, content=b'{"anything": [1, 2, 3]}').status_code == 204
    other = ctx.store.put(status="failed")
    assert ctx.delete(other, content=b"\xff not json").status_code == 204


def test_load_store_error_is_502(ctx: Ctx) -> None:
    analysis_id = ctx.store.put(status="failed")
    ctx.store.fail.add("get_analysis")
    response = ctx.delete(analysis_id)
    assert (response.status_code, response.json()) == (502, {"detail": MSG_STORE})
    assert analysis_id in ctx.store.analyses


def test_store_error_logs_carry_no_names(ctx: Ctx, caplog: pytest.LogCaptureFixture) -> None:
    analysis_id = ctx.store.put(status="failed")
    ctx.store.analyses[analysis_id]["name"] = "비밀이름-표식"
    ctx.store.fail.add("remove_objects")
    with caplog.at_level(logging.DEBUG, logger="imask"):
        assert ctx.delete(analysis_id).status_code == 502
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert analysis_id in logged and "비밀이름" not in logged


def test_get_after_delete_during_poll_is_not_500(ctx: Ctx) -> None:
    # 조회(running → 완료 반영)가 삭제와 겹침: 결과 저장 직전에 행이 지워짐 → 200(지우기 전 값) — 500 이 아니다
    analysis_id = ctx.store.put(status="running", job_id="job_1", upstage_file_id="file_up_1")
    ctx.server.last_status = "completed"
    settings = load_settings(FAKE_ENV)
    ctx.store.before_update = lambda aid, _values: manage.delete_analysis(ctx.store, logic_factory(ctx), settings, aid)
    response = ctx.get(analysis_id)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running" and body["poll_error"]
    assert ctx.get(analysis_id).status_code == 404
