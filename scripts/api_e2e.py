# ==========================================================================
#  FastAPI 백엔드 끝까지 확인 스크립트 (로컬 uvicorn · 배포 사이트 공용)
#  브라우저가 할 일을 그대로 한다: health → 분석 만들기 → 서명 URL 로 Storage 에 올리기 → 시작
#  → 3초마다 조회(상태가 바뀔 때만 한 줄) → 결과 요약 또는 오류 → Upstage 파일 삭제 확인.
#
#  실행(저장소 루트에서, 먼저 uvicorn 을 띄운다):
#    .venv\Scripts\python.exe scripts\api_e2e.py [--base-url http://127.0.0.1:8000]
#        [--file testdocs/iMASK_smoke_bundle.pdf] [--name 분석명] [--interval 3] [--timeout 600]
#        [--skip-upload] [--content-file <올릴 실제 내용>] [--no-start] [--expect done|failed]
#        [--analysis-id <이미 있는 분석 id>] [--no-review]
#    --skip-upload   : 올리지 않고 시작 → '업로드된 파일을 찾을 수 없습니다' 실패 경로(Upstage 호출 없음)
#    --content-file  : 이름·형식은 --file 로 알리고 내용은 이 파일로 올린다 → 형식 불일치 실패 경로
#    --no-start      : 만들기·올리기까지만(한글 파일 이름이 Storage 에 올라가는지 확인할 때)
#    --analysis-id   : 만들기·올리기·시작 없이(**Upstage 작업을 만들지 않음**) 그 분석을 조회해 아래 done 확인과
#                      원본 파일 확인, 검토 기록 모양 확인만 한다(**읽기만 — 검토 동작을 보내지 않음**).
#                      비교할 원본은 --file(기본 합성 묶음). 코드를 고친 뒤 재확인용.
#    --no-review     : 검토 동작 확인(아래)을 끈다(--analysis-id 에서는 검토 기록 모양 확인을 끈다).
#  done 확인(T1 findings-api): 요약(서류 6·추출 5·상) + 화면용 결과 — findings 29·boxes 있는 항목 28·
#    documents 6(kind extracted 5·other 1, other 에 other_guide·extracted 에 validation)·overall 상/권장_조치·
#    risk 분포(허용 값·risk_source 와 맞는지만 — unrated 를 강제하지 않음)·계약 키·id 중복·document_index·
#    boxes 0~1, 기본 응답에 stages·response 없음, 응답 크기(기본 GET vs ?include=stages GET 바이트 — 기본이 작아야 함).
#    원본 파일: GET /analyses/{id}/file 200·키 {url, mime_type, filename} → url 로(사용자 지정 헤더 없이) 받아 올린 내용과
#    sha256 비교. 원문 값(value·masked)·서명 URL 은 출력하지 않는다(개수·분포·바이트 수만).
#  검토 동작 확인(review-actions, 기본 켬): **이번 실행이 만든 분석이 done 이 된 뒤에만** POST /analyses/{id}/review-actions 를
#    차례로 보낸다(actor api_e2e, 글은 이 스크립트가 만든 합성 문구). 처음 조회(needed·version 0·findings {}·이력 S1·S2)
#    → 확인 → 확인 취소 → 2건 한꺼번에 확인 → 같은 항목 다시 확인 409(상태 불일치) → 오탐 표시 → 오탐 취소(→ 미확인)
#    → 분류 수정(정보 종류) → 같은 값 분류 수정(changed false·이력 없음) → 오탐 표시 → 오탐 취소(→ 분류 수정)
#    → 항목 메모 저장·삭제 → 검토 메모 → 검토 완료(남은 미확인 수가 문구에) → 잠김 409·이미 완료 409 → 다시 열기
#    (reviewer·completion_note 남음, reviewed_at null) → 400 두 가지(모르는 type, 501자 글).
#    단계마다 응답 상태·changed·review 값·새 이력 줄(id H{version}·actor·kind·target·change·reason)을 보고 GET 으로 다시
#    읽어 같은지 확인한다(오류 단계는 다시 읽은 review 가 그대로인지 = 쓰기 없음). 마지막에 이력 id H1…Hn 연속,
#    at 이 줄어들지 않음, 저장 줄 수 = 쓴 동작 수 = version, 분석 created_at·updated_at 이 처음 조회와 같음(분석 시각·
#    걸린 시간 불변). 출력은 단계 이름·통과/실패·개수만. 기대 문구는 계약(데모 코어와 같은 전이·문구)을 그대로 적은 것이다.
#    기대값도 계약대로 따로 만든다(백엔드 함수를 쓰지 않음): 표시 이름·위험등급은 JavaScript trim() 공백 집합(_js_trim —
#    U+FEFF 는 지우고 U+0085·U+001C~001F 는 두는 화면 기준), 이력 target 은 저장 안전화(_stored_target — 짝 없는
#    서로게이트·NUL → U+FFFD, 200 코드 포인트 넘으면 앞 199자 + '…'). 검토 동작 본문(_json_body)은 httpx json= 과 같은
#    UTF-8 JSON(같은 크기 — 서버 본문 한도 65,536 바이트 기준)이되 짝 없는 서로게이트만 \udXXX 로 escape 한다
#    (브라우저 JSON.stringify 처럼 — 그런 글자가 든 계약 id 도 보낼 수 있게).
#
#  비밀값(BRIEF §2): 접근 코드는 없다(2026-11-03 없앰). Upstage 키 등은 출력하지 않는다.
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
#  종료 코드: 기대(--expect, 기본 done)대로면 0 — done 이면 위 done 확인·원본 파일 확인·검토 동작 확인(또는 검토 기록
#    모양 확인)도 모두 맞아야 한다. 하나라도 실패하면 1.
# ==========================================================================

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import sys
import time
from collections import Counter
from collections.abc import Callable, Mapping
from datetime import datetime
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

