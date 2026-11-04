# ==========================================================================
#  scripts/make_testdocs.py 테스트 — 브라우저 경로 고르기·명령 인자·임시 폴더 정리를 가짜 실행기로 본다
#  (실제 브라우저를 띄우지 않는다). 그리고 저장소의 합성 시험 묶음(testdocs/final-flow/)이
#  HTML 3개·PDF 3개로 다 있는지, '합성 시험 문서' 표시·A4·쪽 나눔이 있는지, PDF 쪽 수가 맞는지 본다.
# ==========================================================================

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "testdocs" / "final-flow"
# 묶음 → 쪽 수(HTML 의 .page 개수와 같다)
BUNDLES = {"ff-mismatch": 3, "ff-blank-applicant": 2, "ff-team-forms": 4}


def load_script():
    spec = importlib.util.spec_from_file_location("make_testdocs", ROOT / "scripts" / "make_testdocs.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


mt = load_script()


# --- 브라우저 경로 ------------------------------------------------------------


def test_cli_path_wins():
    found = mt.find_browser("D:/b/chrome.exe", {"CHROME_PATH": "E:/env.exe"}, exists=lambda p: True)
    assert found == "D:/b/chrome.exe"


def test_env_path_next():
    found = mt.find_browser(None, {"CHROME_PATH": " E:/env.exe "}, exists=lambda p: True)
    assert found == "E:/env.exe"


def test_given_path_missing_does_not_fall_through():
    everything = lambda p: p != "D:/missing.exe"  # noqa: E731
    assert mt.find_browser("D:/missing.exe", {}, exists=everything) is None
    assert mt.find_browser(None, {"CHROME_PATH": "D:/missing.exe"}, exists=everything) is None


def test_windows_defaults_in_order():
    seen: list[str] = []

    def exists(path: str) -> bool:
        seen.append(path)
        return path.endswith("msedge.exe")

    found = mt.find_browser(None, {"LOCALAPPDATA": "C:/Users/x/AppData/Local"}, exists=exists)
    assert found == mt.WINDOWS_BROWSERS[3]
    assert seen[0] == mt.WINDOWS_BROWSERS[0]
    assert "C:/Users/x/AppData/Local\\Google\\Chrome\\Application\\chrome.exe" in seen


def test_no_browser():
    assert mt.find_browser(None, {}, exists=lambda p: False) is None
    assert mt.main(["--chrome", "D:/none.exe"], environ={}) == mt.EXIT_SETUP


# --- 명령·실행 ----------------------------------------------------------------


def test_build_command(tmp_path):
    html = tmp_path / "묶음 1.html"
    command = mt.build_command("C:/chrome.exe", html, tmp_path / "out.pdf", tmp_path / "profile")
    assert command[0] == "C:/chrome.exe"
    for flag in ("--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--no-first-run"):
        assert flag in command
    assert f"--user-data-dir={tmp_path / 'profile'}" in command
    assert f"--print-to-pdf={tmp_path / 'out.pdf'}" in command
    assert command[-1].startswith("file:///") and "%20" in command[-1]


class FakeRun:
    """--print-to-pdf 경로에 data 를 쓰는 가짜 브라우저. 받은 명령을 남긴다."""

    def __init__(self, data: bytes | None = b"%PDF-1.4\n/Type /Pages /Type /Page /Type /Page\n%%EOF", exc=None):
        self.data = data
        self.exc = exc
        self.commands: list[list[str]] = []

    def __call__(self, command, **kwargs):
        self.commands.append(command)
        assert kwargs.get("timeout") and kwargs.get("capture_output") is True
        if self.exc:
            raise self.exc
        target = next(a.split("=", 1)[1] for a in command if a.startswith("--print-to-pdf="))
        profile = next(a.split("=", 1)[1] for a in command if a.startswith("--user-data-dir="))
        Path(profile).mkdir(parents=True, exist_ok=True)
        (Path(profile) / "Local State").write_bytes(b"{}")
        if self.data is not None:
            Path(target).write_bytes(self.data)
        return subprocess.CompletedProcess(command, 0, b"", b"")


def temp_dirs(root: Path) -> list[Path]:
    return [p for p in root.iterdir() if p.name.startswith("imask-testdocs-")]


def test_make_pdf_moves_result_and_cleans_temp(tmp_path):
    html = tmp_path / "a.html"
    html.write_bytes(b"<p>x</p>")
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"old")
    temp_root = tmp_path / "temp"
    temp_root.mkdir()
    fake = FakeRun()
    data = mt.make_pdf("C:/chrome.exe", html, pdf, run=fake, temp_root=str(temp_root))
    assert pdf.read_bytes() == data and data.startswith(b"%PDF-")  # 덮어씀
    assert mt.count_pages(data) == 2
    assert temp_dirs(temp_root) == []  # 프로필·임시 PDF 모두 지움
    profile = next(a for a in fake.commands[0] if a.startswith("--user-data-dir="))
    assert str(temp_root) in profile


