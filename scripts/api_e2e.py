# ==========================================================================
#  FastAPI 백엔드 끝까지 확인 스크립트 (로컬 uvicorn · 배포 사이트 공용)
#  브라우저가 할 일을 그대로 한다: health → 분석 만들기 → 서명 URL 로 Storage 에 올리기 → 시작
#  → 3초마다 조회(상태가 바뀔 때만 한 줄) → 결과 요약 또는 오류 → Upstage 파일 삭제 확인.
#
#  실행(저장소 루트에서, 먼저 uvicorn 을 띄운다):
#    .venv\Scripts\python.exe scripts\api_e2e.py [--base-url http://127.0.0.1:8000]
#        [--file testdocs/iMASK_smoke_bundle.pdf] [--name 분석명] [--interval 3] [--timeout 600]
#        [--skip-upload] [--content-file <올릴 실제 내용>] [--no-start] [--expect done|failed]
#    --skip-upload   : 올리지 않고 시작 → '업로드된 파일을 찾을 수 없습니다' 실패 경로(Upstage 호출 없음)
#    --content-file  : 이름·형식은 --file 로 알리고 내용은 이 파일로 올린다 → 형식 불일치 실패 경로
#    --no-start      : 만들기·올리기까지만(한글 파일 이름이 Storage 에 올라가는지 확인할 때)
#
#  비밀값(BRIEF §2): 접근 코드는 환경변수 IMASK_DEMO_CODE, 없으면 루트 .env 의 DEMO_ACCESS_CODE.
#    서명 URL·토큰·키는 출력하지 않는다(모든 출력은 _say() 를 지나며 알려진 값을 가린다).
#    배포 사이트의 Vercel 보호를 넘기려면 선택 환경변수 VERCEL_PROTECTION_BYPASS 를
#    x-vercel-protection-bypass 헤더로 보낸다.
#  올리기: .env 에 NEXT_PUBLIC_SUPABASE_URL·NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY 가 있으면 브라우저와 같이
#    공개 키 클라이언트의 upload_to_signed_url(path, token, …)로, 없으면 서명 URL 에 직접 PUT.
#  Upstage 실행 1번 = 크레딧 사용(BRIEF §3). 합성 자료만 올린다.
#  정리: 시간 초과·Ctrl+C·연결 오류·예상 못 한 예외를 포함한 모든 종료 경로의 finally 에서, 관찰한
#    Upstage file id 를 .env 의 UPSTAGE_API_KEY 로 지운다(404 = 이미 지움 = 성공). 시작한 분석이 끝나지 않았는데
#    file id 를 모르면(시작 응답을 받았어도) 분석을 한 번 다시 읽어 얻는다. 그래도 확인할 수 없거나 정리를 못 하면
#    값 없는 문구로 알리고 종료 코드 1.
#  출력의 오류 문구는 원문 전체를 가린 뒤에 자른다(_short).
#  종료 코드: 기대(--expect, 기본 done)대로면 0 — done 이면 서류 6·추출 5·위험도 상도 맞아야 한다. 아니면 1.
# ==========================================================================

from __future__ import annotations

import argparse
import mimetypes
import os
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from imask_backend.redaction import redact  # noqa: E402
from imask_backend.upstage import UpstageClient, UpstageError  # noqa: E402

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_FILE = "testdocs/iMASK_smoke_bundle.pdf"
TERMINAL = {"done", "partial", "failed"}
WITHIN_SECONDS = 180  # queued → running → done 기대 시간(3분)

# 합성 묶음 기대값(BRIEF §3)
EXPECTED_DOCUMENTS = 6
EXPECTED_EXTRACTED = 5
EXPECTED_RISK = "상"

EXIT_OK = 0
EXIT_FAIL = 1

_SECRETS: dict[str, str] = {}


def _setup_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace", line_buffering=True)


def _say(text: str = "") -> None:
    """모든 출력의 유일한 길 — 알려진 비밀값·서명 토큰·인증 문구를 가린다."""
    print(redact(text, _SECRETS))


def _hide(value: str | None, placeholder: str) -> None:
    if isinstance(value, str) and len(value) >= 4:
        _SECRETS[value] = placeholder


def _read_env() -> dict[str, str]:
    """루트 .env(있으면)를 읽는다. 값은 출력하지 않는다."""
    path = ROOT / ".env"
    if not path.is_file():
        return {}
    try:
        from dotenv import dotenv_values
    except ImportError:  # pragma: no cover - requirements-dev.txt 에 있다
        return {}
    return {k: v for k, v in dotenv_values(path).items() if isinstance(v, str)}


