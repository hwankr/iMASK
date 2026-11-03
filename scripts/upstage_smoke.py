# ==========================================================================
#  Upstage 워크플로우 확인 스크립트 (로컬 전용)
#  합성 묶음 하나를 Upstage Agent API 로 한 번 돌려 실제 응답 모양을 확인한다.
#
#  실행(저장소 루트에서):
#    .venv\Scripts\python.exe scripts\upstage_smoke.py [--file testdocs/iMASK_smoke_bundle.pdf]
#        [--interval 3] [--timeout 600] [--out-dir tmp/upstage_smoke]
#    .venv\Scripts\python.exe scripts\upstage_smoke.py --summarize-only tmp/upstage_smoke/<파일>.json
#      → 저장해 둔 원본으로 다시 요약만 한다(네트워크·.env 쓰지 않음).
#
#  흐름: 파일 올리기 → 작업 만들기(include ["all"], config_id) → include[]=last 로 조회 반복
#        → completed 면 include[]=all 로 한 번 더 받아 tmp/ 에 원본 저장 → 요약·기대값 비교
#        → finally 에서 Upstage 파일 삭제(Ctrl+C·오류·시간 초과에도) → 삭제 확인.
#  비밀값: 루트 .env 를 프로그램 안에서 읽는다. 값은 출력하지 않는다(BRIEF §2).
#    모든 출력은 _say() 한 곳을 지나며 imask_backend.redaction.redact 로 API 키·에이전트 id·
#    인증 문구를 가린다. 작업 실패 이유는 공용 job_failure_message 만 쓴다. 저장 원본도 가린다.
#  Upstage 실행 1번 = 크레딧 사용(BRIEF §3). 합성 자료만 올린다.
#  종료 코드: 0 완료 + 기대값 일치, 2 완료했지만 불일치, 1 실패·시간 초과·오류·중단.
# ==========================================================================

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
import time
import traceback
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from imask_backend.config import (  # noqa: E402
    REQUIRED_UPSTAGE_ENV,
    ConfigError,
    UpstageSettings,
    load_upstage_settings,
)
from imask_backend.redaction import redact, redact_value, upstage_secrets  # noqa: E402
from imask_backend.results import parse_stages, summarize  # noqa: E402
from imask_backend.upstage import (  # noqa: E402
    MAX_MESSAGE,
    UpstageClient,
    UpstageError,
    is_success,
    is_terminal,
    job_failure_message,
)

DEFAULT_FILE = "testdocs/iMASK_smoke_bundle.pdf"
DEFAULT_OUT_DIR = "tmp/upstage_smoke"

# 합성 묶음 기대값(BRIEF §3). 서류-분류는 서류 종류를 영문 분류 코드로 돌려주므로
# BRIEF 의 한국어 이름을 코드에 짝지어 비교한다(1~6쪽 순서·뜻이 같다 — 보고서 T1-impl.md).
EXPECTED_DOCUMENT_TYPES = {
    "loan_application": "대출신청서",
    "consent_form": "동의서",
    "income_proof": "소득금액증명",
    "power_of_attorney": "위임장",
    "debt_transaction": "채무내역",
    "Other": "기타",
}
EXPECTED_DOCUMENT_COUNT = 6
EXPECTED_EXTRACTED_COUNT = 5
EXPECTED_RISK_LEVEL = "상"
EXPECTED_FINAL_STAGE = "권장_조치"  # 위험도 상·중·하 → 권장_조치(BRIEF §4)
EXPECTED_OTHER_COUNT = 1  # '기타' 1개

# 조회 중 일시적 오류(연결 오류·5xx·429)를 몇 번까지 연달아 참을지
MAX_TRANSIENT_ERRORS = 5

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_MISMATCH = 2

# 출력에서 가릴 값 → 자리표시자(run 이 설정을 읽은 뒤 채운다)
_SECRETS: dict[str, str] = {}


# --- 출력 -------------------------------------------------------------------


