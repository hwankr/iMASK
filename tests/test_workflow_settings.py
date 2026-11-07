# ==========================================================================
#  웹 설정 화면의 워크플로우 설정(imask_backend.workflow_settings, 네트워크 없음)
#  - 비밀번호: 서버에 없으면 503, 틀리면 401(Upstage·저장소 안 부름). 값은 secrets()·응답·로그에 없음
#    저장소 준비보다도 먼저다 — Supabase 설정이 빠져도 503·401, 비밀번호가 맞으면 500(이름만)
#  - /api/py/settings/ 아래 응답은 상태와 상관없이 Cache-Control: no-store, 다른 경로에는 생기지 않음
#  - 저장: 꼴 → Upstage 에 있는지 → 저장. 없으면 400, 확인 못 하면 502(둘 다 저장 안 함)
#  - 시작: 저장한 값 우선, 없으면 환경 변수. 쓴 값은 분석 행에. 결과 기록은 시작할 때 쓴 값
#  - 목록: 비밀번호가 맨 먼저(틀리면 저장소·Upstage 호출 0), 등록 규칙의 모든 갈래, 삭제, 등록·삭제는 지금 적용 값을 바꾸지 않음
# ==========================================================================

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable, Iterator

import httpx
import pytest
from api_fakes import FAKE_AGENT_ID, FAKE_CONFIG_ID, FAKE_ENV
from fastapi.testclient import TestClient
from shared_ctx import Ctx, install

from api import index as api_index
from api.index import app, get_store
from imask_backend.settings import load_settings
from imask_backend.store import PRESET_COLUMNS, StoreError, SupabaseStore

PASSWORD = "test-settings-password"
AGENT = "agt_SavedAgent42"
CONFIG = "60"
OTHER_AGENT = "agt_OtherAgent7"
OTHER_CONFIG = "61"
OPEN = "/api/py/settings/workflow/open"
SAVE = "/api/py/settings/workflow"
PRESETS = "/api/py/settings/workflow/presets"
PRESETS_DELETE = "/api/py/settings/workflow/presets/delete"
PRESET_KEYS = {"id", "name", "agent_id", "config_id"}
STORE_METHODS = (
    "get_workflow_settings",
    "save_workflow_settings",
    "list_workflow_presets",
    "insert_workflow_preset",
    "delete_workflow_preset",
)
MSG_BAD_NAME = "이름은 1~60자로 넣어 주세요."
MSG_TOO_MANY = "워크플로우는 50개까지 등록할 수 있습니다."
MSG_TAKEN = "같은 이름의 워크플로우가 이미 있습니다."
MSG_FORMAT = "요청 형식이 올바르지 않습니다."
MSG_NOT_ON_UPSTAGE = "Upstage 에 없는 에이전트 또는 설정 번호입니다."
MSG_UNCONFIRMED = "Upstage 에서 확인하지 못했습니다. 잠시 후 다시 시도해 주세요."
MSG_STORE = "데이터 저장소에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요."


