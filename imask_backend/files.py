# ==========================================================================
#  파일 이름·형식 검사 (FastAPI·Supabase 와 무관한 순수 함수)
#  - check_upload(filename, size, mime_type): 만들기 요청의 파일 정보 검사. 어기면 FileCheckError
#    (사용자에게 보일 짧은 한국어 문장). 형식은 PDF·PNG·JPEG, 확장자가 형식과 맞아야 하고,
#    크기는 1바이트 ~ 20MB(DB 버킷 제한과 같다), 이름은 경로를 뗀 뒤 1~200자.
#  - analysis_name(name, filename): 분석명(앞뒤 공백 제거, 60자 이하, 비면 파일 이름).
#  - safe_storage_name(filename): Supabase Storage 키로 쓸 ASCII 이름. Storage 키는 영숫자 등
#    일부 ASCII 만 받아서(한글은 'Invalid key') 줄기의 [A-Za-z0-9._-] 밖 글자 묶음을 '_' 로 바꾸고
#    앞뒤 '._-' 를 지운 뒤 80자까지, 비면 'document'. 확장자는 소문자. 원래 이름은 DB 에 남긴다.
#  - content_matches(content, mime_type): 올라온 내용의 첫 바이트가 형식과 맞는지.
# ==========================================================================

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_FILE_BYTES = 20 * 1024 * 1024  # 20,971,520 — documents 버킷의 file_size_limit 과 같다
MAX_FILENAME_LENGTH = 200
MAX_ANALYSIS_NAME_LENGTH = 60
MAX_SAFE_STEM_LENGTH = 80
DEFAULT_SAFE_STEM = "document"

# 형식 → 허용 확장자(소문자, 점 없이)
ALLOWED_TYPES: dict[str, tuple[str, ...]] = {
    "application/pdf": ("pdf",),
    "image/png": ("png",),
    "image/jpeg": ("jpg", "jpeg"),
}

# 형식별 첫 바이트(PDF 는 앞 1024바이트 안 어딘가에 '%PDF-' 가 있으면 된다 — 앞에 쓰레기 바이트가
# 붙은 PDF 도 PDF 리더가 읽기 때문)
PDF_MAGIC = b"%PDF-"
PDF_SEARCH_BYTES = 1024
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"

MSG_BAD_TYPE = "파일 형식은 PDF·PNG·JPEG 만 올릴 수 있습니다."
MSG_BAD_EXTENSION = "파일 확장자가 형식과 맞지 않습니다(PDF 는 .pdf, PNG 는 .png, JPEG 는 .jpg·.jpeg)."
MSG_BAD_SIZE = "파일 크기는 1바이트 이상 20MB 이하여야 합니다."
MSG_EMPTY_FILENAME = "파일 이름이 비었습니다."
MSG_LONG_FILENAME = f"파일 이름은 {MAX_FILENAME_LENGTH}자 이하여야 합니다."
MSG_LONG_NAME = f"분석명은 {MAX_ANALYSIS_NAME_LENGTH}자 이하여야 합니다."

_UNSAFE_RUN = re.compile(r"[^A-Za-z0-9._-]+")


class FileCheckError(ValueError):
    """요청 검사 실패. message 는 사용자에게 그대로 보여 줄 한국어 문장."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class CheckedUpload:
    filename: str  # 경로를 뗀 원래 이름(DB documents.filename)
    size: int
    mime_type: str
    safe_name: str  # Storage 키·Upstage 에 쓰는 ASCII 이름


def base_name(filename: str) -> str:
    """경로 부분(/·\\)을 떼고 앞뒤 공백을 지운 이름."""
    return re.split(r"[/\\]", filename)[-1].strip()


def split_extension(name: str) -> tuple[str, str]:
    """(줄기, 소문자 확장자). 확장자가 없으면 ''. 점으로 시작하는 이름('.pdf')은 줄기가 빈 이름."""
    stem, dot, ext = name.rpartition(".")
    if not dot:
        return name, ""
    return stem, ext.lower()


def safe_storage_name(filename: str) -> str:
    """Storage 키로 쓸 ASCII 이름(줄기 정리 + 소문자 확장자)."""
    stem, ext = split_extension(base_name(filename))
    stem = _UNSAFE_RUN.sub("_", stem).strip("._-")[:MAX_SAFE_STEM_LENGTH].strip("._-")
    stem = stem or DEFAULT_SAFE_STEM
    ext = _UNSAFE_RUN.sub("", ext)
    return f"{stem}.{ext}" if ext else stem


def check_upload(filename: str, size: int, mime_type: str) -> CheckedUpload:
    """만들기 요청의 파일 정보를 검사한다. 어기면 FileCheckError(구체적인 한국어 문장)."""
    name = base_name(filename)
    if not name:
        raise FileCheckError(MSG_EMPTY_FILENAME)
    if len(name) > MAX_FILENAME_LENGTH:
        raise FileCheckError(MSG_LONG_FILENAME)
    if mime_type not in ALLOWED_TYPES:
        raise FileCheckError(MSG_BAD_TYPE)
    _, ext = split_extension(name)
    if ext not in ALLOWED_TYPES[mime_type]:
        raise FileCheckError(MSG_BAD_EXTENSION)
    # bool 은 int 의 하위 타입이라 따로 막는다(요청 모델이 이미 막지만 함수만 쓸 때를 위해)
    if isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= MAX_FILE_BYTES:
        raise FileCheckError(MSG_BAD_SIZE)
    return CheckedUpload(filename=name, size=size, mime_type=mime_type, safe_name=safe_storage_name(name))


def analysis_name(name: str | None, filename: str) -> str:
    """분석명: 앞뒤 공백을 지우고 60자 이하. 비었으면 파일 이름(60자에서 자름)."""
    cleaned = (name or "").strip()
    if not cleaned:
        return base_name(filename)[:MAX_ANALYSIS_NAME_LENGTH].strip()
    if len(cleaned) > MAX_ANALYSIS_NAME_LENGTH:
        raise FileCheckError(MSG_LONG_NAME)
    return cleaned


def content_matches(content: bytes, mime_type: str) -> bool:
    """내용의 첫 바이트가 형식과 맞는지(PDF 는 앞 1024바이트 안에 '%PDF-')."""
    if mime_type == "application/pdf":
        return PDF_MAGIC in content[:PDF_SEARCH_BYTES]
    if mime_type == "image/png":
        return content.startswith(PNG_MAGIC)
    if mime_type == "image/jpeg":
        return content.startswith(JPEG_MAGIC)
    return False
