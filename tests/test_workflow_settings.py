# ==========================================================================
#  웹 설정 화면의 워크플로우 설정(imask_backend.workflow_settings, 네트워크 없음)
#  - 비밀번호: 서버에 없으면 503, 틀리면 401(Upstage·저장소 안 부름). 값은 secrets()·응답·로그에 없음
#  - 저장: 꼴 → Upstage 에 있는지 → 저장. 없으면 400, 확인 못 하면 502(둘 다 저장 안 함)
#  - 시작: 저장한 값 우선, 없으면 환경 변수. 쓴 값은 분석 행에. 결과 기록은 시작할 때 쓴 값
# ==========================================================================

from __future__ import annotations

import json
import logging
from collections.abc import Iterator

import httpx
import pytest
from api_fakes import FAKE_AGENT_ID, FAKE_CONFIG_ID, FAKE_ENV
from fastapi.testclient import TestClient
from shared_ctx import Ctx, install

from api.index import app
from imask_backend.settings import load_settings
from imask_backend.store import StoreError, SupabaseStore

PASSWORD = "test-settings-password"
AGENT = "agt_SavedAgent42"
CONFIG = "60"
OPEN = "/api/py/settings/workflow/open"
SAVE = "/api/py/settings/workflow"


@pytest.fixture
def ctx(monkeypatch: pytest.MonkeyPatch) -> Iterator[Ctx]:
    context = install(monkeypatch, {**FAKE_ENV, "SETTINGS_PASSWORD": PASSWORD})
    context.server.agents = {
        AGENT: ("v2_full", {CONFIG: "v2_full 최종"}),
        FAKE_AGENT_ID: ("main", {FAKE_CONFIG_ID: "main 설정"}),
    }
    try:
        with TestClient(app) as client:
            context.client = client
            yield context
    finally:
        app.dependency_overrides.clear()


def _save(ctx: Ctx, **overrides: str) -> httpx.Response:
    return ctx.client.post(SAVE, json={"password": PASSWORD, "agent_id": AGENT, "config_id": CONFIG, **overrides})


def _started(ctx: Ctx) -> str:
    analysis_id = ctx.store.put(status="queued")
    assert ctx.start(analysis_id).status_code == 200
    return analysis_id


# --- 비밀번호 ------------------------------------------------------------------------------


def test_no_password_on_server_locks_everyone_out(monkeypatch: pytest.MonkeyPatch) -> None:
    context = install(monkeypatch)  # FAKE_ENV 에는 SETTINGS_PASSWORD 가 없다
    try:
        with TestClient(app) as client:
            for path, body in ((OPEN, {"password": ""}), (SAVE, {"password": "", "agent_id": AGENT, "config_id": CONFIG})):
                response = client.post(path, json=body)
                assert response.status_code == 503
                assert "비밀번호" in response.json()["detail"]
        context.no_upstage()
        assert context.store.workflow is None
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("wrong", ["", " ", "wrong", PASSWORD + "x", PASSWORD.upper(), "\ud800"])
def test_wrong_password_touches_nothing(ctx: Ctx, wrong: str) -> None:
    content = json.dumps({"password": wrong}).encode("ascii")
    headers = {"content-type": "application/json"}
    assert ctx.client.post(OPEN, content=content, headers=headers).status_code in (400, 401)
    body = json.dumps({"password": wrong, "agent_id": AGENT, "config_id": CONFIG}).encode("ascii")
    assert ctx.client.post(SAVE, content=body, headers=headers).status_code in (400, 401)
    ctx.no_upstage()
    assert ctx.store.workflow is None


def test_wrong_password_message(ctx: Ctx) -> None:
    response = ctx.client.post(OPEN, json={"password": "wrong"})
    assert response.status_code == 401 and response.json() == {"detail": "비밀번호가 맞지 않습니다."}