# 검토 동작 계약(review-actions — 조회 응답의 review 블록·POST /analyses/{id}/review-actions)
REVIEW_KEYS = {"status", "memo", "memo_at", "reviewer", "reviewed_at", "completion_note", "findings", "history", "version"}
REVIEW_FINDING_KEYS = {"status", "category", "subject", "exposure", "fp_type", "fp_note", "reclass_note", "memo", "updated_at"}
HISTORY_KEYS = {"id", "at", "actor", "kind", "target", "change", "reason"}
REVIEW_ACTOR = "api_e2e"  # 이 스크립트가 보내는 처리자 이름
SYSTEM_ACTOR = "시스템"
ANALYSIS_TARGET = "분석 건"
UNNAMED_FINDING = "이름 없는 항목"
RISK_LABELS = {"상": "높음", "중": "보통", "하": "낮음"}
FP_REASON = "개인정보가 아닌 번호·문구"  # 오탐 사유 목록(FP_REASONS)의 첫 값
MSG_REVIEW_BAD_REQUEST = "요청 형식이 올바르지 않습니다."
MSG_REVIEW_TEXT_TOO_LONG = "메모·사유는 500자 이하로 적어 주세요."
MSG_REVIEW_LOCKED = "검토를 완료한 분석은 바꿀 수 없습니다."
MSG_REVIEW_STATE_CHANGED = "탐지 항목 상태가 바뀌었습니다. 새로 고친 뒤 다시 시도해 주세요."
MSG_REVIEW_ALREADY_DONE = "이미 검토를 완료했습니다."
# 이 스크립트가 만든 합성 문구(메모·사유)
TEXT_CONFIRM = "api_e2e 확인"
TEXT_UNCONFIRM = "api_e2e 확인 취소"
TEXT_FP = "api_e2e 오탐 표시"
TEXT_RESTORE = "api_e2e 오탐 취소"
TEXT_RECLASS = "api_e2e 분류 수정"
TEXT_FINDING_MEMO = "api_e2e 항목 메모"
TEXT_MEMO = "api_e2e 검토 메모"
TEXT_COMPLETE = "api_e2e 검토 완료"
TEXT_REOPEN = "api_e2e 다시 열기"

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
        self.transport = transport  # 원본 파일 받기(사용자 지정 헤더 없는 클라이언트)도 같은 전송층을 쓴다(테스트)
        self.start = time.monotonic()
        headers: dict[str, str] = {}
        bypass = os.environ.get("VERCEL_PROTECTION_BYPASS")
        if bypass:
            _hide(bypass, "<VERCEL_PROTECTION_BYPASS>")
            headers["x-vercel-protection-bypass"] = bypass
        for name in ("UPSTAGE_API_KEY", "SUPABASE_SECRET_KEY", "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY"):
            _hide(env.get(name), f"<{name}>")
        _hide(os.environ.get("UPSTAGE_API_KEY"), "<UPSTAGE_API_KEY>")
        _hide(env.get("UPSTAGE_AGENT_ID"), "<UPSTAGE_AGENT_ID>")
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
    """원본 파일 주소를 받아 그 주소로(사용자 지정 헤더 없이) 내려받고 올린 내용과 sha256 을 비교한다. URL 은 출력하지 않는다."""
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
    run.log(f"원본 파일 받기(사용자 지정 헤더 없이): HTTP 200 · {len(downloaded.content):,} bytes · 올린 내용과 sha256 {_mark(same)}")
    return same and no_store


# --- 검토 동작 확인(review-actions) ---------------------------------------------------------
# 기대 문구는 백엔드 코드를 가져다 쓰지 않고 계약(데모 코어 src/services/demo/core.ts 와 같은 전이·문구)을 그대로 적는다.


# JavaScript String.prototype.trim() 이 지우는 글자 = ECMAScript WhiteSpace + LineTerminator(계약 BRIEF §5.1 — 화면 기준).
# Python str.strip() 과 다르다: U+FEFF 는 지우고, U+0085·U+001C~001F 는 지우지 않는다. 백엔드 함수를 쓰지 않고 따로 적는다.
_JS_WHITESPACE = (0x0009, 0x000B, 0x000C, 0x0020, 0x00A0, 0xFEFF)  # TAB VT FF SP NBSP ZWNBSP
_JS_ZS = (0x0020, 0x00A0, 0x1680, *range(0x2000, 0x200B), 0x202F, 0x205F, 0x3000)  # 유니코드 Zs 전체
_JS_LINE_TERMINATORS = (0x000A, 0x000D, 0x2028, 0x2029)  # LF CR LS PS
JS_TRIM_CHARS = "".join(chr(c) for c in sorted({*_JS_WHITESPACE, *_JS_ZS, *_JS_LINE_TERMINATORS}))
TARGET_MAX = 200  # 이력 target 저장 한도(코드 포인트, BRIEF §5.5)
REPLACEMENT_CHAR = chr(0xFFFD)  # 저장할 수 없는 글자(짝 없는 서로게이트·NUL)를 바꿀 글자


