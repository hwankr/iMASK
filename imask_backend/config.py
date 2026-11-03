# ==========================================================================
#  환경변수 읽기 — Upstage 설정
#  - load_upstage_settings(env) 는 넘겨받은 Mapping(os.environ, .env 를 읽은 dict 등)에서
#    UPSTAGE_API_KEY · UPSTAGE_AGENT_ID · UPSTAGE_CONFIG_ID 를 읽는다.
#  - 빠졌거나 빈 이름이 있으면 ConfigError 를 던진다. 오류에는 **이름만** 담고 값은 넣지 않는다.
#  - UPSTAGE_CONFIG_ID 가 없으면 반드시 오류다. config_id 없이 작업을 만들면 Studio 의
#    최신 설정이 돌아 결과가 바뀌기 때문이다(BRIEF §4).
#  - UPSTAGE_BASE_URL 은 선택(없으면 https://api.upstage.ai/v2).
#  - UPSTAGE_PROJECT_ID 는 선택이지만, 에이전트가 Upstage Studio 프로젝트에 속하면 반드시 넣는다 —
#    클라이언트가 모든 요청(파일 올리기·작업 만들기·조회·지우기)에 x-project-id 헤더로 보낸다. 빠지면 올린 파일이
#    프로젝트 밖에 저장돼 작업 만들기가 403 'No access to file' 로 실패한다(2026-11-03 확인, Studio 코드 패널 안내).
#    헤더 값이므로 영문·숫자·_·- 만 받는다(그 밖은 ConfigError — 이름만). 비밀값은 아니다.
# ==========================================================================

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

DEFAULT_UPSTAGE_BASE_URL = "https://api.upstage.ai/v2"

# 반드시 있어야 하는 이름(순서대로 검사·보고한다)
REQUIRED_UPSTAGE_ENV = ("UPSTAGE_API_KEY", "UPSTAGE_AGENT_ID", "UPSTAGE_CONFIG_ID")

# 프로젝트 id(선택) — x-project-id 헤더로 보낸다. 헤더에 넣을 수 있는 글자만(proj_… 꼴)
PROJECT_ID_ENV = "UPSTAGE_PROJECT_ID"
_PROJECT_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,128}")


class ConfigError(Exception):
    """필요한 환경변수가 없거나 비었을 때(또는 형식이 맞지 않을 때). 메시지·속성에는 이름만 담는다."""

    def __init__(self, missing: Iterable[str], reason: str = "환경변수가 비었거나 없습니다"):
        self.missing: tuple[str, ...] = tuple(missing)
        super().__init__(f"{reason}: " + ", ".join(self.missing))


@dataclass(frozen=True)
class UpstageSettings:
    """Upstage 호출 설정. repr 에 키·에이전트 id 가 나오지 않게 숨긴다."""

    api_key: str = field(repr=False)
    agent_id: str = field(repr=False)
    config_id: str = field(repr=False)
    base_url: str = DEFAULT_UPSTAGE_BASE_URL
    # 에이전트가 속한 Upstage 프로젝트(x-project-id 헤더). 없으면 헤더를 보내지 않는다
    project_id: str | None = None


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
    project_id = _clean(env.get(PROJECT_ID_ENV)) or None
    if project_id is not None and not _PROJECT_ID_RE.fullmatch(project_id):
        raise ConfigError([PROJECT_ID_ENV], "환경변수 형식이 맞지 않습니다")
    return UpstageSettings(
        api_key=values["UPSTAGE_API_KEY"],
        agent_id=values["UPSTAGE_AGENT_ID"],
        config_id=values["UPSTAGE_CONFIG_ID"],
        base_url=base_url.rstrip("/"),
        project_id=project_id,
    )
