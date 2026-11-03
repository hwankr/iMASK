# ==========================================================================
#  분석 건 업무 로직 — 만들기·시작·조회 (FastAPI 와 무관해 단위 테스트할 수 있다)
#  BRIEF §4: 한 요청 안에서 Upstage 완료를 기다리지 않는다. 시작 요청은 작업만 만들고 job id 를
#  저장한다. 조회(GET)가 올 때마다 Upstage 상태를 **한 번** 확인해 끝났으면 결과를 저장하고
#  Upstage 파일을 지운다. 백그라운드 스레드·워커는 쓰지 않는다.
#
#  상태 흐름: queued(만들기) → running(시작 선점) → done(완료) | failed(실패)
#  - 선점: update … set status='running' where id=? and status='queued' — 같은 분석을 두 번 시작해
#    Upstage 작업이 둘 생기는 것을 막는다.
#  - 결과 반영: update … where status='running' — 두 조회가 같은 결과를 동시에 처리해도 한 번만.
#  - 선점 뒤 실패는 HTTP 오류가 아니라 failed 행(+ error)으로 돌려준다.
#
#  가림(BRIEF §2): Upstage 문구는 UpstageError.message 와 job_failure_message(job, 서버 비밀값 전체) 만 쓰고,
#  바깥에서 온 문자열이 응답(poll_error·upstage_status)·DB(error)·로그로 나가는 곳은 모두 _scrub()
#  한 곳을 지난다 — 설정의 서버 비밀값 전체(Upstage 키·에이전트 id·Supabase 비밀 키·접근 코드)와
#  서명 URL·토큰·JWT 를 가린 **뒤에** 길이를 자른다. 원본 응답의 최상위 model(에이전트 id)은 저장하지 않는다.
#  조회 중 Upstage 404: job id 를 저장하고(updated_at) 2분이 지났으면 작업이 없어진 것으로 보고 failed.
#  그 밖의 조회 오류(401·403·429·5xx·연결)는 상태를 바꾸지 않고 다음 조회에서 다시 시도한다.
#
#  응답 모양(analysis_out): result 에서 원본(response)과 단계별 결과(stages)를 빼고, 화면이 바로 쓰는
#  documents·findings·overall(imask_backend.findings.build_view — 조회할 때 계산, 저장 형식은 그대로)을 더한다.
#  stages 는 include_stages(조회의 ?include=stages)일 때만 넣는다. 넣을 stages 는 response_stages() 한 경계를
#  지난다 — 만들다 예외(파싱 RecursionError 포함)가 나거나 반복문으로 잰 중첩 깊이가 MAX_STAGES_DEPTH(64, 실제는
#  10 안쪽 — 응답 직렬화기 한도 약 97 보다 충분히 낮게)를 넘으면 값 없는 경고 후 stages: [] (조회가 500 이 되지 않게).
#  짝 없는 서로게이트가 든 문자열·키도 여기서는 원문 그대로 둔다 — api/index.py 의 응답 도우미가 그런 응답만
#  ASCII escape JSON 으로 보낸다(imask_backend.textsafe, 코디네이터 결정 T1-fix5).
#  원본 파일 주소(file_link): 문서 행의 storage_path 로 10분짜리 서명 다운로드 URL. 서명 URL 은 로그에 남기지 않는다.
# ==========================================================================

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol

from .config import ConfigError
from .files import (
    MAX_FILE_BYTES,
    analysis_name,
    check_upload,
    content_matches,
    safe_storage_name,
)
from .findings import build_view, view_stages
from .redaction import redact, redact_value
from .results import parse_stages, summarize
from .settings import STORAGE_BUCKET, Settings
from .store import Store, StoreError
from .upstage import (
    PENDING_STATUSES,
    UpstageError,
    is_success,
    is_terminal,
    job_failure_message,
)

logger = logging.getLogger("imask.analyses")

QUEUED = "queued"
RUNNING = "running"
DONE = "done"
PARTIAL = "partial"
FAILED = "failed"

RESULT_FORMAT = "imask-upstage-v1"
# 시작 요청이 job id 를 저장하지 못한 채 이만큼 지나면 실패로 본다(Vercel maxDuration 60초보다 넉넉히)
STALE_START = timedelta(minutes=5)
# job id 저장 뒤 이만큼 지나도 Upstage 가 그 작업을 404 로 답하면 없어진 작업으로 본다(만든 직후의 일시적 404 대비)
JOB_NOT_FOUND_GRACE = timedelta(minutes=2)
MAX_ERROR_LENGTH = 500
MAX_STATUS_LENGTH = 40

