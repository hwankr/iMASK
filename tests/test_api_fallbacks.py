# ==========================================================================
#  T2-fix2 R2-M1 — 대체 응답(마지막 다시 읽기 실패)에서도 저장에 성공한 값은 빠지지 않는다.
#  시작: 성공(running + job id + file id), Upstage 작업 실패(failed + 저장된 file id), 선점 뒤 경쟁 패배,
#  조회: 완료 반영·실패 반영·404 종료·만료 처리. 모두 메모리 가짜 저장소와 MockTransport.
# ==========================================================================

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from api_fakes import FAKE_ACCESS_CODE, FAKE_ENV, FakeStore, FakeUpstageServer
from fastapi.testclient import TestClient

from api.index import app, get_store, get_upstage
from imask_backend.analyses import poll_analysis
from imask_backend.settings import get_settings, load_settings
from imask_backend.upstage import UpstageClient

CODE = {"X-Demo-Code": FAKE_ACCESS_CODE}
STALE = "분석 시작이 끝나지 않았습니다. 새 분석으로 다시 올려 주세요."
REREAD_FAILED = "분석 상태를 다시 읽지 못했습니다. 다음 조회에서 다시 확인합니다."
START_REREAD_FAILED = "분석 시작 결과를 확인하지 못했습니다. 잠시 후 분석 건을 다시 조회해 주세요."


@pytest.fixture
def env() -> Iterator[tuple[TestClient, FakeStore, FakeUpstageServer]]:
    settings = load_settings(FAKE_ENV)
    store = FakeStore()
    server = FakeUpstageServer()

    def upstage_override() -> Iterator[Any]:
        client = UpstageClient.from_settings(
            settings.upstage(), extra_secrets=settings.secrets(), transport=httpx.MockTransport(server.handle)
        )
        try:
            yield lambda: client
        finally:
            client.close()

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_upstage] = upstage_override
    with TestClient(app) as client:
        yield client, store, server
    app.dependency_overrides.clear()


def _ago(minutes: float) -> str:
    return (datetime.now(UTC) - timedelta(minutes=minutes)).isoformat()


def _file_ids(body: dict[str, Any]) -> list[str | None]:
    return [d["upstage_file_id"] for d in body["documents"]]


# --- 시작 ---------------------------------------------------------------------------


def test_start_success_with_failed_final_reread_keeps_job_and_file_ids(env: Any) -> None:
    client, store, server = env
    analysis_id = store.put()
    store.fail_get_calls = {2}  # 1: 시작 전 읽기, 2: 마지막 다시 읽기
    response = client.post(f"/api/py/analyses/{analysis_id}/start", headers=CODE)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    assert body["upstage_job_id"] == "job_fake2"
    assert _file_ids(body) == ["file_fake1"]
    # 응답 대체 행이 DB 와 같다
    stored = store.analyses[analysis_id]
    assert stored["upstage_job_id"] == body["upstage_job_id"]
    assert [d["upstage_file_id"] for d in store.docs_of(analysis_id)] == _file_ids(body)
    assert body["updated_at"] == stored["updated_at"]  # 갱신 응답의 시각
    assert server.deleted == []  # 작업이 도는 중이라 파일을 지우지 않는다


def test_start_job_failure_with_failed_final_reread_keeps_saved_file_id(env: Any) -> None:
    client, store, server = env
    analysis_id = store.put()
    server.errors[("POST", "responses")] = (400, {"error": {"message": "bad config"}})
    store.fail_get_calls = {2}
    body = client.post(f"/api/py/analyses/{analysis_id}/start", headers=CODE).json()
    assert body["status"] == "failed"
    assert body["error"] == store.analyses[analysis_id]["error"]
    assert body["error"].startswith("Upstage 분석을 시작하지 못했습니다: 작업 만들기: HTTP 400")
    assert _file_ids(body) == ["file_fake1"]  # DB 에 저장된 값(파일은 서버가 이미 지움)
    assert server.deleted == ["file_fake1"]


