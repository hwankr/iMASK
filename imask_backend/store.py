# ==========================================================================
#  Supabase 테이블·Storage 접근 (supabase-py 동기 클라이언트, 서버 비밀 키)
#  - Store(Protocol): 업무 로직(analyses.py)이 쓰는 작은 인터페이스. 테스트는 메모리 가짜로 바꾼다.
#  - SupabaseStore: create_client(SUPABASE_URL, SUPABASE_SECRET_KEY) 로 analyses·documents 테이블과
#    documents 비공개 버킷을 다룬다. RLS 는 켜져 있고 정책이 없어 비밀 키(service_role)로만 읽고 쓴다.
#  - 조건부 갱신(update_analysis 의 expect_status 등): `update … where id=? and status=?` 를 한 번에
#    보내고 바뀐 행이 없으면 None. 같은 분석을 두 요청이 동시에 처리해도 한 번만 반영된다.
#  - 오류는 StoreError 하나로 감싼다. 메시지는 값 없는 짧은 문구(로그용 — 동작 이름 + 예외 종류 + 영숫자 오류 코드 + HTTP 상태)이고,
#    화면에는 업무 로직이 정한 한국어 문장만 내보낸다.
#  - 검토 행(analysis_reviews, 분석 1건당 1행 — imask_backend.reviews 가 쓴다). analyses 행은 건드리지 않는다.
#    REVIEW_COLUMNS 에 items(검토사항 해결 기록 — 마이그레이션 20261104094327)도 읽는다.
#    get_review: 행 하나(없으면 None). insert_review: upsert(on_conflict=analysis_id, ignore_duplicates) =
#    `insert … on conflict (analysis_id) do nothing` — 이미 행이 있으면 빈 응답 → None(예외로 흐름을 가르지 않는다).
#    update_review: `update … where analysis_id=? and version=?` — 바뀐 행이 없으면 None(다른 요청이 먼저 씀).
#    검토 행 오류(_review_error)는 값 없이: 동작 이름 + 예외 종류 + 영숫자 오류 코드만(바깥 오류 원문·메모·분석 id 없음).
#    분석·문서·파일 경로의 _error 도 값 없는 오류다(_quiet_error 와 같다 — 바깥 오류 원문·분석 id·경로를 넣지 않는다).
#    get_analysis(…, quiet=True)(검토 동작 경로 — 처음 읽기와 지워졌는지 다시 읽기, live-report V-T1-1 M1)는
#    검토 행과 같은 꼴(HTTP 상태 없음).
#  - 서명 다운로드 URL(create_signed_download_url): storage3 2.33 의 create_signed_url(path, expires_in) 은
#    {'signedURL', 'signedUrl'} 에 이미 절대 주소(Storage 기준 주소 + /object/sign/…?token=…)를 담아 준다.
#    다른 버전·가짜가 상대 경로를 주면 Storage 기준 주소(client.storage_url)에 붙인다. 없는 객체는 None.
#    서명 URL 은 로그에 남기지 않는다.
#  - started_at(분석을 마지막으로 시작한 시각, shared-analyses BRIEF §5.1): ANALYSIS_COLUMNS 로 읽는다.
#    claim_analysis 가 status='running' 과 같은 조건부 갱신에 started_at(서버 UTC ISO)을 넣는다. insert_analysis 는 넣지 않는다.
#  - 공유 목록(list_analyses): LIST_SELECT 한 번(result 열 전체·agent_id·upstage_job_id·storage_path·upstage_file_id 없음 —
#    위험등급·서류 수는 JSON 경로 값만), created_at desc, id desc, limit. analysis_reviews 는 1:1 이라 객체 또는 null.
#  - 삭제: remove_objects(paths) = storage3 remove(DELETE /object/{bucket}, {"prefixes": paths}). Storage 는 권한을 통과해
#    실제로 지운 객체 목록만 200 으로 돌려준다(supabase/storage deleteObjects) — 없는 경로도, 지우지 못한 경로도 목록에서
#    빠질 뿐이다. 그래서 목록에 없는 경로(목록이 아니면 모든 경로)는 storage3 info(메타데이터만)로 하나씩 확인해 '없음'이
#    확실할 때만(본문 statusCode 404 + not_found) 성공, 아직 있거나 확인 실패면 StoreError(행을 지우지 않게).
#    remove 의 예외(StorageApiError·연결 오류)도 모두 StoreError — 404 꼴이라도 성공으로 보지 않는다.
#    delete_analysis → 지운 행 수: DELETE ?id=eq.… + Prefer return=minimal,count=exact(PostgREST 는 204 + Content-Range
#    */N 으로 지운 행 수를 알린다 — 지운 행의 result 를 돌려받지 않는다). 개수 헤더가 없으면 응답 행 수(없으면 0).
#  - 새 경로의 오류(list_analyses·remove_objects·지우기 확인·delete_analysis — shared-analyses BRIEF §4)는 _quiet_error:
#    고정 동작 이름 + 예외 종류 + 영숫자 짧은 코드 + HTTP 상태만(바깥 message·details·hint 는 가려서라도 넣지 않는다).
#  - 실행 구분(§5.6): update_analysis 의 expect_job_id(upstage_job_id = 그 값)·expect_updated_at(updated_at = 읽은 문자열
#    그대로) 조건 — 다시 분석으로 같은 분석이 여러 번 실행될 때 옛 실행의 요청이 새 실행을 덮어쓰지 않게.
#    update_document 의 expect_file_id·expect_no_file(문서 upstage_file_id 비교 후 교환 — select=id 로 바뀐 행이 있었는지 돌려줌),
#    delete_analysis 의 expect_updated_at(읽은 실행만 지우기, §5.3 3단계)도 같은 뜻이다(V-T1-2 R1·R2).
#    claim_analysis 의 expect_updated_at(시작이 읽은 행일 때만 선점 — V-T1-3 v3-m1 ①)도 같다.
#  - 워크플로우 설정(workflow_settings, 한 행 — 마이그레이션 20261107034956): get_workflow_settings 는 행(없으면 None),
#    save_workflow_settings 는 upsert(id = 1). 오류는 _quiet_error(값 없이). analyses.config_id(그 분석을 시작할 때 쓴 설정 번호)도
#    ANALYSIS_COLUMNS 로 읽는다 — 이 열이 없는 DB 에 이 코드를 올리면 조회가 실패하므로 마이그레이션을 먼저 적용한다.
# ==========================================================================

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

