# ==========================================================================
#  실제 분석 공유 목록·삭제·다시 분석 (FastAPI 와 무관해 단위 테스트할 수 있다)
#  계약: .orchestration/shared-analyses/BRIEF.md §5.2~5.6. 로그인 없이 주소를 아는 누구나 모든 분석을 보고·지우고·다시
#  분석한다(대회용으로 받아들인 위험). 완료(done) 분석의 analyses 행은 쓰지 않는다(updated_at 트리거).
#
#  - 목록(list_out): 질의 limit 은 정확히 한 번·^[0-9]{1,3}$·1~200 일 때만(없으면 100, 그 밖 400 — parse_limit).
#    저장소 질의 한 번(store.list_analyses — result 열 전체 없이 JSON 경로 두 값만). Upstage 를 부르지 않고 쓰지 않는다.
#    항목: id·name·status·error·created_at·updated_at·started_at·documents(올린 파일 — filename·size_bytes·mime_type,
#    만든 순)·risk_level(문자열만)·review(list_review — done 이고 서류 수가 bool 아닌 정수 ≥ 1 이면 검토 행 status 가
#    'done' 일 때 'done', 그 밖 'needed' / 그 밖 분석 'none'). 상세는 build_view 의 유효 서류로 '검토할 수 있음'을 보므로
#    서류 수 ≥ 1 인데 유효 서류 0 인 결과는 목록 needed·상세 review null 로 어긋난다(알려진 차이 — 고치지 않음).
#    행 하나를 만들다 예외가 나면 값 없는 경고 후 그 행만 뺀다.
#  - 삭제(delete_analysis): 404(uuid 아님·행 없음) → Storage 원본 지우기(없음이 확인된 객체는 성공, 남았거나 확인
#    실패면 502 — 행을 지우지 않는다: 원본이 버킷에 남은 채 행만 사라지지 않게, store.remove_objects) → 행 지우기(읽은
#    실행만 — id + 읽은 updated_at. 0행이면 다시 읽어 없으면 404, 바뀌었으면 새로 읽은 행으로 Storage·행 지우기를 다시, 모두
#    3번 지면 409, 오류 502) → Upstage 파일 지우기(실제로 지운 행 = 마지막 읽기의 문서 file id 로. 최선 — httpx 단계별
#    시간 제한(연결 5초·읽기·쓰기·풀 10초) 클라이언트로,
#    전체 마감은 아니어서 바이트를 조금씩 흘리는 응답이면 더 길어질 수 있다. 실패·설정 없음은 file id·예외 종류·HTTP 상태만
#    남기는 경고, 지울 file id 가 없으면 클라이언트를 만들지 않음).
#    상태와 상관없이 지운다. analyses 행을 갱신하지 않는다. 진행 중인 Upstage 작업은 취소 API 가 없어 결과를 버린다.
#  - 다시 분석(retry_out): 본문 {"actor"} 하나(parse_retry_body — 검토 동작과 같은 parse_json·_actor_ok).
#    오류 순서 404 → 409(queued·running '이미 분석하고 있습니다.' / 그 밖 '실패한 분석만…') → 500(Upstage 설정, 아무것도
#    바꾸지 않은 채) → 되돌리기(failed → queued 조건부 — status=failed + updated_at = 처음 읽은 값(그 사이 다른 요청이
#    한 바퀴 돌아 다시 failed 가 된 행을 같은 실행으로 착각하지 않게), error·result·upstage_job_id 비우고 started_at = 지금;
#    지면 다시 읽어 404 / 409 두 문구 / 502) → 이력 한 줄(kind 'retry' — 검토 행 version 조건부 쓰기, 실패해도 계속) → 기존
#    start_analysis(선점 → 원본 → Upstage 올리기·작업 만들기; 시작의 409 '이미 시작한 분석입니다.' 는 '이미 분석하고
#    있습니다.' 로 — 단 다시 읽어 행이 없으면(그 사이 지워짐) 404). 응답은 조회와 같은 AnalysisOut(review 는 규칙대로 —
#    대기·분석 중·실패면 null).
#  로그·StoreError 문구에는 고정 문구·분석 id·파일 경로·Upstage file id·예외 종류·HTTP 상태·짧은 코드까지만(바깥 오류 원문·
#  분석 이름·오류 원문·이력 글·서명 URL 없음 — BRIEF §4). 로그에 넣는 id·경로도 _scrub(값, secrets, 100)(_log_id)을 지난다.
# ==========================================================================

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from .analyses import (
    DONE,
    FAILED,
    MSG_ALREADY_STARTED,
    MSG_NOT_FOUND,
    QUEUED,
    RUNNING,
    ApiError,
    UpstageAPI,
    UpstageFactory,
    _load,
    _scrub,
    _uuid_or_404,
    start_analysis,
)
from .config import ConfigError
from .upstage import UpstageError
from .reviews import (
    ANALYSIS_TARGET,
    MAX_TEXT,
    MSG_BAD_ACTOR,
    MSG_BAD_REQUEST,
    HistoryFull,
    _actor_ok,
    _is_int,
    analysis_read_out,
    append_history_line,
    js_trim,
    parse_json,
    safe_line_text,
    safe_target,
)
from .settings import Settings
from .store import Store, StoreError

