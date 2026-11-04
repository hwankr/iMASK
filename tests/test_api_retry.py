# ==========================================================================
#  POST /api/py/analyses/{id}/retry — 실패한 분석을 같은 원본으로 진짜 다시 분석 (shared-analyses BRIEF §5.4·5.6, 네트워크 없음)
#  - 본문 표(413·400 형식·actor 규칙·키 더함/빠짐), 오류 순서(413 → 400 → 404 → 409 → 500), 상태 표
#  - 되돌리기 값(조건 status=failed)·되돌리기 패배(404 / 409 두 문구 / 502), 설정 빠짐 500(아무것도 안 바뀜·Upstage 없음)
#  - 이력 한 줄(id·at·actor·kind·target·change·reason, 안전화·자르기, 파일 이름 없음 → '분석 건', version 1 / +1,
#    마지막 줄보다 앞서지 않는 at), 이력 쓰기 실패·3번 경쟁·1000줄·틀린 version 이어도 다시 분석 계속
#  - 원본 없음 → 200 failed(Upstage 호출 0), 성공 → 200 running(올리기 1·작업 1, started_at 새 값), 시작 409 → '이미 분석하고 있습니다.'
#  - 동시에 두 번 → 작업 1개, 다시 분석 직후·도중 삭제, 응답이 조회와 같은 모양
# ==========================================================================

from __future__ import annotations

import copy
import json
import logging
from datetime import UTC, datetime
from typing import Any

import pytest
from api_fakes import FAKE_ENV
from fake_reviews import ACTOR, SMALL, custom_result
from fastapi.testclient import TestClient
from shared_ctx import (  # noqa: F401
    ANALYSIS_KEYS,
    MSG_BAD_ACTOR,
    MSG_BUSY,
    MSG_FILE_MISSING,
    MSG_FORMAT,
    MSG_NOT_FOUND,
    MSG_ONLY_FAILED,
    MSG_RETRY_CONFLICT,
    MSG_STORE,
    MSG_TOO_LARGE,
    RETRY_CHANGE,
    Ctx,
    ctx,
    install,
    logic_factory,
)

from api.index import app
from imask_backend import manage
from imask_backend.analyses import start_analysis
from imask_backend.reviews import MAX_BODY_BYTES
from imask_backend.settings import load_settings

PREVIOUS_ERROR = "Upstage 분석을 시작하지 못했습니다: 파일 올리기: HTTP 403 — No access to file"
SETTINGS = load_settings(FAKE_ENV)


def _failed(ctx: Ctx, **kw: Any) -> str:
    kw.setdefault("error", PREVIOUS_ERROR)
    return ctx.store.put(status="failed", **kw)


def _parse(at: str) -> datetime:
    return datetime.fromisoformat(at)


# --- 본문 ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b" ",
        b"null",
        b"[]",
        b'["actor"]',
        b'"x"',
        b"1",
        b"{}",
        b'{"actor": 1}',
        b'{"actor": null}',
        b'{"actor": true}',
        b'{"actor": ["a"]}',
        b'{"actor": {"name": "a"}}',
        b'{"actor": "a", "x": 1}',
        b'{"actor": "a", "reason": ""}',
        b'{"Actor": "a"}',
        b'{"name": "a"}',
        b'{"actor": "a", "actor": "b"}',
        b'{"actor": NaN}',
        b'{"actor": "a", "n": Infinity}',
        b'{"actor": "a"',
        b'{"actor": "a"}x',
        b"\xff\xfe{}",
        b'{"actor": "\xed\xa0\x80"}',  # UTF-8 로 쓴 서로게이트(올바른 UTF-8 아님)
        b'{"actor": ' + b"[" * 30000,
    ],
)
def test_bad_bodies_are_400(ctx: Ctx, raw: bytes) -> None:
    analysis_id = _failed(ctx)
    response = ctx.retry(analysis_id, raw)
    assert (response.status_code, response.json()) == (400, {"detail": MSG_FORMAT})
    assert ctx.store.calls == []  # 본문 검사가 먼저 — 저장소를 읽지도 않는다
    ctx.no_upstage()


