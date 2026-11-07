# ==========================================================================
#  서버 전체 환경 설정 (FastAPI 백엔드)
#  - load_settings(env): Mapping(os.environ 등)에서 필요한 이름만 읽어 Settings 로. 값이 빠져도
#    예외를 던지지 않는다 — 앱 import·health 는 늘 돌고, 값이 필요한 순간에만 ConfigError(이름만).
#  - get_settings(): os.environ 을 처음 한 번 읽어 캐시(FastAPI 의존성으로 쓴다. 테스트는 바꿔 끼운다).
#    로컬은 `uvicorn --env-file .env`, Vercel 은 프로젝트 환경변수로 들어온다(코드는 .env 를 읽지 않는다).
#  - 진짜 비밀값(BRIEF §2): SUPABASE_SECRET_KEY · UPSTAGE_API_KEY. (접근 코드 DEMO_ACCESS_CODE 는 2026-11-03 없앰)
#    repr 에 나오지 않고, secrets() 로 가림 사전(값 → 자리표시자)을 만든다. 에이전트 id 도 가린다.
#  - SETTINGS_PASSWORD: 웹 설정 화면(/settings)의 비밀번호. 없으면 그 화면을 열 수 없다. secrets() 에는 넣지 않는다 —
#    짧은 값이라 넣으면 분석 결과 속 같은 숫자까지 가려진다. 응답·로그에 내보내는 곳은 없다.
# ==========================================================================

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from types import MappingProxyType

from .config import (
    PROJECT_ID_ENV,
    REQUIRED_UPSTAGE_ENV,
    ConfigError,
    UpstageSettings,
    load_upstage_settings,
)
from .redaction import AGENT_ID_PLACEHOLDER, API_KEY_PLACEHOLDER

REQUIRED_SUPABASE_ENV = ("SUPABASE_URL", "SUPABASE_SECRET_KEY")
# 선택 — 프로젝트 id 는 에이전트가 Upstage 프로젝트에 속하면 필요하다(config.PROJECT_ID_ENV). 여기 없으면 서버가 읽지 못한다
SETTINGS_PASSWORD_ENV = "SETTINGS_PASSWORD"
OPTIONAL_ENV = ("UPSTAGE_BASE_URL", PROJECT_ID_ENV, SETTINGS_PASSWORD_ENV)
KNOWN_ENV = REQUIRED_SUPABASE_ENV + REQUIRED_UPSTAGE_ENV + OPTIONAL_ENV

SUPABASE_KEY_PLACEHOLDER = "<SUPABASE_SECRET_KEY>"

# 원본 파일을 두는 비공개 버킷(supabase/migrations/…_init_analyses_documents.sql)
STORAGE_BUCKET = "documents"


def _clean(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


@dataclass(frozen=True)
class SupabaseSettings:
    url: str
    secret_key: str = field(repr=False)


@dataclass(frozen=True)
class Settings:
    """필요한 환경변수만 담은 읽기 전용 설정. repr 에 값이 나오지 않는다."""

    values: Mapping[str, str] = field(repr=False)

    def _get(self, name: str) -> str:
        return _clean(self.values.get(name))

    def _missing(self, names: tuple[str, ...]) -> list[str]:
        return [name for name in names if not self._get(name)]

    # --- 있는지만 -----------------------------------------------------------

    def configured(self) -> dict[str, bool]:
        """health 용: 값은 넣지 않고 있는지만."""
        return {
            "supabase": not self._missing(REQUIRED_SUPABASE_ENV),
            "upstage": not self._missing(REQUIRED_UPSTAGE_ENV),
            "upstage_project": bool(self._get(PROJECT_ID_ENV)),
        }

    # --- 값이 필요한 곳 -------------------------------------------------------

    def supabase(self) -> SupabaseSettings:
        missing = self._missing(REQUIRED_SUPABASE_ENV)
        if missing:
            raise ConfigError(missing)
        return SupabaseSettings(url=self._get("SUPABASE_URL").rstrip("/"), secret_key=self._get("SUPABASE_SECRET_KEY"))

    def upstage(self) -> UpstageSettings:
        """T1 의 load_upstage_settings 그대로(빠진 이름이 있으면 ConfigError)."""
        return load_upstage_settings(self.values)

    def settings_password(self) -> str:
        """웹 설정 화면의 비밀번호. 없으면 빈 문자열."""
        return self._get(SETTINGS_PASSWORD_ENV)

    def secrets(self) -> dict[str, str]:
        """가림 사전(값 → 자리표시자). 빈 값은 넣지 않는다."""
        pairs = (
            ("UPSTAGE_API_KEY", API_KEY_PLACEHOLDER),
            ("UPSTAGE_AGENT_ID", AGENT_ID_PLACEHOLDER),
            ("SUPABASE_SECRET_KEY", SUPABASE_KEY_PLACEHOLDER),
        )
        return {value: placeholder for name, placeholder in pairs if (value := self._get(name))}


def load_settings(env: Mapping[str, str]) -> Settings:
    """env 에서 알려진 이름만 복사한다(예외 없음)."""
    values = {name: env[name] for name in KNOWN_ENV if isinstance(env.get(name), str)}
    return Settings(values=MappingProxyType(values))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """os.environ 을 처음 한 번 읽어 캐시한다(FastAPI 의존성)."""
    return load_settings(os.environ)