# --- 사용자에게 보이는 문장 -------------------------------------------------------
MSG_NOT_FOUND = "분석 건을 찾을 수 없습니다."
MSG_ALREADY_STARTED = "이미 시작한 분석입니다."
MSG_PREPARE_FAILED = "분석을 준비하지 못했습니다. 잠시 후 다시 시도해 주세요."
MSG_START_RECORD_FAILED = "분석 시작 결과를 저장하지 못했습니다. 잠시 후 다시 시도해 주세요."
MSG_NO_DOCUMENT = "분석할 파일이 없습니다. 새 분석으로 다시 올려 주세요."
MSG_FILE_MISSING = "업로드된 파일을 찾을 수 없습니다. 파일을 다시 올려 주세요."
MSG_FILE_READ_FAILED = "업로드된 파일을 읽지 못했습니다. 새 분석으로 다시 올려 주세요."
MSG_FILE_TOO_LARGE = "업로드된 파일이 20MB 를 넘습니다."
MSG_CONTENT_MISMATCH = "파일 내용이 PDF·PNG·JPEG 형식이 아닙니다."
MSG_START_SAVE_FAILED = "분석 시작 정보를 저장하지 못했습니다. 새 분석으로 다시 올려 주세요."
MSG_START_INTERNAL = "분석을 시작하는 중 서버 오류가 발생했습니다. 새 분석으로 다시 올려 주세요."
MSG_START_STALE = "분석 시작이 끝나지 않았습니다. 새 분석으로 다시 올려 주세요."
MSG_UPSTAGE_START = "Upstage 분석을 시작하지 못했습니다: {reason}"
MSG_UPSTAGE_FAILED = "Upstage 분석이 실패했습니다: {reason}"
MSG_POLL_FAILED = "Upstage 상태를 확인하지 못했습니다: {reason}"
MSG_RESULT_FETCH_FAILED = "Upstage 결과를 받지 못했습니다: {reason}"
MSG_POLL_NO_STATUS = "Upstage 응답에 상태가 없습니다."
MSG_SAVE_FAILED = "분석 상태를 저장하지 못했습니다. 다음 조회에서 다시 시도합니다."
MSG_JOB_NOT_FOUND = "Upstage 작업을 찾을 수 없습니다. 새 분석으로 다시 올려 주세요."
# 조건부 갱신에 져서(다른 요청이 먼저 저장) 최신 행을 다시 읽어야 하는데 그것도 실패했을 때
MSG_REREAD_FAILED = "분석 상태를 다시 읽지 못했습니다. 다음 조회에서 다시 확인합니다."
MSG_START_REREAD_FAILED = "분석 시작 결과를 확인하지 못했습니다. 잠시 후 분석 건을 다시 조회해 주세요."
MSG_ORIGINAL_MISSING = "원본 파일을 찾을 수 없습니다."
MSG_ORIGINAL_LINK_FAILED = "원본 파일 주소를 만들지 못했습니다. 잠시 후 다시 시도해 주세요."

# 원본 파일 서명 다운로드 URL 유효 시간(초) — BRIEF §5: 10분
SIGNED_DOWNLOAD_SECONDS = 600
# ?include=stages 로 넣을 stages 의 최대 중첩 깊이(실제 단계는 10 안쪽, 응답 직렬화기 한도는 약 97)
MAX_STAGES_DEPTH = 64


