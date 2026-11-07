# ==========================================================================
#  웹 설정 화면(/settings) — 분석에 쓸 Upstage 에이전트 id·설정 번호를 재배포 없이 바꾼다
#  - 값은 workflow_settings 테이블(한 행)에 둔다. 행이 있으면 환경 변수(UPSTAGE_AGENT_ID·UPSTAGE_CONFIG_ID)보다 먼저 쓰고,
#    없으면 환경 변수를 쓴다(analyses.run_workflow). API 키·프로젝트 id 는 환경 변수 그대로다.
#  - 비밀번호: 환경 변수 SETTINGS_PASSWORD 와 같아야 읽고 저장할 수 있다. 환경 변수가 없으면 아무도 열 수 없다.
#    값은 코드·저장소·응답·로그에 넣지 않는다.
#  - 저장 전에 꼴(agt_…·숫자)을 보고 Upstage 에 그 에이전트와 설정이 있는지 확인한다 — 워크플로우 이름 같은 잘못된 값이
#    들어가면 모든 분석이 실패하기 때문이다. 확인하지 못하면(연결 오류·5xx) 저장하지 않는다.
#  - 응답은 {agent_id, config_id, agent_name, config_name}. 로그에 값을 남기지 않는다.
#  - 워크플로우 목록(workflow_presets): 이름을 붙여 등록해 두는 값이고, 적용은 그 값을 저장 경로(save_workflow)로 workflow_settings 에
#    복사하는 것이다. 그래서 등록·삭제는 지금 적용 값을 바꾸지 않고, 분석을 시작하는 쪽은 이 목록을 읽지 않는다. 항목 고치기는 없다.
#    등록 순서: 이름 → 꼴 → 목록을 읽어 한도(MAX_PRESETS)·같은 이름 → Upstage 에 있는지 → 저장(그 사이 같은 이름이 들어왔으면 409) → 다시 읽기.
#    삭제: id 꼴만 보고 지운다(없는 id 도 성공 — 다른 사람이 먼저 지웠을 수 있다). Upstage 를 부르지 않는다.
#    화면을 열 때 목록을 함께 준다(presets). 항목마다 Upstage 를 부르지 않는다. 모양이 틀린 행은 건너뛴다.
#  FastAPI 와 무관한 업무 로직이다(경로는 api/index.py).
# ==========================================================================

from __future__ import annotations

import hmac
import logging
import re
import unicodedata
from collections.abc import Mapping
from typing import Any

from .analyses import ApiError, UpstageFactory, run_workflow
from .settings import Settings
from .store import Store
from .upstage import UpstageError

logger = logging.getLogger("imask.workflow_settings")

# 에이전트 id·설정 번호의 꼴 — 실제 값 agt_ + 영문·숫자, 설정 번호는 숫자 문자열(external_id)
_AGENT_ID = re.compile(r"agt_[A-Za-z0-9_-]{1,128}")
_CONFIG_ID = re.compile(r"[0-9]{1,9}")
# 목록 항목 id — uuid.UUID 는 중괄호·하이픈 없는 꼴도 받으므로 꼴을 직접 본다
_PRESET_ID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")

MAX_PRESETS = 50  # 목록 한도
MAX_PRESET_NAME = 60  # 이름 길이(코드 포인트)
_BAD_NAME_CATEGORIES = frozenset({"Cc", "Cs"})  # 제어 문자·서로게이트

MSG_NO_PASSWORD = "서버에 설정 비밀번호가 없어 열 수 없습니다."
MSG_WRONG_PASSWORD = "비밀번호가 맞지 않습니다."
MSG_BAD_AGENT = "에이전트 ID 는 agt_ 로 시작해야 합니다."
MSG_BAD_CONFIG = "설정 번호는 숫자로 넣어 주세요."
MSG_NOT_ON_UPSTAGE = "Upstage 에 없는 에이전트 또는 설정 번호입니다."
MSG_CHECK_FAILED = "Upstage 에서 확인하지 못했습니다. 잠시 후 다시 시도해 주세요."
MSG_BAD_PRESET_NAME = "이름은 1~60자로 넣어 주세요."
MSG_TOO_MANY_PRESETS = "워크플로우는 50개까지 등록할 수 있습니다."
MSG_PRESET_NAME_TAKEN = "같은 이름의 워크플로우가 이미 있습니다."
MSG_BAD_PRESET_ID = "요청 형식이 올바르지 않습니다."


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


def _clean_workflow(agent_id: str, config_id: str) -> tuple[str, str]:
    """공백을 지우고 꼴을 본다. 틀리면 400(Upstage 를 부르기 전에 끊는다)."""
    agent_id, config_id = agent_id.strip(), config_id.strip()
    if not _AGENT_ID.fullmatch(agent_id):
        raise ApiError(400, MSG_BAD_AGENT)
    if not _CONFIG_ID.fullmatch(config_id):
        raise ApiError(400, MSG_BAD_CONFIG)
    return agent_id, config_id