from .settings import STORAGE_BUCKET, Settings

logger = logging.getLogger("imask.store")

# 응답에 쓰는 열만 고른다(agent_id·storage_path 는 DB 에만 — 업무 로직이 쓰므로 읽기는 한다)
ANALYSIS_COLUMNS = "id,name,status,agent_id,config_id,upstage_job_id,result,error,created_at,updated_at,started_at"
DOCUMENT_COLUMNS = "id,analysis_id,filename,storage_path,size_bytes,mime_type,upstage_file_id,created_at"
# 공유 목록(BRIEF §5.2) — 질의 한 번. result 는 JSON 경로 두 값만(분석 하나의 result 는 150~320KB), 비밀·내부 열은 넣지 않는다
LIST_SELECT = (
    "id,name,status,error,created_at,updated_at,started_at,"
    "risk_level:result->summary->>risk_level,document_count:result->summary->document_count,"
    "documents(id,filename,size_bytes,mime_type,created_at),analysis_reviews(status)"
)
REVIEW_TABLE = "analysis_reviews"
REVIEW_COLUMNS = (
    "analysis_id,status,memo,memo_at,reviewer,reviewed_at,completion_note,findings,items,history,version,created_at,updated_at"
)
WORKFLOW_TABLE = "workflow_settings"
WORKFLOW_COLUMNS = "agent_id,config_id,updated_at"
WORKFLOW_ROW_ID = 1  # 행은 하나뿐이다(테이블의 check 제약)
# 검토 행 오류 로그에 남겨도 되는 오류 코드(PostgREST PGRST205·Postgres SQLSTATE 23514 등 — 영숫자만, 16자까지)
_ERROR_CODE = re.compile(r"[A-Za-z0-9]{1,16}")
# 값 없는 오류에 남겨도 되는 HTTP 상태(세 자리 숫자만)
_HTTP_STATUS = re.compile(r"[1-5][0-9]{2}")


