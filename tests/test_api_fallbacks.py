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
from imask_backend.settings import get_settings, load_settings
from imask_backend.upstage import UpstageClient

CODE = {"X-Demo-Code": FAKE_ACCESS_CODE}


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


def test_start_lost_race_with_failed_final_reread_is_failed(env: Any) -> None:
    client, store, server = env
    analysis_id = store.put()
    calls = {"n": 0}
    original = store.update_analysis

    def update(aid: str, values: Any, **kw: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 2:  # job id 저장 직전에 만료 처리가 이김
            store.analyses[aid].update(status="failed", error="분석 시작이 끝나지 않았습니다. 새 분석으로 다시 올려 주세요.")
        return original(aid, values, **kw)

    store.update_analysis = update  # type: ignore[method-assign]
    store.fail_get_calls = {2}
    body = client.post(f"/api/py/analyses/{analysis_id}/start", headers=CODE).json()
    assert body["status"] == "failed"
    assert body["upstage_job_id"] is None
    assert _file_ids(body) == ["file_fake1"]
    assert server.deleted == ["file_fake1"]


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


def test_poll_lost_update_with_failed_final_reread_uses_values(env: Any) -> None:
    client, store, server = env
    analysis_id = _running(store, server)
    server.last_status = "completed"

    def other_poll_wins(aid: str, _values: Any) -> None:
        store.analyses[aid].update(status="done", result={"format": "imask-upstage-v1", "summary": {}})

    store.before_update = other_poll_wins
    store.fail_get_calls = {2}
    body = client.get(f"/api/py/analyses/{analysis_id}", headers=CODE).json()
    assert body["status"] == "done"
    assert _file_ids(body) == ["file_up1"]


def test_poll_job_gone_with_failed_final_reread(env: Any) -> None:
    client, store, server = env
    analysis_id = _running(store, server, updated_at=_ago(3))
    server.errors[("GET", "response")] = (404, {"error": {"message": "gone"}})
    store.fail_get_calls = {2}
    body = client.get(f"/api/py/analyses/{analysis_id}", headers=CODE).json()
    assert body["status"] == "failed"
    assert body["error"] == "Upstage 작업을 찾을 수 없습니다. 새 분석으로 다시 올려 주세요."
    assert _file_ids(body) == ["file_up1"]


def test_stale_start_with_failed_final_reread(env: Any) -> None:
    client, store, server = env
    server.files["file_up1"] = ("document.pdf", b"")
    analysis_id = store.put(status="running", updated_at=_ago(6), upstage_file_id="file_up1")
    store.fail_get_calls = {2}
    body = client.get(f"/api/py/analyses/{analysis_id}", headers=CODE).json()
    assert body["status"] == "failed"
    assert _file_ids(body) == ["file_up1"]
    assert server.deleted == ["file_up1"]