@pytest.mark.parametrize(
    "actor",
    ["", " ", " a", "a ", "　a", "a" * 41, "a\nb", "\t", "\u0000", "a\u0007", "\ud800", "a\udfffb", "\u007f"],
)
def test_bad_actor_is_400_with_its_own_message(ctx: Ctx, actor: str) -> None:
    analysis_id = _failed(ctx)
    response = ctx.retry(analysis_id, {"actor": actor})
    assert (response.status_code, response.json()) == (400, {"detail": MSG_BAD_ACTOR})
    assert ctx.store.calls == []


@pytest.mark.parametrize("actor", ["a" * 40, ACTOR, "😀" * 40, "검토 담당 1"])
def test_good_actors_are_accepted(ctx: Ctx, actor: str) -> None:
    analysis_id = _failed(ctx)
    response = ctx.retry(analysis_id, {"actor": actor})
    assert response.status_code == 200
    assert ctx.store.reviews[analysis_id]["history"][-1]["actor"] == actor


def test_body_over_the_limit_is_413(ctx: Ctx) -> None:
    analysis_id = _failed(ctx)
    raw = b'{"actor": "a"}' + b" " * (MAX_BODY_BYTES + 1 - len(b'{"actor": "a"}'))
    response = ctx.retry(analysis_id, raw)
    assert (response.status_code, response.json()) == (413, {"detail": MSG_TOO_LARGE})
    assert ctx.store.calls == []


def test_big_content_length_is_413(ctx: Ctx) -> None:
    analysis_id = _failed(ctx)
    response = ctx.retry(analysis_id, b'{"actor": "a"}', headers={"content-length": "99999999999999999999"})
    assert response.status_code == 413


def test_body_of_exactly_the_limit_is_accepted(ctx: Ctx) -> None:
    analysis_id = _failed(ctx)
    raw = b'{"actor": "a"}' + b" " * (MAX_BODY_BYTES - len(b'{"actor": "a"}'))
    assert len(raw) == MAX_BODY_BYTES
    assert ctx.retry(analysis_id, raw).status_code == 200


def test_parse_retry_body_directly() -> None:
    assert manage.parse_retry_body(b'{"actor": "a"}') == "a"
    for raw in (b'{"actor": "a", "b": 1}', b"{}", b"[]"):
        with pytest.raises(manage.ApiError) as info:
            manage.parse_retry_body(raw)
        assert info.value.detail == MSG_FORMAT
    with pytest.raises(manage.ApiError) as info:
        manage.parse_retry_body(b'{"actor": " a"}')
    assert info.value.detail == MSG_BAD_ACTOR


# --- 오류 순서·상태 -----------------------------------------------------------------------------


def test_error_order(monkeypatch: pytest.MonkeyPatch) -> None:
    env = {k: v for k, v in FAKE_ENV.items() if not k.startswith("UPSTAGE_")}
    context = install(monkeypatch, env)
    try:
        with TestClient(app) as client:
            context.client = client
            unknown = "00000000-0000-4000-8000-000000000000"
            too_big = b"[" * (MAX_BODY_BYTES + 1)
            assert context.retry(unknown, too_big).status_code == 413  # 413 이 400 보다 먼저
            assert context.retry(unknown, b"{}").status_code == 400  # 400 이 404 보다 먼저
            assert context.retry(unknown, {"actor": " x"}).json() == {"detail": MSG_BAD_ACTOR}
            assert context.retry("not-a-uuid").json() == {"detail": MSG_NOT_FOUND}
            assert context.retry(unknown).json() == {"detail": MSG_NOT_FOUND}  # 404 가 409 보다 먼저
            done = context.store.put(status="done", job_id="j")
            assert context.retry(done).json() == {"detail": MSG_ONLY_FAILED}  # 409 가 500(설정) 보다 먼저
            failed = context.store.put(status="failed", error=PREVIOUS_ERROR)
            before = copy.deepcopy(context.store.analyses[failed])
            response = context.retry(failed)
            assert response.status_code == 500
            assert response.json() == {"detail": "서버 설정이 빠졌습니다: UPSTAGE_API_KEY, UPSTAGE_AGENT_ID, UPSTAGE_CONFIG_ID"}
            # 아무것도 바꾸지 않은 채
            assert context.store.analyses[failed] == before
            assert context.store.updates == [] and context.store.review_writes == []
    finally:
        app.dependency_overrides.clear()
    context.no_upstage()