def utc_now_iso() -> str:
    """지금(서버 시계, UTC) ISO 8601 — started_at 처럼 서버가 정하는 시각."""
    return datetime.now(UTC).isoformat()


class StoreError(Exception):
    """Supabase 호출 실패. message 는 가린 짧은 문구(로그용)."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class Store(Protocol):
    """업무 로직이 쓰는 저장소 인터페이스(행은 dict, 시각은 ISO 8601 문자열)."""

    def get_workflow_settings(self) -> dict[str, Any] | None:
        """웹에서 저장한 워크플로우 설정(agent_id·config_id·updated_at). 저장한 적이 없으면 None."""
        ...

    def save_workflow_settings(self, agent_id: str, config_id: str) -> dict[str, Any]:
        """워크플로우 설정을 저장한다(한 행 upsert) → 저장한 행."""
        ...

    def insert_analysis(self, name: str) -> dict[str, Any]: ...

    def insert_document(
        self, analysis_id: str, *, filename: str, storage_path: str, size_bytes: int, mime_type: str
    ) -> dict[str, Any]: ...

    def delete_analysis(self, analysis_id: str, *, expect_updated_at: str | None = None) -> int:
        """analyses 행을 지운다(documents·analysis_reviews 는 FK cascade) → 지운 행 수(없었거나 updated_at 이 다르면 0)."""
        ...

    def list_analyses(self, limit: int) -> list[dict[str, Any]]:
        """공유 목록 행(LIST_SELECT 모양, created_at desc·id desc, limit 개까지)."""
        ...

    def remove_objects(self, paths: Sequence[str]) -> None:
        """버킷 객체들을 지운다. 이미 없는 객체는 성공, 그 밖 실패는 StoreError. 빈 목록이면 부르지 않는다."""
        ...

    def create_signed_upload_url(self, path: str) -> dict[str, str]:
        """{'signed_url', 'token', 'path'}"""
        ...

    def get_analysis(self, analysis_id: str, *, quiet: bool = False) -> dict[str, Any] | None:
        """analyses 행 + 'documents'(그 분석의 문서 행 목록, 만든 순). 없으면 None.

        quiet 면 저장소 오류를 값 없이(검토 행과 같은 수준 — 동작 이름 + 예외 종류 + 영숫자 오류 코드) 낸다.
        검토 동작 경로(imask_backend.reviews)만 쓴다. 기본값(False)은 지금 그대로(다른 경로의 로그를 바꾸지 않음).
        """
        ...

    def claim_analysis(
        self, analysis_id: str, *, started_at: str | None = None, expect_updated_at: str | None = None
    ) -> dict[str, Any] | None:
        """queued → running 원자적 선점(같은 갱신으로 started_at = 주어진 시각, 없으면 지금). expect_updated_at 이면
        updated_at = 그 값(시작이 읽은 행)일 때만. 바뀐 행이 없으면 None."""
        ...

    def update_analysis(
        self,
        analysis_id: str,
        values: Mapping[str, Any],
        *,
        expect_status: str | None = None,
        expect_no_job: bool = False,
        expect_job_id: str | None = None,
        expect_updated_at: str | None = None,
    ) -> dict[str, Any] | None:
        """조건(상태, upstage_job_id 가 null 또는 그 값, updated_at 이 읽은 값)을 붙인 갱신. 바뀐 행이 없으면 None."""
        ...

    def update_document(
        self,
        document_id: str,
        values: Mapping[str, Any],
        *,
        expect_file_id: str | None = None,
        expect_no_file: bool = False,
    ) -> bool:
        """문서 행 갱신(upstage_file_id 가 expect_file_id 이거나 null(expect_no_file)일 때만) → 바뀐 행이 있었는지."""
        ...

    def download(self, path: str) -> bytes | None:
        """버킷에서 파일 내용. 파일이 없으면 None."""
        ...

    def create_signed_download_url(self, path: str, expires_in: int) -> str | None:
        """버킷 객체의 서명 다운로드 URL(절대 주소, expires_in 초 유효). 객체가 없으면 None, 그 밖 실패는 StoreError."""
        ...

    def get_review(self, analysis_id: str) -> dict[str, Any] | None:
        """analysis_reviews 행(REVIEW_COLUMNS). 없으면 None."""
        ...

    def insert_review(self, values: Mapping[str, Any]) -> dict[str, Any] | None:
        """insert … on conflict (analysis_id) do nothing → 만든 행. 이미 행이 있으면 None."""
        ...

    def update_review(
        self, analysis_id: str, values: Mapping[str, Any], *, expect_version: int
    ) -> dict[str, Any] | None:
        """update … where analysis_id=? and version=expect_version → 바뀐 행. 바뀐 행이 없으면 None."""
        ...


def _first(data: Any) -> dict[str, Any] | None:
    if isinstance(data, list):
        return data[0] if data and isinstance(data[0], dict) else None
    return data if isinstance(data, dict) else None


def _removed_names(result: Any) -> set[str]:
    """storage3 remove 의 반환(지운 객체 목록)에서 이름들. 목록이 아니거나 이름이 없는 항목은 세지 않는다."""
    if not isinstance(result, list):
        return set()
    return {item["name"] for item in result if isinstance(item, Mapping) and isinstance(item.get("name"), str)}


def _is_missing_object(exc: BaseException) -> bool:
    """storage3 StorageApiError 가 '객체 없음'이 확실한지 — Storage 의 NoSuchKey 는 본문 {statusCode "404",
    error "not_found"(옛 이름 NoSuchKey)} 이다(supabase/storage internal/errors/codes.ts). 본문을 못 읽은 404·
    버킷 없음('Bucket not found')·권한 오류는 확실하지 않다."""
    status = str(getattr(exc, "status", "") or "")
    code = getattr(exc, "code", None)
    return status == "404" and code in ("not_found", "NoSuchKey")


def _is_not_found(exc: BaseException) -> bool:
    """storage3 StorageApiError 가 '파일 없음'인지(Storage 는 404 를 본문 statusCode 로 알린다)."""
    status = str(getattr(exc, "status", "") or "")
    code = str(getattr(exc, "code", "") or "")
    message = str(getattr(exc, "message", "") or "").lower()
    return status == "404" or code in ("not_found", "NoSuchKey") or "not found" in message


class SupabaseStore:
    """supabase-py 로 Store 를 구현한다. 클라이언트는 설정마다 하나를 만들어 다시 쓴다."""

    def __init__(self, client: Any, secrets: Mapping[str, str] | None = None, bucket: str = STORAGE_BUCKET):
        self._client = client
        self._secrets = dict(secrets or {})
        self._bucket = bucket

    @classmethod
    def from_settings(cls, settings: Settings, **client_kwargs: Any) -> SupabaseStore:
        """ConfigError(이름만)는 그대로 올린다."""
        conf = settings.supabase()
        from supabase import create_client  # 무거운 import 를 실제로 쓸 때까지 미룬다

        client = create_client(conf.url, conf.secret_key, **client_kwargs)
        return cls(client, settings.secrets())

    # --- 내부 -----------------------------------------------------------------

    def _error(self, action: str, exc: BaseException) -> StoreError:
        """저장소 오류(분석·문서·파일 경로 공통) — 값 없이: 고정 동작 이름 + 예외 종류 + 영숫자 오류 코드 + HTTP 상태.

        _quiet_error 와 같다. 바깥 오류 원문(PostgREST·Storage 문구 — 요청 주소의 분석 id·경로가 섞일 수 있다)은
        가려서라도 로그·StoreError 문구에 넣지 않는다. 원래 예외는 끊는다.
        """
        return self._quiet_error(action, exc)

    @staticmethod
    def _quiet_error(action: str, exc: BaseException, *, with_status: bool = True) -> StoreError:
        """값 없는 오류(공용): 고정 동작 이름 + 예외 종류 + 영숫자만인 짧은 오류 코드 + HTTP 상태(세 자리 숫자, 있으면).

        바깥 오류 원문(exc.message·details·hint·str(exc) — PostgREST·Postgres·Storage 문구, 요청 주소에는 이름·메모·
        분석 id·경로가 섞일 수 있다)은 가려서라도 로그·StoreError 문구에 넣지 않는다. 원래 예외는 끊는다.
        새 경로(목록·객체 지우기·지우기 확인·행 지우기, shared-analyses BRIEF §4)와 검토 행(_review_error)이 쓴다.
        """
        code = getattr(exc, "code", None)
        text = f"{action}: {type(exc).__name__}"
        if isinstance(code, str) and _ERROR_CODE.fullmatch(code):
            text += f" ({code})"
        if with_status:
            status = str(getattr(exc, "status", "") or "")
            if _HTTP_STATUS.fullmatch(status):
                text += f" HTTP {status}"
        logger.warning("%s", text)
        return StoreError(text)

    @staticmethod
    def _review_error(action: str, exc: BaseException) -> StoreError:
        """검토 행 오류(BRIEF §5.3): 값 없이 — 고정 동작 이름 + 예외 종류 + 영숫자만인 짧은 오류 코드(있으면).

        바깥 오류 원문(exc.message·str(exc) — PostgREST·Postgres 문구·요청 주소에는 메모·분석 id 가 섞일 수 있다)은
        로그에도 StoreError 문구에도 넣지 않는다. api 의 StoreError 처리기도 이 문구만 본다. 원래 예외는 끊는다.
        """
        return SupabaseStore._quiet_error(action, exc, with_status=False)

    def _table(self, name: str) -> Any:
        return self._client.table(name)

    def _storage(self) -> Any:
        return self._client.storage.from_(self._bucket)

    # --- 테이블 ---------------------------------------------------------------

    def get_workflow_settings(self) -> dict[str, Any] | None:
        try:
            response = self._table(WORKFLOW_TABLE).select(WORKFLOW_COLUMNS).eq("id", WORKFLOW_ROW_ID).limit(1).execute()
        except Exception as exc:
            raise self._quiet_error("워크플로우 설정 읽기", exc) from None
        return _first(response.data)

    def save_workflow_settings(self, agent_id: str, config_id: str) -> dict[str, Any]:
        values = {"id": WORKFLOW_ROW_ID, "agent_id": agent_id, "config_id": config_id}
        try:
            response = self._table(WORKFLOW_TABLE).upsert(values, on_conflict="id").execute()
        except Exception as exc:
            raise self._quiet_error("워크플로우 설정 저장", exc) from None
        row = _first(response.data)
        if row is None:
            raise StoreError("워크플로우 설정 저장: 응답에 행이 없습니다")
        return row

    def insert_analysis(self, name: str) -> dict[str, Any]:
        try:
            response = self._table("analyses").insert({"name": name, "status": "queued"}).execute()
        except Exception as exc:
            raise self._error("분석 행 만들기", exc) from None
        row = _first(response.data)
        if row is None:
            raise StoreError("분석 행 만들기: 응답에 행이 없습니다")
        return row

    def insert_document(
        self, analysis_id: str, *, filename: str, storage_path: str, size_bytes: int, mime_type: str
    ) -> dict[str, Any]:
        values = {
            "analysis_id": analysis_id,
            "filename": filename,
            "storage_path": storage_path,
            "size_bytes": size_bytes,
            "mime_type": mime_type,
        }
        try:
            response = self._table("documents").insert(values).execute()
        except Exception as exc:
            raise self._error("문서 행 만들기", exc) from None
        row = _first(response.data)
        if row is None:
            raise StoreError("문서 행 만들기: 응답에 행이 없습니다")
        return row

    def delete_analysis(self, analysis_id: str, *, expect_updated_at: str | None = None) -> int:
        # documents·analysis_reviews 는 외래 키 on delete cascade 로 함께 지워진다.
        # return=minimal + count=exact: PostgREST 는 204 + Content-Range */N(N = 지운 행 수) — 지운 행(result 포함)을 받지 않는다
        # expect_updated_at(§5.3 3단계 — V-T1-2 R2): 읽은 실행만 지운다(updated_at = 읽은 문자열 그대로). 없으면 id 만.
        from postgrest.types import CountMethod, ReturnMethod  # supabase 와 함께 쓸 때까지 미룬다

        try:
            query = (
                self._table("analyses")
                .delete(returning=ReturnMethod.minimal, count=CountMethod.exact)
                .eq("id", analysis_id)
            )
            if expect_updated_at is not None:
                query = query.eq("updated_at", expect_updated_at)
            response = query.execute()
        except Exception as exc:
            raise self._quiet_error("분석 행 지우기", exc) from None
        count = getattr(response, "count", None)
        if isinstance(count, int) and not isinstance(count, bool):
            return count
        data = getattr(response, "data", None)
        return len(data) if isinstance(data, list) else 0

    def list_analyses(self, limit: int) -> list[dict[str, Any]]:
        try:
            response = (
                self._table("analyses")
                .select(LIST_SELECT)
                .order("created_at", desc=True)
                .order("id", desc=True)
                .limit(limit)
                .execute()
            )
        except Exception as exc:
            raise self._quiet_error("분석 목록 읽기", exc) from None
        data = response.data
        if not isinstance(data, list):
            raise StoreError("분석 목록 읽기: 응답 모양이 다릅니다")
        return data

    def get_analysis(self, analysis_id: str, *, quiet: bool = False) -> dict[str, Any] | None:
        try:
            response = (
                self._table("analyses")
                .select(f"{ANALYSIS_COLUMNS},documents({DOCUMENT_COLUMNS})")
                .eq("id", analysis_id)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            # 둘 다 값 없는 오류 — quiet(검토 동작 경로)는 HTTP 상태도 넣지 않는다(검토 행과 같은 꼴), 기본은 _error
            if quiet:
                raise self._quiet_error("분석 읽기", exc, with_status=False) from None
            raise self._error("분석 읽기", exc) from None
        row = _first(response.data)
        if row is None:
            return None
        documents = row.get("documents")
        docs = [d for d in documents if isinstance(d, dict)] if isinstance(documents, list) else []
        row["documents"] = sorted(docs, key=lambda d: (str(d.get("created_at") or ""), str(d.get("id") or "")))
        return row

    def claim_analysis(
        self, analysis_id: str, *, started_at: str | None = None, expect_updated_at: str | None = None
    ) -> dict[str, Any] | None:
        # 상태와 시작 시각을 한 번의 조건부 갱신으로(진 요청은 started_at 도 바꾸지 못한다). expect_updated_at(V-T1-3 v3-m1 ①):
        # 시작이 읽은 행의 updated_at 일 때만 — 오래 멈췄던 시작이 그 사이 새로 돈 queued 순환을 가로채지 않게
        values = {"status": "running", "started_at": started_at or utc_now_iso()}
        return self.update_analysis(analysis_id, values, expect_status="queued", expect_updated_at=expect_updated_at)

    def update_analysis(
        self,
        analysis_id: str,
        values: Mapping[str, Any],
        *,
        expect_status: str | None = None,
        expect_no_job: bool = False,
        expect_job_id: str | None = None,
        expect_updated_at: str | None = None,
    ) -> dict[str, Any] | None:
        # expect_job_id·expect_updated_at(shared-analyses §5.6 실행 구분): eq 필터. updated_at 은 읽은 문자열 그대로
        # 보낸다(PostgREST 가 timestamptz 로 바꿔 비교 — httpx 가 '+' 를 %2B 로 보낸다)
        try:
            query = self._table("analyses").update(dict(values)).eq("id", analysis_id)
            if expect_status is not None:
                query = query.eq("status", expect_status)
            if expect_no_job:
                query = query.is_("upstage_job_id", "null")
            if expect_job_id is not None:
                query = query.eq("upstage_job_id", expect_job_id)
            if expect_updated_at is not None:
                query = query.eq("updated_at", expect_updated_at)
            response = query.execute()
        except Exception as exc:
            raise self._error("분석 갱신", exc) from None
        return _first(response.data)

    def update_document(
        self,
        document_id: str,
        values: Mapping[str, Any],
        *,
        expect_file_id: str | None = None,
        expect_no_file: bool = False,
    ) -> bool:
        # 비교 후 교환(shared-analyses §5.6 — V-T1-2 R1): upstage_file_id 가 읽은 값(expect_file_id)이거나 null(expect_no_file)
        # 일 때만. select=id + return=representation 으로 바뀐 행의 id 만 돌려받아 바뀐 행이 있었는지 센다(개수 헤더에
        # 기대지 않는다). 기존 '문서 갱신' 오류 문구(_error)는 그대로.
        try:
            query = self._table("documents").update(dict(values)).eq("id", document_id)
            if expect_no_file:
                query = query.is_("upstage_file_id", "null")
            elif expect_file_id is not None:
                query = query.eq("upstage_file_id", expect_file_id)
            response = query.select("id").execute()
        except Exception as exc:
            raise self._error("문서 갱신", exc) from None
        data = getattr(response, "data", None)
        return isinstance(data, list) and any(isinstance(item, dict) for item in data)

    # --- 검토 행(analysis_reviews) ---------------------------------------------

    def get_review(self, analysis_id: str) -> dict[str, Any] | None:
        try:
            response = (
                self._table(REVIEW_TABLE).select(REVIEW_COLUMNS).eq("analysis_id", analysis_id).limit(1).execute()
            )
        except Exception as exc:
            raise self._review_error("검토 행 읽기", exc) from None
        return _first(response.data)

    def insert_review(self, values: Mapping[str, Any]) -> dict[str, Any] | None:
        # Prefer: return=representation,resolution=ignore-duplicates + ?on_conflict=analysis_id
        # = insert … on conflict (analysis_id) do nothing returning * — 충돌이면 빈 목록
        try:
            response = (
                self._table(REVIEW_TABLE).upsert(dict(values), on_conflict="analysis_id", ignore_duplicates=True).execute()
            )
        except Exception as exc:
            raise self._review_error("검토 행 만들기", exc) from None
        return _first(response.data)

    def update_review(
        self, analysis_id: str, values: Mapping[str, Any], *, expect_version: int
    ) -> dict[str, Any] | None:
        try:
            response = (
                self._table(REVIEW_TABLE)
                .update(dict(values))
                .eq("analysis_id", analysis_id)
                .eq("version", expect_version)
                .execute()
            )
        except Exception as exc:
            raise self._review_error("검토 행 갱신", exc) from None
        return _first(response.data)

    # --- Storage --------------------------------------------------------------

    def create_signed_upload_url(self, path: str) -> dict[str, str]:
        try:
            data = self._storage().create_signed_upload_url(path)
        except Exception as exc:
            raise self._error("서명 업로드 URL 만들기", exc) from None
        # storage3 2.33 은 {'signed_url', 'signedUrl', 'token', 'path'} 를 돌려준다
        signed_url: Any = None
        token: Any = None
        if isinstance(data, Mapping):
            signed_url = data.get("signed_url") or data.get("signedUrl")
            token = data.get("token")
        if not isinstance(signed_url, str) or not signed_url or not isinstance(token, str) or not token:
            raise StoreError("서명 업로드 URL 만들기: 응답에 URL·토큰이 없습니다")
        return {"signed_url": signed_url, "token": token, "path": path}

    def remove_objects(self, paths: Sequence[str]) -> None:
        # storage3 remove → DELETE /object/{bucket} {"prefixes": [...]}: 지운 객체 목록(200). Storage 는 prefixes 가 비면
        # 400 이라 빈 목록이면 부르지 않는다. 돌려준 목록에 없는 경로는 '이미 없었음'으로 단정하지 않고 하나씩 확인한다
        # (권한 등으로 일부만 지웠을 수 있다 — 원본이 남은 채 행이 지워지지 않게). 목록이 아니면 모든 경로를 확인한다.
        action = "원본 파일 지우기"
        targets = list(dict.fromkeys(p for p in paths if isinstance(p, str) and p))
        if not targets:
            return
        try:
            result = self._storage().remove(targets)
        except Exception as exc:
            raise self._quiet_error(action, exc) from None
        removed = _removed_names(result)
        for path in targets:
            if path not in removed and not self._object_gone(path):
                logger.warning("%s: 지우지 못한 객체가 남음", action)
                raise StoreError(f"{action}: 지우지 못한 객체가 남음")

    def _object_gone(self, path: str) -> bool:
        """객체가 정말 없는지 — storage3 info(GET /object/info/{bucket}/{path}: 메타데이터만, 내용을 받지 않는다).

        없음이 확실한 응답(본문 statusCode "404" + error not_found·NoSuchKey)이면 True, 있으면(200) False,
        그 밖(권한·버킷 없음·본문 없는 404·연결 오류)은 확인 실패 StoreError. HEAD(exists)는 본문이 없어
        400·404 를 모두 '없음'으로 보므로 쓰지 않는다.
        """
        try:
            self._storage().info(path)
        except Exception as exc:
            if _is_missing_object(exc):
                return True
            raise self._quiet_error("원본 파일 지우기 확인", exc) from None
        return False

    def download(self, path: str) -> bytes | None:
        try:
            return self._storage().download(path)
        except Exception as exc:
            if _is_not_found(exc):
                return None
            raise self._error("파일 받기", exc) from None

    def create_signed_download_url(self, path: str, expires_in: int) -> str | None:
        action = "서명 다운로드 URL 만들기"
        try:
            data = self._storage().create_signed_url(path, expires_in)
        except Exception as exc:
            # 없는 객체: Storage 는 HTTP 400 + 본문 statusCode "404"(download 와 같다)
            if _is_not_found(exc):
                return None
            raise self._error(action, exc) from None
        url: Any = None
        if isinstance(data, Mapping):
            url = data.get("signedURL") or data.get("signedUrl") or data.get("signed_url")
        if not isinstance(url, str) or not url.strip():
            raise StoreError(f"{action}: 응답에 URL 이 없습니다")
        return self._absolute(url.strip(), action)

    def _absolute(self, url: str, action: str) -> str:
        """상대 경로(/object/sign/…)면 Storage 기준 주소에 붙인다. 이미 절대 주소면 그대로."""
        if url.startswith(("https://", "http://")):
            return url
        base = str(getattr(self._client, "storage_url", "") or "")
        if not base.startswith(("https://", "http://")):
            raise StoreError(f"{action}: 상대 경로를 붙일 Storage 주소가 없습니다")
        return base.rstrip("/") + "/" + url.lstrip("/")


# 설정(URL·키)마다 클라이언트 하나를 다시 쓴다(요청마다 만들면 인증 클라이언트까지 새로 만든다)
_STORE_CACHE: dict[tuple[str, str], SupabaseStore] = {}
_STORE_LOCK = threading.Lock()


def cached_store(settings: Settings) -> SupabaseStore:
    conf = settings.supabase()
    key = (conf.url, conf.secret_key)
    with _STORE_LOCK:
        store = _STORE_CACHE.get(key)
        if store is None:
            store = SupabaseStore.from_settings(settings)
            _STORE_CACHE.clear()
            _STORE_CACHE[key] = store
    return store