_JSON_U_ESCAPE = chr(92) + "u"  # JSON 문자열의 \uXXXX escape 머리


def _json_body(value: Any) -> bytes:
    """검토 동작 본문 JSON 바이트 — httpx `json=` 과 같은 모양(ensure_ascii=False · 구분자 , : · NaN 금지 · UTF-8)이되,
    UTF-8 로 인코딩할 수 없는 **짝 없는 서로게이트만** `\\udXXX` 로 escape 한다(브라우저 JSON.stringify 와 같은 값).
    정상 유니코드(한글 등)는 UTF-8 그대로라 본문 크기가 httpx `json=` 과 같다(서버 본문 한도 65,536 바이트 기준).
    서로게이트는 JSON 문자열 안에만 나오므로 그 자리의 escape 는 늘 올바른 JSON 이고, 결과는 늘 유효한 UTF-8 이다.
    (json.loads 로 만든 문자열에는 상위·하위 서로게이트가 따로 붙어 있는 경우가 없다 — 있다면 서버가 한 글자로 합쳐 읽는다.)"""
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    escaped = "".join(f"{_JSON_U_ESCAPE}{ord(char):04x}" if 0xD800 <= ord(char) <= 0xDFFF else char for char in text)
    return escaped.encode("utf-8")


def _js_trim(text: str) -> str:
    """JavaScript `text.trim()` 과 같은 결과(앞뒤의 JS_TRIM_CHARS 만 지운다)."""
    return text.strip(JS_TRIM_CHARS)


def _stored_target(text: str) -> str:
    """이력 target 이 저장되는 모양(BRIEF §5.5): 짝 없는 서로게이트·NUL → U+FFFD, 200 코드 포인트를 넘으면 앞 199자 + '…'."""
    cleaned = "".join(REPLACEMENT_CHAR if char == "\x00" or 0xD800 <= ord(char) <= 0xDFFF else char for char in text)
    return cleaned if len(cleaned) <= TARGET_MAX else cleaned[: TARGET_MAX - 1] + "…"


def _when(value: Any) -> datetime | None:
    """ISO 8601(시간대 포함) → datetime. 못 읽으면 None. DB 시각(timestamptz)과 이력 문자열을 같은 기준으로 비교한다."""
    if not isinstance(value, str) or not value:
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else None


def _review_targets(result: Any) -> list[dict[str, str]]:
    """검토할 수 있는 탐지 항목(화면에 보이는 항목) — 표시 번호·표시 이름·AI 값. 화면 toLiveFindings 와 같은 순서."""
    if not isinstance(result, Mapping):
        return []
    documents = result.get("documents") if isinstance(result.get("documents"), list) else []
    findings = result.get("findings") if isinstance(result.get("findings"), list) else []
    seen: list[int] = []
    for doc in documents:
        if not isinstance(doc, Mapping):
            continue
        index, start, end = doc.get("index"), doc.get("page_start"), doc.get("page_end")
        if _is_int(index) and index >= 0 and _is_int(start) and start >= 1 and _is_int(end) and end >= 1 and index not in seen:
            seen.append(index)
    numbers = {index: number for number, index in enumerate(sorted(seen), 1)}
    seq: dict[int, int] = {}
    targets: list[dict[str, str]] = []
    for finding in findings:
        if not isinstance(finding, Mapping):
            continue
        index = finding.get("document_index")
        if not _is_int(index) or index not in numbers:
            continue
        number = numbers[index]
        seq[number] = seq.get(number, 0) + 1
        label, field = finding.get("label"), finding.get("field")
        # 표시 이름: label → field → '이름 없는 항목'(화면 toLiveFindings 처럼 JavaScript trim 기준)
        name = (_js_trim(label) if isinstance(label, str) else "") or (_js_trim(field) if isinstance(field, str) else "")
        category, subject, exposure = finding.get("category"), finding.get("subject"), finding.get("exposure")
        targets.append(
            {
                "id": str(finding.get("id")),
                "num": f"D{number}-{seq[number]:02d}",
                "label": name or UNNAMED_FINDING,
                "category": category if category in CATS else "기타 개인정보",
                "subject": subject if subject in SUBJECTS else "기타",
                "exposure": exposure if exposure in EXPOSURES else "전체 노출",
            }
        )
    return targets


def _risk_label(result: Mapping[str, Any]) -> str:
    """S2 의 위험등급 — overall.level(비면 summary.risk_level) 상·중·하 → 높음·보통·낮음, 그 밖 미평가."""
    overall = result.get("overall") if isinstance(result.get("overall"), Mapping) else {}
    level = overall.get("level")
    if not (isinstance(level, str) and _js_trim(level)):
        summary = result.get("summary") if isinstance(result.get("summary"), Mapping) else {}
        level = summary.get("risk_level")
    return RISK_LABELS.get(_js_trim(level) if isinstance(level, str) else "", "미평가")