@pytest.fixture
def ctx(monkeypatch: pytest.MonkeyPatch) -> Iterator[Ctx]:
    context = install(monkeypatch, {**FAKE_ENV, "SETTINGS_PASSWORD": PASSWORD})
    context.server.agents = {
        AGENT: ("v2_full", {CONFIG: "v2_full 최종"}),
        OTHER_AGENT: ("v3", {OTHER_CONFIG: "v3 시험"}),
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


def _add(ctx: Ctx, **overrides: str) -> httpx.Response:
    return ctx.client.post(PRESETS, json={"password": PASSWORD, "name": "v2 최종", "agent_id": AGENT, "config_id": CONFIG, **overrides})


def _delete(ctx: Ctx, preset_id: str, **overrides: str) -> httpx.Response:
    return ctx.client.post(PRESETS_DELETE, json={"password": PASSWORD, "id": preset_id, **overrides})


def _raw(ctx: Ctx, path: str, body: dict[str, object]) -> httpx.Response:
    """짝 없는 서로게이트처럼 httpx 의 json= 이 보낼 수 없는 값을 ASCII escape JSON 으로 보낸다."""
    content = json.dumps(body, ensure_ascii=True).encode("ascii")
    return ctx.client.post(path, content=content, headers={"content-type": "application/json"})


def _names(response: httpx.Response) -> list[str]:
    return [preset["name"] for preset in response.json()["presets"]]


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
        "presets": [],
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


def test_save_response_has_no_presets(ctx: Ctx) -> None:
    # 저장(적용) 응답은 지금처럼 네 키만
    ctx.store.put_preset("v2 최종", AGENT, CONFIG)
    assert set(_save(ctx).json()) == {"agent_id", "config_id", "agent_name", "config_name"}


# --- 목록: 비밀번호 ---------------------------------------------------------------------------


def _preset_bodies(password: str) -> list[tuple[str, dict[str, object]]]:
    return [
        (PRESETS, {"password": password, "name": "이름", "agent_id": AGENT, "config_id": CONFIG}),
        # 비밀번호가 꼴 검사보다 먼저다
        (PRESETS, {"password": password, "name": "", "agent_id": "", "config_id": ""}),
        (PRESETS_DELETE, {"password": password, "id": str(uuid.uuid4())}),
        (PRESETS_DELETE, {"password": password, "id": "uuid 아님"}),
    ]


@pytest.mark.parametrize(
    ("wrong", "status"),
    [("", 401), (" ", 401), ("wrong", 401), (PASSWORD + "x", 401), (PASSWORD.upper(), 401), ("\ud800", 400)],
)
def test_wrong_password_on_preset_paths_touches_nothing(ctx: Ctx, wrong: str, status: int) -> None:
    # 저장소가 불리면 fail 때문에 502 가 된다. 짝 없는 서로게이트는 길이 제한(Field)이 있는 비밀번호 칸에서 본문 형식 오류(400)로 막힌다
    ctx.store.fail.update(STORE_METHODS)
    ctx.store.put_preset("있던 항목", AGENT, CONFIG)
    for path, body in _preset_bodies(wrong):
        response = _raw(ctx, path, body)
        assert response.status_code == status
        assert response.json()["detail"] == ("비밀번호가 맞지 않습니다." if status == 401 else MSG_FORMAT)
    ctx.no_upstage()
    assert ctx.store.preset_calls == [] and ctx.store.calls == []
    assert [preset["name"] for preset in ctx.store.presets] == ["있던 항목"] and ctx.store.workflow is None


@pytest.mark.parametrize("path", [PRESETS, PRESETS_DELETE])
def test_missing_password_is_400_and_touches_nothing(ctx: Ctx, path: str) -> None:
    body = {"name": "이름", "agent_id": AGENT, "config_id": CONFIG} if path == PRESETS else {"id": str(uuid.uuid4())}
    response = ctx.client.post(path, json=body)
    assert response.status_code == 400 and response.json() == {"detail": MSG_FORMAT}
    ctx.no_upstage()
    assert ctx.store.preset_calls == [] and ctx.store.presets == []


def test_no_password_on_server_locks_preset_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    context = install(monkeypatch)  # FAKE_ENV 에는 SETTINGS_PASSWORD 가 없다
    try:
        with TestClient(app) as client:
            for path, body in _preset_bodies(""):
                assert client.post(path, json=body).status_code == 503
        context.no_upstage()
        assert context.store.preset_calls == []
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("path", "body"),
    [
        (PRESETS, {"password": PASSWORD, "agent_id": AGENT, "config_id": CONFIG}),
        (PRESETS, {"password": PASSWORD, "name": 1, "agent_id": AGENT, "config_id": CONFIG}),
        (PRESETS, {"password": PASSWORD, "name": None, "agent_id": AGENT, "config_id": CONFIG}),
        (PRESETS, {"password": PASSWORD, "name": "이름", "agent_id": 1, "config_id": CONFIG}),
        (PRESETS, {"password": PASSWORD, "name": "이름", "agent_id": AGENT, "config_id": 60}),
        (PRESETS, {"password": PASSWORD, "name": "이름", "agent_id": AGENT}),
        (PRESETS_DELETE, {"password": PASSWORD}),
        (PRESETS_DELETE, {"password": PASSWORD, "id": 1}),
        (PRESETS_DELETE, {"password": PASSWORD, "id": None}),
    ],
)
def test_bad_preset_body_is_400(ctx: Ctx, path: str, body: dict[str, object]) -> None:
    response = ctx.client.post(path, json=body)
    assert response.status_code == 400 and response.json() == {"detail": MSG_FORMAT}
    ctx.no_upstage()
    assert ctx.store.preset_calls == []


# --- 목록: 열기 --------------------------------------------------------------------------------


def test_open_lists_presets_in_registered_order(ctx: Ctx) -> None:
    first = ctx.store.put_preset("하나", AGENT, CONFIG)
    second = ctx.store.put_preset("둘", FAKE_AGENT_ID, FAKE_CONFIG_ID)
    response = ctx.client.post(OPEN, json={"password": PASSWORD})
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.json()["presets"] == [
        {"id": first["id"], "name": "하나", "agent_id": AGENT, "config_id": CONFIG},
        {"id": second["id"], "name": "둘", "agent_id": FAKE_AGENT_ID, "config_id": FAKE_CONFIG_ID},
    ]
    assert ctx.store.preset_limits == [50]


def test_same_time_is_ordered_by_id(ctx: Ctx) -> None:
    low, high = "00000000-0000-4000-8000-000000000001", "ffffffff-0000-4000-8000-000000000001"
    ctx.store.put_preset("뒤", AGENT, CONFIG, id=high, created_at="2026-11-07T00:00:00+00:00")
    ctx.store.put_preset("앞", AGENT, CONFIG, id=low, created_at="2026-11-07T00:00:00+00:00")
    assert _names(ctx.client.post(OPEN, json={"password": PASSWORD})) == ["앞", "뒤"]


