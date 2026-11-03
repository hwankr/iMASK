# ==========================================================================
#  Supabase 테이블·Storage 접근 (supabase-py 동기 클라이언트, 서버 비밀 키)
#  - Store(Protocol): 업무 로직(analyses.py)이 쓰는 작은 인터페이스. 테스트는 메모리 가짜로 바꾼다.
#  - SupabaseStore: create_client(SUPABASE_URL, SUPABASE_SECRET_KEY) 로 analyses·documents 테이블과
#    documents 비공개 버킷을 다룬다. RLS 는 켜져 있고 정책이 없어 비밀 키(service_role)로만 읽고 쓴다.
#  - 조건부 갱신(update_analysis 의 expect_status 등): `update … where id=? and status=?` 를 한 번에
#    보내고 바뀐 행이 없으면 None. 같은 분석을 두 요청이 동시에 처리해도 한 번만 반영된다.
#  - 오류는 StoreError 하나로 감싼다. 메시지는 redaction.redact 로 가린 짧은 문구(로그용)이고,
#    화면에는 업무 로직이 정한 한국어 문장만 내보낸다.
#  - 서명 다운로드 URL(create_signed_download_url): storage3 2.33 의 create_signed_url(path, expires_in) 은
#    {'signedURL', 'signedUrl'} 에 이미 절대 주소(Storage 기준 주소 + /object/sign/…?token=…)를 담아 준다.
#    다른 버전·가짜가 상대 경로를 주면 Storage 기준 주소(client.storage_url)에 붙인다. 없는 객체는 None.
#    서명 URL 은 로그에 남기지 않는다.
# ==========================================================================

from __future__ import annotations

import logging
import threading
from collections.abc import Mapping
from typing import Any, Protocol

from .redaction import redact
from .settings import STORAGE_BUCKET, Settings

logger = logging.getLogger("imask.store")

# 응답에 쓰는 열만 고른다(agent_id·storage_path 는 DB 에만 — 업무 로직이 쓰므로 읽기는 한다)
ANALYSIS_COLUMNS = "id,name,status,agent_id,upstage_job_id,result,error,created_at,updated_at"
DOCUMENT_COLUMNS = "id,analysis_id,filename,storage_path,size_bytes,mime_type,upstage_file_id,created_at"
MAX_ERROR_DETAIL = 300


class StoreError(Exception):
    """Supabase 호출 실패. message 는 가린 짧은 문구(로그용)."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class Store(Protocol):
    """업무 로직이 쓰는 저장소 인터페이스(행은 dict, 시각은 ISO 8601 문자열)."""

    def insert_analysis(self, name: str) -> dict[str, Any]: ...

    def insert_document(
        self, analysis_id: str, *, filename: str, storage_path: str, size_bytes: int, mime_type: str
    ) -> dict[str, Any]: ...

    def delete_analysis(self, analysis_id: str) -> None: ...

    def create_signed_upload_url(self, path: str) -> dict[str, str]:
        """{'signed_url', 'token', 'path'}"""
        ...

    def get_analysis(self, analysis_id: str) -> dict[str, Any] | None:
        """analyses 행 + 'documents'(그 분석의 문서 행 목록, 만든 순). 없으면 None."""
        ...

    def claim_analysis(self, analysis_id: str) -> dict[str, Any] | None:
        """queued → running 원자적 선점. 바뀐 행이 없으면 None."""
        ...

    def update_analysis(
        self,
        analysis_id: str,
        values: Mapping[str, Any],
        *,
        expect_status: str | None = None,
        expect_no_job: bool = False,
    ) -> dict[str, Any] | None:
        """조건(상태, upstage_job_id 가 null)을 붙인 갱신. 바뀐 행이 없으면 None."""
        ...

    def update_document(self, document_id: str, values: Mapping[str, Any]) -> None: ...

    def download(self, path: str) -> bytes | None:
        """버킷에서 파일 내용. 파일이 없으면 None."""
        ...

    def create_signed_download_url(self, path: str, expires_in: int) -> str | None:
        """버킷 객체의 서명 다운로드 URL(절대 주소, expires_in 초 유효). 객체가 없으면 None, 그 밖 실패는 StoreError."""
        ...


def _first(data: Any) -> dict[str, Any] | None:
    if isinstance(data, list):
        return data[0] if data and isinstance(data[0], dict) else None
    return data if isinstance(data, dict) else None


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
        """예외 종류와 짧은 이유만(가린 뒤). 원래 예외는 끊는다(요청 정보를 품을 수 있어서)."""
        detail = getattr(exc, "message", None) or str(exc)
        text = redact(f"{action}: {type(exc).__name__}: {detail}", self._secrets, limit=MAX_ERROR_DETAIL)
        logger.warning("%s", text)
        return StoreError(text)

    def _table(self, name: str) -> Any:
        return self._client.table(name)

    def _storage(self) -> Any:
        return self._client.storage.from_(self._bucket)

    # --- 테이블 ---------------------------------------------------------------

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

    def delete_analysis(self, analysis_id: str) -> None:
        # documents 는 외래 키 on delete cascade 로 함께 지워진다
        try:
            self._table("analyses").delete().eq("id", analysis_id).execute()
        except Exception as exc:
            raise self._error("분석 행 지우기", exc) from None

    def get_analysis(self, analysis_id: str) -> dict[str, Any] | None:
        try:
            response = (
                self._table("analyses")
                .select(f"{ANALYSIS_COLUMNS},documents({DOCUMENT_COLUMNS})")
                .eq("id", analysis_id)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            raise self._error("분석 읽기", exc) from None
        row = _first(response.data)
        if row is None:
            return None
        documents = row.get("documents")
        docs = [d for d in documents if isinstance(d, dict)] if isinstance(documents, list) else []
        row["documents"] = sorted(docs, key=lambda d: (str(d.get("created_at") or ""), str(d.get("id") or "")))
        return row

    def claim_analysis(self, analysis_id: str) -> dict[str, Any] | None:
        return self.update_analysis(analysis_id, {"status": "running"}, expect_status="queued")

    def update_analysis(
        self,
        analysis_id: str,
        values: Mapping[str, Any],
        *,
        expect_status: str | None = None,
        expect_no_job: bool = False,
    ) -> dict[str, Any] | None:
        try:
            query = self._table("analyses").update(dict(values)).eq("id", analysis_id)
            if expect_status is not None:
                query = query.eq("status", expect_status)
            if expect_no_job:
                query = query.is_("upstage_job_id", "null")
            response = query.execute()
        except Exception as exc:
            raise self._error("분석 갱신", exc) from None
        return _first(response.data)

    def update_document(self, document_id: str, values: Mapping[str, Any]) -> None:
        try:
            self._table("documents").update(dict(values)).eq("id", document_id).execute()
        except Exception as exc:
            raise self._error("문서 갱신", exc) from None

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