@pytest.mark.parametrize("fake", [FakeRun(data=None), FakeRun(data=b"<html>not pdf"),
                                  FakeRun(exc=subprocess.TimeoutExpired("chrome", 1)), FakeRun(exc=FileNotFoundError())])
def test_make_pdf_failure_keeps_old_pdf(tmp_path, fake):
    html = tmp_path / "a.html"
    html.write_bytes(b"<p>x</p>")
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-old")
    temp_root = tmp_path / "temp"
    temp_root.mkdir()
    with pytest.raises(mt.MakeError):
        mt.make_pdf("C:/chrome.exe", html, pdf, run=fake, temp_root=str(temp_root))
    assert pdf.read_bytes() == b"%PDF-old"
    assert temp_dirs(temp_root) == []


def test_make_pdf_file_errors_are_make_errors(tmp_path, monkeypatch):
    html = tmp_path / "a.html"
    html.write_bytes(b"<p>x</p>")
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-old")
    with pytest.raises(mt.MakeError, match="임시 폴더"):  # 없는 임시 위치
        mt.make_pdf("C:/chrome.exe", html, pdf, run=FakeRun(), temp_root=str(tmp_path / "없음" / "더 없음"))
    temp_root = tmp_path / "temp"
    temp_root.mkdir()

    def locked(*args, **kwargs):
        raise PermissionError("잠김")

    monkeypatch.setattr(mt.shutil, "move", locked)
    with pytest.raises(mt.MakeError, match="옮기지 못했습니다"):
        mt.make_pdf("C:/chrome.exe", html, pdf, run=FakeRun(), temp_root=str(temp_root))
    assert pdf.read_bytes() == b"%PDF-old"
    assert temp_dirs(temp_root) == []


def test_main_with_fake_browser(tmp_path, capsys):
    for name in ("b.html", "a.html"):
        (tmp_path / name).write_bytes(b"<p>x</p>")
    browser = tmp_path / "chrome.exe"
    browser.write_bytes(b"")
    code = mt.main(["--chrome", str(browser), "--dir", str(tmp_path)], run=FakeRun(), environ={})
    out = capsys.readouterr().out
    assert code == mt.EXIT_OK
    assert "a.html → a.pdf" in out and "b.html → b.pdf" in out and "2쪽" in out and "완료 2/2" in out
    assert (tmp_path / "a.pdf").read_bytes().startswith(b"%PDF-")


def test_main_reports_failures(tmp_path, capsys):
    (tmp_path / "a.html").write_bytes(b"<p>x</p>")
    browser = tmp_path / "chrome.exe"
    browser.write_bytes(b"")
    code = mt.main(["--chrome", str(browser), "--dir", str(tmp_path)], run=FakeRun(data=None), environ={})
    assert code == mt.EXIT_FAILED
    assert "실패 a.html" in capsys.readouterr().err
    assert mt.main(["--chrome", str(browser), "--dir", str(tmp_path), "없음.html"], run=FakeRun(), environ={}) == mt.EXIT_SETUP


def test_count_pages():
    assert mt.count_pages(b"/Type /Pages /Type /Page /Type/Page /Type /PageLabel") == 2
    assert mt.count_pages(b"") == 0


# --- 저장소의 시험 묶음 ------------------------------------------------------------


def test_bundle_files_present():
    assert sorted(p.name for p in DOCS.glob("*.html")) == sorted(f"{n}.html" for n in BUNDLES)
    assert sorted(p.name for p in DOCS.glob("*.pdf")) == sorted(f"{n}.pdf" for n in BUNDLES)


@pytest.mark.parametrize("name", sorted(BUNDLES))
def test_bundle_html(name):
    raw = (DOCS / f"{name}.html").read_bytes()
    assert b"\r" not in raw and not raw.startswith(b"\xef\xbb\xbf")
    html = raw.decode("utf-8")
    pages = html.count('<div class="page">')
    assert pages == BUNDLES[name]
    assert html.count("합성 시험 문서") >= pages  # 쪽마다 표시
    assert "size: A4" in html and '"Malgun Gothic"' in html and "page-break-after: always" in html


@pytest.mark.parametrize("name", sorted(BUNDLES))
def test_bundle_pdf(name):
    data = (DOCS / f"{name}.pdf").read_bytes()
    assert data.startswith(b"%PDF-")
    assert mt.count_pages(data) == BUNDLES[name]
