# ==========================================================================
#  재발 방지(T4) — 소스에 JWT·Supabase 비밀 키 꼴 글자를 그대로 두지 않는다
#  저장소 비밀값 검사(GitGuardian)가 테스트의 가짜 JWT 를 진짜로 오인해 PR 검사가 실패했다.
#  가짜 값은 tests/fake_tokens.py 가 실행 중에 만든다. 여기서는 api/·imask_backend/·scripts/·tests/·src/
#  의 텍스트 파일을 읽어 아래 두 꼴이 글자 그대로 있으면 실패한다.
#  - JWT 꼴: 'eyJ' + base64url 8자 이상 + '.' + 8자 이상 + '.'
#  - Supabase 비밀 키 꼴: 'sb_' 'secret_' + 키 글자 8자 이상
#  이 파일의 정규식은 조각을 이어 만들어 스스로 걸리지 않는다. 공개 키(sb_publishable_…)·'Bearer …' 문장은 대상 아님.
#  순회는 폴더·파일 링크(symlink, Windows junction)를 따라가지 않고, 실제 경로 기록으로 순환을 막는다(T4-fix1).
# ==========================================================================

from __future__ import annotations

import os
import re
import stat
import sys
from collections.abc import Iterator
from itertools import islice
from pathlib import Path

import pytest
from api_fakes import FAKE_SUPABASE_KEY, FakeStore
from fake_tokens import fake_jwt, fake_supabase_secret

from imask_backend.redaction import JWT_PLACEHOLDER, redact

ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = ("api", "imask_backend", "scripts", "tests", "src")
SKIP_DIRS = frozenset({"node_modules", ".next", ".venv", "tmp", ".orchestration", "__pycache__", ".pytest_cache"})

_KEY_CHAR = "[A-Za-z0-9_-]"
JWT_LITERAL = re.compile("ey" + "J" + _KEY_CHAR + "{8,}" + r"\." + _KEY_CHAR + "{8,}" + r"\.")
SUPABASE_SECRET_LITERAL = re.compile("sb_" + "secret_" + _KEY_CHAR + "{8,}")
PATTERNS = {"JWT": JWT_LITERAL, "Supabase 비밀 키": SUPABASE_SECRET_LITERAL}


# Windows junction(마운트 지점)의 reparse tag. stat 에 없는 버전을 위해 값을 같이 둔다
_MOUNT_POINT_TAG = getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", 0xA0000003)


def is_link(entry: os.DirEntry[str]) -> bool:
    """symlink(POSIX·Windows, 파일·폴더)나 Windows junction 이면 True. 따라가지 않는다."""
    if entry.is_symlink():
        return True
    is_junction = getattr(entry, "is_junction", None)  # Python 3.12+
    if is_junction is not None:
        return bool(is_junction())
    # 3.12 미만: Windows 는 lstat 의 reparse tag 로 junction 을 알아본다(POSIX 에는 junction 이 없다)
    return getattr(entry.stat(follow_symlinks=False), "st_reparse_tag", 0) == _MOUNT_POINT_TAG


def _entries(folder: str | Path) -> list[os.DirEntry[str]]:
    with os.scandir(folder) as it:
        return sorted(it, key=lambda e: e.name)


def iter_source_texts(root: Path | None = None) -> Iterator[tuple[Path, str]]:
    """검사 폴더 아래 텍스트 파일(UTF-8, NUL 없음)을 (경로, 내용)으로. root 기본값은 저장소 루트.

    - 제외 폴더(SKIP_DIRS)로는 내려가지 않는다.
    - 폴더·파일 링크(symlink, Windows junction)는 따라가지도 읽지도 않는다 — 링크로 제외 폴더나
      바깥을 가리켜 경계를 넘지 않게. 검사 폴더 자체가 링크여도 건너뛴다.
    - 방어로 resolve() 한 실제 폴더 경로를 기록해 같은 폴더를 두 번 보지 않는다(순환 방지).
    """
    base_root = ROOT if root is None else root
    tops = {e.name: e for e in _entries(base_root)}
    seen: set[Path] = set()
    for top in SCAN_DIRS:
        entry = tops.get(top)
        if entry is None or is_link(entry) or not entry.is_dir(follow_symlinks=False):
            continue
        stack = [Path(entry.path)]
        while stack:
            folder = stack.pop()
            real = folder.resolve()
            if real in seen:
                continue
            seen.add(real)
            for child in _entries(folder):
                if is_link(child):
                    continue
                if child.is_dir(follow_symlinks=False):
                    if child.name not in SKIP_DIRS:
                        stack.append(Path(child.path))
                    continue
                if not child.is_file(follow_symlinks=False):
                    continue
                data = Path(child.path).read_bytes()
                if b"\0" in data:
                    continue
                try:
                    yield Path(child.path), data.decode("utf-8")
                except UnicodeDecodeError:
                    continue


