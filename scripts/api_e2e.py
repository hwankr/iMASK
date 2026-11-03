# ==========================================================================
#  FastAPI 백엔드 끝까지 확인 스크립트 (로컬 uvicorn · 배포 사이트 공용)
#  브라우저가 할 일을 그대로 한다: health → 분석 만들기 → 서명 URL 로 Storage 에 올리기 → 시작
#  → 3초마다 조회(상태가 바뀔 때만 한 줄) → 결과 요약 또는 오류 → Upstage 파일 삭제 확인.
#
#  실행(저장소 루트에서, 먼저 uvicorn 을 띄운다):
#    .venv\Scripts\python.exe scripts\api_e2e.py [--base-url http://127.0.0.1:8000]
#        [--file testdocs/iMASK_smoke_bundle.pdf] [--name 분석명] [--interval 3] [--timeout 600]
#        [--skip-upload] [--content-file <올릴 실제 내용>] [--no-start] [--expect done|failed]
#        [--analysis-id <이미 있는 분석 id>]
#    --skip-upload   : 올리지 않고 시작 → '업로드된 파일을 찾을 수 없습니다' 실패 경로(Upstage 호출 없음)
#    --content-file  : 이름·형식은 --file 로 알리고 내용은 이 파일로 올린다 → 형식 불일치 실패 경로
#    --no-start      : 만들기·올리기까지만(한글 파일 이름이 Storage 에 올라가는지 확인할 때)
#    --analysis-id   : 만들기·올리기·시작 없이(**Upstage 작업을 만들지 않음**) 그 분석을 조회해 아래 done 확인과
#                      원본 파일 확인만 한다. 비교할 원본은 --file(기본 합성 묶음). 코드를 고친 뒤 재확인용.
#  done 확인(T1 findings-api): 요약(서류 6·추출 5·상) + 화면용 결과 — findings 29·boxes 있는 항목 28·
#    documents 6(kind extracted 5·other 1, other 에 other_guide·extracted 에 validation)·overall 상/권장_조치·
#    risk 분포(허용 값·risk_source 와 맞는지만 — unrated 를 강제하지 않음)·계약 키·id 중복·document_index·
#    boxes 0~1, 기본 응답에 stages·response 없음, 응답 크기(기본 GET vs ?include=stages GET 바이트 — 기본이 작아야 함).
#    원본 파일: GET /analyses/{id}/file 200·키 {url, mime_type, filename} → url 로(접근 코드 없이) 받아 올린 내용과
#    sha256 비교. 원문 값(value·masked)·서명 URL 은 출력하지 않는다(개수·분포·바이트 수만).
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
#  종료 코드: 기대(--expect, 기본 done)대로면 0 — done 이면 위 done 확인과 원본 파일 확인도 모두 맞아야 한다. 아니면 1.
# ==========================================================================

from __future__ import annotations

import argparse
import hashlib
import mimetypes
import os
import sys
import time
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from imask_backend.fields import CATS, EXPOSURES, SUBJECTS  # noqa: E402
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
EXPECTED_FINDINGS = 29
EXPECTED_BOXED = 28  # 3쪽 소득 정보 하나는 위치(page)를 못 찾아 좌표가 없다
EXPECTED_NEXT_STAGE = "권장_조치"
EXPECTED_KINDS = {"extracted": 5, "other": 1}

