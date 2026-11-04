# ==========================================================================
#  V-T1-2 회귀(shared-analyses T1-fix2, 네트워크 없음)
#  - R1 문서 file id 비교 후 교환: 늦게 이어진 옛 시작이 새 실행의 file id 를 덮어쓰지 않음(최종 문서 = 새 실행 file, 옛 시작의
#    file 만 지움, 뒤의 DELETE 가 새 file 도 정리), 시작 중 행이 지워지면 작업 만들기 0회, 아직 이 실행이면 실패 기록
#  - R2 읽은 실행만 지우기: 삭제가 읽은 뒤 다시 분석이 끝나도 새 업로드를 정리, 행 지우기가 먼저 이기면 시작이 자기 업로드를
#    지움, 3번 모두 지면 409(행·원본 상태 일관), 정상 순서·404·두 번 삭제 그대로
#  - R3 로그의 id 가림: 가짜 비밀키·서명 URL·1만 자 + 제어 문자 file id → 로그에 원문 없음·길이 제한
#  - r1 이긴 조회의 상태 표시: 이긴 뒤 다시 읽은 행이 새 실행이면 upstage_status null, 같은 실행이면 그대로
#  - T1-fix3 v3-m1: 선점도 읽은 updated_at 일 때만(①), 문서 교환에 져도 아직 이 실행이면 다시 읽은 값으로 다시 교환(②, 3번).
#    검증 V-T1-3 의 두 순서(만료된 옛 시작이 먼저 문서를 씀 / 낡은 선점 전 읽기가 새 queued 순환을 가로챔)를 스레드로 겹쳐 재현.
# ==========================================================================

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
from typing import Any

import httpx
import pytest
from api_fakes import FAKE_ENV, FAKE_SUPABASE_KEY
from shared_ctx import MSG_DELETE_ROW, MSG_NOT_FOUND, Ctx, ctx, logic_factory  # noqa: F401

from imask_backend import manage
from imask_backend.analyses import poll_analysis, start_analysis
from imask_backend.settings import load_settings

SETTINGS = load_settings(FAKE_ENV)
MSG_START_SAVE_FAILED = "분석 시작 정보를 저장하지 못했습니다. 새 분석으로 다시 올려 주세요."


def _uploaded(ctx: Ctx) -> list[str]:
    return list(ctx.server.files)


# --- R1 문서 file id 비교 후 교환 -------------------------------------------------------------------


