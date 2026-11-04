# ==========================================================================
#  started_at·이력 순서·겹친 요청 (shared-analyses BRIEF §5.1·5.5·5.6, 네트워크 없음)
#  - started_at: 선점이 status='running' 과 같은 조건부 갱신으로 넣음, 모든 AnalysisOut 응답(만들기·시작·조회·검토 동작·
#    다시 분석)에 키가 있음, 만들기는 null
#  - 이력 순서: S1 → retry 줄들 → S2 → 그 밖 줄(저장 순서), 실제 흐름(만들기 → 실패 → 다시 분석 2번 → 완료 → 검토 동작)에서
#    at 이 줄지 않음
#  - 겹침: 검토 동작 중 분석이 지워짐 → 404(FK 위반·경쟁 패배 모두), 지워지지 않았으면 그대로 502·409,
#    /start 의 _latest_or_502 '행 없음' → 404(다시 읽기 저장소 오류는 그대로 502)
# ==========================================================================

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from api_fakes import FAKE_ENV, PDF_BYTES
from fake_reviews import ACTOR, SMALL, custom_result
from shared_ctx import ANALYSIS_KEYS, MSG_NOT_FOUND, MSG_STORE, Ctx, ctx, logic_factory  # noqa: F401

from imask_backend import manage
from imask_backend.reviews import review_block, review_scope, row_view
from imask_backend.settings import load_settings

SETTINGS = load_settings(FAKE_ENV)
MSG_REVIEW_CONFLICT = "다른 요청과 겹쳐 저장하지 못했습니다. 잠시 후 다시 시도해 주세요."
MSG_START_REREAD_FAILED = "분석 시작 결과를 확인하지 못했습니다. 잠시 후 분석 건을 다시 조회해 주세요."


def _line(n: int, kind: str, at: str = "2026-11-04T00:00:00+00:00") -> dict[str, str]:
    return {"id": f"H{n}", "at": at, "actor": "가", "kind": kind, "target": "t", "change": "c", "reason": ""}


# --- started_at -------------------------------------------------------------------------------


def test_claim_sets_started_at_in_the_same_conditional_update(ctx: Ctx) -> None:
    analysis_id = ctx.store.put()
    read_stamp = ctx.store.analyses[analysis_id]["updated_at"]
    t0 = datetime.now(UTC)
    body = ctx.start(analysis_id).json()
    t1 = datetime.now(UTC)
    claim = ctx.store.updates[0]
    assert claim[1] == {"status": "running", "started_at": claim[1]["started_at"]}
    assert claim[2] == {"expect_status": "queued", "expect_no_job": False, "expect_updated_at": read_stamp}  # v3-m1 ①
    assert t0 <= datetime.fromisoformat(claim[1]["started_at"]) <= t1
    assert body["started_at"] == claim[1]["started_at"] == ctx.store.analyses[analysis_id]["started_at"]
    # 진 선점은 started_at 도 바꾸지 못한다
    assert ctx.start(analysis_id).status_code == 409
    assert ctx.store.analyses[analysis_id]["started_at"] == claim[1]["started_at"]


def test_started_at_only_written_by_claim_and_retry(ctx: Ctx) -> None:
    analysis_id = ctx.store.put()
    ctx.start(analysis_id)
    ctx.server.last_status = "completed"
    ctx.get(analysis_id)  # 완료 반영
    writers = [values for _, values, _ in ctx.store.updates if "started_at" in values]
    assert len(writers) == 1 and writers[0]["status"] == "running"


def test_every_analysis_out_response_has_started_at(ctx: Ctx) -> None:
    created = ctx.create().json()["analysis"]
    assert set(created) == ANALYSIS_KEYS and created["started_at"] is None
    analysis_id = created["id"]
    assert ctx.get(analysis_id).json()["started_at"] is None  # 대기
    path = ctx.store.docs_of(analysis_id)[0]["storage_path"]
    ctx.store.objects[path] = PDF_BYTES
    started = ctx.start(analysis_id).json()
    assert set(started) == ANALYSIS_KEYS and isinstance(started["started_at"], str)
    got = ctx.get(analysis_id).json()
    assert set(got) == ANALYSIS_KEYS and got["started_at"] == started["started_at"]
    # 검토 동작 응답(완료 분석)
    done = ctx.store.put(status="done", job_id="j", result=custom_result(SMALL), started_at="2026-11-04T00:00:00+00:00")
    acted = ctx.act(done, "save_memo", text="m").json()["analysis"]
    assert set(acted) == ANALYSIS_KEYS and acted["started_at"] == "2026-11-04T00:00:00+00:00"
    # 다시 분석 응답
    failed = ctx.store.put(status="failed", error="e")
    retried = ctx.retry(failed).json()
    assert set(retried) == ANALYSIS_KEYS and isinstance(retried["started_at"], str)


