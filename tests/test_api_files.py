# ==========================================================================
#  imask_backend.files — 파일 이름·형식 검사, 안전한 Storage 이름, 내용 첫 바이트
# ==========================================================================

from __future__ import annotations

import pytest

from imask_backend.files import (
    MAX_FILE_BYTES,
    MSG_BAD_EXTENSION,
    MSG_BAD_SIZE,
    MSG_BAD_TYPE,
    MSG_EMPTY_FILENAME,
    MSG_LONG_FILENAME,
    MSG_LONG_NAME,
    FileCheckError,
    analysis_name,
    base_name,
    check_upload,
    content_matches,
    safe_storage_name,
)


@pytest.mark.parametrize(
    ("original", "expected"),
    [
        ("iMASK_smoke_bundle.pdf", "iMASK_smoke_bundle.pdf"),
        ("대출 서류.pdf", "document.pdf"),
        ("김 2024 묶음.PDF", "2024.pdf"),
        ("합성_묶음.pdf", "document.pdf"),
        ("scan (1).JPG", "scan_1.jpg"),
        ("a b  c.png", "a_b_c.png"),
        ("...--a--...jpeg", "a.jpeg"),
        (".pdf", "document.pdf"),
        ("C:\\Users\\me\\묶음 v2.pdf", "v2.pdf"),
        ("dir/sub/report.final.PDF", "report.final.pdf"),
        ("x" * 100 + ".pdf", "x" * 80 + ".pdf"),
        ("a" * 79 + "_bc.pdf", "a" * 79 + ".pdf"),  # 80자에서 자른 뒤 끝의 '_' 도 지운다
    ],
)
def test_safe_storage_name_rules(original: str, expected: str) -> None:
    assert safe_storage_name(original) == expected


def test_safe_storage_name_is_ascii_storage_key() -> None:
    for name in ("대출 서류.pdf", "김 2024 묶음.PDF", "🙂.png", "名前.jpeg"):
        safe = safe_storage_name(name)
        assert safe.isascii()
        assert all(ch.isalnum() or ch in "._-" for ch in safe)


def test_base_name_strips_both_separators_and_spaces() -> None:
    assert base_name("  C:\\a\\b/c.pdf  ") == "c.pdf"
    assert base_name("dir/") == ""


@pytest.mark.parametrize(
    ("filename", "mime"),
    [
        ("a.pdf", "application/pdf"),
        ("a.PDF", "application/pdf"),
        ("a.png", "image/png"),
        ("a.jpg", "image/jpeg"),
        ("a.JPEG", "image/jpeg"),
    ],
)
def test_check_upload_accepts_matching_types(filename: str, mime: str) -> None:
    checked = check_upload(filename, 10, mime)
    assert checked.filename == filename
    assert checked.mime_type == mime


@pytest.mark.parametrize(
    ("filename", "size", "mime", "message"),
    [
        ("a.gif", 10, "image/gif", MSG_BAD_TYPE),
        ("a.pdf", 10, "application/octet-stream", MSG_BAD_TYPE),
        ("a.png", 10, "application/pdf", MSG_BAD_EXTENSION),
        ("a.jpg", 10, "image/png", MSG_BAD_EXTENSION),
        ("a", 10, "application/pdf", MSG_BAD_EXTENSION),
        ("a.pdf", 0, "application/pdf", MSG_BAD_SIZE),
        ("a.pdf", -1, "application/pdf", MSG_BAD_SIZE),
        ("a.pdf", MAX_FILE_BYTES + 1, "application/pdf", MSG_BAD_SIZE),
        ("a.pdf", True, "application/pdf", MSG_BAD_SIZE),
        ("   ", 10, "application/pdf", MSG_EMPTY_FILENAME),
        ("dir/", 10, "application/pdf", MSG_EMPTY_FILENAME),
        ("x" * 197 + ".pdf", 10, "application/pdf", MSG_LONG_FILENAME),
    ],
)
def test_check_upload_rejects(filename: str, size: int, mime: str, message: str) -> None:
    with pytest.raises(FileCheckError) as info:
        check_upload(filename, size, mime)
    assert info.value.message == message


def test_check_upload_size_bounds_and_long_name_ok() -> None:
    assert check_upload("a.pdf", 1, "application/pdf").size == 1
    assert check_upload("a.pdf", MAX_FILE_BYTES, "application/pdf").size == MAX_FILE_BYTES
    assert check_upload("x" * 196 + ".pdf", 10, "application/pdf").filename == "x" * 196 + ".pdf"


def test_analysis_name() -> None:
    assert analysis_name("  분석 1  ", "a.pdf") == "분석 1"
    assert analysis_name(None, "묶음.pdf") == "묶음.pdf"
    assert analysis_name("   ", "묶음.pdf") == "묶음.pdf"
    assert analysis_name("가" * 60, "a.pdf") == "가" * 60
    assert analysis_name(None, "x" * 100 + ".pdf") == "x" * 60
    with pytest.raises(FileCheckError) as info:
        analysis_name("가" * 61, "a.pdf")
    assert info.value.message == MSG_LONG_NAME


def test_content_matches() -> None:
    assert content_matches(b"%PDF-1.7 ...", "application/pdf")
    assert content_matches(b"\x00" * 1000 + b"%PDF-1.4", "application/pdf")
    assert not content_matches(b"\x00" * 1024 + b"%PDF-1.4", "application/pdf")
    assert not content_matches(b"not a pdf", "application/pdf")
    assert content_matches(b"\x89PNG\r\n\x1a\n....", "image/png")
    assert not content_matches(b"\x89PNG....", "image/png")
    assert content_matches(b"\xff\xd8\xff\xe0....", "image/jpeg")
    assert not content_matches(b"%PDF-1.7", "image/jpeg")
    assert not content_matches(b"%PDF-1.7", "text/plain")
    assert not content_matches(b"", "application/pdf")