@pytest.mark.parametrize(
    ("status", "detail"),
    [
        ("queued", MSG_BUSY),
        ("running", MSG_BUSY),
        ("done", MSG_ONLY_FAILED),
        ("partial", MSG_ONLY_FAILED),
        ("weird", MSG_ONLY_FAILED),
        (None, MSG_ONLY_FAILED),
    ],
)
def test_status_table(ctx: Ctx, status: Any, detail: str) -> None:
    analysis_id = ctx.store.put(status=status, job_id="job_1" if status == "running" else None)
    before = copy.deepcopy(ctx.store.analyses[analysis_id])
    response = ctx.retry(analysis_id)
    assert (response.status_code, response.json()) == (409, {"detail": detail})
    assert ctx.store.analyses[analysis_id] == before
    assert ctx.store.updates == [] and ctx.store.review_writes == []
    ctx.no_upstage()


def test_load_store_error_is_502(ctx: Ctx) -> None:
    analysis_id = _failed(ctx)
    ctx.store.fail.add("get_analysis")
    response = ctx.retry(analysis_id)
    assert (response.status_code, response.json()) == (502, {"detail": MSG_STORE})
    ctx.no_upstage()


# --- 되돌리기 ---------------------------------------------------------------------------------


def test_revert_is_one_conditional_update_with_the_contract_values(ctx: Ctx) -> None:
    analysis_id = _failed(ctx, job_id="job_old", result={"format": "imask-upstage-v1", "summary": {}})
    read_stamp = ctx.store.analyses[analysis_id]["updated_at"]
    seen: list[dict[str, Any]] = []
    ctx.store.before_update = lambda aid, values: seen.append(dict(values))
    t0 = datetime.now(UTC)
    assert ctx.retry(analysis_id).status_code == 200
    t1 = datetime.now(UTC)
    (values,) = seen
    assert set(values) == {"status", "error", "result", "upstage_job_id", "started_at"}
    assert {k: v for k, v in values.items() if k != "started_at"} == {"status": "queued", "error": None, "result": None, "upstage_job_id": None}
    assert t0 <= _parse(values["started_at"]) <= t1 and _parse(values["started_at"]).utcoffset().total_seconds() == 0
    # 처음 읽은 실행에만(updated_at = 처음 읽은 값 — V-T1-1 M2)
    assert ctx.store.updates[0][2] == {"expect_status": "failed", "expect_no_job": False, "expect_updated_at": read_stamp}
    # 그 다음은 기존 시작 경로: 선점(queued → running) → job id 저장(running, job 없음, updated_at = 선점이 돌려준 값)
    # 선점은 되돌리기가 돌려준 updated_at 을 읽은 행에만(v3-m1 ①)
    assert ctx.store.updates[1][1]["status"] == "running"
    assert ctx.store.updates[1][2] == {"expect_status": "queued", "expect_no_job": False, "expect_updated_at": ctx.store.update_stamps[0]}
    assert ctx.store.updates[2][2] == {"expect_status": "running", "expect_no_job": True, "expect_updated_at": ctx.store.update_stamps[1]}
    assert ctx.store.analyses[analysis_id]["upstage_job_id"] == "job_fake2"