def test_existing_rows_without_started_at_read_as_null(ctx: Ctx) -> None:
    analysis_id = ctx.store.put(status="done", job_id="j")
    del ctx.store.analyses[analysis_id]["started_at"]  # 옛 행(열이 null) 흉내
    assert ctx.get(analysis_id).json()["started_at"] is None


# --- 이력 순서 --------------------------------------------------------------------------------


def test_history_order_is_s1_retries_s2_then_the_rest() -> None:
    row = {"id": "a", "status": "done", "created_at": "2026-11-01T00:00:00+00:00", "updated_at": "2026-11-02T00:00:00+00:00", "documents": [{}], "result": custom_result(SMALL)}
    scope = review_scope(row, row_view(row))
    assert scope is not None
    stored = [_line(1, "retry"), _line(2, "confirm"), "모양이 틀린 줄", _line(3, "retry"), _line(4, "memo"), {**_line(5, "retry"), "at": 5}, _line(6, "unknown")]
    block = review_block(row, scope, {"version": 6, "history": stored})
    assert [h["id"] for h in block["history"]] == ["S1", "H1", "H3", "S2", "H2", "H4"]
    # S1·S2 내용은 그대로
    assert block["history"][0]["at"] == row["created_at"] and block["history"][3]["at"] == row["updated_at"]
    assert block["history"][3]["kind"] == "ai"


def test_history_without_retries_is_unchanged() -> None:
    row = {"id": "a", "status": "done", "created_at": "c", "updated_at": "u", "documents": [{}], "result": custom_result(SMALL)}
    scope = review_scope(row, row_view(row))
    assert scope is not None
    block = review_block(row, scope, {"version": 2, "history": [_line(1, "confirm"), _line(2, "memo")]})
    assert [h["id"] for h in block["history"]] == ["S1", "S2", "H1", "H2"]
    assert [h["id"] for h in review_block(row, scope, None)["history"]] == ["S1", "S2"]


def test_real_flow_history_times_never_go_backwards(ctx: Ctx) -> None:
    # 만들기 → 시작 실패 → 다시 분석(또 실패) → 다시 분석(성공) → 완료 → 검토 동작
    created = ctx.create(filename="대출 서류.pdf").json()
    analysis_id = created["analysis"]["id"]
    ctx.store.objects[created["upload"]["path"]] = PDF_BYTES
    ctx.server.errors[("POST", "responses")] = (500, {"error": {"message": "busy"}})
    assert ctx.start(analysis_id).json()["status"] == "failed"
    assert ctx.retry(analysis_id).json()["status"] == "failed"
    del ctx.server.errors[("POST", "responses")]
    assert ctx.retry(analysis_id).json()["status"] == "running"
    ctx.server.last_status = "completed"
    done = ctx.get(analysis_id).json()
    assert done["status"] == "done" and done["review"] is not None
    assert ctx.act(analysis_id, "save_memo", text="확인").status_code == 200
    history = ctx.get(analysis_id).json()["review"]["history"]
    assert [(h["id"], h["kind"]) for h in history] == [("S1", "request"), ("H1", "retry"), ("H2", "retry"), ("S2", "ai"), ("H3", "memo")]
    times = [datetime.fromisoformat(h["at"]) for h in history]
    assert times == sorted(times)
    assert history[1]["target"] == "대출 서류.pdf" and history[1]["actor"] == ACTOR
    assert history[1]["reason"].startswith("Upstage 분석을 시작하지 못했습니다") and history[2]["reason"] == history[1]["reason"]


# --- 겹침: 검토 동작 -----------------------------------------------------------------------------


def _done(ctx: Ctx) -> str:
    return ctx.store.put(status="done", job_id="j", result=custom_result(SMALL))


def _delete_hook(store: Any, analysis_id: str) -> None:
    store.delete_analysis(analysis_id)  # 쓰기 직전에 다른 요청이 분석을 지움(cascade)


def test_review_action_on_an_analysis_deleted_before_the_insert_is_404(ctx: Ctx) -> None:
    analysis_id = _done(ctx)
    ctx.store.review_hooks = [_delete_hook]
    response = ctx.act(analysis_id, "save_memo", text="m")
    assert (response.status_code, response.json()) == (404, {"detail": MSG_NOT_FOUND})
    assert analysis_id not in ctx.store.reviews


def test_review_action_on_an_analysis_deleted_before_the_update_is_404(ctx: Ctx) -> None:
    analysis_id = _done(ctx)
    ctx.store.put_review(analysis_id)
    ctx.store.review_hooks = [_delete_hook]
    response = ctx.act(analysis_id, "save_memo", text="m")
    assert (response.status_code, response.json()) == (404, {"detail": MSG_NOT_FOUND})
    # update(바뀐 행 없음) → 다시 읽기(행 없음) → insert(FK 위반) → 분석 다시 읽기(없음) → 404
    assert [w[0] for w in ctx.store.review_writes] == ["update_review", "insert_review"]


