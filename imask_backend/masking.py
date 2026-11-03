# ==========================================================================
#  노출 상태 추정과 가림 미리보기 — **표시용 가공일 뿐 판별이 아니다**
#  추출된 값이 원문에서 이미 가려져 있었는지(exposure)와, 화면에 원문 대신 보여 줄 가린 꼴(masked)을
#  간단한 글자 규칙으로 만든다. 개인정보인지·위험한지는 정하지 않는다(위험등급은 워크플로우 값만 옮긴다).
#
#  exposure(value, kind): 가림 문자 수 m, 가림 문자가 아닌 글자·숫자(str.isalnum, 한글 포함) 수 a 로
#    m == 0 → 전체 노출, a == 0 → 마스킹됨, 그 밖 → 부분 마스킹. ';' 로 여러 값이어도 값 전체로 한 번 센다.
#    가림 문자: * ＊ ● ○ ■ □ ◆ ◇ ★ ☆. 숫자 종류(rrn·id_number·birth_date·phone·account·card)에서만
#    X x × 도 가림 문자로 센다(이메일 'example' 의 x 같은 것을 가림으로 보지 않게).
#  masked(value, kind): ';' 로 나눈 조각마다(구분자·앞뒤 공백은 그대로) 종류별 규칙을 쓴다.
#    불변식 — 길이가 원문과 같고, 각 글자는 원문 그대로이거나 '*' 로만 바뀐다(원문의 가림 문자는 그대로).
#    마지막 안전장치: 가림 문자가 없던 조각이 규칙 뒤에도 그대로면(글자·숫자가 있는데) 글자·숫자를 모두 '*'.
#    그래서 글자·숫자가 있는 '전체 노출' 값의 masked 는 원문과 반드시 다르다.
#  규칙 예: 홍길동→홍*동 · 800101-1234567→800101-1****** · 010-1234-5678→010-****-5678 ·
#    1980년 1월 1일→1980년 *월 *일 · 1234-5678-9012-3456→1234-****-****-3456 ·
#    가상특별시 모의구 예시대로 77, 9층→가상특별시 모의구 **** **, ** · 연봉: 12,340,000원→연봉: 1*,***,****
# ==========================================================================

from __future__ import annotations

import re
from collections.abc import Callable

STAR = "*"
MASK_CHARS = frozenset("*＊●○■□◆◇★☆")
X_CHARS = frozenset("Xx×")
NUMERIC_KINDS = frozenset({"rrn", "id_number", "birth_date", "phone", "account", "card"})

EXPOSED = "전체 노출"
PARTIAL = "부분 마스킹"
MASKED = "마스킹됨"

_PHONE_SEPARATORS = frozenset("-()+.")
_WHITESPACE_SPLIT = re.compile(r"(\s+)")


def _phone_like(core: str) -> bool:
    """숫자(str.isdigit — 숫자 세기·keep_digits 와 같은 정의, 전각 숫자 포함)·-·공백·괄호·+·. 만으로 된 글자인지."""
    return bool(core) and all(ch.isdigit() or ch.isspace() or ch in _PHONE_SEPARATORS for ch in core)


def mask_chars(kind: str) -> frozenset[str]:
    """그 종류에서 가림 문자로 세는 글자."""
    return MASK_CHARS | X_CHARS if kind in NUMERIC_KINDS else MASK_CHARS


def exposure(value: str, kind: str) -> str:
    """값 속 가림 문자로 노출 상태를 추정한다(값 전체로 한 번)."""
    masks = mask_chars(kind)
    masked_count = sum(1 for ch in value if ch in masks)
    plain_count = sum(1 for ch in value if ch.isalnum() and ch not in masks)
    if masked_count == 0:
        return EXPOSED
    if plain_count == 0:
        return MASKED
    return PARTIAL


# --- 조각 규칙(모두 '글자를 그대로 두거나 * 로' 만 한다) -----------------------------------


def _star(ch: str, masks: frozenset[str]) -> str:
    """원문의 가림 문자는 그대로, 그 밖은 '*'."""
    return ch if ch in masks else STAR