def test_open_calls_upstage_once_regardless_of_presets(ctx: Ctx) -> None:
    for number in range(5):
        ctx.store.put_preset(f"항목 {number}", AGENT, CONFIG)
    assert ctx.client.post(OPEN, json={"password": PASSWORD}).status_code == 200
    # 지금 적용 값의 에이전트·설정 한 번씩만(항목마다 부르지 않는다)
    assert [r.url.path for r in ctx.server.requests] == [f"/v2/agents/{FAKE_AGENT_ID}", f"/v2/agents/{FAKE_AGENT_ID}/configs/{FAKE_CONFIG_ID}"]


def test_open_skips_malformed_rows(ctx: Ctx) -> None:
    good = ctx.store.put_preset("정상", AGENT, CONFIG)
    ctx.store.put_preset("번호가 숫자", AGENT, 60)
    ctx.store.put_preset(None, AGENT, CONFIG)
    ctx.store.put_preset("에이전트 없음", None, CONFIG)
    out = ctx.client.post(OPEN, json={"password": PASSWORD}).json()
    assert out["presets"] == [{"id": good["id"], "name": "정상", "agent_id": AGENT, "config_id": CONFIG}]


def test_open_is_502_when_presets_cannot_be_read(ctx: Ctx) -> None:
    ctx.store.fail.add("list_workflow_presets")
    response = ctx.client.post(OPEN, json={"password": PASSWORD})
    assert response.status_code == 502 and response.json() == {"detail": MSG_STORE}
    ctx.no_upstage()


def test_open_shows_presets_when_upstage_is_down(ctx: Ctx) -> None:
    ctx.store.put_preset("하나", AGENT, CONFIG)
    ctx.server.errors[("GET", "agent")] = (500, {"error": {"message": "oops"}})
    response = ctx.client.post(OPEN, json={"password": PASSWORD})
    assert response.status_code == 200 and _names(response) == ["하나"]
    assert response.json()["agent_name"] is None


def test_open_passes_surrogates_through_json_out(ctx: Ctx) -> None:
    ctx.store.put_preset("이름\ud800", AGENT, CONFIG)
    response = ctx.client.post(OPEN, json={"password": PASSWORD})
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.json()["presets"][0]["name"] == "이름\ud800"


# --- 목록: 등록 --------------------------------------------------------------------------------


def test_add_checks_upstage_then_stores_and_returns_the_list(ctx: Ctx) -> None:
    ctx.store.put_preset("있던 항목", FAKE_AGENT_ID, FAKE_CONFIG_ID)
    response = _add(ctx)
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    presets = response.json()["presets"]
    assert set(response.json()) == {"presets"} and [set(preset) for preset in presets] == [PRESET_KEYS, PRESET_KEYS]
    assert [preset["name"] for preset in presets] == ["있던 항목", "v2 최종"]
    assert (presets[1]["agent_id"], presets[1]["config_id"]) == (AGENT, CONFIG)
    assert [r.url.path for r in ctx.server.requests] == [f"/v2/agents/{AGENT}", f"/v2/agents/{AGENT}/configs/{CONFIG}"]
    assert ctx.store.preset_calls == ["list_workflow_presets", "insert_workflow_preset", "list_workflow_presets"]


def test_add_trims_spaces(ctx: Ctx) -> None:
    response = _add(ctx, name="  v2 최종\t\n", agent_id=f"  {AGENT}\n", config_id=f" {CONFIG} ")
    assert response.status_code == 200
    assert ctx.store.presets[0]["name"] == "v2 최종"
    assert (ctx.store.presets[0]["agent_id"], ctx.store.presets[0]["config_id"]) == (AGENT, CONFIG)


@pytest.mark.parametrize("name", ["가" * 60, "😀" * 60, "a" * 59 + "😀"])
def test_add_accepts_60_code_points(ctx: Ctx, name: str) -> None:
    assert _add(ctx, name=name).status_code == 200
    assert ctx.store.presets[0]["name"] == name


def test_add_counts_length_after_trimming(ctx: Ctx) -> None:
    assert _add(ctx, name=" " + "가" * 60 + " ").status_code == 200


@pytest.mark.parametrize(
    "name",
    [
        "",
        " ",
        "　\t\n",
        "가" * 61,
        "😀" * 61,
        "가" * 300,  # 본문 모델이 아니라 업무 로직이 이름 문구로 막는다
        "가\x00나",
        "가\n나",
        "가\t나",
        "가\x7f나",
        "가\x9f나",
        "가\ud800나",
        "\udfff",
    ],
)
def test_bad_name_is_refused_before_store_and_upstage(ctx: Ctx, name: str) -> None:
    response = _raw(ctx, PRESETS, {"password": PASSWORD, "name": name, "agent_id": AGENT, "config_id": CONFIG})
    assert response.status_code == 400 and response.json() == {"detail": MSG_BAD_NAME}
    ctx.no_upstage()
    assert ctx.store.preset_calls == [] and ctx.store.presets == []