@pytest.mark.parametrize("body", [{}, {"password": 1234}, {"password": None}, {"password": "x" * 201}])
def test_bad_open_body_is_400(ctx: Ctx, body: object) -> None:
    assert ctx.client.post(OPEN, json=body).status_code == 400
    ctx.no_upstage()


def test_password_is_not_in_the_masking_table() -> None:
    # 짧은 값을 가림 사전에 넣으면 분석 결과 속 같은 숫자까지 가려진다
    settings = load_settings({**FAKE_ENV, "SETTINGS_PASSWORD": "1234"})
    assert settings.settings_password() == "1234"
    assert "1234" not in settings.secrets()
    assert "1234" not in repr(settings)
    assert set(settings.configured()) == {"supabase", "upstage", "upstage_project"}  # health 에도 없다


# --- 열기 ----------------------------------------------------------------------------------


def test_open_shows_env_values_until_something_is_saved(ctx: Ctx) -> None:
    response = ctx.client.post(OPEN, json={"password": PASSWORD})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "agent_id": FAKE_AGENT_ID,
        "config_id": FAKE_CONFIG_ID,
        "agent_name": "main",
        "config_name": "main 설정",
    }


def test_open_shows_saved_values(ctx: Ctx) -> None:
    ctx.store.save_workflow_settings(AGENT, CONFIG)
    out = ctx.client.post(OPEN, json={"password": PASSWORD}).json()
    assert (out["agent_id"], out["config_id"], out["agent_name"]) == (AGENT, CONFIG, "v2_full")


def test_open_still_works_when_upstage_is_down(ctx: Ctx, caplog: pytest.LogCaptureFixture) -> None:
    ctx.server.errors[("GET", "agent")] = (500, {"error": {"message": f"oops {FAKE_AGENT_ID}"}})
    with caplog.at_level(logging.WARNING, logger="imask.workflow_settings"):
        response = ctx.client.post(OPEN, json={"password": PASSWORD})
    assert response.status_code == 200
    assert (response.json()["agent_name"], response.json()["config_name"]) == (None, None)
    assert FAKE_AGENT_ID not in caplog.text and PASSWORD not in caplog.text


# --- 저장 ----------------------------------------------------------------------------------


def test_save_checks_upstage_then_stores(ctx: Ctx) -> None:
    response = _save(ctx)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"agent_id": AGENT, "config_id": CONFIG, "agent_name": "v2_full", "config_name": "v2_full 최종"}
    assert ctx.store.workflow is not None and ctx.store.workflow["agent_id"] == AGENT
    assert [r.url.path for r in ctx.server.requests] == [f"/v2/agents/{AGENT}", f"/v2/agents/{AGENT}/configs/{CONFIG}"]


def test_save_trims_spaces(ctx: Ctx) -> None:
    assert _save(ctx, agent_id=f"  {AGENT}\n", config_id=f" {CONFIG} ").status_code == 200
    assert ctx.store.workflow is not None
    assert (ctx.store.workflow["agent_id"], ctx.store.workflow["config_id"]) == (AGENT, CONFIG)


@pytest.mark.parametrize(
    "agent",
    ["", "v2_full", "main_imask_workflow", "agt_", "agt_a/b", "agt_a?b", "agt_a b", "AGT_abc", "agt_한글", "agt_" + "a" * 129],
)
def test_bad_agent_is_refused_before_upstage(ctx: Ctx, agent: str) -> None:
    # 2026-11-06 운영 장애: 워크플로우 이름이 들어가 모든 분석이 400 으로 실패했다
    response = _save(ctx, agent_id=agent)
    assert response.status_code == 400 and "agt_" in response.json()["detail"]
    ctx.no_upstage()
    assert ctx.store.workflow is None


@pytest.mark.parametrize("config", ["", "abc", "6.0", "-1", "6 0", "cfg_1", "1234567890", "٣"])
def test_bad_config_is_refused_before_upstage(ctx: Ctx, config: str) -> None:
    response = _save(ctx, config_id=config)
    assert response.status_code == 400 and "숫자" in response.json()["detail"]
    ctx.no_upstage()
    assert ctx.store.workflow is None