def test_review_action_losing_three_races_then_deleted_is_404(ctx: Ctx) -> None:
    analysis_id = _done(ctx)
    ctx.store.put_review(analysis_id)

    def bump(store: Any, aid: str) -> None:
        store.reviews[aid]["version"] += 1

    def bump_and_delete(store: Any, aid: str) -> None:
        bump(store, aid)
        store.analyses.pop(aid)  # 행만(검토 행은 아직) — 경쟁 패배 뒤 다시 읽기가 '없음'

    ctx.store.review_hooks = [bump, bump, bump_and_delete]
    response = ctx.act(analysis_id, "save_memo", text="m")
    assert (response.status_code, response.json()) == (404, {"detail": MSG_NOT_FOUND})


def test_review_action_losing_three_races_on_a_live_analysis_stays_409(ctx: Ctx) -> None:
    analysis_id = _done(ctx)
    ctx.store.put_review(analysis_id)

    def bump(store: Any, aid: str) -> None:
        store.reviews[aid]["version"] += 1

    ctx.store.review_hooks = [bump, bump, bump]
    response = ctx.act(analysis_id, "save_memo", text="m")
    assert (response.status_code, response.json()) == (409, {"detail": MSG_REVIEW_CONFLICT})


def test_review_write_store_error_on_a_live_analysis_stays_502(ctx: Ctx) -> None:
    analysis_id = _done(ctx)
    ctx.store.fail.add("insert_review")
    response = ctx.act(analysis_id, "save_memo", text="m")
    assert (response.status_code, response.json()) == (502, {"detail": MSG_STORE})


def test_review_write_store_error_with_a_failed_reread_stays_502(ctx: Ctx) -> None:
    analysis_id = _done(ctx)
    ctx.store.fail.add("insert_review")
    ctx.store.fail_get_calls = {2}  # 1 = 처음 읽기, 2 = 쓰기 실패 뒤 다시 읽기
    response = ctx.act(analysis_id, "save_memo", text="m")
    assert (response.status_code, response.json()) == (502, {"detail": MSG_STORE})


def test_review_conflict_with_a_failed_reread_stays_409(ctx: Ctx) -> None:
    analysis_id = _done(ctx)
    ctx.store.put_review(analysis_id)

    def bump(store: Any, aid: str) -> None:
        store.reviews[aid]["version"] += 1

    ctx.store.review_hooks = [bump, bump, bump]
    ctx.store.fail_get_calls = {2}
    assert ctx.act(analysis_id, "save_memo", text="m").status_code == 409


# --- 겹침: 시작 --------------------------------------------------------------------------------


def test_start_losing_the_job_save_to_a_delete_is_404(ctx: Ctx) -> None:
    analysis_id = ctx.store.put()
    original = ctx.store.update_analysis

    def update(aid: str, values: Any, **kw: Any) -> Any:
        if "upstage_job_id" in values:  # job id 저장 직전에 다른 요청이 지움
            manage.delete_analysis(ctx.store, logic_factory(ctx), SETTINGS, aid)
        return original(aid, values, **kw)

    ctx.store.update_analysis = update  # type: ignore[method-assign]
    response = ctx.start(analysis_id)
    assert (response.status_code, response.json()) == (404, {"detail": MSG_NOT_FOUND})
    assert ctx.server.deleted == ["file_fake1"]  # 작업으로 이어지지 않은 파일은 지운다


def test_start_losing_the_failure_record_to_a_delete_is_404(ctx: Ctx) -> None:
    analysis_id = ctx.store.put(content=None)  # 원본 없음 → 실패 기록
    original = ctx.store.update_analysis

    def update(aid: str, values: Any, **kw: Any) -> Any:
        if values.get("status") == "failed":
            ctx.store.analyses.pop(aid)
        return original(aid, values, **kw)

    ctx.store.update_analysis = update  # type: ignore[method-assign]
    response = ctx.start(analysis_id)
    assert (response.status_code, response.json()) == (404, {"detail": MSG_NOT_FOUND})


def test_start_reread_store_error_is_still_502(ctx: Ctx) -> None:
    analysis_id = ctx.store.put(content=None)
    original = ctx.store.update_analysis

    def update(aid: str, values: Any, **kw: Any) -> Any:
        if values.get("status") == "failed":
            ctx.store.analyses[aid]["status"] = "done"  # 다른 요청이 먼저 바꿈
        return original(aid, values, **kw)

    ctx.store.update_analysis = update  # type: ignore[method-assign]
    ctx.store.fail_get_calls = {2}
    response = ctx.start(analysis_id)
    assert (response.status_code, response.json()) == (502, {"detail": MSG_START_REREAD_FAILED})


@pytest.mark.parametrize("status", ["done", "failed", "queued"])
def test_get_after_delete_is_404(ctx: Ctx, status: str) -> None:
    analysis_id = ctx.store.put(status=status, job_id="j" if status == "done" else None)
    assert ctx.delete(analysis_id).status_code == 204
    assert ctx.get(analysis_id).status_code == 404
    assert ctx.client.get(f"/api/py/analyses/{analysis_id}/file").status_code == 404