def _system_lines(row: Mapping[str, Any], targets: list[dict[str, str]]) -> list[dict[str, str]]:
    """조회할 때 만드는 이력 두 줄(S1 분석 요청 · S2 최초 AI 결과)의 기대값."""
    result = row.get("result") if isinstance(row.get("result"), Mapping) else {}
    files = len([d for d in row.get("documents") or [] if isinstance(d, Mapping)])
    base = {"actor": SYSTEM_ACTOR, "target": ANALYSIS_TARGET, "reason": ""}
    return [
        {"id": "S1", "at": row.get("created_at"), "kind": "request", "change": f"문서 {files}개 분석 요청", **base},
        {
            "id": "S2",
            "at": row.get("updated_at"),
            "kind": "ai",
            "change": f"분석 완료 · 탐지 {len(targets)}건 · 위험등급 {_risk_label(result)} · 검토사항 0건",
            **base,
        },
    ]


def _line_problems(line: Any, want: Mapping[str, Any], where: str) -> list[str]:
    if not isinstance(line, Mapping) or set(line) != HISTORY_KEYS:
        return [f"{where}: 이력 줄 모양이 다름"]
    return [f"{where} {key}: {line.get(key)!r} (기대 {value!r})" for key, value in want.items() if line.get(key) != value]


def _review_shape_problems(row: Mapping[str, Any], targets: list[dict[str, str]]) -> list[str]:
    """review 블록의 모양(값은 보지 않음): 키·status·findings·history S1·S2·version."""
    review = row.get("review")
    if not isinstance(review, Mapping):
        return ["review 가 객체가 아님(검토 기록을 읽지 못함)"]
    if set(review) != REVIEW_KEYS:
        return [f"review 키가 계약과 다름 {sorted(set(review) ^ REVIEW_KEYS)}"]
    problems: list[str] = []
    if review["status"] not in ("needed", "done"):
        problems.append(f"status {review['status']!r}")
    version = review["version"]
    if not (_is_int(version) and version >= 0):
        problems.append("version 이 0 이상 정수가 아님")
    findings = review["findings"]
    ids = {t["id"] for t in targets}
    if not isinstance(findings, Mapping):
        problems.append("findings 가 객체가 아님")
    else:
        problems += [f"findings: 검토 가능 항목이 아닌 id {str(k)[:40]}" for k in findings if k not in ids][:3]
        problems += [
            f"findings {str(k)[:40]}: 키가 계약과 다름" for k, v in findings.items() if not (isinstance(v, Mapping) and set(v) == REVIEW_FINDING_KEYS)
        ][:3]
    history = review["history"]
    if not isinstance(history, list) or len(history) < 2:
        problems.append("history 에 S1·S2 두 줄이 없음")
        return problems
    for line, want in zip(history[:2], _system_lines(row, targets), strict=True):
        problems += _line_problems(line, want, str(want["id"]))
    stored = history[2:]
    if any(not isinstance(line, Mapping) or set(line) != HISTORY_KEYS or not str(line.get("id")).startswith("H") for line in stored):
        problems.append("저장된 이력 줄 모양이 다름")
    if _is_int(version) and len(stored) > version:
        problems.append(f"저장된 이력 {len(stored)}줄이 version {version} 보다 많음")
    return problems


def _first_review_problems(row: Mapping[str, Any], targets: list[dict[str, str]]) -> list[str]:
    """새 분석의 처음 review: needed·빈 값·findings {}·S1·S2 만·version 0."""
    problems = _review_shape_problems(row, targets)
    review = row.get("review")
    if problems or not isinstance(review, Mapping):
        return problems
    want = {"status": "needed", "memo": "", "memo_at": None, "reviewer": "", "reviewed_at": None, "completion_note": "", "findings": {}, "version": 0}
    problems += [f"{key}: {review.get(key)!r} (기대 {value!r})" for key, value in want.items() if review.get(key) != value]
    if len(review["history"]) != 2:
        problems.append(f"history {len(review['history'])}줄(기대 S1·S2 2줄)")
    return problems