def test_name_is_checked_before_agent_and_config(ctx: Ctx) -> None:
    response = _add(ctx, name="", agent_id="틀림", config_id="틀림")
    assert response.status_code == 400 and response.json() == {"detail": MSG_BAD_NAME}


@pytest.mark.parametrize("agent", ["", "v2_full", "agt_", "agt_a/b", "agt_a b", "AGT_abc", "agt_한글", "agt_" + "a" * 129])
def test_add_bad_agent_uses_the_save_message(ctx: Ctx, agent: str) -> None:
    response = _add(ctx, agent_id=agent)
    assert response.status_code == 400 and response.json() == {"detail": "에이전트 ID 는 agt_ 로 시작해야 합니다."}
    ctx.no_upstage()
    assert ctx.store.preset_calls == [] and ctx.store.presets == []


@pytest.mark.parametrize("config", ["", "abc", "6.0", "-1", "6 0", "1234567890", "٣"])
def test_add_bad_config_uses_the_save_message(ctx: Ctx, config: str) -> None:
    response = _add(ctx, config_id=config)
    assert response.status_code == 400 and response.json() == {"detail": "설정 번호는 숫자로 넣어 주세요."}
    ctx.no_upstage()
    assert ctx.store.preset_calls == [] and ctx.store.presets == []


def test_add_stops_at_the_limit(ctx: Ctx) -> None:
    for number in range(50):
        ctx.store.put_preset(f"항목 {number}", AGENT, CONFIG)
    response = _add(ctx)
    assert response.status_code == 400 and response.json() == {"detail": MSG_TOO_MANY}
    ctx.no_upstage()
    assert ctx.store.preset_calls == ["list_workflow_presets"] and len(ctx.store.presets) == 50
    assert ctx.store.preset_limits == [50]


def test_add_the_50th_is_allowed(ctx: Ctx) -> None:
    for number in range(49):
        ctx.store.put_preset(f"항목 {number}", AGENT, CONFIG)
    response = _add(ctx)
    assert response.status_code == 200 and len(response.json()["presets"]) == 50


def test_limit_is_checked_before_the_name(ctx: Ctx) -> None:
    for number in range(50):
        ctx.store.put_preset(f"항목 {number}", AGENT, CONFIG)
    response = _add(ctx, name="항목 0")
    assert response.status_code == 400 and response.json() == {"detail": MSG_TOO_MANY}


def test_add_same_name_stops_before_upstage(ctx: Ctx) -> None:
    ctx.store.put_preset("v2 최종", FAKE_AGENT_ID, FAKE_CONFIG_ID)
    for name in ("v2 최종", "  v2 최종 "):
        response = _add(ctx, name=name)
        assert response.status_code == 409 and response.json() == {"detail": MSG_TAKEN}
    ctx.no_upstage()
    assert len(ctx.store.presets) == 1 and "insert_workflow_preset" not in ctx.store.preset_calls


@pytest.mark.parametrize(("agent", "config"), [("agt_NoSuchAgent", CONFIG), (AGENT, "999")])
def test_add_not_on_upstage_is_not_stored(ctx: Ctx, agent: str, config: str) -> None:
    response = _add(ctx, agent_id=agent, config_id=config)
    assert response.status_code == 400 and response.json() == {"detail": MSG_NOT_ON_UPSTAGE}
    assert ctx.store.presets == [] and "insert_workflow_preset" not in ctx.store.preset_calls


@pytest.mark.parametrize(
    ("kind", "error"),
    [
        ("agent", (500, {"error": {"message": "boom"}})),
        ("config", (503, {"error": {"message": "boom"}})),
        ("agent", (429, {"error": {"message": "slow down"}})),
        ("agent", httpx.ConnectError("down")),
        ("config", httpx.ConnectError("down")),
    ],
)
def test_add_unconfirmed_is_not_stored(ctx: Ctx, kind: str, error: object) -> None:
    ctx.server.errors[("GET", kind)] = error
    response = _add(ctx)
    assert response.status_code == 502 and response.json() == {"detail": MSG_UNCONFIRMED}
    assert ctx.store.presets == [] and "insert_workflow_preset" not in ctx.store.preset_calls


def test_add_concurrent_same_name_is_409(ctx: Ctx) -> None:
    # 사전 확인과 Upstage 확인을 지난 뒤, 저장 직전에 다른 요청이 같은 이름을 넣었다(DB unique 충돌)
    ctx.store.before_preset_insert = lambda store: store.put_preset("v2 최종", FAKE_AGENT_ID, FAKE_CONFIG_ID)
    response = _add(ctx)
    assert response.status_code == 409 and response.json() == {"detail": MSG_TAKEN}
    assert [preset["agent_id"] for preset in ctx.store.presets] == [FAKE_AGENT_ID]  # 먼저 넣은 행 그대로