# 공통 계약(BRIEF §5)
DOCUMENT_KEYS = {"index", "type", "page_start", "page_end", "kind", "other_guide", "validation"}
FINDING_KEYS = {
    "id",
    "document_index",
    "field",
    "category",
    "label",
    "subject",
    "mapping_status",
    "value",
    "masked",
    "exposure",
    "risk",
    "risk_source",
    "risk_reason",
    "page",
    "boxes",
    "confidence",
}
OVERALL_KEYS = {"level", "text", "next_stage", "next_text"}
FILE_KEYS = {"url", "mime_type", "filename"}
RISKS = ("high", "medium", "low", "unrated")

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
        self.transport = transport  # 원본 파일 받기(접근 코드 없는 클라이언트)도 같은 전송층을 쓴다(테스트)
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

    def upstage_project(self) -> str | None:
        """에이전트가 속한 Upstage 프로젝트(x-project-id) — 서버가 그 프로젝트에 올린 파일을 확인·정리하려면 같아야 한다."""
        value = os.environ.get("UPSTAGE_PROJECT_ID") or self.env.get("UPSTAGE_PROJECT_ID") or ""
        return value.strip() or None


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


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _box_ok(box: Any) -> bool:
    if not isinstance(box, list) or len(box) != 4:
        return False
    for point in box:
        if not isinstance(point, Mapping) or set(point) != {"x", "y"}:
            return False
        for v in point.values():
            if not isinstance(v, (int, float)) or isinstance(v, bool) or not 0.0 <= v <= 1.0:
                return False
    return True


def _finding_problems(f: Any, doc_indexes: set[Any]) -> list[str]:
    """탐지 항목 하나의 계약 위반(값은 넣지 않고 id·키 이름만)."""
    if not isinstance(f, Mapping):
        return ["finding: 객체가 아님"]
    where = f"finding {str(f.get('id'))[:60]}"
    if set(f) != FINDING_KEYS:
        return [f"{where}: 키가 계약과 다름 {sorted(set(f) ^ FINDING_KEYS)}"]
    value, shown = f["value"], f["masked"]
    checks = [
        (f["id"] == f"{f['document_index']}:{f['field']}", "id 꼴"),
        (f["document_index"] in doc_indexes, "document_index 가 documents 에 없음"),
        (f["category"] in CATS, "category"),
        (f["subject"] in SUBJECTS, "subject"),
        (f["mapping_status"] in ("ok", "needs_review", "unknown"), "mapping_status"),
        (isinstance(value, str) and bool(value.strip()), "value"),
        (isinstance(shown, str) and isinstance(value, str) and len(shown) == len(value), "masked 길이"),
        (f["exposure"] in EXPOSURES, "exposure"),
        (f["risk"] in RISKS, "risk"),
        ((f["risk"] == "unrated") == (f["risk_source"] is None), "risk 와 risk_source"),
        (f["risk_source"] in ("workflow", None), "risk_source"),
        (f["risk_reason"] is None or isinstance(f["risk_reason"], str), "risk_reason"),
        (f["page"] is None or (_is_int(f["page"]) and f["page"] >= 1), "page"),
        (isinstance(f["boxes"], list) and all(_box_ok(b) for b in f["boxes"]), "boxes 0~1"),
        (f["page"] is not None or f["boxes"] == [], "page 없는데 boxes 있음"),
        (f["confidence"] in ("high", "low", None), "confidence"),
    ]
    return [f"{where}: {name}" for passed, name in checks if not passed]


def _document_problems(doc: Any) -> list[str]:
    if not isinstance(doc, Mapping) or set(doc) != DOCUMENT_KEYS:
        diff = sorted(set(doc) ^ DOCUMENT_KEYS) if isinstance(doc, Mapping) else "객체가 아님"
        return [f"document: 키가 계약과 다름 {diff}"]
    where = f"document {str(doc.get('index'))[:20]}"
    start, end = doc["page_start"], doc["page_end"]
    checks = [
        (_is_int(doc["index"]), "index"),
        (doc["kind"] in ("extracted", "other"), "kind"),
        ((start is None and end is None) or (_is_int(start) and _is_int(end) and 1 <= start <= end), "page_start·page_end"),
        (all(doc[k] is None or isinstance(doc[k], str) for k in ("type", "other_guide", "validation")), "type·other_guide·validation"),
    ]
    return [f"{where}: {name}" for passed, name in checks if not passed]