class _ReviewFlow:
    """검토 동작을 차례로 보내고, 응답과 다시 읽은 값을 확인한다. 이번 실행이 만든 분석에만 쓴다."""

    def __init__(self, run: Run, analysis_id: str, first: Mapping[str, Any]) -> None:
        self.run = run
        self.analysis_id = analysis_id
        self.first = first
        review = first.get("review")
        self.review: Mapping[str, Any] = review if isinstance(review, Mapping) else {}
        self.steps = 0
        self.failed = 0
        self.expected_writes = 0  # 이력 한 줄을 남겨야 하는 동작 수
        self.writes = 0  # 실제로 changed true 였던 동작 수

    def report(self, name: str, problems: list[str], note: str = "") -> bool:
        self.steps += 1
        ok = not problems
        if not ok:
            self.failed += 1
        _say(f"  [{'통과' if ok else '실패'}] {self.steps:02d}. {name}" + (f" — {note}" if note else ""))
        for problem in problems[:6]:
            _say(f"      - {_short(problem)}")
        return ok

    def finding(self, target: Mapping[str, str]) -> Mapping[str, Any]:
        found = self.review.get("findings", {}).get(target["id"]) if isinstance(self.review.get("findings"), Mapping) else None
        return found if isinstance(found, Mapping) else {}

    def _post(self, body: Mapping[str, Any]) -> tuple[httpx.Response, Any]:
        # 본문은 _json_body 로 직접 만든다 — httpx json= 와 같은 UTF-8 바이트(같은 크기)이되, 짝 없는 서로게이트가 든
        # 계약 id 도 보낼 수 있게 그 글자만 escape(httpx json= 는 UTF-8 로 인코딩하다 실패한다). 서버가 읽는 값은 같다.
        content = _json_body({"actor": REVIEW_ACTOR, **body})
        response = self.run.call(
            "POST",
            f"/api/py/analyses/{self.analysis_id}/review-actions",
            content=content,
            headers={"content-type": "application/json"},
        )
        try:
            data = response.json()
        except ValueError:
            data = None
        return response, data

    def _reread(self, expected: Mapping[str, Any] | None) -> tuple[Mapping[str, Any] | None, list[str]]:
        """GET 으로 다시 읽는다. expected 가 있으면 분석 전체가 같아야 하고, 없으면 review 가 지금 값과 같아야 한다."""
        response, row = _get(self.run, self.analysis_id)
        if response.status_code != 200 or not isinstance(row, Mapping):
            return None, [f"다시 읽기: HTTP {response.status_code}"]
        if expected is not None and row != expected:
            keys = sorted(k for k in set(row) | set(expected) if row.get(k) != expected.get(k))
            return row, [f"다시 읽은 값이 응답과 다름 {keys}"]
        if expected is None and row.get("review") != self.review:
            return row, ["다시 읽은 review 가 바뀜(쓰기가 있었음)"]
        return row, []

    def write(
        self,
        name: str,
        body: Mapping[str, Any],
        line: tuple[str, str, str, str] | None,
        check: Callable[[Mapping[str, Any], Mapping[str, Any]], list[str]] | None = None,
    ) -> bool:
        """200 을 기대하는 동작. line = 새 이력 줄(kind, target, change, reason), None 이면 changed false(쓰기 없음)."""
        before = self.review
        if line is not None:
            self.expected_writes += 1
        response, data = self._post(body)
        if response.status_code != 200 or not isinstance(data, Mapping) or set(data) != {"analysis", "changed"}:
            return self.report(name, [f"HTTP {response.status_code} {_detail(response)}(기대 200 · analysis·changed)"])
        analysis = data["analysis"]
        review = analysis.get("review") if isinstance(analysis, Mapping) else None
        if not isinstance(review, Mapping) or not isinstance(review.get("history"), list):
            return self.report(name, ["응답의 review 가 객체가 아님"])
        problems: list[str] = []
        if analysis.get("upstage_status") is not None or analysis.get("poll_error") is not None:
            problems.append("응답의 upstage_status·poll_error 가 null 이 아님")
        if isinstance(analysis.get("result"), Mapping) and "stages" in analysis["result"]:
            problems.append("응답 result 에 stages 가 있음")
        for key in ("created_at", "updated_at"):
            if analysis.get(key) != self.first.get(key):
                problems.append(f"분석 {key} 가 바뀜")
        changed = data["changed"]
        history, old = review["history"], before["history"]
        if changed is True:
            self.writes += 1
        if line is None:
            if changed is not False:
                problems.append(f"changed {changed!r}(기대 false)")
            if review != before:
                problems.append("바뀐 것이 없는데 review 가 바뀜")
        else:
            version = before["version"] + 1
            if changed is not True:
                problems.append(f"changed {changed!r}(기대 true)")
            if review.get("version") != version:
                problems.append(f"version {review.get('version')!r}(기대 {version})")
            if len(history) != len(old) + 1 or history[:-1] != old:
                problems.append(f"이력 {len(history)}줄(기대 앞 {len(old)}줄 그대로 + 1줄)")
            else:
                kind, target, change, reason = line
                # target 은 저장 안전화를 거친 모양이어야 한다(안전화하지 않은 응답은 여기서 불일치로 잡힌다)
                want = {"id": f"H{version}", "actor": REVIEW_ACTOR, "kind": kind, "target": _stored_target(target), "change": change, "reason": reason}
                problems += _line_problems(history[-1], want, "새 이력")
                if _when(history[-1].get("at")) is None:
                    problems.append("새 이력 at 을 읽을 수 없음")
        if check is not None:
            problems += check(review, before)
        _, reread = self._reread(analysis)
        problems += reread
        self.review = review  # 실패해도 서버의 지금 값을 기준으로 다음 단계를 본다
        note = f"이력 {len(history)}줄 · version {review.get('version')}" + ("" if changed else " · changed false")
        return self.report(name, problems, note)

    def refuse(self, name: str, body: Mapping[str, Any], status: int, detail: str) -> bool:
        """오류를 기대하는 동작 — 상태 코드·문구, 그리고 다시 읽어도 review 가 그대로(쓰기 없음)."""
        response, data = self._post(body)
        problems: list[str] = []
        got = data.get("detail") if isinstance(data, Mapping) else None
        if response.status_code != status or got != detail:
            problems.append(f"HTTP {response.status_code} {_detail(response)}(기대 {status} {detail})")
        _, reread = self._reread(None)
        problems += reread
        return self.report(name, problems, f"HTTP {response.status_code} · 쓰기 없음" if not problems else "")

    # --- 항목 값 확인 도우미 -------------------------------------------------------------

    def last_at(self, review: Mapping[str, Any]) -> datetime | None:
        return _when(review["history"][-1].get("at")) if review.get("history") else None

    def expect_finding(self, review: Mapping[str, Any], target: Mapping[str, str], **want: Any) -> list[str]:
        findings = review.get("findings") if isinstance(review.get("findings"), Mapping) else {}
        value = findings.get(target["id"])
        if not isinstance(value, Mapping) or set(value) != REVIEW_FINDING_KEYS:
            return [f"{target['num']}: 저장 값 모양이 다름"]
        return [f"{target['num']} {key}: {value.get(key)!r} (기대 {expected!r})" for key, expected in want.items() if value.get(key) != expected]

    def touched_now(self, review: Mapping[str, Any], target: Mapping[str, str]) -> list[str]:
        """그 항목의 updated_at = 이번 동작 시각(새 이력 at)."""
        value = (review.get("findings") or {}).get(target["id"]) or {}
        if _when(value.get("updated_at")) is None or _when(value.get("updated_at")) != self.last_at(review):
            return [f"{target['num']} updated_at 이 이번 동작 시각이 아님"]
        return []