@pytest.mark.parametrize("method", ["list_workflow_presets", "insert_workflow_preset"])
def test_add_store_failure_is_502_without_values(ctx: Ctx, caplog: pytest.LogCaptureFixture, method: str) -> None:
    ctx.store.fail.add(method)
    with caplog.at_level(logging.INFO, logger="imask"):
        response = _add(ctx, name="비밀스러운 이름")
    assert response.status_code == 502 and response.json() == {"detail": MSG_STORE}
    assert AGENT not in caplog.text and PASSWORD not in caplog.text and "비밀스러운 이름" not in caplog.text


# --- 목록: 삭제 --------------------------------------------------------------------------------


def test_delete_removes_and_returns_the_list(ctx: Ctx) -> None:
    first = ctx.store.put_preset("하나", AGENT, CONFIG)
    ctx.store.put_preset("둘", AGENT, CONFIG)
    response = _delete(ctx, first["id"])
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert set(response.json()) == {"presets"} and _names(response) == ["둘"]
    ctx.no_upstage()


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "uuid 아님",
        "00000000000040008000000000000001",  # uuid.UUID 는 받지만 꼴이 아니다
        "{00000000-0000-4000-8000-000000000001}",
        "00000000-0000-4000-8000-000000000001\n",
        " 00000000-0000-4000-8000-000000000001",
        "00000000-0000-4000-8000-00000000000g",
        "00000000-0000-4000-8000-000000000001' or '1'='1",
    ],
)
def test_delete_bad_id_is_400_before_store(ctx: Ctx, bad: str) -> None:
    ctx.store.put_preset("하나", AGENT, CONFIG)
    response = _delete(ctx, bad)
    assert response.status_code == 400 and response.json() == {"detail": MSG_FORMAT}
    ctx.no_upstage()
    assert ctx.store.preset_calls == [] and len(ctx.store.presets) == 1


def test_delete_missing_id_is_success(ctx: Ctx) -> None:
    ctx.store.put_preset("하나", AGENT, CONFIG)
    response = _delete(ctx, str(uuid.uuid4()))
    assert response.status_code == 200 and _names(response) == ["하나"]
    ctx.no_upstage()


def test_delete_uppercase_uuid_removes_the_row(ctx: Ctx) -> None:
    target = "abcdef00-0000-4000-8000-0000000000ab"  # 글자가 든 고정 id — 대문자로 바꾸면 달라진다
    ctx.store.put_preset("지울 항목", AGENT, CONFIG, id=target)
    ctx.store.put_preset("남는 항목", AGENT, CONFIG)
    response = _delete(ctx, target.upper())
    assert response.status_code == 200 and _names(response) == ["남는 항목"]
    assert [preset["name"] for preset in ctx.store.presets] == ["남는 항목"]


@pytest.mark.parametrize("method", ["delete_workflow_preset", "list_workflow_presets"])
def test_delete_store_failure_is_502(ctx: Ctx, method: str) -> None:
    ctx.store.fail.add(method)
    response = _delete(ctx, str(uuid.uuid4()))
    assert response.status_code == 502 and response.json() == {"detail": MSG_STORE}


# --- 목록: 지금 적용 값은 그대로 --------------------------------------------------------------------


def test_add_and_delete_do_not_change_the_applied_workflow(ctx: Ctx) -> None:
    assert _save(ctx).status_code == 200
    before = dict(ctx.store.workflow or {})
    assert _add(ctx, name="다른 설정", agent_id=OTHER_AGENT, config_id=OTHER_CONFIG).status_code == 200
    assert ctx.store.workflow == before
    assert _delete(ctx, ctx.store.presets[0]["id"]).status_code == 200
    assert ctx.store.workflow == before
    assert ctx.store.presets == []


def test_add_and_delete_do_not_create_the_applied_row(ctx: Ctx) -> None:
    # 저장한 적이 없으면 등록·삭제 뒤에도 환경 변수를 쓴다
    assert _add(ctx).status_code == 200
    assert _delete(ctx, ctx.store.presets[0]["id"]).status_code == 200
    assert ctx.store.workflow is None
    out = ctx.client.post(OPEN, json={"password": PASSWORD}).json()
    assert (out["agent_id"], out["config_id"]) == (FAKE_AGENT_ID, FAKE_CONFIG_ID)