def test_late_old_upload_does_not_overwrite_the_new_runs_document_file(ctx: Ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    # 검증 V-T1-2 late_old_upload: A 가 올린 뒤 문서 저장 직전에 멈춤 → 조회가 A 를 만료 → B 가 새 실행을 끝까지 → A 재개
    analysis_id = ctx.store.put(status="failed", error="처음 실패")
    original = ctx.store.update_document
    seen: dict[str, Any] = {}

    def update_document(document_id: str, values: Any, **kw: Any) -> bool:
        if "a_file" not in seen:
            seen["a_file"] = values["upstage_file_id"]
            later = datetime.now(UTC) + timedelta(minutes=10)
            seen["expired"] = poll_analysis(ctx.store, logic_factory(ctx), SETTINGS, analysis_id, now=later).row["status"]
            new = manage.retry_analysis(ctx.store, logic_factory(ctx), SETTINGS, analysis_id, "다른 사람")
            seen["b_job"], seen["b_file"] = new["upstage_job_id"], new["documents"][0]["upstage_file_id"]
        return original(document_id, values, **kw)

    monkeypatch.setattr(ctx.store, "update_document", update_document)
    response = ctx.retry(analysis_id)
    assert seen["expired"] == "failed"
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running" and body["upstage_job_id"] == seen["b_job"]
    (doc,) = ctx.store.docs_of(analysis_id)
    assert doc["upstage_file_id"] == seen["b_file"]  # 최종 문서 = B 의 file
    assert ctx.server.deleted == [seen["a_file"]]  # A 의 file 만 지움
    assert len(ctx.server.calls("POST", "responses")) == 1  # A 는 작업을 만들지 않았다
    # 뒤의 DELETE 가 B 의 file 도 정리한다
    assert ctx.delete(analysis_id).status_code == 204
    assert seen["b_file"] in ctx.server.deleted


@pytest.mark.parametrize("read_file", [None, "file_old"])
def test_document_save_is_conditional_on_the_file_id_the_start_read(ctx: Ctx, read_file: Any) -> None:
    analysis_id = ctx.store.put(status="failed", upstage_file_id=read_file)
    assert ctx.retry(analysis_id).status_code == 200
    ((_doc_id, values, conditions),) = ctx.store.document_updates
    assert values == {"upstage_file_id": "file_fake1"}
    assert conditions == ({"expect_file_id": None, "expect_no_file": True} if read_file is None else {"expect_file_id": "file_old", "expect_no_file": False})


@pytest.mark.parametrize("route", ["start", "retry"])
def test_row_deleted_before_the_document_save_makes_no_job(ctx: Ctx, monkeypatch: pytest.MonkeyPatch, route: str) -> None:
    analysis_id = ctx.store.put(status="queued" if route == "start" else "failed")
    original = ctx.store.update_document

    def update_document(document_id: str, values: Any, **kw: Any) -> bool:
        manage.delete_analysis(ctx.store, logic_factory(ctx), SETTINGS, analysis_id)  # 지우는 요청이 먼저 끝남
        return original(document_id, values, **kw)

    monkeypatch.setattr(ctx.store, "update_document", update_document)
    response = ctx.start(analysis_id) if route == "start" else ctx.retry(analysis_id)
    assert (response.status_code, response.json()) == (404, {"detail": MSG_NOT_FOUND})
    assert ctx.server.job_bodies == []  # 지우는 중인 분석에 작업(크레딧)을 만들지 않는다
    assert ctx.server.deleted == ["file_fake1"]  # 자기 업로드만 지운다


def test_document_value_left_by_a_finished_run_is_taken_over_while_the_run_is_still_ours(ctx: Ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    # (T1-fix3 v3-m1 ② 로 바뀐 계약) 시작이 읽은 문서 값이 낡았지만 행은 아직 이 실행의 것(running·job 없음·선점 값):
    # 다시 읽은 문서 값으로 교환을 다시 해 이어서 시작한다(끝난 옛 실행이 남긴 값을 넘겨받음)
    analysis_id = ctx.store.put()
    original = ctx.store.update_document
    calls = {"n": 0}

    def update_document(document_id: str, values: Any, **kw: Any) -> bool:
        calls["n"] += 1
        if calls["n"] == 1:
            ctx.store.documents[document_id]["upstage_file_id"] = "file_other"  # 옛 실행이 먼저 썼다
        return original(document_id, values, **kw)

    monkeypatch.setattr(ctx.store, "update_document", update_document)
    body = ctx.start(analysis_id).json()
    assert body["status"] == "running" and body["upstage_job_id"] == "job_fake2"
    assert [c for _, _, c in ctx.store.document_updates] == [
        {"expect_file_id": None, "expect_no_file": True},
        {"expect_file_id": "file_other", "expect_no_file": False},
    ]
    assert ctx.store.docs_of(analysis_id)[0]["upstage_file_id"] == "file_fake1"
    assert len(ctx.server.job_bodies) == 1 and ctx.server.deleted == []


def test_document_swap_losing_three_times_while_ours_is_a_start_failure(ctx: Ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    analysis_id = ctx.store.put()
    original = ctx.store.update_document
    calls = {"n": 0}

    def update_document(document_id: str, values: Any, **kw: Any) -> bool:
        calls["n"] += 1
        ctx.store.documents[document_id]["upstage_file_id"] = f"file_other_{calls['n']}"  # 매번 다른 값으로 바뀜
        return original(document_id, values, **kw)

    monkeypatch.setattr(ctx.store, "update_document", update_document)
    body = ctx.start(analysis_id).json()
    assert (body["status"], body["error"]) == ("failed", MSG_START_SAVE_FAILED)  # 아직 이 실행이라 실패 기록이 이김
    assert calls["n"] == 3 and len(ctx.store.document_updates) == 3
    assert ctx.server.job_bodies == [] and ctx.server.deleted == ["file_fake1"]
    assert ctx.store.docs_of(analysis_id)[0]["upstage_file_id"] == "file_other_3"  # 남의 값을 덮어쓰지 않음


def test_document_swap_lost_after_the_run_changed_returns_the_latest_row_without_retrying(ctx: Ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    # 실행이 바뀌었으면(만료·다른 선점 — updated_at 이 선점 값과 다름) 다시 교환하지 않고 지금처럼 최신 행·작업 없음·자기 업로드만 지움
    analysis_id = ctx.store.put()
    original = ctx.store.update_document

    def update_document(document_id: str, values: Any, **kw: Any) -> bool:
        ctx.store.documents[document_id]["upstage_file_id"] = "file_new_run"
        row = ctx.store.analyses[analysis_id]
        row["updated_at"] = (datetime.fromisoformat(row["updated_at"]) + timedelta(seconds=1)).isoformat()  # 새 실행의 선점
        return original(document_id, values, **kw)

    monkeypatch.setattr(ctx.store, "update_document", update_document)
    response = ctx.start(analysis_id)
    assert response.status_code == 200 and response.json()["status"] == "running"
    assert len(ctx.store.document_updates) == 1  # 다시 교환하지 않았다
    assert not [v for _, v, _ in ctx.store.updates if v.get("status") == "failed"]  # 실패 기록도 시도하지 않음(lost_race)
    assert ctx.server.job_bodies == [] and ctx.server.deleted == ["file_fake1"]
    assert ctx.store.docs_of(analysis_id)[0]["upstage_file_id"] == "file_new_run"


# --- T1-fix3 v3-m1: 검증 V-T1-3 의 두 순서(요청 두 개를 스레드로 겹친다) ---------------------------------------


def test_expired_old_start_writes_before_the_new_start_document_save(ctx: Ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    # 순서 A: /start A 가 올린 뒤 문서 저장 직전에 멈춤 → 조회가 만료 → 다시 분석 B 가 같은 문서 값(null)을 읽고 올린 뒤
    # 문서 저장 직전에 멈춤 → A 가 먼저 문서를 씀(작업을 만들지만 job id 저장에 져서 자기 파일을 지움) → B 재개
    analysis_id = ctx.store.put(status="queued")
    original = ctx.store.update_document
    ready, release = [Event(), Event()], [Event(), Event()]
    files: list[str] = []

    def gated(document_id: str, values: Any, **kw: Any) -> bool:
        index = len(files)
        files.append(values["upstage_file_id"])
        if index < 2:
            ready[index].set()
            assert release[index].wait(10)
        return original(document_id, values, **kw)

    monkeypatch.setattr(ctx.store, "update_document", gated)
    with ThreadPoolExecutor(max_workers=2) as pool:
        try:
            old = pool.submit(ctx.start, analysis_id)
            assert ready[0].wait(10)
            later = datetime.now(UTC) + timedelta(minutes=6)
            assert poll_analysis(ctx.store, logic_factory(ctx), SETTINGS, analysis_id, now=later).row["status"] == "failed"
            new = pool.submit(ctx.retry, analysis_id)
            assert ready[1].wait(10)
            release[0].set()
            old_response = old.result(timeout=10)
            release[1].set()
            new_response = new.result(timeout=10)
        finally:
            for gate in release:
                gate.set()
    a_file, b_file = files[0], files[1]
    assert old_response.status_code == 200 and new_response.status_code == 200
    body = new_response.json()
    assert body["status"] == "running" and body["upstage_job_id"]  # B 는 running + B 의 작업으로 끝난다
    final = ctx.store.get_analysis(analysis_id)
    assert final["status"] == "running" and final["upstage_job_id"] == body["upstage_job_id"]
    assert final["documents"][0]["upstage_file_id"] == b_file  # 최종 문서 = B 의 file
    assert ctx.server.deleted == [a_file]  # A 의 파일만 지웠다
    # B 는 A 가 남긴 값을 읽고 다시 교환했다(옛 시작이 새 실행의 값을 덮어쓰는 R1 은 다시 생기지 않는다)
    assert [c["expect_file_id"] for _, _, c in ctx.store.document_updates] == [None, None, a_file]
    assert files == [a_file, b_file, b_file]


def test_old_preclaim_read_does_not_win_a_new_queued_cycle(ctx: Ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    # 순서 B: /start A 가 queued 를 읽고 선점 직전에 멈춤 → /start B 가 선점·업로드·작업 즉시 실패 → 다시 분석 C 가 되돌리고
    # 선점 직전에 멈춤 → A 재개(읽은 updated_at 이 낡아 선점에 짐 → 409) → C 재개(선점·시작)
    analysis_id = ctx.store.put(status="queued")
    original = ctx.store.claim_analysis
    a_ready, c_ready, a_release, c_release = Event(), Event(), Event(), Event()
    claims: list[int] = []

    def claim(aid: str, **kw: Any) -> Any:
        number = len(claims)
        claims.append(number)
        if number == 0:
            a_ready.set()
            assert a_release.wait(10)
        if number == 2:
            c_ready.set()
            assert c_release.wait(10)
        return original(aid, **kw)

    monkeypatch.setattr(ctx.store, "claim_analysis", claim)
    with ThreadPoolExecutor(max_workers=2) as pool:
        try:
            a = pool.submit(ctx.start, analysis_id)
            assert a_ready.wait(10)
            ctx.server.create_status = "failed"
            assert ctx.start(analysis_id).json()["status"] == "failed"  # B
            ctx.server.create_status = "in_progress"
            c = pool.submit(ctx.retry, analysis_id)
            assert c_ready.wait(10)
            a_release.set()
            a_response = a.result(timeout=10)
            c_release.set()
            c_response = c.result(timeout=10)
        finally:
            a_release.set()
            c_release.set()
    assert (a_response.status_code, a_response.json()["detail"]) == (409, "이미 시작한 분석입니다.")
    assert c_response.status_code == 200 and c_response.json()["status"] == "running"
    # 업로드·작업은 B(즉시 실패)와 C 의 것뿐 — A 는 아무것도 만들지 않았다
    assert len(ctx.server.calls("POST", "files")) == 2 and len(ctx.server.job_bodies) == 2
    final = ctx.store.get_analysis(analysis_id)
    assert final["status"] == "running" and final["upstage_job_id"] == c_response.json()["upstage_job_id"]
    assert final["documents"][0]["upstage_file_id"] == c_response.json()["documents"][0]["upstage_file_id"]


def test_normal_start_still_saves_the_file_and_creates_one_job(ctx: Ctx) -> None:
    analysis_id = ctx.store.put()
    body = ctx.start(analysis_id).json()
    assert body["status"] == "running" and body["documents"][0]["upstage_file_id"] == "file_fake1"
    assert ctx.store.docs_of(analysis_id)[0]["upstage_file_id"] == "file_fake1"
    assert len(ctx.server.job_bodies) == 1 and ctx.server.deleted == []


# --- R2 읽은 실행만 지우기 --------------------------------------------------------------------------


def test_delete_read_then_a_completed_retry_still_cleans_the_new_upload(ctx: Ctx) -> None:
    # 검증 V-T1-2 delete_read_then_retry: 삭제가 읽은 뒤(원본 지우기 직전) 다시 분석이 job id 저장까지 끝냄
    analysis_id = ctx.store.put(status="failed", error="처음 실패")
    first_stamp = ctx.store.analyses[analysis_id]["updated_at"]
    seen: dict[str, Any] = {}

    def retry_after_the_delete_read(_paths: Any) -> None:
        new = manage.retry_analysis(ctx.store, logic_factory(ctx), SETTINGS, analysis_id, "다른 사람")
        seen["status"], seen["file"] = new["status"], new["documents"][0]["upstage_file_id"]

    ctx.store.before_remove = retry_after_the_delete_read
    response = ctx.delete(analysis_id)
    assert seen["status"] == "running"
    assert response.status_code == 204
    assert analysis_id not in ctx.store.analyses and ctx.get(analysis_id).status_code == 404
    assert not [p for p in ctx.store.objects if analysis_id in p]
    assert seen["file"] in ctx.server.deleted  # 새 업로드의 Upstage 파일도 지웠다
    # 처음 읽은 updated_at 은 졌고, 다시 읽은 값으로 이겼다
    assert ctx.store.delete_conditions[0] == first_stamp and ctx.store.deleted_counts == [0, 1]
    assert ctx.store.delete_conditions[1] != first_stamp


def test_row_delete_winning_first_makes_the_start_drop_its_upload(ctx: Ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    # 반대 순서: 시작이 작업까지 만든 뒤 job id 저장 직전에 삭제가 끝남 → 시작의 저장이 져서 자기 업로드를 지운다
    analysis_id = ctx.store.put(status="failed")
    original = ctx.store.update_analysis

    def update_analysis(aid: str, values: Any, **kw: Any) -> Any:
        if values.get("upstage_job_id"):
            manage.delete_analysis(ctx.store, logic_factory(ctx), SETTINGS, aid)
        return original(aid, values, **kw)

    monkeypatch.setattr(ctx.store, "update_analysis", update_analysis)
    response = ctx.retry(analysis_id)
    assert (response.status_code, response.json()) == (404, {"detail": MSG_NOT_FOUND})
    # 삭제는 그때 문서에 있던 file 을, 시작은 자기 업로드를 지운다(두 번째는 404 = 성공)
    assert "file_fake1" in ctx.server.deleted
    assert analysis_id not in ctx.store.analyses


def test_delete_losing_three_times_is_409_and_keeps_a_consistent_row(ctx: Ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    analysis_id = ctx.store.put(status="done", job_id="j", upstage_file_id="file_up_1")
    ctx.store.put_review(analysis_id, memo="메모")
    original = ctx.store.delete_analysis
    bumps = {"n": 0}

    def delete_analysis(aid: str, **kw: Any) -> int:
        bumps["n"] += 1
        row = ctx.store.analyses[aid]
        row["updated_at"] = (datetime.fromisoformat(row["updated_at"]) + timedelta(seconds=1)).isoformat()  # 다른 요청이 바꿈
        return original(aid, **kw)

    monkeypatch.setattr(ctx.store, "delete_analysis", delete_analysis)
    response = ctx.delete(analysis_id)
    assert (response.status_code, response.json()) == (409, {"detail": MSG_DELETE_ROW})
    assert bumps["n"] == 3 and ctx.store.deleted_counts == [0, 0, 0]
    # 행·문서·검토 행은 그대로, 원본은 지워진 상태(행 지우기 실패 502 와 같은 상태 — 다시 누르면 이어서 지워진다)
    assert analysis_id in ctx.store.analyses and ctx.store.docs_of(analysis_id) and analysis_id in ctx.store.reviews
    assert not [p for p in ctx.store.objects if analysis_id in p]
    ctx.no_upstage()  # 행을 지우지 못했으므로 Upstage 정리도 하지 않는다
    monkeypatch.setattr(ctx.store, "delete_analysis", original)
    assert ctx.delete(analysis_id).status_code == 204
    assert "file_up_1" not in ctx.store.analyses and analysis_id not in ctx.store.analyses


def test_delete_uses_the_read_updated_at_and_keeps_the_normal_order(ctx: Ctx) -> None:
    analysis_id = ctx.store.put(status="done", job_id="j", upstage_file_id="file_up_1")
    stamp = ctx.store.analyses[analysis_id]["updated_at"]
    assert ctx.delete(analysis_id).status_code == 204
    assert ctx.store.calls == ["get_analysis", "remove_objects", "delete_analysis"]
    assert ctx.store.delete_conditions == [stamp]
    assert [r.url.path for r in ctx.server.calls("DELETE", "file")] == ["/v2/files/file_up_1"]


def test_delete_losing_to_another_delete_is_404(ctx: Ctx) -> None:
    analysis_id = ctx.store.put(status="failed")
    ctx.store.before_delete = lambda aid: manage.delete_analysis(ctx.store, logic_factory(ctx), SETTINGS, aid)
    response = ctx.delete(analysis_id)
    assert (response.status_code, response.json()) == (404, {"detail": MSG_NOT_FOUND})
    assert ctx.delete(analysis_id).status_code == 404


def test_delete_reread_store_error_is_502(ctx: Ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    analysis_id = ctx.store.put(status="failed")
    original = ctx.store.delete_analysis

    def delete_analysis(aid: str, **kw: Any) -> int:
        ctx.store.analyses[aid]["updated_at"] = datetime.now(UTC).isoformat() + "x"
        ctx.store.fail_get_calls = {2}
        return original(aid, **kw)

    monkeypatch.setattr(ctx.store, "delete_analysis", delete_analysis)
    assert ctx.delete(analysis_id).status_code == 502
    assert analysis_id in ctx.store.analyses


# --- R3 로그의 id 가림 --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "file_id",
    [FAKE_SUPABASE_KEY, "https://synthetic.invalid/object/sign/x?token=synthetic-signature-value-1234567890", "file_" + "x" * 10000 + "\n\x00synthetic"],
    ids=["fake_secret", "signed_url", "control_long_id"],
)
def test_cleanup_log_ids_are_scrubbed_and_cut(ctx: Ctx, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, file_id: str) -> None:
    analysis_id = ctx.store.put(status="failed", upstage_file_id=file_id)
    original = ctx.server.handle

    def handle(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":  # URL 모양 id 도 같은 실패를 받게
            ctx.server.requests.append(request)
            return httpx.Response(500, json={"error": {"message": "synthetic"}})
        return original(request)

    monkeypatch.setattr(ctx.server, "handle", handle)
    with caplog.at_level(logging.DEBUG, logger="imask"):
        assert ctx.delete(analysis_id).status_code == 204
    messages = [r.getMessage() for r in caplog.records if "Upstage 파일 삭제" in r.getMessage()]
    assert messages
    for message in messages:
        assert file_id not in message and "\x00" not in message and len(message) < 300
        assert FAKE_SUPABASE_KEY not in message and "synthetic-signature-value" not in message
    assert len(ctx.server.calls("DELETE")) == 1  # 지우기 요청에는 원래 id 를 썼다


def test_cleanup_rejected_log_id_is_scrubbed(ctx: Ctx, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    analysis_id = ctx.store.put(status="failed", upstage_file_id=FAKE_SUPABASE_KEY)
    original = ctx.server.handle

    def handle(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            ctx.server.requests.append(request)
            return httpx.Response(200, json={"deleted": False})
        return original(request)

    monkeypatch.setattr(ctx.server, "handle", handle)
    with caplog.at_level(logging.DEBUG, logger="imask"):
        assert ctx.delete(analysis_id).status_code == 204
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "삭제가 거절됨" in logged and FAKE_SUPABASE_KEY not in logged


def test_delete_and_retry_logs_pass_ids_through_scrub(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[Any, int | None]] = []
    original = manage._scrub

    def spy(value: Any, secrets: Any, limit: int | None = 500) -> str:
        seen.append((value, limit))
        return original(value, secrets, limit)

    monkeypatch.setattr(manage, "_scrub", spy)
    secret = "synthetic-secret-value-0123456789"
    assert manage._log_id(f"id-{secret}", {secret: "<X>"}) == "id-<X>"  # noqa: SLF001
    assert len(manage._log_id("y" * 5000, {})) <= 100  # noqa: SLF001
    assert seen == [(f"id-{secret}", 100), ("y" * 5000, 100)]


# --- r1 이긴 조회의 상태 표시 -----------------------------------------------------------------------


def test_winning_old_poll_that_rereads_a_new_run_shows_no_upstage_status(ctx: Ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    analysis_id = ctx.store.put(status="running", job_id="old_job")
    ctx.server.last_status = "failed"
    original = ctx.store.get_analysis
    state = {"reads": 0, "inside": False}

    def get_analysis(aid: str) -> Any:
        state["reads"] += 1
        if state["reads"] == 2 and not state["inside"]:  # 실패 저장에 이긴 뒤 다시 읽기 직전
            state["inside"] = True
            manage.retry_analysis(ctx.store, logic_factory(ctx), SETTINGS, aid, "다른 사람")
            ctx.server.last_status = "in_progress"
        return original(aid)

    monkeypatch.setattr(ctx.store, "get_analysis", get_analysis)
    body = ctx.get(analysis_id).json()
    assert body["status"] == "running" and body["upstage_job_id"] != "old_job"
    assert body["upstage_status"] is None


def test_winning_poll_of_the_same_run_keeps_its_upstage_status(ctx: Ctx) -> None:
    analysis_id = ctx.store.put(status="running", job_id="job_1")
    ctx.server.last_status = "failed"
    body = ctx.get(analysis_id).json()
    assert body["status"] == "failed" and body["upstage_status"] == "failed"


# --- 정상 흐름이 그대로인지(새 분석 → 조회 → 완료 → 검토, 다시 분석 실패·성공, 삭제 한 번) ------------------------


def test_normal_flow_is_unchanged(ctx: Ctx) -> None:
    created = ctx.create().json()
    analysis_id = created["analysis"]["id"]
    ctx.store.objects[created["upload"]["path"]] = b"%PDF-1.7\n% fake synthetic pdf\n"
    assert ctx.start(analysis_id).json()["status"] == "running"
    assert ctx.get(analysis_id).json()["upstage_status"] == "in_progress"
    ctx.server.last_status = "completed"
    done = ctx.get(analysis_id).json()
    assert done["status"] == "done" and done["upstage_status"] == "completed" and done["review"] is not None
    assert ctx.server.deleted == ["file_fake1"]  # 완료 뒤 Upstage 파일 정리
    assert ctx.act(analysis_id, "save_memo", text="확인").status_code == 200
    assert ctx.delete(analysis_id).status_code == 204
    assert ctx.get(analysis_id).status_code == 404
    assert len(ctx.server.job_bodies) == 1


def test_retry_failure_then_success_is_unchanged(ctx: Ctx) -> None:
    analysis_id = ctx.store.put(status="failed", error="처음 실패")
    ctx.server.create_status = "failed"
    assert ctx.retry(analysis_id).json()["status"] == "failed"  # 작업이 바로 실패
    ctx.server.create_status = "in_progress"
    body = ctx.retry(analysis_id).json()
    assert body["status"] == "running" and body["documents"][0]["upstage_file_id"] == "file_fake3"
    # 첫 다시 분석의 file(file_fake1)은 그 실패에서 지웠고, 두 번째는 읽은 값(file_fake1)을 조건으로 교환했다
    assert ctx.server.deleted == ["file_fake1"]
    assert ctx.store.document_updates[-1][2] == {"expect_file_id": "file_fake1", "expect_no_file": False}


def test_create_cleanup_after_another_delete_is_still_502(ctx: Ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    # '쓰는 곳' 표의 만들기 정리(조건 없는 행 지우기): 새 행이 목록에 보여 다른 요청이 먼저 지웠어도 결과가 같다
    original = ctx.store.create_signed_upload_url

    def signed(path: str) -> Any:
        new_id = path.split("/")[1]
        manage.delete_analysis(ctx.store, logic_factory(ctx), SETTINGS, new_id)
        ctx.store.fail.add("create_signed_upload_url")
        return original(path)

    monkeypatch.setattr(ctx.store, "create_signed_upload_url", signed)
    response = ctx.create()
    assert response.status_code == 502 and ctx.store.analyses == {} and ctx.store.documents == {}
    assert ctx.store.deleted_counts == [1, 0]  # 끼어든 삭제 1, 정리 0(이미 없음) — 오류 아님


def test_two_stale_expiries_at_once_fail_once(ctx: Ctx) -> None:
    # '쓰는 곳' 표의 오래된 시작 만료 — 같은 동작 두 번: 하나만 이기고, 진 쪽은 최신(failed) 행
    ctx.server.files["file_orphan"] = ("document.pdf", b"")
    read = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
    analysis_id = ctx.store.put(status="running", updated_at=read, upstage_file_id="file_orphan")
    inner: list[str] = []
    ctx.store.before_update = lambda aid, _v: inner.append(poll_analysis(ctx.store, logic_factory(ctx), SETTINGS, aid).row["status"])
    body = ctx.get(analysis_id).json()
    assert inner == ["failed"] and body["status"] == "failed"
    stale_writes = [c for _, v, c in ctx.store.updates if v.get("status") == "failed"]
    assert len(stale_writes) == 2 and ctx.store.update_stamps.count(None) == 1  # 하나는 졌다
    assert ctx.server.deleted == ["file_orphan"]  # 진 쪽은 파일을 다시 지우지 않는다(이긴 쪽만)


def test_start_after_logic_start_race_still_one_job(ctx: Ctx) -> None:
    analysis_id = ctx.store.put()
    assert start_analysis(ctx.store, logic_factory(ctx), SETTINGS, analysis_id)["status"] == "running"
    assert ctx.start(analysis_id).status_code == 409
    assert len(ctx.server.job_bodies) == 1