@pytest.mark.parametrize(
    ("change", "status", "detail"),
    [
        ("delete", 404, MSG_NOT_FOUND),
        ("queued", 409, MSG_BUSY),
        ("running", 409, MSG_BUSY),
        ("done", 409, MSG_RETRY_CONFLICT),
        ("partial", 409, MSG_RETRY_CONFLICT),
    ],
)
def test_losing_the_revert_rereads(ctx: Ctx, change: str, status: int, detail: str) -> None:
    analysis_id = _failed(ctx)

    def other_request(aid: str, _values: Any) -> None:
        if change == "delete":
            ctx.store.analyses.pop(aid)
        else:
            ctx.store.analyses[aid]["status"] = change

    ctx.store.before_update = other_request
    response = ctx.retry(analysis_id)
    assert (response.status_code, response.json()) == (status, {"detail": detail})
    assert ctx.store.review_writes == []  # 이력도 쓰지 않는다
    ctx.no_upstage()


def test_losing_the_revert_with_a_failed_reread_is_502(ctx: Ctx) -> None:
    analysis_id = _failed(ctx)
    ctx.store.before_update = lambda aid, _values: ctx.store.analyses[aid].update(status="running")
    ctx.store.fail_get_calls = {2}  # 1 = 처음 읽기, 2 = 진 뒤 다시 읽기
    response = ctx.retry(analysis_id)
    assert (response.status_code, response.json()) == (502, {"detail": MSG_STORE})
    ctx.no_upstage()


# --- 이력 한 줄 --------------------------------------------------------------------------------


def test_history_line_creates_the_review_row_at_version_1(ctx: Ctx) -> None:
    analysis_id = _failed(ctx, filename="대출 서류.pdf")
    t0 = datetime.now(UTC)
    assert ctx.retry(analysis_id).status_code == 200
    t1 = datetime.now(UTC)
    row = ctx.store.reviews[analysis_id]
    assert row["version"] == 1 and row["status"] == "needed"
    assert (row["memo"], row["memo_at"], row["reviewer"], row["reviewed_at"], row["completion_note"], row["findings"]) == ("", None, "", None, "", {})
    (line,) = row["history"]
    assert list(line) == ["id", "at", "actor", "kind", "target", "change", "reason"]
    assert {k: v for k, v in line.items() if k != "at"} == {
        "id": "H1",
        "actor": ACTOR,
        "kind": "retry",
        "target": "대출 서류.pdf",
        "change": RETRY_CHANGE,
        "reason": PREVIOUS_ERROR,
    }
    assert t0 <= _parse(line["at"]) <= t1
    (write,) = ctx.store.review_writes
    assert write[0] == "insert_review"


def test_history_line_appends_to_an_existing_row_and_keeps_other_columns(ctx: Ctx) -> None:
    analysis_id = _failed(ctx)
    old = [{"id": "H1", "at": "2026-11-01T00:00:00+00:00", "actor": "가", "kind": "retry", "target": "t", "change": "c", "reason": ""}]
    ctx.store.put_review(analysis_id, version=2, memo="메모", findings={"k": {"status": "open"}}, history=old + ["모양이 틀린 줄"])
    before = copy.deepcopy(ctx.store.reviews[analysis_id])
    assert ctx.retry(analysis_id).status_code == 200
    after = ctx.store.reviews[analysis_id]
    assert after["version"] == 3
    assert after["history"][:2] == before["history"]  # 틀린 줄도 지우지 않는다
    assert after["history"][2]["id"] == "H3" and after["history"][2]["kind"] == "retry"
    assert {k: after[k] for k in ("status", "memo", "findings", "reviewer", "completion_note")} == {
        k: before[k] for k in ("status", "memo", "findings", "reviewer", "completion_note")
    }
    (write,) = ctx.store.review_writes
    assert write[0] == "update_review" and write[3] == 2 and set(write[2]) == {"history", "version"}