logger = logging.getLogger("imask.manage")

# --- 목록 ---------------------------------------------------------------------------------
DEFAULT_LIMIT = 100
MAX_LIMIT = 200
_LIMIT_RE = re.compile(r"[0-9]{1,3}")  # ASCII 숫자만(\d 는 다른 문자의 숫자도 받는다), fullmatch 로만 쓴다

# --- 사용자에게 보이는 문장 -------------------------------------------------------------------
MSG_BUSY = "이미 분석하고 있습니다."
MSG_ONLY_FAILED = "실패한 분석만 다시 분석할 수 있습니다."
MSG_RETRY_CONFLICT = "다른 요청과 겹쳐 다시 분석하지 못했습니다. 잠시 후 다시 시도해 주세요."
MSG_DELETE_FILES_FAILED = "원본 파일을 지우지 못했습니다. 잠시 후 다시 시도해 주세요."
MSG_DELETE_ROW_FAILED = "분석을 지우지 못했습니다. 잠시 후 다시 시도해 주세요."

# --- 삭제 ---------------------------------------------------------------------------------
MAX_DELETE_ATTEMPTS = 3  # 읽은 실행만 지우기: 처음 + 다시 2번(§5.3 3단계)

# --- 다시 분석 이력 줄 ------------------------------------------------------------------------
RETRY_KIND = "retry"
RETRY_CHANGE = "같은 파일로 다시 분석 요청"


# --- 1. 목록 -------------------------------------------------------------------------------


def parse_limit(values: Sequence[str]) -> int:
    """?limit= 값들(request.query_params.getlist) → 개수. 없으면 100, 정확히 한 번·숫자 1~3자리·1~200 이 아니면 400."""
    if not values:
        return DEFAULT_LIMIT
    if len(values) != 1 or not _LIMIT_RE.fullmatch(values[0]):
        raise ApiError(400, MSG_BAD_REQUEST)
    limit = int(values[0])
    if not 1 <= limit <= MAX_LIMIT:
        raise ApiError(400, MSG_BAD_REQUEST)
    return limit


def _first_object(value: Any) -> Mapping[str, Any] | None:
    """1:1 끼워 넣기 값 — 객체면 그대로, 목록이면 첫 객체, 그 밖 None."""
    if isinstance(value, Mapping):
        return value
    if isinstance(value, list):
        return next((item for item in value if isinstance(item, Mapping)), None)
    return None


def list_review(status: Any, document_count: Any, embedded: Any) -> str:
    """목록 항목의 검토 상태(BRIEF §5.2): 'done' · 'needed' · 'none'."""
    if status != DONE or not (_is_int(document_count) and document_count >= 1):
        return "none"
    record = _first_object(embedded)
    return "done" if record is not None and record.get("status") == "done" else "needed"


def _list_documents(documents: Any) -> list[dict[str, Any]]:
    """올린 파일 행 → 만든 순(created_at, 같으면 id) 키 셋만. 객체가 아닌 것은 빼고, 목록이 아니면 []."""
    if not isinstance(documents, list):
        return []
    docs = [d for d in documents if isinstance(d, Mapping)]
    docs.sort(key=lambda d: (str(d.get("created_at") or ""), str(d.get("id") or "")))
    return [{"filename": d.get("filename"), "size_bytes": d.get("size_bytes"), "mime_type": d.get("mime_type")} for d in docs]