@pytest.mark.parametrize(("agent", "config"), [("agt_NoSuchAgent", CONFIG), (AGENT, "999")])
def test_not_on_upstage_is_not_saved(ctx: Ctx, agent: str, config: str) -> None:
    response = _save(ctx, agent_id=agent, config_id=config)
    assert response.status_code == 400
    assert response.json() == {"detail": "Upstage 에 없는 에이전트 또는 설정 번호입니다."}
    assert ctx.store.workflow is None


@pytest.mark.parametrize(
    ("kind", "error"),
    [
        ("agent", (500, {"error": {"message": "boom"}})),
        ("config", (500, {"error": {"message": "boom"}})),
        ("agent", (429, {"error": {"message": "slow down"}})),
        ("agent", httpx.ConnectError("down")),
    ],
)
def test_unconfirmed_is_not_saved(ctx: Ctx, kind: str, error: object) -> None:
    ctx.server.errors[("GET", kind)] = error
    response = _save(ctx)
    assert response.status_code == 502
    assert response.json() == {"detail": "Upstage 에서 확인하지 못했습니다. 잠시 후 다시 시도해 주세요."}
    assert ctx.store.workflow is None


def test_store_failure_is_502_without_values(ctx: Ctx, caplog: pytest.LogCaptureFixture) -> None:
    ctx.store.fail.add("save_workflow_settings")
    with caplog.at_level(logging.INFO, logger="imask"):
        assert _save(ctx).status_code == 502
    assert AGENT not in caplog.text and PASSWORD not in caplog.text


def test_save_logs_no_values(ctx: Ctx, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="imask.workflow_settings"):
        assert _save(ctx).status_code == 200
    assert caplog.text and AGENT not in caplog.text and CONFIG not in caplog.text and PASSWORD not in caplog.text


# --- 분석 시작·결과 ---------------------------------------------------------------------------


def test_start_uses_env_when_nothing_is_saved(ctx: Ctx) -> None:
    analysis_id = _started(ctx)
    body = ctx.server.job_bodies[-1]
    assert (body["model"], body["config_id"]) == (FAKE_AGENT_ID, FAKE_CONFIG_ID)
    row = ctx.store.analyses[analysis_id]
    assert (row["agent_id"], row["config_id"]) == (FAKE_AGENT_ID, FAKE_CONFIG_ID)


def test_start_uses_saved_values_right_away(ctx: Ctx) -> None:
    assert _save(ctx).status_code == 200
    analysis_id = _started(ctx)
    body = ctx.server.job_bodies[-1]
    assert (body["model"], body["config_id"]) == (AGENT, CONFIG)
    row = ctx.store.analyses[analysis_id]
    assert (row["agent_id"], row["config_id"]) == (AGENT, CONFIG)


def test_retry_uses_saved_values(ctx: Ctx) -> None:
    assert _save(ctx).status_code == 200
    analysis_id = ctx.store.put(status="failed", error="이전 실패")
    assert ctx.retry(analysis_id).status_code == 200
    body = ctx.server.job_bodies[-1]
    assert (body["model"], body["config_id"]) == (AGENT, CONFIG)


def test_start_stops_before_claim_when_saved_values_cannot_be_read(ctx: Ctx) -> None:
    ctx.store.fail.add("get_workflow_settings")
    analysis_id = ctx.store.put(status="queued")
    assert ctx.start(analysis_id).status_code == 502
    assert ctx.store.analyses[analysis_id]["status"] == "queued"
    ctx.no_upstage()


def test_half_saved_row_falls_back_to_env(ctx: Ctx) -> None:
    ctx.store.workflow = {"agent_id": AGENT, "config_id": ""}
    _started(ctx)
    assert ctx.server.job_bodies[-1]["model"] == FAKE_AGENT_ID