def test_history_at_is_not_before_the_last_line(ctx: Ctx) -> None:
    analysis_id = _failed(ctx)
    future = "2099-01-01T00:00:00+00:00"
    old = [{"id": "H1", "at": future, "actor": "가", "kind": "retry", "target": "t", "change": "c", "reason": ""}]
    ctx.store.put_review(analysis_id, history=old)
    assert ctx.retry(analysis_id).status_code == 200
    assert ctx.store.reviews[analysis_id]["history"][-1]["at"] == future


@pytest.mark.parametrize(
    ("filename", "target"),
    [
        ("a\ud800b\x00c.pdf", "a�b�c.pdf"),
        ("가" * 200, "가" * 200),
        ("가" * 201, "가" * 199 + "…"),
        ("x" * 250 + ".pdf", "x" * 199 + "…"),
        ("", "분석 건"),
        ("   ", "분석 건"),
        (None, "분석 건"),
        (5, "분석 건"),
    ],
)
def test_history_target_is_the_safe_filename(ctx: Ctx, filename: Any, target: str) -> None:
    analysis_id = _failed(ctx)
    ctx.store.docs_of(analysis_id)[0]["filename"] = filename
    assert ctx.retry(analysis_id).status_code == 200
    assert ctx.store.reviews[analysis_id]["history"][-1]["target"] == target


def test_history_target_without_documents_is_the_analysis(ctx: Ctx) -> None:
    analysis_id = _failed(ctx, with_document=False)
    response = ctx.retry(analysis_id)
    assert response.status_code == 200 and response.json()["status"] == "failed"
    assert ctx.store.reviews[analysis_id]["history"][-1]["target"] == "분석 건"


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        ("짧은 이유", "짧은 이유"),
        ("x" * 500, "x" * 500),
        ("x" * 501, "x" * 499 + "…"),
        ("오류\ud800\x00끝", "오류��끝"),
        (None, ""),
        (5, ""),
    ],
)
def test_history_reason_is_the_safe_previous_error(ctx: Ctx, error: Any, reason: str) -> None:
    analysis_id = _failed(ctx, error=error)
    assert ctx.retry(analysis_id).status_code == 200
    assert ctx.store.reviews[analysis_id]["history"][-1]["reason"] == reason


def _assert_retry_went_on(ctx: Ctx, response: Any) -> None:
    assert response.status_code == 200 and response.json()["status"] == "running"
    assert len(ctx.server.calls("POST", "responses")) == 1


def test_history_store_error_does_not_stop_the_retry(ctx: Ctx, caplog: pytest.LogCaptureFixture) -> None:
    analysis_id = _failed(ctx)
    ctx.store.analyses[analysis_id]["name"] = "비밀이름-표식"
    ctx.store.fail.add("insert_review")
    with caplog.at_level(logging.DEBUG, logger="imask"):
        response = ctx.retry(analysis_id)
    _assert_retry_went_on(ctx, response)
    assert analysis_id not in ctx.store.reviews
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "다시 분석 이력을 저장하지 못함" in logged
    for value in ("비밀이름", PREVIOUS_ERROR, ACTOR):
        assert value not in logged


def test_history_read_error_does_not_stop_the_retry(ctx: Ctx) -> None:
    analysis_id = _failed(ctx)
    ctx.store.fail.add("get_review")
    _assert_retry_went_on(ctx, ctx.retry(analysis_id))


def test_losing_three_history_races_does_not_stop_the_retry(ctx: Ctx, caplog: pytest.LogCaptureFixture) -> None:
    analysis_id = _failed(ctx)
    ctx.store.put_review(analysis_id, version=1)

    def bump(store: Any, aid: str) -> None:
        store.reviews[aid]["version"] += 1

    ctx.store.review_hooks = [bump, bump, bump]
    with caplog.at_level(logging.DEBUG, logger="imask"):
        response = ctx.retry(analysis_id)
    _assert_retry_went_on(ctx, response)
    assert [w[0] for w in ctx.store.review_writes] == ["update_review"] * 3
    assert ctx.store.reviews[analysis_id]["history"] == [] and ctx.store.reviews[analysis_id]["version"] == 4
    assert "계속 겹쳐" in "\n".join(r.getMessage() for r in caplog.records)