def _view_problems(result: Mapping[str, Any]) -> list[str]:
    """documents·findings·overall 의 계약 위반 목록(값 없이 위치·키 이름만)."""
    documents, findings, overall = result.get("documents"), result.get("findings"), result.get("overall")
    if not isinstance(documents, list) or not isinstance(findings, list) or not isinstance(overall, Mapping):
        return ["documents·findings·overall 모양이 다름"]
    problems = [p for doc in documents for p in _document_problems(doc)]
    indexes = [d.get("index") for d in documents if isinstance(d, Mapping)]
    if len(set(map(str, indexes))) != len(indexes):
        problems.append("document index 가 겹침")
    doc_indexes = {i for i in indexes if _is_int(i)}
    problems += [p for finding in findings for p in _finding_problems(finding, doc_indexes)]
    ids = [str(f.get("id")) for f in findings if isinstance(f, Mapping)]
    if len(set(ids)) != len(ids):
        problems.append("finding id 가 겹침")
    if set(overall) != OVERALL_KEYS:
        problems.append(f"overall: 키가 계약과 다름 {sorted(set(overall) ^ OVERALL_KEYS)}")
        return problems
    if overall["level"] not in ("상", "중", "하", "검토 필요", None):
        problems.append("overall.level")
    if overall["next_stage"] not in ("권장_조치", "검토_안내", None):
        problems.append("overall.next_stage")
    if not isinstance(overall["text"], str) or not isinstance(overall["next_text"], str):
        problems.append("overall.text·next_text")
    return problems


def _mark(passed: bool) -> str:
    return "일치" if passed else "불일치"


def _get(run: Run, analysis_id: str, params: Mapping[str, str] | None = None) -> tuple[httpx.Response, Any]:
    response = run.call("GET", f"/api/py/analyses/{analysis_id}", params=params)
    try:
        body = response.json()
    except ValueError:
        body = None
    return response, body


def _print_summary(result: Mapping[str, Any]) -> bool:
    summary = result.get("summary") if isinstance(result.get("summary"), Mapping) else {}
    no_raw = "response" not in result and "stages" not in result
    _say(f"결과 형식: {result.get('format')} · 키 {sorted(result)}(response·stages 없음: {no_raw})")
    _say(f"  서류 수: {summary.get('document_count')}")
    _say(f"  서류 종류: {summary.get('document_types')}")
    _say(f"  추출된 서류 수: {summary.get('extracted_document_count')}")
    _say(f"  위험도: {summary.get('risk_level')}")
    _say(f"  마지막 단계: {summary.get('final_stage')}")
    _say(f"  기타 서류 수: {summary.get('other_document_count')}")
    _say(f"  단계 이름: {summary.get('stage_names')}")
    expected = _summary_ok(summary)
    _say(f"  기대값(서류 {EXPECTED_DOCUMENTS}·추출 {EXPECTED_EXTRACTED}·위험도 {EXPECTED_RISK}): {_mark(expected)}")
    return expected and no_raw