def _check_reviews(run: Run, analysis_id: str) -> bool:
    """새로 만든 분석(done)에 검토 동작을 차례로 보내 확인한다. 기존 분석에는 부르지 않는다(_check_review_shape 만)."""
    _say(f"검토 동작 확인(이번 실행이 만든 분석에만 씀 · actor {REVIEW_ACTOR}):")
    response, first = _get(run, analysis_id)
    if response.status_code != 200 or not isinstance(first, Mapping):
        _say(f"  [실패] 00. 처음 조회 — HTTP {response.status_code}")
        return False
    targets = _review_targets(first.get("result"))
    problems = _first_review_problems(first, targets)
    if len({t["id"] for t in targets}) < 3:
        problems.append(f"검토 가능 항목이 3개보다 적음({len(targets)})")
    flow = _ReviewFlow(run, analysis_id, first)
    if not flow.report("처음 조회 — needed·version 0·findings {}·S1·S2", problems, f"검토 가능 항목 {len(targets)}"):
        _say("검토 동작 확인: 처음 조회가 기대와 달라 동작을 보내지 않습니다")
        return False
    a, b, c = targets[0], targets[1], targets[2]
    cat = a["category"]
    new_cat = next(x for x in CATS if x != cat)
    same = flow.expect_finding
    ai = {"subject": a["subject"], "exposure": a["exposure"]}

    flow.write(
        f"set_status confirmed({a['num']})",
        {"type": "set_status", "finding_id": a["id"], "status": "confirmed", "reason": TEXT_CONFIRM},
        ("confirm", f"{a['num']} {cat}", "미확인 → 확인함", TEXT_CONFIRM),
        lambda r, _: same(r, a, status="confirmed", category=cat, **ai) + flow.touched_now(r, a),
    )
    flow.write(
        f"set_status open({a['num']})",
        {"type": "set_status", "finding_id": a["id"], "status": "open", "reason": TEXT_UNCONFIRM},
        ("unconfirm", f"{a['num']} {cat}", "확인함 → 미확인", TEXT_UNCONFIRM),
        lambda r, _: same(r, a, status="open") + flow.touched_now(r, a),
    )
    flow.write(
        f"confirm_many 2건({b['num']}, {c['num']})",
        {"type": "confirm_many", "finding_ids": [b["id"], c["id"]]},
        ("confirm", "탐지 항목 2건", "미확인 → 확인함", f"{b['num']}, {c['num']}"),
        lambda r, _: same(r, b, status="confirmed") + same(r, c, status="confirmed") + flow.touched_now(r, b) + flow.touched_now(r, c),
    )
    flow.refuse(
        f"set_status confirmed 다시({b['num']}) → 409 상태 불일치",
        {"type": "set_status", "finding_id": b["id"], "status": "confirmed", "reason": ""},
        409,
        MSG_REVIEW_STATE_CHANGED,
    )
    flow.write(
        f"mark_false_positive({a['num']})",
        {"type": "mark_false_positive", "finding_id": a["id"], "reason_type": FP_REASON, "note": TEXT_FP},
        ("fp", f"{a['num']} {a['label']}", f"{cat} → 오탐 ({FP_REASON})", TEXT_FP),
        lambda r, _: same(r, a, status="false_positive", fp_type=FP_REASON, fp_note=TEXT_FP) + flow.touched_now(r, a),
    )
    flow.write(
        f"restore → 미확인({a['num']})",
        {"type": "restore", "finding_id": a["id"], "note": TEXT_RESTORE},
        ("restore", f"{a['num']} {a['label']}", "오탐 → 미확인", TEXT_RESTORE),
        lambda r, _: same(r, a, status="open", fp_type="", fp_note="", category=cat) + flow.touched_now(r, a),
    )
    flow.write(
        f"reclassify 정보 종류({a['num']})",
        {"type": "reclassify", "finding_id": a["id"], "category": new_cat, "reason": TEXT_RECLASS},
        ("reclass", f"{a['num']} {a['label']}", f"정보 종류: {cat} → {new_cat}", TEXT_RECLASS),
        lambda r, _: same(r, a, status="reclassified", category=new_cat, reclass_note=TEXT_RECLASS, **ai) + flow.touched_now(r, a),
    )
    flow.write(
        f"reclassify 같은 값({a['num']}) → changed false",
        {"type": "reclassify", "finding_id": a["id"], "category": new_cat, "subject": a["subject"], "reason": TEXT_RECLASS},
        None,
    )
    flow.write(
        f"mark_false_positive 다시({a['num']})",
        {"type": "mark_false_positive", "finding_id": a["id"], "reason_type": FP_REASON, "note": TEXT_FP},
        ("fp", f"{a['num']} {a['label']}", f"{new_cat} → 오탐 ({FP_REASON})", TEXT_FP),
        lambda r, _: same(r, a, status="false_positive", category=new_cat) + flow.touched_now(r, a),
    )
    flow.write(
        f"restore → 분류 수정({a['num']})",
        {"type": "restore", "finding_id": a["id"], "note": TEXT_RESTORE},
        ("restore", f"{a['num']} {a['label']}", "오탐 → 분류 수정", TEXT_RESTORE),
        lambda r, _: same(r, a, status="reclassified", category=new_cat, fp_type="", fp_note="", reclass_note=TEXT_RECLASS)
        + flow.touched_now(r, a),
    )

    def memo_kept_time(text: str) -> Callable[[Mapping[str, Any], Mapping[str, Any]], list[str]]:
        # 항목 메모는 updated_at 을 바꾸지 않는다(데모와 같다)
        def check(review: Mapping[str, Any], before: Mapping[str, Any]) -> list[str]:
            old = (before.get("findings") or {}).get(a["id"]) or {}
            return same(review, a, memo=text, status="reclassified", updated_at=old.get("updated_at"))

        return check

    flow.write(
        f"save_finding_memo 저장({a['num']})",
        {"type": "save_finding_memo", "finding_id": a["id"], "text": TEXT_FINDING_MEMO},
        ("fmemo", f"{a['num']} {new_cat}", "항목 메모 저장", TEXT_FINDING_MEMO),
        memo_kept_time(TEXT_FINDING_MEMO),
    )
    flow.write(
        f"save_finding_memo 삭제({a['num']})",
        {"type": "save_finding_memo", "finding_id": a["id"], "text": ""},
        ("fmemo", f"{a['num']} {new_cat}", "항목 메모 삭제", ""),
        memo_kept_time(""),
    )

    def memo_check(review: Mapping[str, Any], _before: Mapping[str, Any]) -> list[str]:
        problems = [] if review.get("memo") == TEXT_MEMO else ["memo 가 저장한 글과 다름"]
        if _when(review.get("memo_at")) is None or _when(review.get("memo_at")) != flow.last_at(review):
            problems.append("memo_at 이 이번 동작 시각이 아님")
        return problems

    flow.write(
        "save_memo",
        {"type": "save_memo", "text": TEXT_MEMO},
        ("memo", ANALYSIS_TARGET, "검토 메모 저장", TEXT_MEMO),
        memo_check,
    )

    findings_now = flow.review.get("findings") if isinstance(flow.review.get("findings"), Mapping) else {}
    left = sum(1 for t in targets if ((findings_now.get(t["id"]) or {}).get("status") or "open") == "open")
    rest = f" (남은 항목: 미확인 탐지 {left}건)" if left else ""

    def complete_check(review: Mapping[str, Any], _before: Mapping[str, Any]) -> list[str]:
        problems = [
            f"{key}: {review.get(key)!r} (기대 {value!r})"
            for key, value in {"status": "done", "reviewer": REVIEW_ACTOR, "completion_note": TEXT_COMPLETE}.items()
            if review.get(key) != value
        ]
        if _when(review.get("reviewed_at")) is None or _when(review.get("reviewed_at")) != flow.last_at(review):
            problems.append("reviewed_at 이 이번 동작 시각이 아님")
        return problems

    flow.write(
        f"complete_review(남은 미확인 {left}건)",
        {"type": "complete_review", "note": TEXT_COMPLETE},
        ("complete", ANALYSIS_TARGET, f"검토 필요 → 검토 완료{rest}", TEXT_COMPLETE),
        complete_check,
    )
    flow.refuse(
        f"잠김 — set_status open({b['num']}) → 409",
        {"type": "set_status", "finding_id": b["id"], "status": "open", "reason": ""},
        409,
        MSG_REVIEW_LOCKED,
    )
    flow.refuse("이미 완료 — complete_review → 409", {"type": "complete_review", "note": ""}, 409, MSG_REVIEW_ALREADY_DONE)

    def reopen_check(review: Mapping[str, Any], _before: Mapping[str, Any]) -> list[str]:
        want = {"status": "needed", "reviewed_at": None, "reviewer": REVIEW_ACTOR, "completion_note": TEXT_COMPLETE, "memo": TEXT_MEMO}
        return [f"{key}: {review.get(key)!r} (기대 {value!r})" for key, value in want.items() if review.get(key) != value]

    flow.write(
        "reopen_review(reviewer·completion_note 남음, reviewed_at null)",
        {"type": "reopen_review", "reason": TEXT_REOPEN},
        ("reopen", ANALYSIS_TARGET, "검토 완료 → 검토 필요", TEXT_REOPEN),
        reopen_check,
    )
    flow.refuse("모르는 type → 400", {"type": "delete_everything"}, 400, MSG_REVIEW_BAD_REQUEST)
    flow.refuse("501자 글 → 400", {"type": "save_memo", "text": "가" * 501}, 400, MSG_REVIEW_TEXT_TOO_LONG)

    # 마지막: 이력 id 연속·시간 순서·줄 수 = 쓴 동작 수·분석 시각 불변
    response, last = _get(run, analysis_id)
    problems = []
    if response.status_code != 200 or not isinstance(last, Mapping) or not isinstance(last.get("review"), Mapping):
        problems.append(f"마지막 조회: HTTP {response.status_code}")
        history: list[Any] = []
        version: Any = None
    else:
        review = last["review"]
        history = review.get("history") if isinstance(review.get("history"), list) else []
        version = review.get("version")
        stored = history[2:]
        ids = [line.get("id") if isinstance(line, Mapping) else None for line in stored]
        if ids != [f"H{i}" for i in range(1, len(stored) + 1)]:
            problems.append("이력 id 가 H1…Hn 연속이 아님")
        times = [_when(line.get("at")) if isinstance(line, Mapping) else None for line in history]
        if any(t is None for t in times):
            problems.append("이력 at 을 읽을 수 없는 줄이 있음")
        elif any(later < earlier for earlier, later in zip(times, times[1:], strict=False)):
            problems.append("이력 at 이 줄어드는 곳이 있음")
        if not (len(stored) == flow.expected_writes == flow.writes == version):
            problems.append(f"저장 이력 {len(stored)}줄 · 쓴 동작 {flow.writes} · 기대 {flow.expected_writes} · version {version}")
        for key in ("created_at", "updated_at"):
            if last.get(key) != first.get(key):
                problems.append(f"분석 {key} 가 처음 조회와 다름")
        if review.get("status") != "needed":
            problems.append(f"status {review.get('status')!r}(기대 needed)")
    flow.report(
        "마지막 — 이력 H1…Hn 연속·시간 순서·줄 수 = 쓴 동작 수·분석 created_at·updated_at 그대로",
        problems,
        f"이력 {len(history)}줄(S1·S2 포함) · 쓴 동작 {flow.writes} · version {version}",
    )
    ok = flow.failed == 0
    _say(f"검토 동작 확인: {flow.steps - flow.failed}/{flow.steps} 통과 · 쓴 동작 {flow.writes}건 — {'기대대로' if ok else '기대와 다름'}")
    return ok