def _setup_console() -> None:
    """Windows 콘솔·파이프에서 한글이 깨지지 않게 UTF-8, 줄 단위로 내보낸다."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace", line_buffering=True)


def _say(text: str = "") -> None:
    """모든 출력의 유일한 길 — 비밀값·인증 문구를 가린 뒤 내보낸다."""
    print(redact(text, _SECRETS))


def _fmt_elapsed(seconds: float) -> str:
    return f"{seconds:6.1f}s"


def _log(start: float | None, message: str) -> None:
    prefix = f"[{_fmt_elapsed(time.monotonic() - start)}] " if start is not None else ""
    _say(prefix + message)


# --- 환경 -------------------------------------------------------------------


def _read_env(root: Path) -> dict[str, str]:
    """루트 .env 를 읽고, 같은 이름의 OS 환경변수가 있으면 그쪽을 쓴다. 값은 출력하지 않는다."""
    values: dict[str, str] = {}
    env_path = root / ".env"
    if env_path.is_file():
        try:
            from dotenv import dotenv_values
        except ImportError:  # pragma: no cover - requirements-dev.txt 에 들어 있다
            raise SystemExit("python-dotenv 가 없습니다. requirements-dev.txt 를 설치하세요.") from None
        values.update({k: v for k, v in dotenv_values(env_path).items() if v is not None})
    for name in REQUIRED_UPSTAGE_ENV + ("UPSTAGE_BASE_URL",):
        if os.environ.get(name):
            values[name] = os.environ[name]
    return values


# --- 요약 -------------------------------------------------------------------


def _same_types(actual: Any, expected: Mapping[str, str]) -> bool:
    return isinstance(actual, list) and sorted(map(str, actual)) == sorted(expected)


def _labelled(codes: Any) -> Any:
    """분류 코드 옆에 기대값의 한국어 이름을 붙인다(모르는 코드는 그대로)."""
    if not isinstance(codes, list):
        return codes
    return [f"{c}({EXPECTED_DOCUMENT_TYPES[c]})" if c in EXPECTED_DOCUMENT_TYPES else str(c) for c in codes]


def print_summary(response: Mapping[str, Any]) -> int:
    """단계 목록·요약값·기대값 비교를 출력하고 종료 코드(0 일치 / 2 불일치)를 돌려준다."""
    stages = parse_stages(response)
    summary = summarize(stages)

    _say()
    _say("== 단계(output[].model, 순서대로) ==")
    if not stages:
        _say("  (output 이 비었습니다)")
    for index, stage in enumerate(stages, 1):
        data = stage["data"]
        kind = type(data).__name__
        add = stage["additional_values"]
        add_kind = "없음" if add is None else type(add).__name__
        extra = f"  content {len(stage['contents'])}개" if len(stage["contents"]) != 1 else ""
        _say(f"  {index:2d}. {stage['name']}  [{stage['key'] or '?'}]  status={stage['status']}  "
             f"data={kind}  additional_values={add_kind}{extra}")
    _say("  이름별 개수: " + ", ".join(f"{n}×{c}" for n, c in summary["stage_counts"].items()))

    _say()
    _say("== 요약 ==")
    _say(f"  단계 이름     : {summary['stage_names']}")
    _say(f"  서류 수       : {summary['document_count']}")
    _say(f"  서류 종류     : {_labelled(summary['document_types'])}")
    _say(f"  추출 서류 수  : {summary['extracted_document_count']}")
    _say(f"  위험도        : {summary['risk_level']}")
    _say(f"  마지막 단계   : {summary['final_stage']}")
    _say(f"  기타 서류 수  : {summary['other_document_count']}")

    checks = [
        ("서류 수", EXPECTED_DOCUMENT_COUNT, summary["document_count"],
         summary["document_count"] == EXPECTED_DOCUMENT_COUNT),
        ("서류 종류", _labelled(list(EXPECTED_DOCUMENT_TYPES)), _labelled(summary["document_types"]),
         _same_types(summary["document_types"], EXPECTED_DOCUMENT_TYPES)),
        ("추출 서류 수", EXPECTED_EXTRACTED_COUNT, summary["extracted_document_count"],
         summary["extracted_document_count"] == EXPECTED_EXTRACTED_COUNT),
        ("위험도", EXPECTED_RISK_LEVEL, summary["risk_level"],
         summary["risk_level"] == EXPECTED_RISK_LEVEL),
        ("마지막 단계", EXPECTED_FINAL_STAGE, summary["final_stage"],
         summary["final_stage"] == EXPECTED_FINAL_STAGE),
        ("기타 서류 수", EXPECTED_OTHER_COUNT, summary["other_document_count"],
         summary["other_document_count"] == EXPECTED_OTHER_COUNT),
    ]
    _say()
    _say("== 기대값 비교 ==")
    for label, expected, actual, ok in checks:
        _say(f"  {'일치  ' if ok else '불일치'} {label}: 기대 {expected} / 실제 {actual}")
    all_ok = all(ok for *_, ok in checks)
    _say(f"  결과: {'일치' if all_ok else '불일치'}")
    return EXIT_OK if all_ok else EXIT_MISMATCH


def _print_failure(response: Mapping[str, Any]) -> None:
    """실패 이유 — 공용 job_failure_message(가림·길이 제한)만 쓴다."""
    _say(f"  이유: {job_failure_message(response, _SECRETS)}")


# --- 실행 -------------------------------------------------------------------


def _transient(exc: UpstageError) -> bool:
    return exc.status_code is None or exc.status_code == 429 or exc.status_code >= 500


def _call_with_retry[T](start: float, label: str, fn: Callable[[], T], interval: float) -> T:
    """일시적 오류(연결·429·5xx)는 MAX_TRANSIENT_ERRORS 번까지 다시 시도한다."""
    errors = 0
    while True:
        try:
            return fn()
        except UpstageError as exc:
            errors += 1
            if not _transient(exc) or errors >= MAX_TRANSIENT_ERRORS:
                raise
            _log(start, f"{label} 일시 오류({errors}/{MAX_TRANSIENT_ERRORS}): {exc.message} — 다시 시도")
            time.sleep(interval)


def redact_secrets(value: Any, secrets: Mapping[str, str]) -> Any:
    """저장 전 가림 — 공용 redact_value(알려진 값 + 인증 문구). 응답 최상위 model 에 에이전트 id 가 온다."""
    return redact_value(value, secrets)


def _save(out_dir: Path, job_id: str, response: Mapping[str, Any], secrets: Mapping[str, str]) -> Path:
    """원본 응답을 tmp/ 에 저장한다(비밀값은 자리표시자로 가림, BRIEF §2)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", job_id)[:80] or "job"
    path = out_dir / f"{stamp}_{safe_id}.json"
    body = redact_secrets(response, secrets)
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def run(args: argparse.Namespace) -> int:
    file_path = (ROOT / args.file) if not Path(args.file).is_absolute() else Path(args.file)
    if not file_path.is_file():
        _say(f"파일이 없습니다: {args.file}")
        return EXIT_FAIL
    out_dir = (ROOT / args.out_dir) if not Path(args.out_dir).is_absolute() else Path(args.out_dir)

    try:
        settings = load_upstage_settings(_read_env(ROOT))
    except ConfigError as exc:
        _say(f"설정 오류: {exc}")
        return EXIT_FAIL

    secrets = upstage_secrets(settings.api_key, settings.agent_id)
    _SECRETS.clear()
    _SECRETS.update(secrets)
    content = file_path.read_bytes()
    mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    _say(f"파일: {_show_path(file_path)} ({len(content)} bytes, {mime_type})")
    _say(f"조회 간격 {args.interval}s, 제한 {args.timeout}s")

    start = time.monotonic()
    uploaded: dict[str, str] = {}  # 올린 파일 id(정리용)
    code = EXIT_FAIL
    cleaned = True
    with UpstageClient(settings.api_key, settings.base_url, project_id=settings.project_id) as client:
        try:
            code = _drive(client, settings, args, file_path.name, content, mime_type, out_dir, secrets, start, uploaded)
        except UpstageError as exc:
            _log(start, f"Upstage 오류: {exc.message}")
            code = EXIT_FAIL
        except KeyboardInterrupt:
            _log(start, "중단(Ctrl+C)")
            code = EXIT_FAIL
        except Exception as exc:  # 스크립트 버그 등 — 가린 짧은 문구만(원문 traceback 을 내지 않음)
            _log(start, _unexpected_error_line(exc))
            code = EXIT_FAIL
        finally:
            if "file_id" in uploaded:
                cleaned = _cleanup(client, uploaded["file_id"], start)
    # 올린 파일을 지우지 못했으면 결과와 상관없이 실패로 끝낸다(BRIEF §3)
    return code if cleaned else EXIT_FAIL