def list_item(row: Mapping[str, Any]) -> dict[str, Any]:
    """목록 행(store.LIST_SELECT 모양) → 응답 항목. 행이 객체가 아니면 TypeError(부르는 쪽이 그 행만 뺀다)."""
    if not isinstance(row, Mapping):
        raise TypeError("목록 행이 객체가 아닙니다")
    status = row.get("status")
    risk_level = row.get("risk_level")
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "status": status,
        "error": row.get("error"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "started_at": row.get("started_at"),
        "documents": _list_documents(row.get("documents")),
        "risk_level": risk_level if isinstance(risk_level, str) else None,
        "review": list_review(status, row.get("document_count"), row.get("analysis_reviews")),
    }


def list_out(store: Store, limit: int) -> dict[str, Any]:
    """GET /api/py/analyses 응답 {"analyses": [...]}(DB 순서 그대로). 저장소 오류는 StoreError(api 가 502)."""
    rows = store.list_analyses(limit)
    items: list[dict[str, Any]] = []
    for row in rows:
        try:
            items.append(list_item(row))
        except Exception as exc:  # 목록 전체가 500 이 되지 않게 — 값 없이 예외 종류만
            logger.warning("목록 행 하나를 만들지 못해 뺍니다: %s", type(exc).__name__)
    return {"analyses": items}


# --- 2. 삭제 -------------------------------------------------------------------------------


def _unique_strings(documents: Sequence[Mapping[str, Any]], key: str) -> list[str]:
    values = (doc.get(key) for doc in documents)
    return list(dict.fromkeys(v for v in values if isinstance(v, str) and v))


def _log_id(value: Any, secrets: Mapping[str, str]) -> str:
    """로그에 넣는 id·경로(분석 id·Upstage file id·저장 경로)도 DB·바깥에서 온 문자열 — 기존 _scrub 경계(비밀값·서명 URL·
    토큰 가림 + 100자 자르기)를 지나게 한다(BRIEF §4, V-T1-2 R3)."""
    return _scrub(value, secrets, 100)


def _delete_files_quietly(client: UpstageAPI, file_ids: Sequence[str], secrets: Mapping[str, str]) -> None:
    """Upstage 파일을 하나씩 지운다(404 는 이미 지움 = 성공). 실패는 가린 file id + 예외 종류(+ HTTP 상태)만 경고한다 —
    Upstage 오류 message 는 가려서라도 남기지 않는다(BRIEF §4). 지우기 요청에는 원래 id 를 쓴다.
    기존 조회·시작의 _delete_upstage_files 는 그대로 둔다."""
    for file_id in dict.fromkeys(file_ids):
        try:
            if not client.delete_file(file_id):
                logger.warning("지운 분석의 Upstage 파일 삭제가 거절됨: %s", _log_id(file_id, secrets))
        except UpstageError as exc:
            status = f" HTTP {exc.status_code}" if isinstance(exc.status_code, int) else ""
            logger.warning("지운 분석의 Upstage 파일 삭제 실패: %s: UpstageError%s", _log_id(file_id, secrets), status)
        except ValueError as exc:
            logger.warning("지운 분석의 Upstage 파일 삭제 실패: %s: %s", _log_id(file_id, secrets), type(exc).__name__)


def _cleanup_upstage(
    cleanup: UpstageFactory, file_ids: Sequence[str], analysis_id: str, secrets: Mapping[str, str]
) -> None:
    """행을 지운 뒤 Upstage 파일 지우기(최선). 실패·설정 없음은 값 없는 경고만 — 응답은 그대로 204."""
    if not file_ids:
        return  # 클라이언트를 만들지도 않는다
    try:
        client: UpstageAPI = cleanup()
        _delete_files_quietly(client, file_ids, secrets)  # UpstageError(시간 초과 포함)·ValueError 는 여기서 경고
    except ConfigError:
        logger.warning("Upstage 설정이 없어 지운 분석의 Upstage 파일을 지우지 못함: %s", _log_id(analysis_id, secrets))
    except Exception as exc:
        logger.warning("지운 분석의 Upstage 파일을 지우지 못함: %s: %s", _log_id(analysis_id, secrets), type(exc).__name__)