class Run:
    """한 번 실행의 상태. 정리(finally)에 쓰도록 분석 id·관찰한 Upstage file id 를 모은다."""

    def __init__(self, args: argparse.Namespace, env: Mapping[str, str], transport: httpx.BaseTransport | None = None):
        self.args = args
        self.env = env
        self.start = time.monotonic()
        code = os.environ.get("IMASK_DEMO_CODE") or env.get("DEMO_ACCESS_CODE") or ""
        _hide(code, "<DEMO_ACCESS_CODE>")
        headers = {"X-Demo-Code": code} if code else {}
        bypass = os.environ.get("VERCEL_PROTECTION_BYPASS")
        if bypass:
            _hide(bypass, "<VERCEL_PROTECTION_BYPASS>")
            headers["x-vercel-protection-bypass"] = bypass
        for name in ("UPSTAGE_API_KEY", "SUPABASE_SECRET_KEY", "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY"):
            _hide(env.get(name), f"<{name}>")
        _hide(os.environ.get("UPSTAGE_API_KEY"), "<UPSTAGE_API_KEY>")
        _hide(env.get("UPSTAGE_AGENT_ID"), "<UPSTAGE_AGENT_ID>")
        self.has_code = bool(code)
        self.http = httpx.Client(
            base_url=args.base_url.rstrip("/"),
            headers=headers,
            timeout=httpx.Timeout(90.0, connect=10.0),
            transport=transport,
        )
        # 정리용 실행 상태
        self.analysis_id: str | None = None
        self.start_requested = False
        self.start_row_received = False
        self.terminal = False
        self.file_ids: dict[str, None] = {}  # 순서 있는 집합

    def log(self, message: str) -> None:
        _say(f"[{time.monotonic() - self.start:6.1f}s] {message}")

    def call(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        response = self.http.request(method, path, **kwargs)
        return response

    def observe(self, row: Mapping[str, Any]) -> None:
        """응답의 분석 건에서 Upstage file id 와 끝났는지를 기억한다."""
        for doc in row.get("documents") or []:
            file_id = doc.get("upstage_file_id") if isinstance(doc, Mapping) else None
            if isinstance(file_id, str) and file_id:
                self.file_ids[file_id] = None
        self.terminal = row.get("status") in TERMINAL

    def upstage_key(self) -> str:
        return os.environ.get("UPSTAGE_API_KEY") or self.env.get("UPSTAGE_API_KEY") or ""

    def upstage_base(self) -> str:
        return self.env.get("UPSTAGE_BASE_URL") or "https://api.upstage.ai/v2"


def _short(text: Any) -> str:
    """원문 전체를 가린 **뒤에** 200자로 자른다(잘린 비밀값·토큰 조각이 남지 않게)."""
    return redact(text, _SECRETS, limit=200)


def _detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return _short(response.text)
    return _short(body.get("detail") if isinstance(body, dict) else body)


def _upload(run: Run, upload: Mapping[str, str], content: bytes, mime_type: str) -> bool:
    """서명 URL 로 올린다(브라우저 방식). 서명 URL·토큰은 출력하지 않는다."""
    _hide(upload.get("token"), "<SIGNED_TOKEN>")
    _hide(upload.get("signed_url"), "<SIGNED_URL>")
    url = run.env.get("NEXT_PUBLIC_SUPABASE_URL")
    key = run.env.get("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY")
    try:
        if url and key:
            from supabase import create_client

            client = create_client(url, key)
            client.storage.from_(upload["bucket"]).upload_to_signed_url(
                upload["path"], upload["token"], content, {"content-type": mime_type}
            )
            run.log(f"올리기 완료(공개 키 + 서명 토큰, uploadToSignedUrl 과 같은 방식): {upload['path']}")
        else:
            name = upload["path"].rsplit("/", 1)[-1]
            response = httpx.put(
                upload["signed_url"],
                files={"file": (name, content, mime_type)},
                data={"cacheControl": "3600"},
                timeout=60.0,
            )
            if not response.is_success:
                run.log(f"올리기 실패: HTTP {response.status_code} {_detail(response)}")
                return False
            run.log(f"올리기 완료(서명 URL 에 직접 PUT): {upload['path']}")
        return True
    except Exception as exc:  # 오류 문구는 원문 전체를 가린 뒤 한 줄로
        run.log(f"올리기 실패: {_short(f'{type(exc).__name__}: {exc}')}")
        return False


def _summary_ok(summary: Mapping[str, Any]) -> bool:
    return (
        summary.get("document_count") == EXPECTED_DOCUMENTS
        and summary.get("extracted_document_count") == EXPECTED_EXTRACTED
        and summary.get("risk_level") == EXPECTED_RISK
    )


def _check_upstage_files(run: Run, documents: list[Mapping[str, Any]]) -> bool | None:
    """(정상 종료 때) 서버가 Upstage 파일을 지웠는지(GET /files/{id} 404). 키가 없으면 None(확인 안 함)."""
    key = run.upstage_key()
    file_ids = [d.get("upstage_file_id") for d in documents if d.get("upstage_file_id")]
    if not file_ids:
        run.log("Upstage 파일 확인: 올린 파일 없음")
        return True
    if not key:
        run.log("Upstage 파일 확인: UPSTAGE_API_KEY 가 없어 건너뜀")
        return None
    _hide(key, "<UPSTAGE_API_KEY>")
    ok = True
    with UpstageClient(key, run.upstage_base()) as client:
        for file_id in file_ids:
            exists = client.file_exists(str(file_id))
            state = {True: "아직 있음", False: "지워짐(404)", None: "확인 실패"}.get(exists, "확인 실패")
            run.log(f"Upstage 파일 {file_id}: {state}")
            ok = ok and exists is False
    return ok


def _reread_for_cleanup(run: Run) -> bool:
    """정리에 필요한 file id 를 얻으려고 분석을 한 번 다시 읽는다. 상태·파일 여부를 확인했으면 True."""
    try:
        response = run.call("GET", f"/api/py/analyses/{run.analysis_id}")
    except httpx.HTTPError as exc:
        run.log(f"정리: 분석을 다시 읽지 못했습니다({type(exc).__name__})")
        return False
    if response.status_code != 200:
        run.log(f"정리: 분석을 다시 읽지 못했습니다(HTTP {response.status_code})")
        return False
    try:
        row = response.json()
    except ValueError:
        run.log("정리: 분석을 다시 읽었지만 응답 모양이 다릅니다")
        return False
    if not isinstance(row, Mapping):
        run.log("정리: 분석을 다시 읽었지만 응답 모양이 다릅니다")
        return False
    run.observe(row)
    # 끝났으면 서버가 정리했고, file id 가 있으면 여기서 지운다. 둘 다 아니면 시작이 서버에서 아직 돌거나
    # 응답이 일부만 왔을 수 있어 Upstage 에 파일이 남았는지 알 수 없다.
    return run.terminal or bool(run.file_ids)


def _cleanup(run: Run) -> bool:
    """모든 종료 경로의 finally — 이번 실행이 Upstage 에 남겼을 수 있는 파일을 지운다(404 = 성공).

    '시작 응답을 받았다'와 '정리에 필요한 file id 를 확보했다'는 다르다: 시작을 요청한 분석이 끝나지 않았고
    file id 도 모르면(응답을 받았더라도) 분석을 한 번 다시 읽어 확보한다. 그래도 상태·파일 여부를 확인할 수
    없으면 정리 성공으로 치지 않는다(False → 종료 코드 1). 정리를 못 해도 False.
    """
    if run.analysis_id is None or not run.start_requested:
        return True  # 시작하지 않았으면 Upstage 에 올린 것이 없다
    known = True
    if not run.terminal and not run.file_ids:
        known = _reread_for_cleanup(run)
        if not known:
            run.log("정리 확인 못 함: 시작한 분석이 Upstage 에 파일을 남겼는지 확인하지 못했습니다")
    if not run.file_ids:
        return known
    key = run.upstage_key()
    count = len(run.file_ids)
    if not key:
        if run.terminal:
            # 끝난 분석의 파일은 서버(조회)가 이미 지웠다
            run.log("정리: UPSTAGE_API_KEY 가 없어 건너뜀(끝난 분석의 파일은 서버가 지움)")
            return known
        run.log(f"정리 못 함: UPSTAGE_API_KEY 가 없어 Upstage 파일 {count}개를 지우지 못했습니다")
        return False
    _hide(key, "<UPSTAGE_API_KEY>")
    ok = True
    with UpstageClient(key, run.upstage_base()) as client:
        for file_id in run.file_ids:
            try:
                if not client.delete_file(file_id):
                    run.log(f"정리 못 함: Upstage 파일 {file_id} 삭제가 거절됐습니다")
                    ok = False
            except UpstageError as exc:
                # 바깥 문구는 내보내지 않는다(클라이언트가 이미 잘랐을 수 있어서) — 상태 코드만
                shown = f"HTTP {exc.status_code}" if exc.status_code else "연결 오류"
                run.log(f"정리 못 함: Upstage 파일 {file_id}: {shown}")
                ok = False
    if ok:
        run.log(f"정리: Upstage 파일 {count}개 삭제 요청 완료(이미 지워졌으면 404 = 성공)")
    return ok and known


def _flow(run: Run, args: argparse.Namespace) -> int:
    file_path = (ROOT / args.file) if not Path(args.file).is_absolute() else Path(args.file)
    filename = file_path.name
    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    content_path = Path(args.content_file) if args.content_file else file_path
    content = content_path.read_bytes()
    _say(f"대상: {args.base_url} · 파일 {filename}({mime_type}) · 올릴 내용 {content_path.name} {len(content):,} bytes")
    _say(f"기대: {args.expect}" + (" · 올리지 않음" if args.skip_upload else "") + (" · 시작하지 않음" if args.no_start else ""))
    if not run.has_code:
        _say("접근 코드가 없습니다(IMASK_DEMO_CODE 또는 .env 의 DEMO_ACCESS_CODE).")
        return EXIT_FAIL

    # 1. health
    health = run.call("GET", "/api/py/health")
    run.log(f"health: HTTP {health.status_code} {health.json() if health.is_success else _detail(health)}")
    if not health.is_success:
        return EXIT_FAIL

    # 2. 만들기
    body: dict[str, Any] = {"filename": filename, "size": len(content), "mime_type": mime_type}
    if args.name is not None:
        body["name"] = args.name
    created = run.call("POST", "/api/py/analyses", json=body)
    if created.status_code != 201:
        run.log(f"만들기 실패: HTTP {created.status_code} {_detail(created)}")
        return EXIT_FAIL
    payload = created.json()
    analysis = payload["analysis"]
    upload = payload["upload"]
    analysis_id = analysis["id"]
    run.analysis_id = analysis_id
    t_queued = time.monotonic()
    leaked = [k for k in ("agent_id", "storage_path") if k in created.text]
    run.log(f"만들기: HTTP 201 id={analysis_id} 상태={analysis['status']} 이름={analysis['name']!r}")
    run.log(f"  문서 이름={analysis['documents'][0]['filename']!r} → Storage 경로 {upload['path']}")
    if leaked:
        run.log(f"  응답에 들어가면 안 되는 키: {leaked}")
        return EXIT_FAIL

    # 3. 올리기
    if args.skip_upload:
        run.log("올리기 건너뜀(--skip-upload)")
    elif not _upload(run, upload, content, mime_type):
        return EXIT_FAIL
    if args.no_start:
        run.log("시작하지 않고 끝냄(--no-start)")
        _say(f"분석 id: {analysis_id}")
        return EXIT_OK

    # 4. 시작
    run.start_requested = True
    started = run.call("POST", f"/api/py/analyses/{analysis_id}/start")
    if started.status_code != 200:
        run.log(f"시작 실패: HTTP {started.status_code} {_detail(started)}")
        return EXIT_FAIL
    row = started.json()
    run.start_row_received = True
    run.observe(row)
    t_running = time.monotonic() if row["status"] == "running" else None
    run.log(f"시작: HTTP 200 상태={row['status']} job={row.get('upstage_job_id')}" + (f" 오류={row['error']!r}" if row.get("error") else ""))

    # 5. 조회
    seen = (row["status"], row.get("upstage_status"), row.get("poll_error"))
    deadline = time.monotonic() + args.timeout
    while row["status"] not in TERMINAL:
        if time.monotonic() > deadline:
            run.log(f"시간 초과({args.timeout}s) — 마지막 상태 {row['status']}")
            return EXIT_FAIL
        time.sleep(args.interval)
        polled = run.call("GET", f"/api/py/analyses/{analysis_id}")
        if polled.status_code != 200:
            run.log(f"조회 실패: HTTP {polled.status_code} {_detail(polled)}")
            continue
        row = polled.json()
        run.observe(row)
        state = (row["status"], row.get("upstage_status"), row.get("poll_error"))
        if state != seen:
            extra = f" upstage={row.get('upstage_status')}" if row.get("upstage_status") else ""
            extra += f" poll_error={row['poll_error']!r}" if row.get("poll_error") else ""
            run.log(f"조회: 상태={row['status']}{extra}")
            seen = state
    t_end = time.monotonic()

    # 6. 결과
    _say(f"분석 id: {analysis_id}")
    _say(f"job id: {row.get('upstage_job_id')}")
    _say(f"최종 상태: {row['status']}")
    ok = row["status"] == args.expect
    if row["status"] == "done":
        result = row.get("result") or {}
        summary = result.get("summary") or {}
        _say(f"결과 형식: {result.get('format')} · 키 {sorted(result)}(response 없음: {'response' not in result})")
        _say(f"  서류 수: {summary.get('document_count')}")
        _say(f"  서류 종류: {summary.get('document_types')}")
        _say(f"  추출된 서류 수: {summary.get('extracted_document_count')}")
        _say(f"  위험도: {summary.get('risk_level')}")
        _say(f"  마지막 단계: {summary.get('final_stage')}")
        _say(f"  기타 서류 수: {summary.get('other_document_count')}")
        _say(f"  단계 이름: {summary.get('stage_names')}")
        expected = _summary_ok(summary)
        _say(f"  기대값(서류 {EXPECTED_DOCUMENTS}·추출 {EXPECTED_EXTRACTED}·위험도 {EXPECTED_RISK}): {'일치' if expected else '불일치'}")
        ok = ok and expected and "response" not in result
    else:
        _say(f"오류 문구: {row.get('error')!r}")
        ok = ok and bool(row.get("error"))

    files_ok = _check_upstage_files(run, row.get("documents") or [])
    if files_ok is False:
        ok = False

    if t_running is not None and row["status"] == "done":
        total = t_end - t_queued
        _say(f"queued → running → done: {total:.1f}s ({'3분 안' if total <= WITHIN_SECONDS else '3분 넘음'})")
    _say(f"결과: {'기대대로' if ok else '기대와 다름'} (기대 {args.expect})")
    return EXIT_OK if ok else EXIT_FAIL


def run_e2e(args: argparse.Namespace, *, transport: httpx.BaseTransport | None = None) -> int:
    """_flow 를 돌리고, 어떻게 끝나든(시간 초과·Ctrl+C·연결 오류·예상 못 한 예외) finally 에서 정리한다."""
    env = _read_env()
    run = Run(args, env, transport=transport)
    code = EXIT_FAIL
    cleaned = False
    try:
        try:
            code = _flow(run, args)
        except KeyboardInterrupt:
            _say("중단됨(Ctrl+C)")
        except httpx.HTTPError as exc:
            _say(f"연결 오류: {type(exc).__name__}")
        except Exception as exc:
            _say(f"예상 못 한 오류: {_short(f'{type(exc).__name__}: {exc}')}")
    finally:
        try:
            cleaned = _cleanup(run)
        except KeyboardInterrupt:
            _say("정리 중 중단됨(Ctrl+C) — Upstage 파일을 지웠는지 확인하지 못했습니다")
        except Exception as exc:
            _say(f"정리 중 오류: {_short(type(exc).__name__)} — Upstage 파일을 지웠는지 확인하지 못했습니다")
        run.http.close()
    if not cleaned:
        _say("정리를 끝내지 못해 실패로 끝냅니다")
        return EXIT_FAIL
    return code


def main(argv: list[str] | None = None, *, transport: httpx.BaseTransport | None = None) -> int:
    _setup_console()
    parser = argparse.ArgumentParser(description="iMASK FastAPI 백엔드 끝까지 확인")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--file", default=DEFAULT_FILE, help="이름·형식을 알릴 파일(기본 합성 묶음)")
    parser.add_argument("--name", default=None, help="분석명(없으면 서버가 파일 이름을 쓴다)")
    parser.add_argument("--interval", type=float, default=3.0)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--skip-upload", action="store_true", help="올리지 않고 시작(실패 경로)")
    parser.add_argument("--content-file", default=None, help="실제로 올릴 내용(형식 불일치 실패 경로)")
    parser.add_argument("--no-start", action="store_true", help="만들기·올리기까지만")
    parser.add_argument("--expect", choices=("done", "failed"), default="done")
    args = parser.parse_args(argv)
    try:
        return run_e2e(args, transport=transport)
    except KeyboardInterrupt:  # 정리 바깥(설정 읽기 등)에서의 중단
        _say("중단됨(Ctrl+C)")
        return EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