def find_literals(text: str) -> list[tuple[int, str]]:
    """(줄 번호, 꼴 이름) 목록. 맞은 글자 자체는 돌려주지 않는다(실패 메시지에 값을 옮기지 않게)."""
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for name, pattern in PATTERNS.items():
            if pattern.search(line):
                hits.append((lineno, name))
    return hits


def test_scan_reads_the_source_folders() -> None:
    scanned = {path.relative_to(ROOT).as_posix() for path, _ in iter_source_texts()}
    # 검사가 빈 목록으로 통과하지 않게 — 각 폴더의 알려진 파일과 이 파일 자신을 읽는다
    for expected in (
        "api/index.py",
        "imask_backend/redaction.py",
        "scripts/api_e2e.py",
        "tests/test_no_secret_literals.py",
        "tests/fake_tokens.py",
        "src/services/api/upload.test.ts",
    ):
        assert expected in scanned
    assert not any(part in SKIP_DIRS for path in scanned for part in path.split("/"))


def test_no_jwt_or_supabase_secret_literals_in_sources() -> None:
    found = [
        f"{path.relative_to(ROOT).as_posix()}:{lineno} ({name})"
        for path, text in iter_source_texts()
        for lineno, name in find_literals(text)
    ]
    assert not found, "JWT·비밀 키 꼴 글자를 소스에 두지 말고 tests/fake_tokens.py 로 실행 중에 만드세요: " + ", ".join(found)


@pytest.mark.parametrize(
    "value",
    [
        fake_jwt({"sub": "fake"}),
        fake_jwt({"fake": "probe"}, signature=b"fake-signature-value"),
        fake_jwt({"fake": "x"}, signature=b"signature-fake"),
        fake_jwt({"fake": "0123456789abcdef0123456789abcdef"}),
    ],
    ids=["redaction", "boundaries", "e2e_script", "fake_store"],
)
def test_runtime_jwt_keeps_the_shape_redaction_catches(value: str) -> None:
    # 가짜 값이 런타임에는 여전히 JWT 꼴 — 검출 규칙에도, 제품 가림 규칙에도 걸린다
    assert find_literals(f"bad {value} given") == [(1, "JWT")]
    assert redact(f"bad {value} given") == f"bad {JWT_PLACEHOLDER} given"
    assert value.count(".") == 2 and "=" not in value


def test_fake_store_upload_token_is_a_runtime_jwt() -> None:
    first = FakeStore().create_signed_upload_url("analyses/a/document.pdf")["token"]
    second = FakeStore().create_signed_upload_url("analyses/a/document.pdf")["token"]
    assert first != second
    assert find_literals(first) == [(1, "JWT")]
    assert redact(first) == JWT_PLACEHOLDER


def test_runtime_supabase_secret_keeps_its_shape() -> None:
    assert FAKE_SUPABASE_KEY == fake_supabase_secret()
    assert find_literals(FAKE_SUPABASE_KEY) == [(1, "Supabase 비밀 키")]


@pytest.mark.parametrize(
    "text",
    [
        "const FAKE_KEY = 'sb_publishable_fixture-only';",  # 공개 키 꼴은 대상 아님
        "Authorization: Bearer some-unknown-token-123",
        "JWT 꼴(eyJ….….…)은 <REDACTED_JWT>",
        "eyJshort.abc.def",  # 덩이가 8자보다 짧다
        "새 형식 서버 비밀 키(sb_" + "secret_…)",
        JWT_LITERAL.pattern,
        SUPABASE_SECRET_LITERAL.pattern,
    ],
    ids=["publishable_key", "bearer_sentence", "redaction_comment", "short_segments", "readme_sentence", "jwt_regex", "secret_regex"],
)
def test_detector_leaves_ordinary_text_alone(text: str) -> None:
    assert find_literals(text) == []


# --- fix1: 폴더 링크(symlink·junction)는 따라가지 않는다 ------------------------------------

SCAN_CAP = 500  # 순환을 따라가면 이 개수에 닿는다 — 테스트가 멈추지 않고 실패하게
EXPECTED_FIXTURE_SCAN = {"src/clean.ts": [], "tests/real_hit.txt": [(1, "JWT")]}


@pytest.fixture
def links() -> Iterator[list[Path]]:
    """만든 링크를 기록했다가 링크만 지운다(대상 폴더·파일은 tmp_path 와 함께 정리)."""
    made: list[Path] = []
    yield made
    for link in reversed(made):
        try:
            if os.name == "nt" and os.path.isdir(link):
                os.rmdir(link)  # Windows 폴더 링크·junction: 링크만 지운다
            else:
                os.unlink(link)
        except OSError:
            pass