def _print_view(result: Mapping[str, Any]) -> bool:
    """화면용 결과의 개수·분포만 출력한다(value·masked·본문은 출력하지 않음)."""
    documents = [d for d in result.get("documents") or [] if isinstance(d, Mapping)]
    findings = [f for f in result.get("findings") or [] if isinstance(f, Mapping)]
    overall = result.get("overall") if isinstance(result.get("overall"), Mapping) else {}
    others = [d for d in documents if d.get("kind") == "other"]
    extracted = [d for d in documents if d.get("kind") == "extracted"]
    kinds = dict(Counter(str(d.get("kind")) for d in documents))
    guides = sum(1 for d in others if d.get("other_guide"))
    validations = sum(1 for d in extracted if d.get("validation"))
    docs_ok = (
        len(documents) == EXPECTED_DOCUMENTS
        and kinds == EXPECTED_KINDS
        and guides == len(others)
        and validations == len(extracted)
    )
    boxed = sum(1 for f in findings if f.get("boxes"))
    counts_ok = len(findings) == EXPECTED_FINDINGS and boxed == EXPECTED_BOXED
    overall_ok = overall.get("level") == EXPECTED_RISK and overall.get("next_stage") == EXPECTED_NEXT_STAGE
    text, next_text = overall.get("text"), overall.get("next_text")
    _say("화면용 결과(documents·findings·overall):")
    _say(
        f"  documents: {len(documents)} · kind {kinds} · other_guide 있음 {guides}/{len(others)}"
        f" · validation 있음 {validations}/{len(extracted)} (기대 {EXPECTED_DOCUMENTS} · {EXPECTED_KINDS}): {_mark(docs_ok)}"
    )
    _say(f"  findings: {len(findings)} · boxes 있는 항목 {boxed} (기대 {EXPECTED_FINDINGS} · {EXPECTED_BOXED}): {_mark(counts_ok)}")
    _say(f"  risk 분포: {dict(Counter(str(f.get('risk')) for f in findings))}")
    _say(f"  risk_source 분포: {dict(Counter(str(f.get('risk_source')) for f in findings))}")
    _say(f"  exposure 분포: {dict(Counter(str(f.get('exposure')) for f in findings))}")
    _say(f"  mapping_status 분포: {dict(Counter(str(f.get('mapping_status')) for f in findings))}")
    _say(f"  confidence 분포: {dict(Counter(str(f.get('confidence')) for f in findings))}")
    _say(f"  서류별 항목 수: {dict(Counter(f.get('document_index') for f in findings))}")
    _say(
        f"  overall: level={overall.get('level')} · next_stage={overall.get('next_stage')}"
        f" · text {len(text) if isinstance(text, str) else '?'}자 · next_text {len(next_text) if isinstance(next_text, str) else '?'}자"
        f" (기대 {EXPECTED_RISK} · {EXPECTED_NEXT_STAGE}): {_mark(overall_ok)}"
    )
    problems = _view_problems(result)
    _say(f"  계약 모양(키·허용 값·id 중복·document_index·boxes 0~1): {'맞음' if not problems else f'문제 {len(problems)}개'}")
    for problem in problems[:10]:
        _say(f"    - {_short(problem)}")
    return docs_ok and counts_ok and overall_ok and not problems


def _verify_done(run: Run, analysis_id: str) -> bool:
    """done 분석을 다시 읽어(기본·?include=stages) 요약·화면용 결과·응답 크기를 확인한다. done 조회는 Upstage 를 부르지 않는다."""
    plain, row = _get(run, analysis_id)
    if plain.status_code != 200 or not isinstance(row, Mapping):
        run.log(f"done 확인: 조회 실패 HTTP {plain.status_code} {_detail(plain)}")
        return False
    if row.get("status") != "done":
        run.log(f"done 확인: 상태가 done 이 아님({row.get('status')})")
        return False
    result = row.get("result") if isinstance(row.get("result"), Mapping) else {}
    ok = _print_summary(result)
    ok = _print_view(result) and ok

    staged, staged_row = _get(run, analysis_id, {"include": "stages"})
    staged_result = staged_row.get("result") if isinstance(staged_row, Mapping) else None
    has_stages = isinstance(staged_result, Mapping) and isinstance(staged_result.get("stages"), list)
    no_response = isinstance(staged_result, Mapping) and "response" not in staged_result
    small, big = len(plain.content), len(staged.content)
    ratio = f"{small / big:.1%}" if big else "?"
    size_ok = staged.status_code == 200 and has_stages and no_response and small < big
    _say(
        f"응답 크기: 기본 GET {small:,} bytes · ?include=stages GET {big:,} bytes(HTTP {staged.status_code}) · 기본이 {ratio}"
        f" · include=stages 에 stages 있음 {has_stages}·response 없음 {no_response}: {_mark(size_ok)}"
    )
    return ok and size_ok


