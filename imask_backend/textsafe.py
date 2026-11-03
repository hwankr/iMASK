# ==========================================================================
#  응답 문자열 안전성 — 짝 없는 서로게이트가 든 응답을 ASCII escape JSON 으로 (코디네이터 결정, T1-fix5)
#  파싱된 Python 문자열에는 짝 없는 서로게이트(U+D800~U+DFFF 코드 포인트, 예: JSON 의 "\ud800" escape)가 들어올
#  수 있다. 그대로는 UTF-8 로 인코딩되지 않아 정상 응답 직렬화가 실패(500)한다.
#  결정: 응답에 그런 문자열이 **하나라도 있을 때만** 응답 JSON 을 json.dumps(…, ensure_ascii=True) 로 만든
#  ASCII 본문(서로게이트·비 ASCII 는 \uXXXX escape)으로 보낸다. 이름·값은 **원문 그대로** — 바꾸지도, 이름을 새로
#  짓지도 않는다(그래서 키 충돌·객체 간 대응 문제가 없다. json.loads 하면 원래 키·값이 되살아난다).
#  서로게이트가 없으면 이 모듈을 거치지 않는 정상 경로 그대로(정상 응답은 바이트까지 같다).
#  escape 경로의 NaN·inf 는 정상 경로(pydantic 이 null 로 바꿈)와 같게 null 로 바꾼 사본을 만든 뒤 allow_nan=False.
#  컨테이너 훑기·사본 만들기는 반복문(재귀 없음)이다.
# ==========================================================================

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import Any


def text_is_safe(text: str) -> bool:
    """UTF-8 로 인코딩되는지(짝 없는 서로게이트가 없는지). ASCII 면 바로 참."""
    if text.isascii():
        return True
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def has_unpaired_surrogates(root: Any) -> bool:
    """dict 키·값, list·tuple 안의 문자열 중 UTF-8 로 인코딩되지 않는 것이 있는지(반복문, 같은 컨테이너는 한 번)."""
    stack: list[Any] = [root]
    seen: set[int] = set()
    while stack:
        node = stack.pop()
        if isinstance(node, str):
            if not text_is_safe(node):
                return True
        elif isinstance(node, (Mapping, list, tuple)):
            if id(node) in seen:
                continue
            seen.add(id(node))
            if isinstance(node, Mapping):
                for key, value in node.items():
                    if isinstance(key, str) and not text_is_safe(key):
                        return True
                    stack.append(value)
            else:
                stack.extend(node)
    return False


def _finite(value: Any) -> Any:
    return None if isinstance(value, float) and not math.isfinite(value) else value


def finite_copy(root: Any) -> Any:
    """NaN·inf 를 None 으로 바꾼 사본(dict·list 를 새로 만들고 tuple 은 list 로). 키·문자열은 그대로. 반복문."""
    copies: dict[int, Any] = {}
    pending: list[tuple[Any, Any]] = []

    def fresh(node: Any) -> Any:
        if isinstance(node, (Mapping, list, tuple)):
            if id(node) not in copies:
                copies[id(node)] = {} if isinstance(node, Mapping) else []
                pending.append((node, copies[id(node)]))
            return copies[id(node)]
        return _finite(node)

    top = fresh(root)
    while pending:
        source, target = pending.pop()
        if isinstance(source, Mapping):
            for key, value in source.items():
                target[key] = fresh(value)
        else:
            target.extend(fresh(value) for value in source)
    return top


def escaped_json_bytes(root: Any) -> bytes:
    """ASCII escape JSON 본문 — 짝 없는 서로게이트·비 ASCII 는 \\uXXXX, NaN·inf 는 null. 이름·값은 원문 그대로."""
    text = json.dumps(finite_copy(root), ensure_ascii=True, allow_nan=False, separators=(",", ":"), default=str)
    return text.encode("ascii")
