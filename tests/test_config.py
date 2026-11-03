# ==========================================================================
#  config.py 테스트 — 빠진 이름은 이름만 담아 오류, UPSTAGE_CONFIG_ID 빈 값은 오류.
# ==========================================================================

from __future__ import annotations

import pytest

from imask_backend.config import (
    DEFAULT_UPSTAGE_BASE_URL,
    PROJECT_ID_ENV,
    ConfigError,
    UpstageSettings,
    load_upstage_settings,
)
from imask_backend.settings import load_settings

FULL = {
    "UPSTAGE_API_KEY": "fake-key-value-111",
    "UPSTAGE_AGENT_ID": "fake-agent-value-222",
    "UPSTAGE_CONFIG_ID": "3",
}


def test_loads_all_values():
    settings = load_upstage_settings(FULL)
    assert settings == UpstageSettings(
        api_key="fake-key-value-111",
        agent_id="fake-agent-value-222",
        config_id="3",
        base_url=DEFAULT_UPSTAGE_BASE_URL,
    )


def test_repr_hides_values():
    text = repr(load_upstage_settings(FULL))
    for value in FULL.values():
        if len(value) > 1:
            assert value not in text


@pytest.mark.parametrize("name", ["UPSTAGE_API_KEY", "UPSTAGE_AGENT_ID", "UPSTAGE_CONFIG_ID"])
def test_missing_name_reports_only_the_name(name):
    env = {k: v for k, v in FULL.items() if k != name}
    with pytest.raises(ConfigError) as info:
        load_upstage_settings(env)
    assert info.value.missing == (name,)
    assert name in str(info.value)
    for value in FULL.values():
        if len(value) > 1:
            assert value not in str(info.value)


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_config_id_is_error(blank):
    with pytest.raises(ConfigError) as info:
        load_upstage_settings({**FULL, "UPSTAGE_CONFIG_ID": blank})
    assert info.value.missing == ("UPSTAGE_CONFIG_ID",)


def test_all_missing_lists_every_name_in_order():
    with pytest.raises(ConfigError) as info:
        load_upstage_settings({})
    assert info.value.missing == ("UPSTAGE_API_KEY", "UPSTAGE_AGENT_ID", "UPSTAGE_CONFIG_ID")


def test_values_are_stripped_and_base_url_override():
    settings = load_upstage_settings(
        {**FULL, "UPSTAGE_CONFIG_ID": " 3 ", "UPSTAGE_BASE_URL": "https://example.test/v2/"}
    )
    assert settings.config_id == "3"
    assert settings.base_url == "https://example.test/v2"


# --- 프로젝트 id(선택, x-project-id 헤더) -------------------------------------------


def test_project_id_is_optional():
    assert load_upstage_settings(FULL).project_id is None


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_project_id_is_none(blank):
    assert load_upstage_settings({**FULL, PROJECT_ID_ENV: blank}).project_id is None


def test_project_id_is_stripped():
    settings = load_upstage_settings({**FULL, PROJECT_ID_ENV: "  proj_Test-123_x "})
    assert settings.project_id == "proj_Test-123_x"


@pytest.mark.parametrize("bad", ["proj test", "proj\r\nx-evil: 1", "프로젝트", "proj/1", "p" * 129])
def test_bad_project_id_reports_only_the_name(bad):
    # 헤더 값으로 보내므로 영문·숫자·_·- 만 받는다 — 오류에는 이름만(값 없음)
    with pytest.raises(ConfigError) as info:
        load_upstage_settings({**FULL, PROJECT_ID_ENV: bad})
    assert info.value.missing == (PROJECT_ID_ENV,)
    assert "형식" in str(info.value)
    assert bad.strip() not in str(info.value)


def test_server_settings_keep_project_id():
    # load_settings 는 알려진 이름만 복사한다 — 프로젝트 id 가 빠지면 서버가 헤더를 못 보낸다
    settings = load_settings({**FULL, PROJECT_ID_ENV: "proj_Test123"})
    assert settings.upstage().project_id == "proj_Test123"
    assert settings.configured()["upstage_project"] is True
    assert load_settings(FULL).configured()["upstage_project"] is False