def make_fixture_tree(tmp_path: Path) -> tuple[Path, Path, Path]:
    """가짜 검사 범위(root). 진짜 파일 하나에만 JWT 꼴 값. 제외 폴더·바깥 폴더에도 같은 꼴 값을 둔다."""
    root = tmp_path / "repo"
    for top in ("tests", "src"):
        (root / top).mkdir(parents=True)
    (root / "tests" / "real_hit.txt").write_text(f"a = {fake_jwt({'real': 'hit'})}\n", encoding="utf-8")
    (root / "src" / "clean.ts").write_text("export const x = 1;\n", encoding="utf-8")
    excluded = root / ".orchestration"
    outside = tmp_path / "outside"
    for folder in (excluded, outside):
        folder.mkdir()
        (folder / "linked.txt").write_text(f"b = {fake_jwt({'linked': folder.name})}\n", encoding="utf-8")
    return root, excluded, outside


def scan_fixture(root: Path) -> dict[str, list[tuple[int, str]]]:
    entries = list(islice(iter_source_texts(root), SCAN_CAP))
    assert len(entries) < SCAN_CAP, "순회가 끝나지 않는다(순환 링크를 따라갔다)"
    found: dict[str, list[tuple[int, str]]] = {}
    for path, text in entries:
        rel = path.relative_to(root).as_posix()
        assert rel not in found, f"같은 파일을 두 번 읽었다: {rel}"
        found[rel] = find_literals(text)
    return dict(sorted(found.items()))


def make_junction(link: Path, target: Path, made: list[Path]) -> None:
    if sys.platform != "win32":
        pytest.skip("Windows junction 은 Windows 에서만 만든다")
    try:
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    except (ImportError, AttributeError, OSError) as exc:
        pytest.skip(f"junction 을 만들 수 없다: {exc}")
    made.append(link)
    assert os.path.isdir(link) and link.resolve() == target.resolve()  # 링크가 실제로 대상으로 이어진다


def make_symlink(link: Path, target: Path, made: list[Path]) -> None:
    try:
        os.symlink(target, link, target_is_directory=target.is_dir())
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink 를 만들 수 없다(Windows 는 개발자 모드나 관리자 권한이 필요): {exc}")
    made.append(link)
    assert os.path.islink(link) and link.resolve() == target.resolve()


def link_cases(root: Path, excluded: Path, outside: Path) -> list[tuple[Path, Path]]:
    return [
        (root / "tests" / "linked-cache", excluded),  # (a) 제외 대상(.orchestration)을 다른 이름으로
        (root / "src" / "linked-outside", outside),  # 검사 범위 바깥 폴더
        (root / "scripts", outside),  # 검사 폴더 자체가 링크
        (root / "tests" / "loop", root / "tests"),  # (c) 자기 상위 폴더 → 순환
        (root / "src" / "up", root),  # (c) 범위 루트 → 순환
    ]


def test_scan_does_not_follow_windows_junctions(tmp_path: Path, links: list[Path]) -> None:
    root, excluded, outside = make_fixture_tree(tmp_path)
    for link, target in link_cases(root, excluded, outside):
        make_junction(link, target, links)
    assert scan_fixture(root) == EXPECTED_FIXTURE_SCAN


def test_scan_does_not_follow_symlinks(tmp_path: Path, links: list[Path]) -> None:
    root, excluded, outside = make_fixture_tree(tmp_path)
    for link, target in link_cases(root, excluded, outside):
        make_symlink(link, target, links)
    make_symlink(root / "tests" / "linked-file.txt", outside / "linked.txt", links)  # 링크된 파일도 읽지 않는다
    assert scan_fixture(root) == EXPECTED_FIXTURE_SCAN


def test_seen_real_paths_stop_a_cycle_even_if_link_check_misses(
    tmp_path: Path, links: list[Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    # 방어 겹: 링크 판별이 빠져도(가정) resolve() 한 실제 경로 기록으로 순환이 끝나고 파일을 두 번 읽지 않는다.
    # junction 은 is_dir(follow_symlinks=False) 가 참이라 이 경로를 실제로 탄다(그래서 Windows 에서만)
    root, _, _ = make_fixture_tree(tmp_path)
    make_junction(root / "tests" / "loop", root / "tests", links)
    monkeypatch.setattr(sys.modules[__name__], "is_link", lambda entry: False)
    assert scan_fixture(root) == EXPECTED_FIXTURE_SCAN