def _keep_positions(core: str, positions: list[int], head: int, tail: int, masks: frozenset[str]) -> str:
    """positions(가릴 후보 글자 자리) 중 앞 head·뒤 tail 개만 남긴다. 짧으면 이미 가렸을 때 그대로, 아니면 앞 절반."""
    n = len(positions)
    if n > head + tail:
        keep = set(positions[:head]) | (set(positions[n - tail :]) if tail > 0 else set())
    elif any(ch in masks for ch in core):
        return core
    else:
        keep = set(positions[: n // 2])
    hide = set(positions) - keep
    return "".join(_star(ch, masks) if i in hide else ch for i, ch in enumerate(core))


def keep_digits(core: str, head: int, tail: int, masks: frozenset[str]) -> str:
    """숫자 n 개 중 앞 head·뒤 tail 개만 남기고 가운데 숫자를 '*'. 숫자가 아닌 글자는 그대로."""
    return _keep_positions(core, [i for i, ch in enumerate(core) if ch.isdigit()], head, tail, masks)


def _keep_alnum(core: str, head: int, tail: int, masks: frozenset[str]) -> str:
    positions = [i for i, ch in enumerate(core) if ch.isalnum() and ch not in masks]
    return _keep_positions(core, positions, head, tail, masks)


def _name(core: str, masks: frozenset[str]) -> str:
    if len(core) <= 1:
        return "".join(_star(ch, masks) for ch in core)
    if len(core) == 2:
        return core[0] + _star(core[1], masks)
    return core[0] + "".join(_star(ch, masks) for ch in core[1:-1]) + core[-1]


def _rrn(core: str, masks: frozenset[str]) -> str:
    return keep_digits(core, 7, 0, masks)


def _id_number(core: str, masks: frozenset[str]) -> str:
    if sum(1 for ch in core if ch.isdigit()) == 13:
        return _rrn(core, masks)
    return _keep_alnum(core, 2, 2, masks)


def _email(core: str, masks: frozenset[str]) -> str:
    at = core.rfind("@")
    if at < 0:
        return _text(core, masks)
    local, domain = core[:at], core[at:]
    keep = 0 if len(local) <= 1 else 1 if len(local) <= 3 else 2
    return local[:keep] + "".join(_star(ch, masks) for ch in local[keep:]) + domain


def _hide_alnum(token: str, masks: frozenset[str], keep_first: bool) -> str:
    """토큰의 글자·숫자를 '*'(keep_first 면 첫 글자·숫자 하나는 남김). 가림 문자·문장부호는 그대로."""
    out: list[str] = []
    kept = not keep_first
    for ch in token:
        if ch.isalnum() and ch not in masks:
            if not kept:
                kept = True
                out.append(ch)
            else:
                out.append(STAR)
        else:
            out.append(ch)
    return "".join(out)


def _address(core: str, masks: frozenset[str]) -> str:
    pieces = _WHITESPACE_SPLIT.split(core)
    tokens = [p for p in pieces if p and not p.isspace()]
    keep = 2 if len(tokens) > 2 else 1
    out: list[str] = []
    seen = 0
    for piece in pieces:
        if not piece or piece.isspace():
            out.append(piece)
            continue
        out.append(piece if seen < keep else _hide_alnum(piece, masks, keep_first=False))
        seen += 1
    return "".join(out)


def _tokens(text: str, masks: frozenset[str]) -> str:
    """공백으로 나눈 토큰마다 첫 글자·숫자만 남기고 나머지 글자·숫자를 '*'."""
    return "".join(
        piece if not piece or piece.isspace() else _hide_alnum(piece, masks, keep_first=True)
        for piece in _WHITESPACE_SPLIT.split(text)
    )


def _phone(core: str, masks: frozenset[str]) -> str:
    return keep_digits(core, 3, 4, masks)


def _text(core: str, masks: frozenset[str]) -> str:
    if "@" in core:
        return _email(core, masks)
    digits = sum(1 for ch in core if ch.isdigit())
    if _phone_like(core) and 9 <= digits <= 12:
        return _phone(core, masks)
    colon = core.find(":")
    if colon >= 0:
        return core[: colon + 1] + _tokens(core[colon + 1 :], masks)
    return _tokens(core, masks)


_RULES: dict[str, Callable[[str, frozenset[str]], str]] = {
    "name": _name,
    "rrn": _rrn,
    "id_number": _id_number,
    "birth_date": lambda core, masks: keep_digits(core, 4, 0, masks),
    "phone": _phone,
    "account": lambda core, masks: keep_digits(core, 3, 3, masks),
    "card": lambda core, masks: keep_digits(core, 4, 4, masks),
    "email": _email,
    "address": _address,
    "text": _text,
}


def _mask_piece(piece: str, kind: str, masks: frozenset[str]) -> str:
    stripped = piece.strip()
    if not stripped:
        return piece
    start = len(piece) - len(piece.lstrip())
    lead, trail = piece[:start], piece[start + len(stripped) :]
    rule = _RULES.get(kind, _text)
    core = rule(stripped, masks)
    # 안전장치: 가림 문자가 없던 조각이 그대로면 글자·숫자를 모두 가린다
    if core == stripped and not any(ch in masks for ch in stripped):
        core = _hide_alnum(stripped, masks, keep_first=False)
    return lead + core + trail


def masked(value: str, kind: str) -> str:
    """가림 미리보기. 길이는 원문과 같고 글자는 원문 그대로이거나 '*'."""
    masks = mask_chars(kind)
    return ";".join(_mask_piece(piece, kind, masks) for piece in value.split(";"))