def test_full_history_does_not_stop_the_retry(ctx: Ctx) -> None:
    analysis_id = _failed(ctx)
    line = {"id": "H1", "at": "2026-11-01T00:00:00+00:00", "actor": "가", "kind": "memo", "target": "t", "change": "c", "reason": ""}
    ctx.store.put_review(analysis_id, version=1000, history=[line] * 1000)
    _assert_retry_went_on(ctx, ctx.retry(analysis_id))
    assert len(ctx.store.reviews[analysis_id]["history"]) == 1000 and ctx.store.review_writes == []


def test_bad_review_version_does_not_stop_the_retry(ctx: Ctx) -> None:
    analysis_id = _failed(ctx)
    ctx.store.put_review(analysis_id, version=0)
    _assert_retry_went_on(ctx, ctx.retry(analysis_id))
    assert ctx.store.review_writes == []


def test_unexpected_history_error_does_not_stop_the_retry(ctx: Ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    analysis_id = _failed(ctx)

    def boom(*_args: Any, **_kw: Any) -> None:
        raise RuntimeError("x")

    monkeypatch.setattr(manage, "append_history_line", boom)
    _assert_retry_went_on(ctx, ctx.retry(analysis_id))


# --- 시작 --------------------------------------------------------------------------------------


def test_success_starts_a_new_job_with_a_new_started_at(ctx: Ctx) -> None:
    analysis_id = _failed(ctx, filename="대출 서류.pdf", job_id="job_old")
    ctx.store.analyses[analysis_id]["started_at"] = "2026-11-01T00:00:00+00:00"
    t0 = datetime.now(UTC)
    response = ctx.retry(analysis_id)
    t1 = datetime.now(UTC)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == ANALYSIS_KEYS
    assert body["status"] == "running" and body["error"] is None and body["result"] is None
    assert body["upstage_job_id"] == "job_fake2" and body["documents"][0]["upstage_file_id"] == "file_fake1"
    assert body["review"] is None and body["upstage_status"] is None and body["poll_error"] is None
    assert t0 <= _parse(body["started_at"]) <= t1
    assert len(ctx.server.calls("POST", "files")) == 1 and len(ctx.server.calls("POST", "responses")) == 1
    assert ctx.server.calls("DELETE", "file") == [] and ctx.made == [None]
    # 다시 분석 중에 또 누르면 409
    again = ctx.retry(analysis_id)
    assert (again.status_code, again.json()) == (409, {"detail": MSG_BUSY})
    assert len(ctx.server.calls("POST", "responses")) == 1


def test_response_has_the_same_shape_as_get(ctx: Ctx) -> None:
    analysis_id = _failed(ctx)
    retried = ctx.retry(analysis_id).json()
    got = ctx.get(analysis_id).json()  # 조회는 running 이라 Upstage 상태를 한 번 본다
    assert got["upstage_status"] == "in_progress"
    assert retried == {**got, "upstage_status": None}


def test_missing_original_is_200_failed_without_upstage_calls(ctx: Ctx) -> None:
    analysis_id = _failed(ctx, content=None)
    response = ctx.retry(analysis_id)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed" and body["error"] == MSG_FILE_MISSING and body["review"] is None
    assert body["started_at"] is not None
    assert ctx.server.requests == []
    assert ctx.store.reviews[analysis_id]["history"][-1]["reason"] == PREVIOUS_ERROR
    # 다시 실패한 분석은 또 다시 분석할 수 있다(이력 version 이 늘어난다)
    assert ctx.retry(analysis_id).status_code == 200
    assert [h["id"] for h in ctx.store.reviews[analysis_id]["history"]] == ["H1", "H2"]
    assert ctx.store.reviews[analysis_id]["history"][-1]["reason"] == MSG_FILE_MISSING


def test_start_losing_the_claim_is_reported_as_busy(ctx: Ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    analysis_id = _failed(ctx)
    monkeypatch.setattr(ctx.store, "claim_analysis", lambda aid, **kw: None)  # 그 사이 다른 요청이 선점
    response = ctx.retry(analysis_id)
    assert (response.status_code, response.json()) == (409, {"detail": MSG_BUSY})
    assert ctx.server.requests == []


def test_two_retries_at_once_make_one_job(ctx: Ctx) -> None:
    analysis_id = _failed(ctx)
    inner: list[dict[str, Any]] = []

    def other_request(aid: str, _values: Any) -> None:
        # 이 요청의 되돌리기 직전에 다른 다시 분석이 끝까지 간다
        inner.append(manage.retry_analysis(ctx.store, logic_factory(ctx), SETTINGS, aid, "다른 사람"))

    ctx.store.before_update = other_request
    response = ctx.retry(analysis_id)
    assert (response.status_code, response.json()) == (409, {"detail": MSG_BUSY})
    assert inner[0]["status"] == "running"
    assert len(ctx.server.calls("POST", "responses")) == 1 and len(ctx.server.calls("POST", "files")) == 1
    assert [h["actor"] for h in ctx.store.reviews[analysis_id]["history"]] == ["다른 사람"]


def test_retry_and_start_racing_claim_once(ctx: Ctx) -> None:
    analysis_id = _failed(ctx)
    original = ctx.store.claim_analysis
    started: list[str] = []

    def claim(aid: str, **kw: Any) -> Any:
        if not started:  # 다시 분석의 선점 직전에 /start(같은 업무 로직)가 먼저 선점해 작업을 만든다
            started.append("in")
            started.append(start_analysis(ctx.store, logic_factory(ctx), SETTINGS, aid)["status"])
        return original(aid, **kw)

    ctx.store.claim_analysis = claim  # type: ignore[method-assign]
    response = ctx.retry(analysis_id)
    assert started == ["in", "running"]
    assert (response.status_code, response.json()) == (409, {"detail": MSG_BUSY})
    assert len(ctx.server.calls("POST", "responses")) == 1


def test_delete_right_after_retry(ctx: Ctx) -> None:
    analysis_id = _failed(ctx)
    assert ctx.retry(analysis_id).status_code == 200
    assert ctx.delete(analysis_id).status_code == 204
    assert ctx.get(analysis_id).status_code == 404
    assert [r.url.path for r in ctx.server.calls("DELETE", "file")] == ["/v2/files/file_fake1"]


def test_delete_while_the_retry_is_starting_ends_404_and_cleans_its_upload(ctx: Ctx) -> None:
    analysis_id = _failed(ctx)
    original = ctx.store.update_document

    def update_document(document_id: str, values: Any, **kw: Any) -> bool:
        # 파일을 올린 직후(file id 저장 전) 다른 요청이 분석을 지운다
        manage.delete_analysis(ctx.store, logic_factory(ctx), SETTINGS, analysis_id)
        return original(document_id, values, **kw)

    ctx.store.update_document = update_document  # type: ignore[method-assign]
    response = ctx.retry(analysis_id)
    assert (response.status_code, response.json()) == (404, {"detail": MSG_NOT_FOUND})
    # 자기가 올린 Upstage 파일을 지운다(작업으로 이어지지 않음). 문서 file id 저장(비교 후 교환)이 져서 작업도 만들지 않는다
    assert ctx.server.deleted == ["file_fake1"]
    assert ctx.server.job_bodies == []
    assert ctx.get(analysis_id).status_code == 404


@pytest.mark.parametrize("after", ["claim", "download"])
def test_delete_after_the_revert_ends_404_never_500(ctx: Ctx, after: str) -> None:
    analysis_id = _failed(ctx)
    if after == "claim":
        original_claim = ctx.store.claim_analysis

        def claim(aid: str, **kw: Any) -> Any:
            manage.delete_analysis(ctx.store, logic_factory(ctx), SETTINGS, aid)
            return original_claim(aid, **kw)

        ctx.store.claim_analysis = claim  # type: ignore[method-assign]
    else:
        original_download = ctx.store.download

        def download(path: str) -> Any:
            manage.delete_analysis(ctx.store, logic_factory(ctx), SETTINGS, analysis_id)
            return original_download(path)

        ctx.store.download = download  # type: ignore[method-assign]
    response = ctx.retry(analysis_id)
    # claim: 선점이 짐 → 다시 읽어 행이 없으면 404 / download: 원본 없음 → 실패 기록에 짐 → 다시 읽기 '행 없음' → 404
    assert (response.status_code, response.json()) == (404, {"detail": MSG_NOT_FOUND})
    assert ctx.server.calls("POST", "responses") == []


def test_losing_the_claim_with_a_failed_reread_stays_busy(ctx: Ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    analysis_id = _failed(ctx)
    monkeypatch.setattr(ctx.store, "claim_analysis", lambda aid, **kw: None)
    ctx.store.fail_get_calls = {3}  # 1 = 다시 분석의 읽기, 2 = 시작의 읽기, 3 = 선점에 진 뒤 다시 읽기
    response = ctx.retry(analysis_id)
    assert (response.status_code, response.json()) == (409, {"detail": MSG_BUSY})


def test_retry_logic_accepts_a_fixed_clock(ctx: Ctx) -> None:
    analysis_id = _failed(ctx)
    fixed = datetime(2026, 11, 4, 1, 2, 3, tzinfo=UTC)
    seen: list[dict[str, Any]] = []
    ctx.store.before_update = lambda aid, values: seen.append(dict(values))
    row = manage.retry_analysis(ctx.store, logic_factory(ctx), SETTINGS, analysis_id, ACTOR, now=lambda: fixed)
    assert seen[0]["started_at"] == "2026-11-04T01:02:03+00:00"
    assert ctx.store.reviews[analysis_id]["history"][-1]["at"] == "2026-11-04T01:02:03+00:00"
    assert row["status"] == "running"


def test_retry_body_and_result_never_reach_the_logs(ctx: Ctx, caplog: pytest.LogCaptureFixture) -> None:
    analysis_id = _failed(ctx, filename="비밀파일-표식.pdf")
    ctx.store.fail.add("insert_review")
    with caplog.at_level(logging.DEBUG, logger="imask"):
        ctx.retry(analysis_id, {"actor": "비밀처리자"})
    logged = "\n".join(r.getMessage() for r in caplog.records)
    for value in ("비밀파일", "비밀처리자", PREVIOUS_ERROR):
        assert value not in logged


def test_retry_response_with_an_unpaired_surrogate_name_is_ascii_escaped(ctx: Ctx) -> None:
    # 다시 분석 응답 본문은 _json_out 을 지난다 — 짝 없는 서로게이트 이름이면 ASCII escape
    analysis_id = _failed(ctx)
    ctx.store.analyses[analysis_id]["name"] = "이름\ud800"
    response = ctx.retry(analysis_id)
    assert response.status_code == 200 and response.content.isascii() and b"\\ud800" in response.content
    assert json.loads(response.content)["name"] == "이름\ud800"


def test_review_block_of_a_retried_then_done_analysis(ctx: Ctx) -> None:
    analysis_id = _failed(ctx)
    assert ctx.retry(analysis_id).status_code == 200
    # Upstage 가 끝났다고 가정하고 결과를 넣는다(완료 반영은 조회 경로가 한다 — 여기서는 저장 형식만)
    ctx.store.analyses[analysis_id].update(status="done", result=custom_result(SMALL))
    history = ctx.get(analysis_id).json()["review"]["history"]
    assert [h["id"] for h in history] == ["S1", "H1", "S2"] and history[1]["kind"] == "retry"