def test_start_failure_before_upload_with_failed_final_reread(env: Any) -> None:
    client, store, _ = env
    analysis_id = store.put(content=None)
    store.fail_get_calls = {2}
    body = client.post(f"/api/py/analyses/{analysis_id}/start", headers=CODE).json()
    assert body["status"] == "failed"
    assert body["error"] == "업로드된 파일을 찾을 수 없습니다. 파일을 다시 올려 주세요."
    assert _file_ids(body) == [None]


def test_start_lost_race_with_failed_final_reread_is_502_not_guessed(env: Any) -> None:
    client, store, server = env
    analysis_id = store.put()
    calls = {"n": 0}
    original = store.update_analysis

    def update(aid: str, values: Any, **kw: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 2:  # job id 저장 직전에 만료 처리가 이김
            store.analyses[aid].update(status="failed", error=STALE)
        return original(aid, values, **kw)

    store.update_analysis = update  # type: ignore[method-assign]
    store.fail_get_calls = {2}
    response = client.post(f"/api/py/analyses/{analysis_id}/start", headers=CODE)
    # 조건부 갱신(job id 저장)에 졌고 다시 읽기도 실패 — 상태를 지어내지 않고 502(다시 조회하게)
    assert response.status_code == 502
    assert response.json() == {"detail": START_REREAD_FAILED}
    assert server.deleted == ["file_fake1"]  # 작업으로 이어지지 않은 파일은 지운다
    assert store.analyses[analysis_id]["upstage_job_id"] is None
    after = client.get(f"/api/py/analyses/{analysis_id}", headers=CODE).json()
    assert after["status"] == "failed"
    assert after["error"] == STALE  # 승자(만료 처리)가 저장한 상태


def test_start_lost_race_with_working_reread_returns_winner(env: Any) -> None:
    client, store, _ = env
    analysis_id = store.put()
    calls = {"n": 0}
    original = store.update_analysis

    def update(aid: str, values: Any, **kw: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 2:
            store.analyses[aid].update(status="failed", error=STALE)
        return original(aid, values, **kw)

    store.update_analysis = update  # type: ignore[method-assign]
    body = client.post(f"/api/py/analyses/{analysis_id}/start", headers=CODE).json()
    assert body["status"] == "failed"
    assert body["error"] == STALE  # 승자의 저장 값(지어낸 문구가 아님)


def test_start_failure_record_lost_with_failed_final_reread_is_502(env: Any) -> None:
    client, store, _ = env
    analysis_id = store.put(content=None)  # 파일 없음 → 실패 기록을 시도
    original = store.update_analysis

    def update(aid: str, values: Any, **kw: Any) -> Any:
        if values.get("status") == "failed":  # 실패 기록 직전에 만료 처리가 이김
            store.analyses[aid].update(status="failed", error=STALE)
        return original(aid, values, **kw)

    store.update_analysis = update  # type: ignore[method-assign]
    store.fail_get_calls = {2}
    response = client.post(f"/api/py/analyses/{analysis_id}/start", headers=CODE)
    assert response.status_code == 502
    assert response.json() == {"detail": START_REREAD_FAILED}
    assert store.analyses[analysis_id]["error"] == STALE  # 이 요청의 문구로 덮어쓰지 않음


# --- 조회 ---------------------------------------------------------------------------


def _running(store: FakeStore, server: FakeUpstageServer, **kw: Any) -> str:
    server.files["file_up1"] = ("document.pdf", b"")
    return store.put(status="running", job_id="job_up1", upstage_file_id="file_up1", **kw)


def test_poll_done_with_failed_final_reread_returns_saved_result(env: Any) -> None:
    client, store, server = env
    analysis_id = _running(store, server)
    server.last_status = "completed"
    store.fail_get_calls = {2}  # 1: 조회 읽기, 2: 반영 뒤 다시 읽기
    body = client.get(f"/api/py/analyses/{analysis_id}", headers=CODE).json()
    assert body["status"] == "done"
    assert body["upstage_job_id"] == "job_up1"
    assert _file_ids(body) == ["file_up1"]
    assert body["result"]["summary"]["document_count"] == 6
    assert "response" not in body["result"]
    assert body["updated_at"] == store.analyses[analysis_id]["updated_at"]


def test_poll_failed_job_with_failed_final_reread(env: Any) -> None:
    client, store, server = env
    analysis_id = _running(store, server)
    server.last_status = "failed"
    server.last_extra = {"error": {"message": "unreadable"}}
    store.fail_get_calls = {2}
    body = client.get(f"/api/py/analyses/{analysis_id}", headers=CODE).json()
    assert body["status"] == "failed"
    assert body["error"] == "Upstage 분석이 실패했습니다: unreadable"
    assert _file_ids(body) == ["file_up1"]


def test_poll_lost_update_with_failed_final_reread_does_not_guess(env: Any) -> None:
    client, store, server = env
    analysis_id = _running(store, server)
    server.last_status = "completed"

    def other_poll_wins(aid: str, _values: Any) -> None:
        store.analyses[aid].update(status="done", result={"format": "imask-upstage-v1", "summary": {}})

    store.before_update = other_poll_wins
    store.fail_get_calls = {2}
    body = client.get(f"/api/py/analyses/{analysis_id}", headers=CODE).json()
    # 반영하지 못한 값을 확정하지 않는다: 조회 전 running 행 + poll_error(다음 조회가 승자의 상태를 읽는다)
    assert body["status"] == "running"
    assert body["poll_error"] == REREAD_FAILED
    assert body["result"] is None and body["error"] is None
    assert _file_ids(body) == ["file_up1"]
    assert server.deleted == ["file_up1"]  # 작업은 끝났으므로 파일 정리는 그대로
    assert client.get(f"/api/py/analyses/{analysis_id}", headers=CODE).json()["status"] == "done"


def test_poll_job_gone_with_failed_final_reread(env: Any) -> None:
    client, store, server = env
    analysis_id = _running(store, server, updated_at=_ago(3))
    server.errors[("GET", "response")] = (404, {"error": {"message": "gone"}})
    store.fail_get_calls = {2}
    body = client.get(f"/api/py/analyses/{analysis_id}", headers=CODE).json()
    assert body["status"] == "failed"
    assert body["error"] == "Upstage 작업을 찾을 수 없습니다. 새 분석으로 다시 올려 주세요."
    assert _file_ids(body) == ["file_up1"]


def test_stale_start_lost_with_failed_final_reread_keeps_running(env: Any) -> None:
    client, store, server = env
    server.files["file_up1"] = ("document.pdf", b"")
    analysis_id = store.put(status="running", updated_at=_ago(6), upstage_file_id="file_up1")

    def start_saves_job_first(aid: str, _values: Any) -> None:
        store.update_analysis(aid, {"upstage_job_id": "job_now"}, expect_status="running", expect_no_job=True)

    store.before_update = start_saves_job_first
    store.fail_get_calls = {2}
    body = client.get(f"/api/py/analyses/{analysis_id}", headers=CODE).json()
    assert body["status"] == "running"
    assert body["error"] is None
    assert body["poll_error"] == REREAD_FAILED
    assert server.calls("DELETE") == []  # 실행 중인 작업의 입력은 지우지 않는다
    assert client.get(f"/api/py/analyses/{analysis_id}", headers=CODE).json()["upstage_job_id"] == "job_now"


def test_stale_start_with_failed_final_reread(env: Any) -> None:
    client, store, server = env
    server.files["file_up1"] = ("document.pdf", b"")
    analysis_id = store.put(status="running", updated_at=_ago(6), upstage_file_id="file_up1")
    store.fail_get_calls = {2}
    body = client.get(f"/api/py/analyses/{analysis_id}", headers=CODE).json()
    assert body["status"] == "failed"
    assert _file_ids(body) == ["file_up1"]
    assert server.deleted == ["file_up1"]


# --- R3-m1: 조건부 갱신 패배 + 다시 읽기 실패(fix3) ----------------------------------------
# 검증 재현과 같은 방식: 실제 GET 의 조건부 UPDATE 직전에 별도 poll_analysis(진짜 UpstageClient)가 먼저
# 저장한다. 두 요청이 본 Upstage 상태가 다르고(completed 와 2분 지난 404), 진 쪽의 마지막 SELECT 만 실패할 수 있다.

RACES = [("completed", "404", "failed"), ("404", "completed", "done")]
RACE_IDS = ["winner_404_failed", "winner_completed_done"]


def _race(env: Any, loser_view: str, winner_view: str, *, fail_loser_reread: bool) -> tuple[Any, ...]:
    client, store, server = env
    settings = load_settings(FAKE_ENV)
    server.files["file_race"] = ("document.pdf", b"")
    analysis_id = store.put(status="running", job_id="job_race", upstage_file_id="file_race", updated_at=_ago(3))
    if fail_loser_reread:
        store.fail_get_calls = {4}  # 1 진 쪽 읽기, 2 승자 읽기, 3 승자 다시 읽기, 4 진 쪽 다시 읽기(실패)
    server.last_status = "completed"
    if loser_view == "404":
        server.errors[("GET", "response")] = (404, {"error": {"message": "missing job"}})
    winner: dict[str, Any] = {}

    def other_request_wins(aid: str, _values: Any) -> None:
        if winner_view == "404":
            server.errors[("GET", "response")] = (404, {"error": {"message": "missing job"}})
        else:
            server.errors.pop(("GET", "response"), None)
        with UpstageClient.from_settings(
            settings.upstage(), extra_secrets=settings.secrets(), transport=httpx.MockTransport(server.handle)
        ) as service:
            winner["status"] = poll_analysis(store, lambda: service, settings, aid).row["status"]

    store.before_update = other_request_wins
    response = client.get(f"/api/py/analyses/{analysis_id}", headers=CODE)
    return client, store, server, analysis_id, response, winner


@pytest.mark.parametrize(("loser_view", "winner_view", "winner_status"), RACES, ids=RACE_IDS)
def test_conditional_update_loser_with_failed_reread_returns_running(
    env: Any, loser_view: str, winner_view: str, winner_status: str
) -> None:
    client, store, server, analysis_id, response, winner = _race(env, loser_view, winner_view, fail_loser_reread=True)
    body = response.json()
    stored = store.analyses[analysis_id]
    assert winner["status"] == winner_status == stored["status"]
    # 진 쪽: 저장 안 된 종료 상태를 확정하지 않는다
    assert response.status_code == 200
    assert body["status"] == "running"
    assert body["poll_error"] == REREAD_FAILED
    assert body["result"] is None
    assert body["error"] is None
    assert body["upstage_job_id"] == "job_race"
    assert set(server.files) - set(server.deleted) == set()  # 파일은 남지 않는다(승자가 지웠거나 404 = 성공)
    # 다음 GET 은 승자가 저장한 상태
    after = client.get(f"/api/py/analyses/{analysis_id}", headers=CODE).json()
    assert after["status"] == winner_status
    assert after["error"] == stored["error"]
    assert (after["result"] is not None) == (winner_status == "done")
    assert after["poll_error"] is None


@pytest.mark.parametrize(("loser_view", "winner_view", "winner_status"), RACES, ids=RACE_IDS)
def test_conditional_update_loser_with_working_reread_returns_winner(
    env: Any, loser_view: str, winner_view: str, winner_status: str
) -> None:
    _, store, _, analysis_id, response, _ = _race(env, loser_view, winner_view, fail_loser_reread=False)
    body = response.json()
    stored = store.analyses[analysis_id]
    assert body["status"] == winner_status == stored["status"]
    assert body["error"] == stored["error"]
    assert body["updated_at"] == stored["updated_at"]
    assert body["poll_error"] is None
