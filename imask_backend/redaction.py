# ==========================================================================
#  비밀값 가림 — imask_backend 공용 경계(BRIEF §2)
#  Upstage 오류 메시지와 작업 실패 이유는 다음 단계에서 analyses.error 에 저장되어 화면에
#  그대로 보인다. 그래서 문자열을 밖으로 내보내기 전에 여기 한 곳에서 가린다.
#  - 알려진 값(API 키, 에이전트 id 등)을 자리표시자로: <UPSTAGE_API_KEY>, <UPSTAGE_AGENT_ID>
#  - 'Authorization: Bearer <토큰>', 'Bearer <토큰>' 꼴 문구는 통째로 <REDACTED_AUTH>
#    (자리표시자에 authorization·bearer 낱말을 남기지 않는다)
#  - 길이 제한은 가림이 끝난 **뒤에** 자른다(잘린 비밀값 조각이 남지 않게)
#  - 4자보다 짧은 값은 가리지 않는다(config_id '3' 같은 짧은 식별자로 'HTTP 403' 이 깨지지 않게).
#  - redact_value(값): dict·list 를 재귀로 가린다. JSON 객체·배열이 든 문자열은 풀어서 구조를
#    유지한 채 가리고 같은 구분자로 다시 직렬화한다(JSON 문법을 깨지 않게). 가릴 것이 없으면 원문 그대로.
# ==========================================================================

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

API_KEY_PLACEHOLDER = "<UPSTAGE_API_KEY>"
AGENT_ID_PLACEHOLDER = "<UPSTAGE_AGENT_ID>"
AUTH_PLACEHOLDER = "<REDACTED_AUTH>"

# 이보다 짧은 값은 가리지 않는다(일반 글자·숫자와 겹쳐 메시지가 망가지므로)
MIN_SECRET_LENGTH = 4

# 'Authorization: Bearer x', "'authorization': 'Bearer x'", 'Authorization=x', 'Authorization Bearer x'
_AUTH_HEADER = re.compile(
    r"""\bauthorization\b['"]?\s*(?:[:=]\s*['"]?\s*(?:(?:bearer|basic|token)\s+)?|(?:bearer|basic|token)\s+)[^\s,;"'<>]+""",
    re.IGNORECASE,
)
# 홀로 쓰인 'Bearer <토큰>'(RFC 6750 b64token 글자, 8자 이상 — 'bearer bonds' 같은 낱말은 두기 위해)
_BEARER_TOKEN = re.compile(r"\bbearer\s+[A-Za-z0-9\-._~+/]{8,}=*", re.IGNORECASE)

Secrets = Mapping[str, str]


def upstage_secrets(api_key: str | None, agent_id: str | None = None) -> dict[str, str]:
    """가릴 값 → 자리표시자 사전. 빈 값은 넣지 않는다."""
    secrets: dict[str, str] = {}
    if isinstance(api_key, str) and api_key:
        secrets[api_key] = API_KEY_PLACEHOLDER
    if isinstance(agent_id, str) and agent_id:
        secrets[agent_id] = AGENT_ID_PLACEHOLDER
    return secrets


def redact(text: Any, secrets: Secrets | None = None, *, limit: int | None = None) -> str:
    """text 를 문자열로 바꾸고 인증 문구·알려진 값을 가린 뒤, limit 이 있으면 자른다."""
    value = text if isinstance(text, str) else str(text)
    value = _AUTH_HEADER.sub(AUTH_PLACEHOLDER, value)
    value = _BEARER_TOKEN.sub(AUTH_PLACEHOLDER, value)
    if secrets:
        # 긴 값부터(한 값이 다른 값을 품는 경우)
        for secret in sorted(secrets, key=len, reverse=True):
            if isinstance(secret, str) and len(secret) >= MIN_SECRET_LENGTH and secret in value:
                value = value.replace(secret, secrets[secret])
    if limit is not None and limit > 0 and len(value) > limit:
        value = value[: limit - 1] + "…"
    return value


def redact_value(value: Any, secrets: Secrets | None = None) -> Any:
    """dict·list 안의 모든 문자열(키 포함)을 가린다. 다른 타입은 그대로.

    - 키가 Authorization(Proxy-Authorization)인 문자열 값은 통째로 <REDACTED_AUTH>. 키는 그대로 둔다.
    - JSON 객체·배열로 풀리는 문자열(Upstage content[].text·additional_values 등)은 정규식으로
      문자열째 치환하지 않고, 풀어서 구조를 유지한 채 재귀로 가린 뒤 다시 직렬화한다 — 정규식이
      JSON 의 따옴표·콜론을 먹어 문법이 깨지지 않게(R2-m1). 가릴 것이 없으면 원문 문자열 그대로.
    """
    if isinstance(value, str):
        as_json = _redact_json_text(value, secrets)
        return as_json if as_json is not None else redact(value, secrets)
    if isinstance(value, Mapping):
        out: dict[Any, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and _AUTH_KEY.match(key) and isinstance(item, str) and item:
                out[key] = AUTH_PLACEHOLDER
            else:
                out[redact_value(key, secrets)] = redact_value(item, secrets)
        return out
    if isinstance(value, list):
        return [redact_value(v, secrets) for v in value]
    return value


# 값을 통째로 가릴 키 이름(대소문자 무시)
_AUTH_KEY = re.compile(r"^\s*(?:proxy-)?authorization\s*$", re.IGNORECASE)

# 원문 JSON 의 모양을 맞춰 보는 후보(구분자·들여쓰기). 맞는 것이 없으면 첫 후보.
_JSON_LAYOUTS: tuple[dict[str, Any], ...] = (
    {"separators": (", ", ": ")},
    {"separators": (",", ":")},
    {"indent": 2},
)


def _redact_json_text(text: str, secrets: Secrets | None) -> str | None:
    """JSON 객체·배열 문자열이면 구조를 유지해 가린 문자열, 아니면 None(일반 문자열로 처리)."""
    stripped = text.strip()
    if not stripped or stripped[0] not in "{[":
        return None
    try:
        parsed = json.loads(text)
    except (ValueError, RecursionError):
        return None
    if not isinstance(parsed, (dict, list)):
        return None
    masked = redact_value(parsed, secrets)
    if masked == parsed:
        return text  # 바뀐 것이 없으면 원문(구분자·이스케이프)을 그대로 둔다
    layout = _JSON_LAYOUTS[0]
    for candidate in _JSON_LAYOUTS:
        if any(json.dumps(parsed, ensure_ascii=ascii_, **candidate) == text for ascii_ in (False, True)):
            layout = candidate
            break
    return json.dumps(masked, ensure_ascii=False, **layout)
