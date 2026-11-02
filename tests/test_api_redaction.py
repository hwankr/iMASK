# ==========================================================================
#  imask_backend.redaction — 서명 URL·토큰·JWT 규칙(T2-fix1 M3). 값은 모두 가짜.
#  일반 문장·HTTP 상태 문구는 그대로, 가림은 길이 제한 전, JSON 구조 유지 가림(redact_value)과 함께 동작.
# ==========================================================================

from __future__ import annotations

import json

import pytest
from fake_tokens import fake_jwt

from imask_backend.redaction import (
    JWT_PLACEHOLDER,
    SIGNED_URL_PLACEHOLDER,
    TOKEN_PLACEHOLDER,
    redact,
    redact_value,
)

TOKEN = "FAKE_SIGNED_" + "Q" * 40
JWT = fake_jwt({"sub": "fake"})  # 실행 중에 만든다(소스에 JWT 꼴 글자를 두지 않음)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            f"cannot read https://p.supabase.co/storage/v1/object/upload/sign/documents/a.pdf?token={TOKEN} end",
            f"cannot read {SIGNED_URL_PLACEHOLDER} end",
        ),
        (f"rel /object/upload/sign/documents/a/b.pdf?token={TOKEN}", f"rel {SIGNED_URL_PLACEHOLDER}"),
        (
            f"x https://p.supabase.co/storage/v1/object/sign/documents/a.pdf?token={TOKEN}&download=1, ok",
            f"x {SIGNED_URL_PLACEHOLDER}, ok",
        ),
        (f"(see https://h.invalid/object/sign/b/a.png?token={TOKEN}).", f"(see {SIGNED_URL_PLACEHOLDER})."),
        (f"token={TOKEN}&a=1", f"token={TOKEN_PLACEHOLDER}&a=1"),
        (f"access_token={TOKEN}", f"access_token={TOKEN_PLACEHOLDER}"),
        (f"u=https%3A%2F%2Fh%2Fx%3Ftoken%3D{TOKEN}%26y%3D1", f"u=https%3A%2F%2Fh%2Fx%3Ftoken%3D{TOKEN_PLACEHOLDER}%26y%3D1"),
        (f'{{"token": "{TOKEN}", "path": "a.pdf"}}', f'{{"token": "{TOKEN_PLACEHOLDER}", "path": "a.pdf"}}'),
        ('{"signedUrl": "https://h/a?b=1"}', f'{{"signedUrl": "{TOKEN_PLACEHOLDER}"}}'),
        ('{"signed_url":"https://h/a?b=1"}', f'{{"signed_url":"{TOKEN_PLACEHOLDER}"}}'),
        (f'{{\\"token\\": \\"{TOKEN}\\"}}', f'{{\\"token\\": \\"{TOKEN_PLACEHOLDER}\\"}}'),
        (f"{{'token': '{TOKEN}', 'path': 'a'}}", f"{{'token': '{TOKEN_PLACEHOLDER}', 'path': 'a'}}"),
        (f"bad {JWT} given", f"bad {JWT_PLACEHOLDER} given"),
    ],
)
def test_signed_url_token_and_jwt_rules(text: str, expected: str) -> None:
    assert redact(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "작업 조회: HTTP 403 — Forbidden",
        "파일 올리기: HTTP 500 — internal error",
        "Authorization header missing",
        "bearer bonds",
        "invalid token",
        "max_tokens=5 이 아니라 6",  # 'token=' 이 아님
        '{"input_tokens": 11711, "output_tokens": 936}',
        "see https://example.com/docs?page=2",
        "https://p.supabase.co/storage/v1/object/sign/documents/a.pdf",  # 쿼리 없는 경로만은 권한이 아님
    ],
)
def test_plain_text_is_unchanged(text: str) -> None:
    assert redact(text) == text


def test_redaction_is_idempotent() -> None:
    once = redact(f"x https://h/object/upload/sign/d/a.pdf?token={TOKEN} token={TOKEN} {JWT}")
    assert redact(once) == once


def test_redaction_happens_before_truncation() -> None:
    text = "x" * 190 + f"token={TOKEN}"  # 토큰이 200자 경계에 걸친다
    out = redact(text, limit=200)
    assert len(out) <= 200
    assert TOKEN[:8] not in out
    jwt_text = "y" * 195 + JWT  # 자르면 JWT 자리로 4자만 남는다 — 그 4자를 본다(JWT 규칙이 없으면 실패)
    assert JWT[:4] not in redact(jwt_text, limit=200)


def test_redact_value_keeps_json_structure_with_token_fields() -> None:
    inner = json.dumps({"token": TOKEN, "signedUrl": "https://h/a?b=1", "n": 1, "input_tokens": 5})
    masked = redact_value({"error": inner, "signed_url": "https://h/x?token=" + TOKEN, "list": [JWT]})
    parsed = json.loads(masked["error"])
    assert parsed == {"token": TOKEN_PLACEHOLDER, "signedUrl": TOKEN_PLACEHOLDER, "n": 1, "input_tokens": 5}
    assert masked["signed_url"] == TOKEN_PLACEHOLDER
    assert masked["list"] == [JWT_PLACEHOLDER]
    assert TOKEN not in json.dumps(masked) and JWT not in json.dumps(masked)


def test_redact_value_leaves_clean_json_text_untouched() -> None:
    text = json.dumps({"path": "a.pdf", "n": 1}, separators=(",", ":"))
    assert redact_value(text) == text