def _unexpected_error_line(exc: BaseException) -> str:
    """예상 못 한 예외의 진단 한 줄: 가림 → 개행을 공백으로 → MAX_MESSAGE(300)자로 자름."""
    where = traceback.extract_tb(exc.__traceback__)[-1] if exc.__traceback__ else None
    place = f" @ {Path(where.filename).name}:{where.lineno}" if where else ""
    text = redact(f"예상치 못한 오류({type(exc).__name__}{place}): {exc}", _SECRETS)
    text = re.sub(r"\s*[\r\n]+\s*", " ", text).strip()
    return redact(text, _SECRETS, limit=MAX_MESSAGE)


def _drive(
    client: UpstageClient,
    settings: UpstageSettings,
    args: argparse.Namespace,
    filename: str,
    content: bytes,
    mime_type: str,
    out_dir: Path,
    secrets: Mapping[str, str],
    start: float,
    uploaded: dict[str, str],
) -> int:
    """올리기 → 작업 만들기 → 조회 반복 → 저장·요약. 올린 파일 id 는 uploaded 에 넣는다."""
    file_id = client.upload_file(filename, content, mime_type)
    uploaded["file_id"] = file_id
    _log(start, f"파일 올림: file id {file_id}")

    job = client.create_job(settings.agent_id, settings.config_id, file_id)
    job_id = str(job["id"])
    status = job.get("status")
    _log(start, f"작업 만듦: job id {job_id}  상태 {status}")

    last_status = status
    while not is_terminal(status):
        if time.monotonic() - start > args.timeout:
            _log(start, f"시간 초과({args.timeout}s): 마지막 상태 {status}")
            return EXIT_FAIL
        time.sleep(args.interval)
        job = _call_with_retry(start, "조회", lambda: client.get_job(job_id, "last"), args.interval)
        status = job.get("status")
        if status != last_status:
            _log(start, f"상태 {last_status} → {status}")
            last_status = status

    elapsed = time.monotonic() - start
    _say()
    _say(f"job id   : {job_id}")
    _say(f"최종 상태: {status}")
    _say(f"걸린 시간: {elapsed:.1f}s (파일 올리기부터)")

    if not is_success(status):
        _say("작업이 성공하지 못했습니다.")
        _print_failure(job)
        saved = _save(out_dir, job_id, job, secrets)
        _say(f"마지막 응답 저장: {_show_path(saved)}")
        return EXIT_FAIL

    full = _call_with_retry(start, "전체 조회", lambda: client.get_job(job_id, "all"), args.interval)
    saved = _save(out_dir, job_id, full, secrets)
    _say(f"원본 저장: {_show_path(saved)}")
    return print_summary(full)


