# ==========================================================================
#  redaction.py 테스트 — 알려진 값·인증 문구 가림, 가림 뒤 길이 제한, 중첩 값.
#  모든 값은 지어낸 가짜 값이다.
# ==========================================================================

from __future__ import annotations

import json

import pytest

from imask_backend.redaction import (
    AGENT_ID_PLACEHOLDER,
    API_KEY_PLACEHOLDER,
    AUTH_PLACEHOLDER,
    redact,
    redact_value,
    upstage_secrets,
)
from imask_backend.results import parse_stages, summarize

FAKE_KEY = "up-fake-KEY-0123456789abcdef"
FAKE_AGENT = "agent-fake-ID-98765"
SECRETS = upstage_secrets(FAKE_KEY, FAKE_AGENT)


def assert_clean(text: str) -> None:
    assert FAKE_KEY not in text
    assert FAKE_AGENT not in text
    assert "authorization" not in text.lower()
    assert "bearer" not in text.lower()


def test_upstage_secrets_skips_empty():
    assert upstage_secrets(FAKE_KEY, None) == {FAKE_KEY: API_KEY_PLACEHOLDER}
    assert upstage_secrets("", "") == {}
    assert SECRETS == {FAKE_KEY: API_KEY_PLACEHOLDER, FAKE_AGENT: AGENT_ID_PLACEHOLDER}


def test_known_values_become_placeholders():
    text = redact(f"key={FAKE_KEY} model={FAKE_AGENT}", SECRETS)
    assert text == f"key={API_KEY_PLACEHOLDER} model={AGENT_ID_PLACEHOLDER}"


@pytest.mark.parametrize(
    "raw",
    [
        f"Authorization: Bearer {FAKE_KEY}; agent={FAKE_AGENT}",
        f"authorization=Bearer {FAKE_KEY}",
        f"{{'authorization': 'Bearer {FAKE_KEY}'}}",
        f'{{"Authorization": "Bearer {FAKE_KEY}"}}',
        f"AUTHORIZATION Bearer {FAKE_KEY}",
        f"Authorization: Basic dXNlcjpwYXNz and {FAKE_AGENT}",
        f"token was Bearer {FAKE_KEY} (expired)",
        "sent bearer abcdefgh12345678== to server",
    ],
)
def test_auth_phrases_are_removed_whole(raw):
    text = redact(raw, SECRETS)
    assert_clean(text)
    assert AUTH_PLACEHOLDER in text


def test_auth_phrase_removed_even_without_known_values():
    text = redact("Authorization: Bearer some-unknown-token-123")
    assert text == AUTH_PLACEHOLDER
    assert "some-unknown-token" not in text


def test_ordinary_words_are_kept():
    # 토큰이 붙지 않은 낱말은 그대로 둔다
    assert redact("Authorization header missing") == "Authorization header missing"
    assert redact("bearer bonds") == "bearer bonds"


def test_short_values_are_not_redacted():
    # config_id '3' 같은 짧은 식별자로 'HTTP 403' 이 깨지지 않게
    assert redact("작업 만들기: HTTP 403", {"3": "<CONFIG>"}) == "작업 만들기: HTTP 403"


def test_limit_applies_after_redaction():
    # 키가 길이 제한 경계에 걸쳐 있어도 잘린 조각이 남지 않는다
    raw = "x" * 290 + FAKE_KEY + "y" * 100
    text = redact(raw, SECRETS, limit=300)
    assert len(text) <= 300
    assert FAKE_KEY[:8] not in text
    assert text.endswith("…")


def test_longer_secret_first():
    secrets = {"abcd": "<SHORT>", "abcdefgh": "<LONG>"}
    assert redact("abcdefgh", secrets) == "<LONG>"


def test_non_string_input():
    assert redact(None) == "None"
    assert redact(12345, SECRETS) == "12345"


def test_redact_value_walks_nested_keys_and_values():
    value = {
        "model": FAKE_AGENT,
        "list": [f"x-{FAKE_KEY}-y", 1, None, {"auth": f"Authorization: Bearer {FAKE_KEY}"}],
        FAKE_AGENT: "as key",
    }
    out = redact_value(value, SECRETS)
    assert out == {
        "model": AGENT_ID_PLACEHOLDER,
        "list": [f"x-{API_KEY_PLACEHOLDER}-y", 1, None, {"auth": AUTH_PLACEHOLDER}],
        AGENT_ID_PLACEHOLDER: "as key",
    }