def test_deleting_the_applied_preset_keeps_the_applied_values(ctx: Ctx) -> None:
    # 적용 = 항목 값을 저장 경로로 복사 → 그 항목을 지워도 지금 적용·분석 시작 값은 그대로
    assert _add(ctx).status_code == 200
    preset = ctx.store.presets[0]
    assert _save(ctx, agent_id=preset["agent_id"], config_id=preset["config_id"]).status_code == 200
    assert _delete(ctx, preset["id"]).status_code == 200
    assert ctx.store.workflow is not None
    assert (ctx.store.workflow["agent_id"], ctx.store.workflow["config_id"]) == (AGENT, CONFIG)
    out = ctx.client.post(OPEN, json={"password": PASSWORD}).json()
    assert (out["agent_id"], out["config_id"], out["presets"]) == (AGENT, CONFIG, [])
    analysis_id = _started(ctx)
    body = ctx.server.job_bodies[-1]
    assert (body["model"], body["config_id"]) == (AGENT, CONFIG)
    assert (ctx.store.analyses[analysis_id]["agent_id"], ctx.store.analyses[analysis_id]["config_id"]) == (AGENT, CONFIG)


def test_start_does_not_read_the_preset_list(ctx: Ctx) -> None:
    ctx.store.fail.add("list_workflow_presets")  # 읽으면 실패한다
    ctx.store.put_preset("하나", AGENT, CONFIG)
    _started(ctx)
    assert ctx.server.job_bodies[-1]["model"] == FAKE_AGENT_ID
    assert ctx.store.preset_calls == []


# --- 목록: 로그 --------------------------------------------------------------------------------


def test_preset_paths_log_no_values(ctx: Ctx, caplog: pytest.LogCaptureFixture) -> None:
    name = "로그에 없어야 할 이름"
    with caplog.at_level(logging.DEBUG, logger="imask"):
        assert ctx.client.post(OPEN, json={"password": PASSWORD}).status_code == 200
        assert _add(ctx, name=name).status_code == 200
        assert _add(ctx, name=name).status_code == 409
        assert _add(ctx, name="없는 설정", config_id="999").status_code == 400
        assert _add(ctx, name="잘못된 꼴\x00", agent_id="틀림").status_code == 400
        ctx.server.errors[("GET", "agent")] = (500, {"error": {"message": f"oops {AGENT}"}})
        assert _add(ctx, name="연결 오류").status_code == 502
        preset_id = ctx.store.presets[0]["id"]
        assert _delete(ctx, preset_id).status_code == 200
    assert caplog.text
    for value in (name, "없는 설정", "연결 오류", preset_id, AGENT, PASSWORD):
        assert value not in caplog.text


# --- 설정 경로: 비밀번호가 저장소 준비보다 먼저 ---------------------------------------------------


def _four_paths(password: str) -> list[tuple[str, dict[str, object]]]:
    return [
        (OPEN, {"password": password}),
        (SAVE, {"password": password, "agent_id": AGENT, "config_id": CONFIG}),
        (PRESETS, {"password": password, "name": "이름", "agent_id": AGENT, "config_id": CONFIG}),
        (PRESETS_DELETE, {"password": password, "id": str(uuid.uuid4())}),
    ]


@pytest.fixture
def no_supabase(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[str | None], tuple[Ctx, list[object]]]]:
    """get_store 를 바꿔 끼우지 않고 Supabase 설정만 뺀 앱 → (ctx, 저장소를 만들려 한 기록). 인자는 서버 비밀번호(None 이면 없음)."""

    def build(password: str | None) -> tuple[Ctx, list[object]]:
        env = {key: value for key, value in FAKE_ENV.items() if key not in ("SUPABASE_URL", "SUPABASE_SECRET_KEY")}
        if password is not None:
            env["SETTINGS_PASSWORD"] = password
        context = install(monkeypatch, env)
        del app.dependency_overrides[get_store]  # 진짜 get_store(설정이 없으면 ConfigError)
        built: list[object] = []
        real = api_index.cached_store

        def spy(settings: object) -> object:
            built.append(settings)
            return real(settings)  # type: ignore[arg-type]

        monkeypatch.setattr(api_index, "cached_store", spy)
        context.client = client
        return context, built

    try:
        with TestClient(app) as client:
            yield build
    finally:
        app.dependency_overrides.clear()


def test_no_server_password_is_503_before_the_store(no_supabase: Callable[[str | None], tuple[Ctx, list[object]]]) -> None:
    context, built = no_supabase(None)
    for path, body in _four_paths(PASSWORD):
        response = context.client.post(path, json=body)
        assert response.status_code == 503 and response.json() == {"detail": "서버에 설정 비밀번호가 없어 열 수 없습니다."}
        assert response.headers["cache-control"] == "no-store"
    assert built == []
    context.no_upstage()


def test_wrong_password_is_401_before_the_store(no_supabase: Callable[[str | None], tuple[Ctx, list[object]]]) -> None:
    context, built = no_supabase(PASSWORD)
    for path, body in _four_paths("wrong"):
        response = context.client.post(path, json=body)
        assert response.status_code == 401 and response.json() == {"detail": "비밀번호가 맞지 않습니다."}
        assert response.headers["cache-control"] == "no-store"
    assert built == []
    context.no_upstage()


