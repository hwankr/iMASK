# ==========================================================================
#  imask_backend.textsafe — 짝 없는 서로게이트가 든 응답만 ASCII escape JSON 으로(T1-fix5, 코디네이터 결정)
#  이름·값은 원문 그대로다(바꾸지도 이름을 새로 짓지도 않음). escape 경로의 NaN·inf 는 null. 훑기·사본은 반복문.
#  단위 + 씨앗을 고정한 성질 테스트(검출·왕복·ASCII). 값은 모두 지어낸 것.
#  주의: 이웃한 서로게이트 escape 는 따로 쓴 리터럴을 이어 붙인다 — 편집 도구가 한 리터럴의 짝 escape 를 실제
#  보충 평면 글자로 합칠 수 있어서. 또 high 바로 뒤 low 가 오는 문자열은 JSON 을 오가며 한 글자로 합쳐지므로
#  (json.loads·브라우저 JSON.parse 모두) 왕복 성질 테스트의 생성기는 그런 이웃을 만들지 않는다.
# ==========================================================================

from __future__ import annotations

import json
import math
import random
from typing import Any

import pytest

from imask_backend.textsafe import (
    escaped_json_bytes,
    finite_copy,
    has_unpaired_surrogates,
    text_is_safe,
)

HIGH = "\ud800"
HIGH_LAST = "\udbff"
LOW = "\udc00"
LOW_LAST = "\udfff"
REPL = "�"


def test_text_is_safe() -> None:
    assert text_is_safe("abc") and text_is_safe("한글 😀") and text_is_safe(REPL)
    assert not text_is_safe("a" + HIGH) and not text_is_safe(LOW_LAST + "b")


@pytest.mark.parametrize(
    ("value", "found"),
    [
        ({"a": ["b", {"c": "한글"}], "d": ("😀", 1, None, 2.5)}, False),
        ({"a" + HIGH: 1}, True),  # 키
        ({"a": [{"b": ("x", "y" + LOW)}]}, True),  # 튜플 안 값
        (["ok", REPL, "#2"], False),
        ("plain" + LOW_LAST, True),
        (12, False),
    ],
)
def test_has_unpaired_surrogates(value: Any, found: bool) -> None:
    assert has_unpaired_surrogates(value) is found


def test_detection_and_copy_are_iterative() -> None:
    deep: Any = "end" + HIGH
    for _ in range(20_000):  # 재귀였다면 RecursionError
        deep = [deep]
    assert has_unpaired_surrogates(deep)
    copied = finite_copy(deep)
    for _ in range(20_000):
        copied = copied[0]
    assert copied == "end" + HIGH
    shared = {"x": float("nan")}
    out = finite_copy({"a": shared, "b": shared})
    assert out["a"] is out["b"] and out["a"] == {"x": None}  # 같은 dict 는 한 번만 복사


def test_escaped_body_keeps_names_and_values_exactly() -> None:
    value = {"x" + HIGH: "값" + LOW_LAST, "x" + LOW_LAST: ["😀", "한글", {"k": REPL + "#2"}], "n": 1, "t": True, "z": None}
    body = escaped_json_bytes(value)
    assert body.isascii()
    assert json.loads(body) == value  # 키·값(고립 서로게이트·이모지·한글 포함)이 그대로 되살아난다
    assert list(json.loads(body)) == list(value)  # 순서도
    assert b"\\ud800" in body and b"\\udfff" in body


def test_escaped_body_turns_nan_and_inf_into_null() -> None:
    value = {"a" + HIGH: [float("nan"), float("inf"), -math.inf, 1.5], "b": (float("nan"),)}
    loaded = json.loads(escaped_json_bytes(value))
    assert loaded == {"a" + HIGH: [None, None, None, 1.5], "b": [None]}
    assert value["a" + HIGH][0] != value["a" + HIGH][0]  # 원본은 그대로(NaN)


# --- 성질 테스트(씨앗 고정) --------------------------------------------------------------------

SEED = 20261103
TRIALS = 400  # 씨앗 SEED 로 만든 무작위 키·값 객체 400개
PIECES = (HIGH, HIGH_LAST, LOW, LOW_LAST, REPL, "#2", "#3", "b", "한", "😀", " ")


def random_text(rng: random.Random) -> str:
    """서로게이트·U+FFFD·#n·보통 글자를 섞은 문자열 — high 바로 뒤 low 는 만들지 않는다(JSON 왕복에서 합쳐짐)."""
    out = rng.choice(("", "x", "가", "ab"))
    for _ in range(rng.randint(0, 4)):
        piece = rng.choice(PIECES)
        if out and "\ud800" <= out[-1] <= "\udbff" and "\udc00" <= piece[0] <= "\udfff":
            piece = "b"
        out += piece
    return out


def test_property_escape_round_trip() -> None:
    rng = random.Random(SEED)
    for _ in range(TRIALS):
        inner = {random_text(rng): random_text(rng) for _ in range(rng.randint(1, 6))}
        value = {"data": inner, "items": [dict(inner), [random_text(rng) for _ in range(3)]], "n": rng.randint(-5, 5)}
        texts = [*inner, *inner.values(), *value["items"][1]]
        assert has_unpaired_surrogates(value) is any(not text_is_safe(t) for t in texts)
        body = escaped_json_bytes(value)
        assert body.isascii()
        loaded = json.loads(body)
        assert loaded == value and list(loaded["data"]) == list(inner)  # 이름·값·순서 원문 그대로
