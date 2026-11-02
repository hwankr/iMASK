# ==========================================================================
#  환경변수 읽기 — Upstage 설정
#  - load_upstage_settings(env) 는 넘겨받은 Mapping(os.environ, .env 를 읽은 dict 등)에서
#    UPSTAGE_API_KEY · UPSTAGE_AGENT_ID · UPSTAGE_CONFIG_ID 를 읽는다.
#  - 빠졌거나 빈 이름이 있으면 ConfigError 를 던진다. 오류에는 **이름만** 담고 값은 넣지 않는다.
#  - UPSTAGE_CONFIG_ID 가 없으면 반드시 오류다. config_id 없이 작업을 만들면 Studio 의
#    최신 설정이 돌아 결과가 바뀌기 때문이다(BRIEF §4).
#  - UPSTAGE_BASE_URL 은 선택(없으면 https://api.upstage.ai/v2).
# ==========================================================================

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

DEFAULT_UPSTAGE_BASE_URL = "https://api.upstage.ai/v2"

# 반드시 있어야 하는 이름(순서대로 검사·보고한다)
REQUIRED_UPSTAGE_ENV = ("UPSTAGE_API_KEY", "UPSTAGE_AGENT_ID", "UPSTAGE_CONFIG_ID")


class ConfigError(Exception):
    """필요한 환경변수가 없거나 비었을 때. 메시지·속성에는 이름만 담는다."""

    def __init__(self, missing: Iterable[str]):
        self.missing: tuple[str, ...] = tuple(missing)
        super().__init__("환경변수가 비었거나 없습니다: " + ", ".join(self.missing))


@dataclass(frozen=True)
class UpstageSettings:
    """Upstage 호출 설정. repr 에 키·에이전트 id 가 나오지 않게 숨긴다."""

    api_key: str = field(repr=False)
    agent_id: str = field(repr=False)
    config_id: str = field(repr=False)
    base_url: str = DEFAULT_UPSTAGE_BASE_URL


def _clean(value: object) -> str:
    """값을 문자열로 바꾸고 앞뒤 공백을 지운다. None·문자열이 아닌 값은 빈 문자열."""
    return value.strip() if isinstance(value, str) else ""


def load_upstage_settings(env: Mapping[str, str]) -> UpstageSettings:
    """env 에서 Upstage 설정을 읽는다. 빠진 이름이 있으면 ConfigError(이름만)."""
    values = {name: _clean(env.get(name)) for name in REQUIRED_UPSTAGE_ENV}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ConfigError(missing)
    base_url = _clean(env.get("UPSTAGE_BASE_URL")) or DEFAULT_UPSTAGE_BASE_URL
    return UpstageSettings(
        api_key=values["UPSTAGE_API_KEY"],
        agent_id=values["UPSTAGE_AGENT_ID"],
        config_id=values["UPSTAGE_CONFIG_ID"],
        base_url=base_url.rstrip("/"),
    )