# --- R2-m1: JSON 이 든 문자열은 구조를 유지한 채 가린다 ------------------------------------


def _json_with_auth_key(**dump_kwargs) -> str:
    payload = {"Authorization": f"Bearer {FAKE_KEY}", "applicant_name": "가짜 이름", "model": FAKE_AGENT}
    return json.dumps(payload, ensure_ascii=False, **dump_kwargs)


@pytest.mark.parametrize(
    "dump_kwargs",
    [{}, {"separators": (",", ":")}, {"indent": 2}],
    ids=["default-separators", "compact", "indent-2"],
)
def test_json_string_with_authorization_key_stays_valid_json(dump_kwargs):
    raw = _json_with_auth_key(**dump_kwargs)
    masked = redact_value(raw, SECRETS)

    parsed = json.loads(masked)  # 가린 뒤에도 JSON 이다
    assert parsed == {
        "Authorization": AUTH_PLACEHOLDER,
        "applicant_name": "가짜 이름",  # 일반 필드 보존(ensure_ascii=False — 한글 그대로)
        "model": AGENT_ID_PLACEHOLDER,
    }
    assert FAKE_KEY not in masked and FAKE_AGENT not in masked
    assert "가짜 이름" in masked
    # 원래와 같은 구분자·들여쓰기로 다시 직렬화
    assert masked == json.dumps(parsed, ensure_ascii=False, **dump_kwargs)


def test_json_string_without_secrets_is_returned_unchanged():
    raw = '{"a":1,  "b" : "\\uac00", "list": [1, 2]}'  # 특이한 공백·유니코드 이스케이프도 그대로
    assert "\\u" in raw
    assert redact_value(raw, SECRETS) == raw


def test_json_array_and_nested_json_strings():
    inner = json.dumps({"Authorization": f"Bearer {FAKE_KEY}", "keep": "x"})
    raw = json.dumps([{"message": f"Authorization: Bearer {FAKE_KEY}", "inner": inner}, "ok"])
    masked = redact_value(raw, SECRETS)
    outer = json.loads(masked)
    assert outer[0]["message"] == AUTH_PLACEHOLDER
    assert json.loads(outer[0]["inner"]) == {"Authorization": AUTH_PLACEHOLDER, "keep": "x"}
    assert outer[1] == "ok"
    assert FAKE_KEY not in masked


def test_authorization_key_in_plain_dict_masks_any_value():
    value = {"authorization": "sk-raw-token-without-scheme", "Proxy-Authorization": "Basic abc", "other": "keep"}
    assert redact_value(value, SECRETS) == {
        "authorization": AUTH_PLACEHOLDER,
        "Proxy-Authorization": AUTH_PLACEHOLDER,
        "other": "keep",
    }


def test_text_that_only_looks_like_json_uses_text_rules():
    raw = f"{{not json Authorization: Bearer {FAKE_KEY}"
    masked = redact_value(raw, SECRETS)
    assert masked == "{not json " + AUTH_PLACEHOLDER
    assert redact_value('"Authorization header missing"', SECRETS) == '"Authorization header missing"'


def test_summary_counts_survive_redaction_of_json_text():
    extract_text = json.dumps({"Authorization": f"Bearer {FAKE_KEY}", "applicant_name": "가짜"}, ensure_ascii=False)
    response = {
        "status": "completed",
        "output": [
            {"model": "Information Extract - 민감정보_추출", "status": "completed", "content": [{"text": extract_text}]},
            {
                "model": "step_2_classify",
                "status": "completed",
                "content": [
                    {"text": "loan_application", "additional_values": json.dumps({"document_type": {"_value": "loan_application"}, "authorization": "Bearer " + FAKE_KEY})},
                ],
            },
        ],
    }
    masked = redact_value(response, SECRETS)
    assert FAKE_KEY not in json.dumps(masked, ensure_ascii=False)
    before, after = summarize(response), summarize(masked)
    assert before == after
    assert after["extracted_document_count"] == 1
    assert after["document_types"] == ["loan_application"]
    assert parse_stages(masked)[0]["data"] == {"Authorization": AUTH_PLACEHOLDER, "applicant_name": "가짜"}