def test_bad_body_is_400_before_the_store(no_supabase: Callable[[str | None], tuple[Ctx, list[object]]]) -> None:
    context, built = no_supabase(PASSWORD)
    for path, _ in _four_paths(PASSWORD):
        response = context.client.post(path, json={})
        assert response.status_code == 400 and response.json() == {"detail": MSG_FORMAT}
        assert response.headers["cache-control"] == "no-store"
    assert built == []
    context.no_upstage()


def test_right_password_reports_missing_names_only(
    no_supabase: Callable[[str | None], tuple[Ctx, list[object]]], caplog: pytest.LogCaptureFixture
) -> None:
    context, built = no_supabase(PASSWORD)
    with caplog.at_level(logging.INFO, logger="imask"):
        for path, body in _four_paths(PASSWORD):
            response = context.client.post(path, json=body)
            assert response.status_code == 500
            assert response.json() == {"detail": "서버 설정이 빠졌습니다: SUPABASE_URL, SUPABASE_SECRET_KEY"}
            assert response.headers["cache-control"] == "no-store"
            for value in (PASSWORD, FAKE_ENV["UPSTAGE_API_KEY"], FAKE_AGENT_ID, AGENT):
                assert value not in response.text and value not in caplog.text
    # 비밀번호를 지난 뒤에야 저장소를 만들려 했고, 설정이 없어 거기서 멈췄다
    assert len(built) == 4
    context.no_upstage()
    assert context.store.preset_calls == [] and context.store.calls == []


def test_store_is_made_once_per_request_after_the_password(ctx: Ctx) -> None:
    # 바꿔 끼운 저장소를 그대로 쓰고, 비밀번호가 틀리면 그 공급자도 부르지 않는다
    made: list[int] = []

    def provider() -> object:
        made.append(1)
        return ctx.store

    app.dependency_overrides[get_store] = provider  # ctx 정리가 지운다
    for path, body in _four_paths("wrong"):
        assert ctx.client.post(path, json=body).status_code == 401
    assert made == []
    for path, body in _four_paths(PASSWORD):
        assert ctx.client.post(path, json=body).status_code == 200
    assert len(made) == 4


# --- 설정 경로: Cache-Control: no-store -----------------------------------------------------------


def _assert_no_store(response: httpx.Response, status: int) -> None:
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"


def test_settings_200s_are_no_store(ctx: Ctx) -> None:
    for path, body in _four_paths(PASSWORD):
        _assert_no_store(ctx.client.post(path, json=body), 200)


@pytest.mark.parametrize("bad", [b"", b"{", b"[]", b'{"password": 1}'])
def test_settings_body_errors_are_no_store(ctx: Ctx, bad: bytes) -> None:
    for path, _ in _four_paths(PASSWORD):
        response = ctx.client.post(path, content=bad, headers={"content-type": "application/json"})
        _assert_no_store(response, 400)
        assert response.json() == {"detail": MSG_FORMAT}


def test_settings_logic_400s_are_no_store(ctx: Ctx) -> None:
    _assert_no_store(_save(ctx, agent_id="틀림"), 400)
    _assert_no_store(_save(ctx, config_id="999"), 400)
    _assert_no_store(_add(ctx, name=""), 400)
    _assert_no_store(_add(ctx, agent_id="틀림"), 400)
    _assert_no_store(_delete(ctx, "uuid 아님"), 400)


def test_settings_401s_are_no_store(ctx: Ctx) -> None:
    for path, body in _four_paths("wrong"):
        _assert_no_store(ctx.client.post(path, json=body), 401)


def test_settings_409_is_no_store(ctx: Ctx) -> None:
    assert _add(ctx).status_code == 200
    _assert_no_store(_add(ctx), 409)


@pytest.mark.parametrize(
    ("path_index", "method"),
    [(0, "list_workflow_presets"), (1, "save_workflow_settings"), (2, "list_workflow_presets"), (3, "delete_workflow_preset")],
)
def test_settings_store_502s_are_no_store(ctx: Ctx, path_index: int, method: str) -> None:
    ctx.store.fail.add(method)
    path, body = _four_paths(PASSWORD)[path_index]
    response = ctx.client.post(path, json=body)
    _assert_no_store(response, 502)
    assert response.json() == {"detail": MSG_STORE}


def test_settings_upstage_502s_are_no_store(ctx: Ctx) -> None:
    ctx.server.errors[("GET", "agent")] = (500, {"error": {"message": "boom"}})
    _assert_no_store(_save(ctx), 502)
    _assert_no_store(_add(ctx), 502)


