# ==========================================================================
#  테스트용 가짜 JWT·Supabase 비밀 키 — 실행 중에 만든다(T4)
#  소스에 JWT·비밀 키처럼 생긴 글자를 그대로 두면 저장소 비밀값 검사(GitGuardian)가 진짜로 오인한다.
#  그래서 조각을 이어 붙이거나 인코딩해서 런타임에만 그 모양이 되게 한다. 값은 모두 지어낸 가짜다.
#  - fake_jwt(payload): 헤더·payload 를 압축 JSON → base64url(패딩 없음)로, 가짜 서명 바이트를 붙여
#    'xxx.yyy.zzz'. 기본 헤더는 {"alg":"HS256"} — 예전 리터럴과 같은 문자열이 나오게 typ 은 넣지 않는다.
#  - fake_supabase_secret(body): 'sb_' + 'secret_' + body. 런타임 값은 Supabase 새 형식 비밀 키 꼴이다.
#  재발 방지는 tests/test_no_secret_literals.py 가 맡는다.
# ==========================================================================

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from typing import Any

DEFAULT_HEADER: Mapping[str, Any] = {"alg": "HS256"}
DEFAULT_SIGNATURE = b"fake-signature"


def b64url(raw: bytes) -> str:
    """base64url, 끝의 '=' 패딩 없이."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _segment(obj: Mapping[str, Any]) -> str:
    return b64url(json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def fake_jwt(
    payload: Mapping[str, Any],
    *,
    signature: bytes = DEFAULT_SIGNATURE,
    header: Mapping[str, Any] | None = None,
) -> str:
    """가짜 JWT(서명 검증 불가). 가림 규칙(eyJ….….…)에 걸리는 모양이다."""
    return ".".join((_segment(DEFAULT_HEADER if header is None else header), _segment(payload), b64url(signature)))


def fake_supabase_secret(body: str = "FAKE-supabase-key-9876") -> str:
    """가짜 Supabase 서버 비밀 키. 접두사를 조각으로 나눠 소스에 키 꼴 글자가 남지 않게 한다."""
    return "sb_" + "secret_" + body