def _confirm_on_upstage(upstage: UpstageFactory, settings: Settings, agent_id: str, config_id: str) -> dict[str, Any]:
    """Upstage 에 그 에이전트와 설정이 있는지 → 이름. 없으면 400, 확인하지 못하면 502."""
    settings.upstage()  # 환경 변수가 빠졌으면 ConfigError → 500(API 키가 없으면 어차피 분석을 돌릴 수 없다)
    try:
        return upstage().get_workflow(agent_id, config_id)
    except UpstageError as exc:
        if exc.status_code == 404:
            raise ApiError(400, MSG_NOT_ON_UPSTAGE) from None
        logger.warning("워크플로우를 확인하지 못함: HTTP %s", exc.status_code)
        raise ApiError(502, MSG_CHECK_FAILED) from None


def save_workflow(
    store: Store, upstage: UpstageFactory, settings: Settings, agent_id: str, config_id: str
) -> dict[str, Any]:
    """꼴 → Upstage 에 있는지 → 저장. 모르는 값이면 400, Upstage 를 확인하지 못하면 502(어느 쪽이든 저장하지 않는다)."""
    agent_id, config_id = _clean_workflow(agent_id, config_id)
    names = _confirm_on_upstage(upstage, settings, agent_id, config_id)
    store.save_workflow_settings(agent_id, config_id)  # StoreError → api 가 502
    logger.info("워크플로우 설정을 저장함")
    return _out(agent_id, config_id, names)


# --- 워크플로우 목록 ---------------------------------------------------------------------------


def _preset_out(row: Any) -> dict[str, str] | None:
    """화면에 줄 네 칸. 문자열이 아닌 칸이 있으면 None(그 행은 건너뛴다)."""
    if not isinstance(row, Mapping):
        return None
    out: dict[str, str] = {}
    for key in ("id", "name", "agent_id", "config_id"):
        value = row.get(key)
        if not isinstance(value, str):
            return None
        out[key] = value
    return out


def _presets_out(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [out for out in map(_preset_out, rows) if out is not None]


def list_presets(store: Store) -> list[dict[str, str]]:
    """등록해 둔 목록(등록한 순). 읽지 못하면 StoreError → api 가 502."""
    return _presets_out(store.list_workflow_presets(MAX_PRESETS))


def open_workflow(store: Store, upstage: UpstageFactory, settings: Settings) -> dict[str, Any]:
    """화면을 열 때 — 지금 적용 값 + 목록. 목록을 먼저 읽어 저장소가 안 되면 Upstage 를 부르지 않는다."""
    presets = list_presets(store)
    return {**read_workflow(store, upstage, settings), "presets": presets}


def _clean_preset_name(name: str) -> str:
    name = name.strip()
    # 길이를 먼저 본다 — 아주 긴 이름의 글자를 하나씩 살피지 않게
    if not name or len(name) > MAX_PRESET_NAME or any(unicodedata.category(ch) in _BAD_NAME_CATEGORIES for ch in name):
        raise ApiError(400, MSG_BAD_PRESET_NAME)
    return name


def add_preset(
    store: Store, upstage: UpstageFactory, settings: Settings, name: str, agent_id: str, config_id: str
) -> dict[str, Any]:
    """목록에 등록한다(지금 적용 값은 바꾸지 않는다). 순서는 머리 주석."""
    name = _clean_preset_name(name)
    agent_id, config_id = _clean_workflow(agent_id, config_id)
    rows = store.list_workflow_presets(MAX_PRESETS)
    if len(rows) >= MAX_PRESETS:
        raise ApiError(400, MSG_TOO_MANY_PRESETS)
    if any(isinstance(row, Mapping) and row.get("name") == name for row in rows):
        raise ApiError(409, MSG_PRESET_NAME_TAKEN)
    _confirm_on_upstage(upstage, settings, agent_id, config_id)
    if store.insert_workflow_preset(name, agent_id, config_id) is None:  # 그 사이 다른 요청이 같은 이름을 넣음
        raise ApiError(409, MSG_PRESET_NAME_TAKEN)
    logger.info("워크플로우 목록에 등록함")
    return {"presets": list_presets(store)}


def delete_preset(store: Store, preset_id: str) -> dict[str, Any]:
    """목록에서 지운다(지금 적용 값은 그대로). 없는 id 도 성공 — 200 + 지금 목록."""
    if not _PRESET_ID.fullmatch(preset_id):
        raise ApiError(400, MSG_BAD_PRESET_ID)
    store.delete_workflow_preset(preset_id)
    logger.info("워크플로우 목록에서 지움")
    return {"presets": list_presets(store)}
