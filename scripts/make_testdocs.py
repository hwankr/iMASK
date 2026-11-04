# ==========================================================================
#  합성 시험 묶음 PDF 만들기 (로컬 전용)
#  testdocs/final-flow/*.html 을 설치된 Chrome(또는 Edge) 헤드리스 --print-to-pdf 로 같은 이름의 .pdf 로
#  만든다. 이미 있는 PDF 는 덮어쓴다. 시험 묶음의 뜻·기대 결과는 docs/final-workflow.md.
#
#  실행(저장소 루트에서):
#    .venv\Scripts\python.exe scripts\make_testdocs.py [--chrome <브라우저 경로>] [--dir testdocs/final-flow] [이름.html …]
#  브라우저 경로: --chrome > 환경변수 CHROME_PATH > Windows 기본 경로(Chrome → Edge) 순.
#    --chrome·CHROME_PATH 를 줬는데 그 파일이 없으면 기본 경로로 넘어가지 않고 멈춘다.
#  흐름(파일마다): %TEMP% 아래 임시 폴더(--user-data-dir·임시 PDF) → 브라우저 실행 → '%PDF-' 로 시작하는지
#    확인 → 원래 이름으로 옮김 → 임시 폴더 지움(실패해도). 실패하면 기존 PDF 는 그대로 둔다.
#  출력: 파일마다 크기·쪽 수(/Type /Page 개수 — 외부 라이브러리 없이 센다).
#  임시 폴더·읽기·옮기기의 파일 오류도 traceback 없이 그 파일의 실패로 적는다(T2-fix1).
#  종료 코드: 0 모두 성공, 1 하나라도 실패, 2 브라우저·HTML 을 찾지 못함. 표준 라이브러리만.
# ==========================================================================

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = ROOT / "testdocs" / "final-flow"
CHROME_ENV = "CHROME_PATH"
WINDOWS_BROWSERS = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)
BROWSER_TIMEOUT = 120  # 초(파일 하나)
PDF_MAGIC = b"%PDF-"
_PAGE = re.compile(rb"/Type\s*/Page(?![A-Za-z])")

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_SETUP = 2


class MakeError(Exception):
    """PDF 하나를 만들지 못함(짧은 한국어 이유)."""


def find_browser(
    cli: str | None = None,
    environ: Mapping[str, str] | None = None,
    exists: Callable[[str], bool] = os.path.isfile,
) -> str | None:
    """브라우저 경로. --chrome > CHROME_PATH > Windows 기본 경로. 준 경로가 없으면 None(넘어가지 않는다)."""
    env = os.environ if environ is None else environ
    if cli:
        return cli if exists(cli) else None
    from_env = (env.get(CHROME_ENV) or "").strip()
    if from_env:
        return from_env if exists(from_env) else None
    local = env.get("LOCALAPPDATA") or ""
    for candidate in WINDOWS_BROWSERS:
        if "%LOCALAPPDATA%" in candidate:
            if not local:
                continue
            candidate = candidate.replace("%LOCALAPPDATA%", local)
        if exists(candidate):
            return candidate
    return None


def build_command(browser: str, html: Path, pdf: Path, user_data_dir: Path) -> list[str]:
    """헤드리스 인쇄 명령. 머리말·꼬리말 없이, 따로 만든 프로필로."""
    return [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        f"--print-to-pdf={pdf}",
        html.resolve().as_uri(),
    ]


def count_pages(data: bytes) -> int:
    """'/Type /Page' 개수('/Pages' 는 빼고). 압축 객체 스트림 안의 쪽은 세지 못한다."""
    return len(_PAGE.findall(data))


def make_pdf(
    browser: str,
    html: Path,
    pdf: Path,
    *,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    temp_root: str | None = None,
    timeout: float = BROWSER_TIMEOUT,
) -> bytes:
    """html → pdf. 성공하면 PDF 바이트, 실패하면 MakeError(기존 pdf 는 그대로). 파일 오류도 MakeError."""
    try:
        work = Path(tempfile.mkdtemp(prefix="imask-testdocs-", dir=temp_root))
    except OSError as exc:
        raise MakeError(f"임시 폴더를 만들지 못했습니다({type(exc).__name__})") from None
    try:
        target = work / "out.pdf"
        command = build_command(browser, html, target, work / "profile")
        try:
            done = run(command, capture_output=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            raise MakeError(f"브라우저가 {timeout:.0f}초 안에 끝나지 않았습니다") from None
        except OSError as exc:
            raise MakeError(f"브라우저를 실행하지 못했습니다({type(exc).__name__})") from None
        try:
            data = target.read_bytes() if target.is_file() else b""
        except OSError as exc:
            raise MakeError(f"만든 PDF 를 읽지 못했습니다({type(exc).__name__})") from None
        if not data.startswith(PDF_MAGIC):
            code = getattr(done, "returncode", None)
            raise MakeError(f"PDF 가 만들어지지 않았습니다(종료 코드 {code})")
        try:
            pdf.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target), str(pdf))
        except OSError as exc:
            raise MakeError(f"PDF 를 {pdf.name} 로 옮기지 못했습니다({type(exc).__name__})") from None
        return data
    finally:
        shutil.rmtree(work, ignore_errors=True)


def html_files(folder: Path, names: Sequence[str]) -> list[Path]:
    if names:
        return [folder / name for name in names]
    return sorted(folder.glob("*.html"))


def main(
    argv: Sequence[str] | None = None,
    *,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    environ: Mapping[str, str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="make_testdocs.py", description="합성 시험 묶음 HTML → PDF")
    parser.add_argument("--chrome", help="브라우저 실행 파일 경로(없으면 CHROME_PATH, 그다음 Windows 기본 경로)")
    parser.add_argument("--dir", default=str(DEFAULT_DIR), help="HTML 폴더(기본: testdocs/final-flow)")
    parser.add_argument("names", nargs="*", help="만들 HTML 파일 이름(없으면 폴더의 *.html 전부)")
    args = parser.parse_args(argv)

    browser = find_browser(args.chrome, environ)
    if browser is None:
        print("브라우저를 찾지 못했습니다 — --chrome 이나 CHROME_PATH 로 Chrome·Edge 경로를 주세요.", file=sys.stderr)
        return EXIT_SETUP
    folder = Path(args.dir)
    files = html_files(folder, args.names)
    missing = [f.name for f in files if not f.is_file()]
    if not files or missing:
        print(f"HTML 을 찾지 못했습니다: {', '.join(missing) or folder}", file=sys.stderr)
        return EXIT_SETUP

    print(f"브라우저: {Path(browser).name} · 폴더: {folder}")
    failed = 0
    for html in files:
        pdf = html.with_suffix(".pdf")
        try:
            data = make_pdf(browser, html, pdf, run=run)
        except MakeError as exc:
            failed += 1
            print(f"실패 {html.name}: {exc}", file=sys.stderr)
            continue
        print(f"{html.name} → {pdf.name}  {len(data):,} B  {count_pages(data)}쪽")
    print(f"완료 {len(files) - failed}/{len(files)}")
    return EXIT_OK if not failed else EXIT_FAILED


def _setup_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    _setup_console()
    sys.exit(main())