def _check_file(run: Run, analysis_id: str, content: bytes) -> bool:
    """원본 파일 주소를 받아 그 주소로(접근 코드 없이) 내려받고 올린 내용과 sha256 을 비교한다. URL 은 출력하지 않는다."""
    response = run.call("GET", f"/api/py/analyses/{analysis_id}/file")
    if response.status_code != 200:
        run.log(f"원본 파일: HTTP {response.status_code} {_detail(response)}")
        return False
    try:
        body = response.json()
    except ValueError:
        body = None
    if not isinstance(body, Mapping):
        run.log("원본 파일: 응답 모양이 다름")
        return False
    url = body.get("url")
    if isinstance(url, str):
        _hide(url, "<SIGNED_DOWNLOAD_URL>")
    keys_ok = set(body) == FILE_KEYS and isinstance(url, str) and url.startswith(("https://", "http://"))
    no_store = "no-store" in response.headers.get("cache-control", "")
    run.log(
        f"원본 파일: HTTP 200 · 키 {sorted(body)}({_mark(keys_ok)}) · mime_type={body.get('mime_type')}"
        f" · filename={body.get('filename')!r} · Cache-Control no-store: {no_store}"
    )
    if not keys_ok:
        return False
    try:
        with httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0), transport=run.transport) as plain:
            downloaded = plain.get(url)
    except httpx.HTTPError as exc:
        run.log(f"원본 파일 받기 실패: {type(exc).__name__}")
        return False
    if downloaded.status_code != 200:
        run.log(f"원본 파일 받기 실패: HTTP {downloaded.status_code}")
        return False
    same = hashlib.sha256(downloaded.content).digest() == hashlib.sha256(content).digest()
    run.log(f"원본 파일 받기(접근 코드 없이): HTTP 200 · {len(downloaded.content):,} bytes · 올린 내용과 sha256 {_mark(same)}")
    return same and no_store


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
    with UpstageClient(key, run.upstage_base(), project_id=run.upstage_project()) as client:
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
    with UpstageClient(key, run.upstage_base(), project_id=run.upstage_project()) as client:
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
    role = "비교할 원본" if args.analysis_id else "올릴 내용"
    _say(f"대상: {args.base_url} · 파일 {filename}({mime_type}) · {role} {content_path.name} {len(content):,} bytes")
    if not run.has_code:
        _say("접근 코드가 없습니다(IMASK_DEMO_CODE 또는 .env 의 DEMO_ACCESS_CODE).")
        return EXIT_FAIL
    if args.analysis_id:
        return _flow_existing(run, args.analysis_id, content)
    _say(f"기대: {args.expect}" + (" · 올리지 않음" if args.skip_upload else "") + (" · 시작하지 않음" if args.no_start else ""))

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
        # 끝난 분석을 다시 읽어 확인한다(done 조회는 Upstage 를 부르지 않는다)
        ok = _verify_done(run, analysis_id) and ok
        ok = _check_file(run, analysis_id, content) and ok
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


def _flow_existing(run: Run, analysis_id: str, content: bytes) -> int:
    """--analysis-id: 만들기·올리기·시작 없이 조회·원본 파일 확인만(Upstage 작업을 만들지 않는다).

    start_requested 가 False 라 정리 단계는 아무것도 지우지 않는다.
    """
    run.analysis_id = analysis_id
    _say(f"기존 분석 확인(만들기·올리기·시작 없음, Upstage 작업 없음): {analysis_id}")
    health = run.call("GET", "/api/py/health")
    run.log(f"health: HTTP {health.status_code} {health.json() if health.is_success else _detail(health)}")
    if not health.is_success:
        return EXIT_FAIL
    done_ok = _verify_done(run, analysis_id)
    file_ok = _check_file(run, analysis_id, content)
    ok = done_ok and file_ok
    _say(f"분석 id: {analysis_id}")
    _say(f"결과: {'기대대로' if ok else '기대와 다름'} (기존 분석 확인)")
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
    parser.add_argument(
        "--analysis-id",
        default=None,
        help="이미 있는 분석을 조회하고 원본 파일만 확인(만들기·올리기·시작 없음 — Upstage 작업을 만들지 않음)",
    )
    args = parser.parse_args(argv)
    try:
        return run_e2e(args, transport=transport)
    except KeyboardInterrupt:  # 정리 바깥(설정 읽기 등)에서의 중단
        _say("중단됨(Ctrl+C)")
        return EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