def _check_review_shape(run: Run, analysis_id: str) -> bool:
    """--analysis-id: 기존 분석은 **읽기만** — review 블록 모양(status·findings·history S1·S2·version)만 본다(POST 없음)."""
    response, row = _get(run, analysis_id)
    if response.status_code != 200 or not isinstance(row, Mapping):
        run.log(f"검토 기록 모양: 조회 실패 HTTP {response.status_code}")
        return False
    targets = _review_targets(row.get("result"))
    problems = _review_shape_problems(row, targets)
    review = row.get("review") if isinstance(row.get("review"), Mapping) else {}
    history = review.get("history") if isinstance(review.get("history"), list) else []
    findings = review.get("findings") if isinstance(review.get("findings"), Mapping) else {}
    default = review.get("status") == "needed" and findings == {} and len(history) == 2 and review.get("version") == 0
    _say(
        f"검토 기록 모양(읽기만, 동작 보내지 않음): status={review.get('status')} · findings {len(findings)}개 · "
        f"이력 {len(history)}줄(S1·S2 포함) · version {review.get('version')} · 기본값(검토 행 없음) {default}: "
        f"{'맞음' if not problems else f'문제 {len(problems)}개'}"
    )
    for problem in problems[:6]:
        _say(f"    - {_short(problem)}")
    return not problems


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
    if args.analysis_id:
        return _flow_existing(run, args, args.analysis_id, content)
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
        if args.no_review:
            _say("검토 동작 확인 건너뜀(--no-review)")
        else:
            # 이번 실행이 만든 분석이 done 이 된 뒤에만 검토 동작을 보낸다
            ok = _check_reviews(run, analysis_id) and ok
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


def _flow_existing(run: Run, args: argparse.Namespace, analysis_id: str, content: bytes) -> int:
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
    if args.no_review:
        _say("검토 기록 모양 확인 건너뜀(--no-review)")
    else:
        ok = _check_review_shape(run, analysis_id) and ok  # 읽기만 — 검토 동작은 보내지 않는다
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
        help="이미 있는 분석을 조회하고 원본 파일·검토 기록 모양만 확인(만들기·올리기·시작·검토 동작 없음 — Upstage 작업을 만들지 않음)",
    )
    parser.add_argument(
        "--no-review",
        action="store_true",
        help="검토 동작 확인을 끈다(기본은 새 분석이 done 이 되면 검토 동작을 보내 확인)",
    )
    args = parser.parse_args(argv)
    try:
        return run_e2e(args, transport=transport)
    except KeyboardInterrupt:  # 정리 바깥(설정 읽기 등)에서의 중단
        _say("중단됨(Ctrl+C)")
        return EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