def test_result_records_the_config_the_run_started_with(ctx: Ctx) -> None:
    assert _save(ctx).status_code == 200
    analysis_id = _started(ctx)
    # 실행 도중에 다른 설정으로 바꿔도 그 실행의 기록은 그대로다
    ctx.store.save_workflow_settings(FAKE_AGENT_ID, FAKE_CONFIG_ID)
    ctx.server.last_status = "completed"
    response = ctx.get(analysis_id)
    assert response.status_code == 200 and response.json()["status"] == "done"
    assert response.json()["result"]["job"]["config_id"] == CONFIG


def test_run_started_before_the_column_uses_env_value(ctx: Ctx) -> None:
    analysis_id = ctx.store.put(status="running", job_id="job_old")
    ctx.server.last_status = "completed"
    response = ctx.get(analysis_id)
    assert response.status_code == 200 and response.json()["result"]["job"]["config_id"] == FAKE_CONFIG_ID


def test_saved_agent_id_is_masked_in_the_stored_result(ctx: Ctx) -> None:
    # 환경 변수에 없는 값도 그 실행의 값이면 가린다(응답에 섞여 와도 저장·화면에 남지 않게)
    assert _save(ctx).status_code == 200
    analysis_id = _started(ctx)
    ctx.server.full_response = {**ctx.server.full_response, "note": f"echo {AGENT}"}
    ctx.server.last_status = "completed"
    assert ctx.get(analysis_id).status_code == 200
    stored = json.dumps(ctx.store.analyses[analysis_id]["result"], ensure_ascii=False)
    assert AGENT not in stored


def test_analysis_response_does_not_show_agent_or_config_columns(ctx: Ctx) -> None:
    assert _save(ctx).status_code == 200
    out = ctx.get(_started(ctx)).json()
    assert "agent_id" not in out and "config_id" not in out


# --- SupabaseStore ----------------------------------------------------------------------------


class _Query:
    def __init__(self, log: list[tuple[str, object]], data: object, error: Exception | None) -> None:
        self.log, self.data, self.error = log, data, error

    def __getattr__(self, name: str):  # select·eq·limit·upsert 를 차례로 적는다
        def call(*args: object, **kwargs: object) -> _Query:
            self.log.append((name, (args, kwargs)))
            return self

        return call

    def execute(self) -> object:
        if self.error is not None:
            raise self.error
        return type("Response", (), {"data": self.data})()


def _store(data: object, error: Exception | None = None) -> tuple[SupabaseStore, list[tuple[str, object]]]:
    log: list[tuple[str, object]] = []
    store = SupabaseStore.__new__(SupabaseStore)
    store._table = lambda name: (log.append(("table", name)), _Query(log, data, error))[1]  # type: ignore[method-assign]
    return store, log


def test_store_reads_the_single_row() -> None:
    store, log = _store([{"agent_id": AGENT, "config_id": CONFIG, "updated_at": "t"}])
    assert store.get_workflow_settings() == {"agent_id": AGENT, "config_id": CONFIG, "updated_at": "t"}
    assert log[0] == ("table", "workflow_settings")
    assert ("eq", (("id", 1), {})) in log


def test_store_read_empty_is_none() -> None:
    assert _store([])[0].get_workflow_settings() is None


def test_store_saves_by_upsert() -> None:
    store, log = _store([{"agent_id": AGENT, "config_id": CONFIG}])
    assert store.save_workflow_settings(AGENT, CONFIG)["config_id"] == CONFIG
    assert ("upsert", (({"id": 1, "agent_id": AGENT, "config_id": CONFIG},), {"on_conflict": "id"})) in log


def test_store_errors_have_no_values() -> None:
    error = RuntimeError(f"failed for {AGENT}")
    for call in (lambda s: s.get_workflow_settings(), lambda s: s.save_workflow_settings(AGENT, CONFIG)):
        with pytest.raises(StoreError) as caught:
            call(_store([], error)[0])
        assert AGENT not in caught.value.message and "RuntimeError" in caught.value.message
    with pytest.raises(StoreError):
        _store([])[0].save_workflow_settings(AGENT, CONFIG)
