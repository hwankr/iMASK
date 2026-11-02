# ==========================================================================
#  config.py 테스트 — 빠진 이름은 이름만 담아 오류, UPSTAGE_CONFIG_ID 빈 값은 오류.
# ==========================================================================

from __future__ import annotations

import pytest

from imask_backend.config import (
    DEFAULT_UPSTAGE_BASE_URL,
    ConfigError,
    UpstageSettings,
    load_upstage_settings,
)

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
