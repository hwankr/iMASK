# ==========================================================================
#  웹 설정 화면(/settings) — 분석에 쓸 Upstage 에이전트 id·설정 번호를 재배포 없이 바꾼다
#  - 값은 workflow_settings 테이블(한 행)에 둔다. 행이 있으면 환경 변수(UPSTAGE_AGENT_ID·UPSTAGE_CONFIG_ID)보다 먼저 쓰고,
#    없으면 환경 변수를 쓴다(analyses.run_workflow). API 키·프로젝트 id 는 환경 변수 그대로다.
#  - 비밀번호: 환경 변수 SETTINGS_PASSWORD 와 같아야 읽고 저장할 수 있다. 환경 변수가 없으면 아무도 열 수 없다.
#    값은 코드·저장소·응답·로그에 넣지 않는다.
#  - 저장 전에 꼴(agt_…·숫자)을 보고 Upstage 에 그 에이전트와 설정이 있는지 확인한다 — 워크플로우 이름 같은 잘못된 값이
#    들어가면 모든 분석이 실패하기 때문이다. 확인하지 못하면(연결 오류·5xx) 저장하지 않는다.
#  - 응답은 {agent_id, config_id, agent_name, config_name}. 로그에 값을 남기지 않는다.
#  FastAPI 와 무관한 업무 로직이다(경로는 api/index.py).
# ==========================================================================

from __future__ import annotations

import hmac
import logging
import re
from typing import Any

from .analyses import ApiError, UpstageFactory, run_workflow
from .settings import Settings
from .store import Store
from .upstage import UpstageError

logger = logging.getLogger("imask.workflow_settings")

# 에이전트 id·설정 번호의 꼴 — 실제 값 agt_ + 영문·숫자, 설정 번호는 숫자 문자열(external_id)
_AGENT_ID = re.compile(r"agt_[A-Za-z0-9_-]{1,128}")
_CONFIG_ID = re.compile(r"[0-9]{1,9}")

MSG_NO_PASSWORD = "서버에 설정 비밀번호가 없어 열 수 없습니다."
MSG_WRONG_PASSWORD = "비밀번호가 맞지 않습니다."
MSG_BAD_AGENT = "에이전트 ID 는 agt_ 로 시작해야 합니다."
MSG_BAD_CONFIG = "설정 번호는 숫자로 넣어 주세요."
MSG_NOT_ON_UPSTAGE = "Upstage 에 없는 에이전트 또는 설정 번호입니다."
MSG_CHECK_FAILED = "Upstage 에서 확인하지 못했습니다. 잠시 후 다시 시도해 주세요."


def check_password(settings: Settings, given: str) -> None:
    """비밀번호가 맞지 않으면 ApiError. 서버에 비밀번호가 없으면 503(아무도 열 수 없다)."""
    expected = settings.settings_password()
    if not expected:
        raise ApiError(503, MSG_NO_PASSWORD)
    # surrogatepass: 본문의 짝 없는 서로게이트도 예외 없이 '틀림'으로
    if not hmac.compare_digest(given.encode("utf-8", "surrogatepass"), expected.encode("utf-8")):
        raise ApiError(401, MSG_WRONG_PASSWORD)


def _out(agent_id: str, config_id: str, names: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent_id": agent_id,
        "config_id": config_id,
        "agent_name": names.get("agent_name"),
        "config_name": names.get("config_name"),
    }


def read_workflow(store: Store, upstage: UpstageFactory, settings: Settings) -> dict[str, Any]:
    """지금 적용 중인 값(저장한 값, 없으면 환경 변수). 이름은 Upstage 에서 읽고, 못 읽으면 None(화면은 열린다)."""
    agent_id, config_id = run_workflow(store, settings.upstage())
    names: dict[str, Any] = {}
    try:
        names = upstage().get_workflow(agent_id, config_id)
    except UpstageError as exc:
        logger.warning("워크플로우 이름을 읽지 못함: HTTP %s", exc.status_code)
    return _out(agent_id, config_id, names)


def save_workflow(
    store: Store, upstage: UpstageFactory, settings: Settings, agent_id: str, config_id: str
) -> dict[str, Any]:
    """꼴 → Upstage 에 있는지 → 저장. 모르는 값이면 400, Upstage 를 확인하지 못하면 502(어느 쪽이든 저장하지 않는다)."""
    agent_id, config_id = agent_id.strip(), config_id.strip()
    if not _AGENT_ID.fullmatch(agent_id):
        raise ApiError(400, MSG_BAD_AGENT)
    if not _CONFIG_ID.fullmatch(config_id):
        raise ApiError(400, MSG_BAD_CONFIG)
    settings.upstage()  # 환경 변수가 빠졌으면 ConfigError → 500(API 키가 없으면 어차피 분석을 돌릴 수 없다)
    try:
        names = upstage().get_workflow(agent_id, config_id)
    except UpstageError as exc:
        if exc.status_code == 404:
            raise ApiError(400, MSG_NOT_ON_UPSTAGE) from None
        logger.warning("워크플로우를 확인하지 못함: HTTP %s", exc.status_code)
        raise ApiError(502, MSG_CHECK_FAILED) from None
    store.save_workflow_settings(agent_id, config_id)  # StoreError → api 가 502
    logger.info("워크플로우 설정을 저장함")
    return _out(agent_id, config_id, names)