class ApiError(Exception):
    """HTTP 상태와 사용자에게 보일 한국어 문장(api/index.py 가 {"detail": …} 로 바꾼다)."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class UpstageAPI(Protocol):
    """imask_backend.upstage.UpstageClient 중 여기서 쓰는 부분(테스트는 가짜로)."""

    def upload_file(self, filename: str, content: bytes, mime_type: str) -> str: ...
    def create_job(self, agent_id: str, config_id: str, file_id: str) -> dict[str, Any]: ...
    def get_job(self, job_id: str, include: Literal["last", "all"]) -> dict[str, Any]: ...
    def delete_file(self, file_id: str) -> bool: ...
    def failure_message(self, job: Any) -> str: ...
    def redact(self, text: Any, *, limit: int | None = ...) -> str: ...


UpstageFactory = Callable[[], UpstageAPI]


@dataclass(frozen=True)
class PollResult:
    row: dict[str, Any]
    upstage_status: str | None = None
    poll_error: str | None = None


# --- 응답 모양 --------------------------------------------------------------------


def document_out(doc: Mapping[str, Any]) -> dict[str, Any]:
    """documents 행 → 응답(storage_path 는 넣지 않는다)."""
    return {
        "id": doc.get("id"),
        "filename": doc.get("filename"),
        "size_bytes": doc.get("size_bytes"),
        "mime_type": doc.get("mime_type"),
        "upstage_file_id": doc.get("upstage_file_id"),
        "created_at": doc.get("created_at"),
    }


def nesting_exceeds(value: Any, limit: int) -> bool:
    """dict·list 중첩 깊이가 limit 를 넘는지 — 재귀 없이 반복문으로 잰다(맨 바깥 컨테이너가 깊이 1)."""
    stack: list[tuple[Any, int]] = [(value, 1)]
    while stack:
        current, depth = stack.pop()
        if isinstance(current, Mapping):
            children: Iterable[Any] = current.values()
        elif isinstance(current, (list, tuple)):
            children = current
        else:
            continue
        if depth > limit:
            return True
        stack.extend((child, depth + 1) for child in children)
    return False


def response_stages(result: Mapping[str, Any]) -> list[Any]:
    """?include=stages 로 넣을 stages(저장된 것, 없으면 response 에서 parse_stages). 정상 stages 는 그대로.

    만들다 예외가 나거나(깊은 JSON 의 RecursionError 등) 중첩이 MAX_STAGES_DEPTH 를 넘으면 값 없는 경고 후 [].
    """
    try:
        stored = result.get("stages")
        stages = stored if isinstance(stored, list) else view_stages(result)
        if nesting_exceeds(stages, MAX_STAGES_DEPTH):
            logger.warning("단계별 결과의 중첩이 한도(%d)를 넘어 stages 를 빈 목록으로 보냅니다", MAX_STAGES_DEPTH)
            return []
        return list(stages)
    except Exception as exc:
        logger.warning("단계별 결과를 만들지 못해 stages 를 빈 목록으로 보냅니다: %s", type(exc).__name__)
        return []


def result_out(result: Mapping[str, Any], *, include_stages: bool = False) -> dict[str, Any]:
    """저장된 result → 응답의 result. 원본(response)·stages 를 빼고 documents·findings·overall 을 더한다.

    format·job·summary 등 나머지 키는 그대로. include_stages 면 stages(response_stages — 저장된 것, 없으면 response 에서
    parse_stages, 너무 깊거나 만들지 못하면 []).
    """
    out = {key: value for key, value in result.items() if key not in ("response", "stages")}
    out.update(build_view(result))
    if include_stages:
        out["stages"] = response_stages(result)
    return out


def analysis_out(
    row: Mapping[str, Any],
    *,
    include_stages: bool = False,
    upstage_status: str | None = None,
    poll_error: str | None = None,
) -> dict[str, Any]:
    """analyses 행 → AnalysisOut. agent_id 는 빼고, result 는 result_out(원본·stages 없이 화면용 값).

    문자열·키는 원문 그대로(짝 없는 서로게이트 포함) — 응답으로 보내는 방식은 api/index.py 의 _json_out 이 정한다.
    """
    result = row.get("result")
    result = result_out(result, include_stages=include_stages) if isinstance(result, Mapping) else None
    documents = row.get("documents")
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "status": row.get("status"),
        "upstage_job_id": row.get("upstage_job_id"),
        "error": row.get("error"),
        "result": result,
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "documents": [document_out(d) for d in documents if isinstance(d, Mapping)]
        if isinstance(documents, list)
        else [],
        "upstage_status": upstage_status,
        "poll_error": poll_error,
    }


# --- 결과 저장 형식 ----------------------------------------------------------------


def _contains_secret(value: Any, secrets: Mapping[str, str]) -> bool:
    blob = json.dumps(value, ensure_ascii=False, default=str)
    return any(len(secret) >= 4 and secret in blob for secret in secrets)


def build_result(response: Mapping[str, Any], config_id: str, secrets: Mapping[str, str] | None = None) -> dict:
    """include[]=all 응답 → analyses.result(imask-upstage-v1). 요약을 못 뽑아도 예외 없음(값이 None)."""
    stages = parse_stages(response)
    summary = summarize(stages)
    created_at = response.get("created_at")
    usage = response.get("usage")
    result: dict[str, Any] = {
        "format": RESULT_FORMAT,
        "job": {
            "id": response.get("id"),
            "status": response.get("status"),
            "config_id": config_id,
            "created_at": created_at if isinstance(created_at, int) and not isinstance(created_at, bool) else None,
            "usage": dict(usage) if isinstance(usage, Mapping) else None,
        },
        "summary": summary,
        "stages": stages,
        # 원본 그대로 두되 최상위 model(에이전트 id 가 되돌아옴)만 뺀다
        "response": {key: value for key, value in response.items() if key != "model"},
    }
    # 키·접근 코드·에이전트 id 가 어딘가 섞여 왔으면(정상 응답에는 없다) 통째로 가린다
    if secrets and _contains_secret(result, secrets):
        logger.warning("Upstage 결과에 가릴 값이 섞여 있어 가린 뒤 저장합니다")
        result = redact_value(result, secrets)
    return result


# --- 공통 도우미 -------------------------------------------------------------------


def _uuid_or_404(value: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise ApiError(404, MSG_NOT_FOUND) from None


def _load(store: Store, analysis_id: str) -> dict[str, Any]:
    row = store.get_analysis(analysis_id)  # StoreError → api 가 502
    if row is None:
        raise ApiError(404, MSG_NOT_FOUND)
    return row


def _read_latest(store: Store, analysis_id: str) -> dict[str, Any] | None:
    """최신 행. 읽지 못했거나 없으면 None."""
    try:
        return store.get_analysis(analysis_id)
    except StoreError:
        return None


def _reread(store: Store, analysis_id: str, fallback: Mapping[str, Any]) -> dict[str, Any]:
    """**갱신에 이긴 뒤** 다시 읽는다. 읽지 못하면 저장에 성공한 값으로 만든 대체 행(갱신은 이미 끝났으므로).

    조건부 갱신에 **진** 경우에는 쓰지 않는다 — 반영하지 못한 값을 확정된 것처럼 내보내지 않게
    _read_latest 로 승자의 행을 읽고, 그것도 실패하면 조회는 poll_error, 시작은 502 로 다시 확인하게 한다.
    """
    row = _read_latest(store, analysis_id)
    return row if row is not None else dict(fallback)


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _file_ids(documents: Iterable[Any]) -> list[str]:
    ids = [d.get("upstage_file_id") for d in documents if isinstance(d, Mapping)]
    return [i for i in ids if isinstance(i, str) and i]


def _delete_upstage_files(client: UpstageAPI, file_ids: Sequence[str], secrets: Mapping[str, str]) -> None:
    """Upstage 파일을 지운다(404 는 이미 지움 = 성공). 실패는 로그만 — 분석 결과를 바꾸지 않는다."""
    for file_id in dict.fromkeys(file_ids):
        try:
            if not client.delete_file(file_id):
                logger.warning("Upstage 파일 삭제가 거절됨: %s", _scrub(file_id, secrets, 100))
        except (UpstageError, ValueError) as exc:
            reason = exc.message if isinstance(exc, UpstageError) else type(exc).__name__
            logger.warning("Upstage 파일 삭제 실패: %s: %s", _scrub(file_id, secrets, 100), _scrub(reason, secrets))


def _scrub(text: Any, secrets: Mapping[str, str], limit: int | None = MAX_ERROR_LENGTH) -> str:
    """바깥에서 온 문자열이 응답·DB·로그로 나가는 유일한 경계.

    서버 비밀값 전체(settings.secrets())·인증 문구·서명 URL·토큰·JWT 를 가린 뒤에 길이를 자른다.
    """
    return redact(text, secrets, limit=limit)


# --- 1. 만들기 ---------------------------------------------------------------------


def create_analysis(
    store: Store, *, name: str | None, filename: str, size: int, mime_type: str
) -> tuple[dict[str, Any], dict[str, str]]:
    """analyses·documents 행과 서명 업로드 URL 을 만든다 → (분석 행 + documents, upload).

    검사 실패는 ApiError(400), 중간 실패는 만든 행을 지우고 ApiError(502).
    """
    try:
        checked = check_upload(filename, size, mime_type)
        title = analysis_name(name, checked.filename)
    except ValueError as exc:  # FileCheckError
        raise ApiError(400, getattr(exc, "message", str(exc))) from None

    try:
        analysis = store.insert_analysis(title)
    except StoreError:
        raise ApiError(502, MSG_PREPARE_FAILED) from None

    analysis_id = str(analysis.get("id"))
    path = f"analyses/{analysis_id}/{checked.safe_name}"
    try:
        document = store.insert_document(
            analysis_id,
            filename=checked.filename,
            storage_path=path,
            size_bytes=checked.size,
            mime_type=checked.mime_type,
        )
        signed = store.create_signed_upload_url(path)
    except StoreError:
        try:
            store.delete_analysis(analysis_id)  # 문서 행은 cascade 로 함께 지워진다
        except StoreError:
            logger.warning("준비 실패 뒤 분석 행을 지우지 못함: %s", analysis_id)
        raise ApiError(502, MSG_PREPARE_FAILED) from None

    row = {**analysis, "documents": [document]}
    upload = {"bucket": STORAGE_BUCKET, "path": path, "token": signed["token"], "signed_url": signed["signed_url"]}
    return row, upload


# --- 2. 시작 -----------------------------------------------------------------------


class _StartFailed(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@dataclass
class _StartProgress:
    """시작 중 이미 한 일(정리·대체 응답에 쓴다). 저장에 성공한 값은 응답에서 빠지지 않게 한다."""

    doc_id: str | None = None
    file_id: str | None = None  # Upstage 에 올린 파일
    file_saved: bool = False  # documents.upstage_file_id 에 저장됨
    job_row: dict[str, Any] | None = None  # job id 를 저장한 뒤의 analyses 행(갱신 응답)
    lost_race: bool = False  # job id 저장 전에 다른 요청이 행을 바꿈(만료 처리 등)


def _run_start(
    store: Store,
    client: UpstageAPI,
    *,
    analysis_id: str,
    documents: Sequence[Mapping[str, Any]],
    agent_id: str,
    config_id: str,
    secrets: Mapping[str, str],
    progress: _StartProgress,
) -> None:
    """선점한 분석을 Upstage 에 넘긴다. 실패는 _StartFailed(화면 문장). 한 일은 progress 에 남긴다."""
    if not documents:
        raise _StartFailed(MSG_NO_DOCUMENT)
    doc = documents[0]  # 분석 1건 = 묶음 파일 1개
    progress.doc_id = str(doc.get("id"))
    path = str(doc.get("storage_path") or "")
    mime_type = str(doc.get("mime_type") or "")

    try:
        content = store.download(path)
    except StoreError:
        raise _StartFailed(MSG_FILE_READ_FAILED) from None
    if content is None:
        raise _StartFailed(MSG_FILE_MISSING)
    if len(content) > MAX_FILE_BYTES:
        raise _StartFailed(MSG_FILE_TOO_LARGE)
    if not content_matches(content, mime_type):
        raise _StartFailed(MSG_CONTENT_MISMATCH)

    # Upstage 에도 안전한 이름으로 올린다(저장 경로의 마지막 부분 = safe_storage_name)
    upload_name = path.rsplit("/", 1)[-1] or safe_storage_name(str(doc.get("filename") or ""))
    try:
        file_id = client.upload_file(upload_name, content, mime_type)
    except UpstageError as exc:
        raise _StartFailed(MSG_UPSTAGE_START.format(reason=exc.message)) from None
    progress.file_id = file_id

    try:
        store.update_document(progress.doc_id, {"upstage_file_id": file_id})
    except StoreError:
        raise _StartFailed(MSG_START_SAVE_FAILED) from None
    progress.file_saved = True

    try:
        job = client.create_job(agent_id, config_id, file_id)
    except UpstageError as exc:
        raise _StartFailed(MSG_UPSTAGE_START.format(reason=exc.message)) from None
    status = job.get("status")
    if isinstance(status, str) and status and is_terminal(status) and not is_success(status):
        # 실패 이유는 서버 비밀값 전체로 가린 뒤 자른다(클라이언트가 아는 값만으로 자르지 않게)
        raise _StartFailed(MSG_UPSTAGE_START.format(reason=job_failure_message(job, secrets)))

    try:
        saved = store.update_analysis(
            analysis_id,
            {"upstage_job_id": job["id"], "agent_id": agent_id},
            expect_status=RUNNING,
            expect_no_job=True,
        )
    except StoreError:
        raise _StartFailed(MSG_START_SAVE_FAILED) from None
    if saved is None:
        # 그 사이 다른 요청이 이 분석을 끝냈다(예: 시작이 너무 오래 걸려 실패로 바뀜) — 올린 파일만 정리
        logger.warning("시작 결과를 저장하기 전에 분석 상태가 바뀜: %s", analysis_id)
        progress.lost_race = True
        return
    progress.job_row = saved  # 정상: 파일은 작업이 끝난 뒤 조회 쪽에서 지운다


def _documents_with(documents: Sequence[Mapping[str, Any]], progress: _StartProgress) -> list[dict[str, Any]]:
    """DB 에 저장한 upstage_file_id 를 문서 행에 반영한다(대체 응답용)."""
    docs = [dict(d) for d in documents]
    if progress.file_saved and progress.file_id:
        for doc in docs:
            if str(doc.get("id")) == progress.doc_id:
                doc["upstage_file_id"] = progress.file_id
    return docs


def start_analysis(
    store: Store, upstage: UpstageFactory, settings: Settings, analysis_id: str
) -> dict[str, Any]:
    """queued 분석을 선점해 Upstage 작업을 만든다(완료를 기다리지 않음) → 분석 행.

    404·409 는 ApiError. 선점 뒤 실패는 failed 행으로 돌려주고, 실패 표시조차 못 하면 ApiError(502).
    마지막 다시 읽기가 실패하면 대체 행을 돌려주는데, 저장에 성공한 값(job id·file id·상태)은 넣는다.
    """
    analysis_id = _uuid_or_404(analysis_id)
    row = _load(store, analysis_id)
    if row.get("status") != QUEUED:
        raise ApiError(409, MSG_ALREADY_STARTED)
    # 설정이 빠졌으면 선점 전에 멈춘다(ConfigError → 500, 행은 queued 그대로)
    conf = settings.upstage()
    client = upstage()
    secrets = settings.secrets()

    claimed = store.claim_analysis(analysis_id)
    if claimed is None:
        raise ApiError(409, MSG_ALREADY_STARTED)

    documents = [d for d in row.get("documents") or [] if isinstance(d, Mapping)]
    progress = _StartProgress()
    failure: str | None = None
    try:
        _run_start(
            store,
            client,
            analysis_id=analysis_id,
            documents=documents,
            agent_id=conf.agent_id,
            config_id=conf.config_id,
            secrets=secrets,
            progress=progress,
        )
    except _StartFailed as exc:
        failure = exc.message
    except Exception as exc:  # 예상 못 한 오류 — 행을 running 으로 남기지 않는다
        logger.error("분석 시작 중 예상 못 한 오류: %s", _scrub(f"{type(exc).__name__}: {exc}", secrets, 300))
        failure = MSG_START_INTERNAL

    # 작업으로 이어지지 않았으면 올린 파일을 지운다(이어졌으면 끝난 뒤 조회 쪽에서 지운다)
    if progress.file_id and progress.job_row is None:
        _delete_upstage_files(client, [progress.file_id], secrets)

    base = {**row, **claimed, "documents": _documents_with(documents, progress)}
    if failure is not None:
        error = _scrub(failure, secrets)
        try:
            recorded = store.update_analysis(analysis_id, {"status": FAILED, "error": error}, expect_status=RUNNING)
        except StoreError:
            raise ApiError(502, MSG_START_RECORD_FAILED) from None
        if recorded is None:  # 실패 기록에 짐 — 다른 요청(만료 처리)이 먼저 행을 바꿨다
            return _latest_or_502(store, analysis_id)
        fallback = {**base, **recorded}
    elif progress.job_row is not None:
        fallback = {**base, **progress.job_row}  # running + upstage_job_id
    else:  # progress.lost_race — job id 저장 전에 만료 처리가 이 분석을 바꿨다
        return _latest_or_502(store, analysis_id)
    fallback["documents"] = base["documents"]
    return _reread(store, analysis_id, fallback)


def _latest_or_502(store: Store, analysis_id: str) -> dict[str, Any]:
    """조건부 갱신에 진 시작: 승자가 저장한 최신 행. 다시 읽지 못하면 상태를 지어내지 않고 502."""
    latest = _read_latest(store, analysis_id)
    if latest is None:
        raise ApiError(502, MSG_START_REREAD_FAILED)
    return latest


# --- 3. 조회 -----------------------------------------------------------------------


def _failure_reason(job: Mapping[str, Any], secrets: Mapping[str, str]) -> str:
    """실패 이유: error.message·incomplete_details(T1 job_failure_message), 없으면 상태 값.

    클라이언트가 아는 값(Upstage 키·에이전트 id)이 아니라 서버 비밀값 전체로 가린 뒤 자른다.
    """
    reason = job_failure_message(job, secrets)
    status = job.get("status")
    # 이유 필드가 없을 때 T1 문구는 '…(상태: x)' 꼴이다 — 계약대로 상태 값만 쓴다
    if reason == job_failure_message({"status": status}, secrets):
        reason = _scrub(status if isinstance(status, str) and status else "알 수 없음", secrets, MAX_STATUS_LENGTH)
    return reason


def _log_save_failure(exc: StoreError, secrets: Mapping[str, str]) -> None:
    logger.warning("분석 상태 저장 실패: %s", _scrub(exc.message, secrets))


def _job_gone(exc: UpstageError, row: Mapping[str, Any], now: datetime) -> bool:
    """Upstage 404 이고 job id 를 저장한 지(updated_at) 2분이 지났으면 없어진 작업으로 본다."""
    if exc.status_code != 404:
        return False
    updated_at = _parse_time(row.get("updated_at"))
    return updated_at is not None and now - updated_at > JOB_NOT_FOUND_GRACE


def _finish(
    store: Store,
    client: UpstageAPI,
    row: dict[str, Any],
    analysis_id: str,
    values: dict[str, Any],
    secrets: Mapping[str, str],
    shown_status: str | None,
) -> PollResult:
    """끝난 작업을 조건부 갱신(status='running')으로 반영하고 Upstage 파일을 지운다."""
    try:
        updated = store.update_analysis(analysis_id, values, expect_status=RUNNING)
    except StoreError as exc:
        _log_save_failure(exc, secrets)
        return PollResult(row, shown_status, MSG_SAVE_FAILED)  # 파일은 두고 다음 조회에서 다시 처리한다
    # 반영했든(바뀐 행 1) 다른 조회가 먼저 했든(0) 작업은 끝났다 — 파일을 지운다(두 번째 삭제의 404 는 성공)
    _delete_upstage_files(client, _file_ids(row.get("documents") or []), secrets)
    if updated is None:
        # 조건부 갱신에 짐 — 다른 조회가 먼저 저장했다(그쪽이 본 Upstage 상태가 다를 수 있음).
        # 반영하지 못한 values 를 확정된 것처럼 내보내지 않는다: 승자의 행, 읽지 못하면 조회 전 running 행 + poll_error.
        latest = _read_latest(store, analysis_id)
        if latest is None:
            return PollResult(row, shown_status, MSG_REREAD_FAILED)
        return PollResult(latest, shown_status)
    # 이김: 다시 읽기가 실패하면 갱신 응답 행 + 처음 읽은 문서 행(file id)으로
    fallback = {**row, **updated, "documents": row.get("documents") or []}
    return PollResult(_reread(store, analysis_id, fallback), shown_status)


def _fail_stale_start(
    store: Store,
    upstage: UpstageFactory,
    row: dict[str, Any],
    analysis_id: str,
    now: datetime,
    secrets: Mapping[str, str],
) -> PollResult:
    updated_at = _parse_time(row.get("updated_at"))
    if updated_at is None or now - updated_at <= STALE_START:
        return PollResult(row)
    values = {"status": FAILED, "error": MSG_START_STALE}
    try:
        saved = store.update_analysis(analysis_id, values, expect_status=RUNNING, expect_no_job=True)
    except StoreError as exc:
        _log_save_failure(exc, secrets)
        return PollResult(row, poll_error=MSG_SAVE_FAILED)
    if saved is None:
        # 그 사이 다른 요청이 행을 바꿨다(예: 시작 요청이 job id 저장에 성공 → 작업이 돌고 있음).
        # 최신 행을 돌려주고 파일은 건드리지 않는다 — 실행 중인 작업의 입력을 지우지 않게.
        # 다시 읽지 못하면 조회 전 running 행 + poll_error(다음 조회에서 다시 확인).
        latest = _read_latest(store, analysis_id)
        if latest is None:
            return PollResult(row, poll_error=MSG_REREAD_FAILED)
        return PollResult(latest)
    latest = _reread(store, analysis_id, {**row, **saved})
    # 실제로 failed 로 바꾼 경우에만: 시작 요청이 파일만 올리고 멈췄을 수 있다
    file_ids = _file_ids([*(row.get("documents") or []), *(latest.get("documents") or [])])
    if file_ids:
        try:
            _delete_upstage_files(upstage(), file_ids, secrets)
        except ConfigError:
            logger.warning("Upstage 설정이 없어 남은 파일을 지우지 못함: %s", analysis_id)
    return PollResult(latest)


def poll_analysis(
    store: Store,
    upstage: UpstageFactory,
    settings: Settings,
    analysis_id: str,
    *,
    now: datetime | None = None,
) -> PollResult:
    """분석 행을 읽고, running 이면 Upstage 상태를 한 번 확인해 끝났으면 반영한다."""
    analysis_id = _uuid_or_404(analysis_id)
    row = _load(store, analysis_id)
    if row.get("status") != RUNNING:
        return PollResult(row)
    now = now or datetime.now(UTC)
    secrets = settings.secrets()
    job_id = row.get("upstage_job_id")
    if not isinstance(job_id, str) or not job_id:
        return _fail_stale_start(store, upstage, row, analysis_id, now, secrets)

    client = upstage()  # ConfigError → 500
    gone = {"status": FAILED, "error": MSG_JOB_NOT_FOUND}
    try:
        job = client.get_job(job_id, "last")
    except UpstageError as exc:
        if _job_gone(exc, row, now):
            return _finish(store, client, row, analysis_id, dict(gone), secrets, None)
        # 401·403·429·5xx·연결 오류·만든 직후의 404 — 상태를 바꾸지 않고 다음 조회에서 다시
        return PollResult(row, poll_error=_scrub(MSG_POLL_FAILED.format(reason=exc.message), secrets))
    status = job.get("status")
    if not isinstance(status, str) or not status:
        return PollResult(row, poll_error=MSG_POLL_NO_STATUS)
    shown_status = _scrub(status, secrets, MAX_STATUS_LENGTH)
    if status in PENDING_STATUSES:
        return PollResult(row, upstage_status=shown_status)

    if is_success(status):
        try:
            full = client.get_job(job_id, "all")
        except UpstageError as exc:
            if _job_gone(exc, row, now):
                return _finish(store, client, row, analysis_id, dict(gone), secrets, shown_status)
            reason = MSG_RESULT_FETCH_FAILED.format(reason=exc.message)
            return PollResult(row, shown_status, _scrub(reason, secrets))
        result = build_result(full, settings.upstage().config_id, secrets)
        stage_names = result["summary"].get("stage_names") or []
        # 첫 실행에서 output[].model 목록을 남긴다(값 없이 이름만)
        logger.info(
            "Upstage 작업 완료 %s, 단계: %s",
            _scrub(job_id, secrets, 100),
            _scrub(", ".join(map(str, stage_names)), secrets, None),
        )
        values: dict[str, Any] = {"status": DONE, "result": result, "error": None}
    else:
        reason = _failure_reason(job, secrets)
        values = {"status": FAILED, "error": _scrub(MSG_UPSTAGE_FAILED.format(reason=reason), secrets)}
    return _finish(store, client, row, analysis_id, values, secrets, shown_status)


# --- 4. 원본 파일 주소 ---------------------------------------------------------------


def file_link(store: Store, analysis_id: str) -> dict[str, Any]:
    """분석 건의 원본 파일 서명 다운로드 URL(10분) → {"url", "mime_type", "filename"}. 상태와 상관없이.

    404: uuid 아님·행 없음(분석 건) → 문서 행 없음·storage_path 빔·객체 없음(원본 파일). 502: 주소 만들기 실패.
    filename 은 원래 이름(documents.filename). 서명 URL 은 로그에 남기지 않는다.
    """
    analysis_id = _uuid_or_404(analysis_id)
    row = _load(store, analysis_id)  # StoreError → api 가 502
    documents = row.get("documents")
    docs = [d for d in documents if isinstance(d, Mapping)] if isinstance(documents, list) else []
    doc = docs[0] if docs else None  # 분석 1건 = 묶음 파일 1개
    path = doc.get("storage_path") if doc is not None else None
    if doc is None or not isinstance(path, str) or not path.strip():
        raise ApiError(404, MSG_ORIGINAL_MISSING)
    try:
        url = store.create_signed_download_url(path, SIGNED_DOWNLOAD_SECONDS)
    except StoreError:
        raise ApiError(502, MSG_ORIGINAL_LINK_FAILED) from None
    if not isinstance(url, str) or not url:
        raise ApiError(404, MSG_ORIGINAL_MISSING)
    return {"url": url, "mime_type": doc.get("mime_type"), "filename": doc.get("filename")}