def test_settings_503s_are_no_store(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch)  # FAKE_ENV 에는 SETTINGS_PASSWORD 가 없다
    try:
        with TestClient(app) as client:
            for path, body in _four_paths(PASSWORD):
                _assert_no_store(client.post(path, json=body), 503)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("path_index", "method"),
    [(0, "list_workflow_presets"), (1, "save_workflow_settings"), (2, "list_workflow_presets"), (3, "delete_workflow_preset")],
)
def test_settings_unexpected_500s_are_no_store(ctx: Ctx, monkeypatch: pytest.MonkeyPatch, path_index: int, method: str) -> None:
    def broken(*_: object, **__: object) -> None:
        raise RuntimeError("뜻밖의 오류")

    monkeypatch.setattr(ctx.store, method, broken)
    path, body = _four_paths(PASSWORD)[path_index]
    response = ctx.client.post(path, json=body)
    _assert_no_store(response, 500)
    assert response.json() == {"detail": "서버 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."}


def test_settings_unknown_paths_and_methods_are_no_store(ctx: Ctx) -> None:
    _assert_no_store(ctx.client.get(SAVE), 405)
    _assert_no_store(ctx.client.get("/api/py/settings/없는-경로"), 404)


def test_settings_surrogate_response_is_no_store(ctx: Ctx) -> None:
    ctx.store.put_preset("이름\ud800", AGENT, CONFIG)  # _json_out 이 Response 로 돌려주는 길
    _assert_no_store(ctx.client.post(OPEN, json={"password": PASSWORD}), 200)


def test_other_paths_do_not_get_no_store(ctx: Ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    for response in (
        ctx.client.get("/api/py/health"),
        ctx.list(),
        ctx.get(str(uuid.uuid4())),  # 404
        ctx.create(filename="문서.exe"),  # 400
        ctx.client.get("/api/py/settingsx/workflow"),  # 앞 글자만 같은 경로
        ctx.client.post("/api/py/settings", json={}),  # 설정 경로 '아래'가 아니다
    ):
        assert "cache-control" not in response.headers, response.url.path

    def broken(*_: object, **__: object) -> None:
        raise RuntimeError("뜻밖의 오류")

    monkeypatch.setattr(ctx.store, "list_analyses", broken)
    response = ctx.list()
    assert response.status_code == 500 and "cache-control" not in response.headers


def test_original_file_keeps_its_no_store(ctx: Ctx) -> None:
    analysis_id = ctx.store.put(status="queued")
    response = ctx.client.get(f"/api/py/analyses/{analysis_id}/file")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"


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


def test_store_lists_presets_in_registered_order() -> None:
    rows = [{"id": "a", "name": "하나", "agent_id": AGENT, "config_id": CONFIG, "created_at": "t"}]
    store, log = _store(rows)
    assert store.list_workflow_presets(50) == rows
    assert log == [
        ("table", "workflow_presets"),
        ("select", ((PRESET_COLUMNS,), {})),
        ("order", (("created_at",), {})),
        ("order", (("id",), {})),
        ("limit", ((50,), {})),
    ]


@pytest.mark.parametrize("data", [None, {"id": "a"}, "목록"])
def test_store_list_refuses_a_non_list(data: object) -> None:
    with pytest.raises(StoreError):
        _store(data)[0].list_workflow_presets(50)


def test_store_inserts_preset_with_on_conflict_do_nothing() -> None:
    row = {"id": "a", "name": "하나", "agent_id": AGENT, "config_id": CONFIG, "created_at": "t"}
    store, log = _store([row])
    assert store.insert_workflow_preset("하나", AGENT, CONFIG) == row
    assert log == [
        ("table", "workflow_presets"),
        (
            "upsert",
            (({"name": "하나", "agent_id": AGENT, "config_id": CONFIG},), {"on_conflict": "name", "ignore_duplicates": True}),
        ),
    ]


def test_store_insert_conflict_is_none() -> None:
    assert _store([])[0].insert_workflow_preset("하나", AGENT, CONFIG) is None


def test_store_deletes_preset_by_id() -> None:
    preset_id = str(uuid.uuid4())
    store, log = _store([])
    assert store.delete_workflow_preset(preset_id) is None
    assert log == [("table", "workflow_presets"), ("delete", ((), {})), ("eq", (("id", preset_id), {}))]


def test_store_preset_errors_have_no_values(caplog: pytest.LogCaptureFixture) -> None:
    preset_id = str(uuid.uuid4())
    error = RuntimeError(f"failed for {AGENT} {preset_id} 이름값")
    calls = (
        lambda s: s.list_workflow_presets(50),
        lambda s: s.insert_workflow_preset("이름값", AGENT, CONFIG),
        lambda s: s.delete_workflow_preset(preset_id),
    )
    with caplog.at_level(logging.WARNING, logger="imask.store"):
        for call in calls:
            with pytest.raises(StoreError) as caught:
                call(_store([], error)[0])
            assert "RuntimeError" in caught.value.message
            for value in (AGENT, preset_id, "이름값"):
                assert value not in caught.value.message and value not in caplog.text
            assert caught.value.__cause__ is None and caught.value.__suppress_context__