def _show_path(path: Path) -> Path:
    return path.relative_to(ROOT) if path.is_relative_to(ROOT) else path


def _cleanup(client: UpstageClient, file_id: str, start: float) -> bool:
    """올린 파일을 지우고 지워졌는지 확인한다. 예외를 밖으로 내지 않는다.

    지웠으면 True(조회로 확인할 수 없는 경우 포함), 지우지 못했거나 아직 남아 있으면 False.
    """
    _say()
    step = "삭제"
    try:
        deleted = client.delete_file(file_id)
        _log(start, f"Upstage 파일 삭제 요청: {'성공' if deleted else '실패(deleted=false)'}")
        step = "삭제 확인"
        exists = client.file_exists(file_id)
    except UpstageError as exc:
        _log(start, f"Upstage 파일 삭제 실패: {exc.message} — Studio 에서 직접 지워야 합니다(file id {file_id})")
        return False
    except KeyboardInterrupt:
        if step == "삭제":
            _log(start, f"삭제 중 중단 — Studio 에서 직접 지워야 합니다(file id {file_id})")
        else:
            _log(start, f"삭제 확인 중 중단 — 삭제 확인 못 함(Studio 에서 file id {file_id} 를 확인하세요)")
        return False
    verdict = {False: "확인됨(조회 404)", True: "아직 남아 있음", None: "확인 불가(조회 지원 안 함)"}[exists]
    _log(start, f"Upstage 파일 삭제 확인: {verdict}")
    return deleted and exists is not True


def summarize_only(path_text: str) -> int:
    path = Path(path_text)
    if not path.is_absolute():
        path = Path.cwd() / path
    try:
        response = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _say(f"저장 파일을 읽지 못했습니다: {type(exc).__name__}")
        return EXIT_FAIL
    if not isinstance(response, dict):
        _say("저장 파일 모양이 다릅니다(객체가 아님).")
        return EXIT_FAIL
    _say(f"저장 파일로 요약: {path.name}")
    _say(f"job id   : {response.get('id')}")
    _say(f"최종 상태: {response.get('status')}")
    if not is_success(response.get("status")):
        _print_failure(response)
        return EXIT_FAIL
    return print_summary(response)


def main(argv: list[str] | None = None) -> int:
    _setup_console()
    parser = argparse.ArgumentParser(description="Upstage 워크플로우 확인(합성 묶음 1회 실행)")
    parser.add_argument("--file", default=DEFAULT_FILE, help=f"올릴 파일(기본 {DEFAULT_FILE})")
    parser.add_argument("--interval", type=float, default=3.0, help="조회 간격 초(기본 3)")
    parser.add_argument("--timeout", type=float, default=600.0, help="전체 제한 초(기본 600)")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR, help=f"원본 저장 폴더(기본 {DEFAULT_OUT_DIR})")
    parser.add_argument("--summarize-only", metavar="JSON", help="저장해 둔 원본으로 요약만(네트워크 없음)")
    args = parser.parse_args(argv)
    if args.summarize_only:
        return summarize_only(args.summarize_only)
    if args.interval <= 0 or args.timeout <= 0:
        _say("--interval·--timeout 은 0보다 커야 합니다.")
        return EXIT_FAIL
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