def _documents(row: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [d for d in row.get("documents") or [] if isinstance(d, Mapping)]


def delete_analysis(store: Store, cleanup: UpstageFactory, settings: Settings, analysis_id: str) -> None:
    """분석 하나를 원본 파일·문서 행·검토 기록과 함께 지운다(BRIEF §5.3). 성공이면 None(api 가 204).

    읽은 실행만 지운다(§5.3 3단계 — V-T1-2 R2): 행 지우기는 id + 읽은 updated_at 조건. 0행이면 다시 읽어 없으면 404,
    바뀌었으면(그 사이 다시 분석 등) 새로 읽은 행으로 Storage·행 지우기를 다시(처음 포함 MAX_DELETE_ATTEMPTS 번), 모두 지면
    409. Upstage 정리는 실제로 지운 행(마지막 읽기)의 문서 file id 로 — 지우는 사이 다시 분석이 올린 새 파일도 정리된다.
    """
    analysis_id = _uuid_or_404(analysis_id)
    secrets = settings.secrets()
    row = _load(store, analysis_id)  # 없으면 404, StoreError → 502
    for _attempt in range(MAX_DELETE_ATTEMPTS):
        documents = _documents(row)
        paths = _unique_strings(documents, "storage_path")
        try:
            if paths:
                store.remove_objects(paths)
        except StoreError:
            logger.warning("원본 파일을 지우지 못해 분석 행을 두고 멈춤: %s", _log_id(analysis_id, secrets))
            raise ApiError(502, MSG_DELETE_FILES_FAILED) from None

        stamp = row.get("updated_at")
        try:
            deleted = store.delete_analysis(
                analysis_id, expect_updated_at=stamp if isinstance(stamp, str) and stamp else None
            )
        except StoreError:
            logger.warning("분석 행을 지우지 못함: %s", _log_id(analysis_id, secrets))
            raise ApiError(502, MSG_DELETE_ROW_FAILED) from None
        if deleted >= 1:
            _cleanup_upstage(cleanup, _unique_strings(documents, "upstage_file_id"), analysis_id, secrets)
            return
        # 0행: 그 사이 지워졌거나(404) 다른 요청이 행을 바꿨다(다시 읽은 실행으로 다시)
        latest = store.get_analysis(analysis_id)  # StoreError → 502
        if latest is None:
            raise ApiError(404, MSG_NOT_FOUND)
        logger.info("지우는 동안 분석 행이 바뀌어 다시 읽은 실행으로 다시 지웁니다: %s", _log_id(analysis_id, secrets))
        row = latest
    logger.warning("지우는 동안 분석 행이 계속 바뀌어 멈춤: %s", _log_id(analysis_id, secrets))
    raise ApiError(409, MSG_DELETE_ROW_FAILED)


# --- 3. 다시 분석 -----------------------------------------------------------------------------


def parse_retry_body(raw: bytes) -> str:
    """본문 바이트(이미 MAX_BODY_BYTES 이하) → actor. 정확히 {"actor": 문자열} 이 아니면 400, actor 규칙 위반 400."""
    body = parse_json(raw)
    if not isinstance(body, dict) or set(body) != {"actor"} or not isinstance(body["actor"], str):
        raise ApiError(400, MSG_BAD_REQUEST)
    actor = body["actor"]
    if not _actor_ok(actor):
        raise ApiError(400, MSG_BAD_ACTOR)
    return actor


def _retry_target(row: Mapping[str, Any]) -> str:
    """이력 target: 올린 파일 이름(문서 첫 행 filename — 없거나 비면 '분석 건')을 안전화."""
    documents = [d for d in row.get("documents") or [] if isinstance(d, Mapping)]
    filename = documents[0].get("filename") if documents else None
    return safe_target(filename if isinstance(filename, str) and js_trim(filename) else ANALYSIS_TARGET)


def _record_retry(
    store: Store, analysis_id: str, row: Mapping[str, Any], actor: str, now: datetime, secrets: Mapping[str, str]
) -> None:
    """다시 분석 요청을 검토 이력에 한 줄(최선). 실패해도 다시 분석은 계속한다 — 값 없는 경고만."""
    error = row.get("error")
    shown = _log_id(analysis_id, secrets)
    try:
        written = append_history_line(
            store,
            analysis_id,
            actor=actor,
            kind=RETRY_KIND,
            target=_retry_target(row),
            change=RETRY_CHANGE,
            reason=safe_line_text(error if isinstance(error, str) else "", MAX_TEXT),
            now=now,
        )
    except HistoryFull:
        logger.warning("검토 이력이 가득 차 다시 분석 이력을 남기지 못함: %s", shown)
        return
    except StoreError:
        logger.warning("다시 분석 이력을 저장하지 못함: %s", shown)
        return
    except Exception as exc:  # 이미 queued 로 되돌렸으므로 멈추지 않는다 — 값 없이 예외 종류만
        logger.warning("다시 분석 이력을 만들지 못함: %s: %s", shown, type(exc).__name__)
        return
    if written is None:
        logger.warning("다시 분석 이력 쓰기가 다른 요청과 계속 겹쳐 남기지 못함: %s", shown)


def _revert_lost(store: Store, analysis_id: str) -> ApiError:
    """되돌리기 조건부 갱신에 짐 — 다시 읽어 404 / 409 두 문구. 다시 읽기 저장소 오류는 StoreError(api 가 502)."""
    latest = store.get_analysis(analysis_id)
    if latest is None:
        return ApiError(404, MSG_NOT_FOUND)
    if latest.get("status") in (QUEUED, RUNNING):
        return ApiError(409, MSG_BUSY)
    return ApiError(409, MSG_RETRY_CONFLICT)


def retry_analysis(
    store: Store,
    upstage: UpstageFactory,
    settings: Settings,
    analysis_id: str,
    actor: str,
    *,
    now: datetime | Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """실패한 분석을 같은 원본으로 진짜 다시 분석한다(BRIEF §5.4) → 시작이 돌려준 분석 행."""
    analysis_id = _uuid_or_404(analysis_id)
    row = _load(store, analysis_id)  # 없으면 404, StoreError → 502
    status = row.get("status")
    if status in (QUEUED, RUNNING):
        raise ApiError(409, MSG_BUSY)
    if status != FAILED:
        raise ApiError(409, MSG_ONLY_FAILED)
    settings.upstage()  # 설정이 빠졌으면 아무것도 바꾸지 않은 채 ConfigError → 500

    moment = ((now() if callable(now) else now) or datetime.now(UTC)).astimezone(UTC)
    values = {"status": QUEUED, "error": None, "result": None, "upstage_job_id": None, "started_at": moment.isoformat()}
    # 처음 읽은 실행에만 맞게: status=failed + updated_at = 처음 읽은 값(트리거가 갱신마다 바꾸므로 버전 구실)
    read_stamp = row.get("updated_at")
    stamp = read_stamp if isinstance(read_stamp, str) and read_stamp else None
    if store.update_analysis(analysis_id, values, expect_status=FAILED, expect_updated_at=stamp) is None:  # StoreError → 502
        raise _revert_lost(store, analysis_id)

    _record_retry(store, analysis_id, row, actor, moment, settings.secrets())
    try:
        return start_analysis(store, upstage, settings, analysis_id)
    except ApiError as exc:
        if exc.status_code == 409 and exc.detail == MSG_ALREADY_STARTED:  # 선점에 짐 — 다른 요청이 선점했거나 지웠다
            raise _claim_lost(store, analysis_id) from None
        raise


def _claim_lost(store: Store, analysis_id: str) -> ApiError:
    """되돌린 뒤 시작의 선점에 짐: 그 사이 지워졌으면 404, 아니면(다시 읽지 못해도) '이미 분석하고 있습니다.'."""
    try:
        gone = store.get_analysis(analysis_id) is None
    except StoreError:
        gone = False
    return ApiError(404, MSG_NOT_FOUND) if gone else ApiError(409, MSG_BUSY)


def retry_out(
    store: Store,
    upstage: UpstageFactory,
    settings: Settings,
    analysis_id: str,
    actor: str,
    *,
    now: datetime | Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """POST …/retry 응답 — 조회와 같은 AnalysisOut(review 는 규칙대로, upstage_status·poll_error null, stages 없음)."""
    row = retry_analysis(store, upstage, settings, analysis_id, actor, now=now)
    return analysis_read_out(store, row)
