# ==========================================================================
#  API 테스트용 가짜 — 메모리 저장소(FakeStore)와 가짜 Upstage 서버(FakeUpstageServer)
#  - FakeStore 는 imask_backend.store.Store 와 같은 메서드를 메모리 dict 로 구현한다.
#    조건부 갱신(expect_status·expect_no_job)과 cascade 삭제, updated_at 갱신을 흉내 낸다.
#    fail 에 메서드 이름을 넣으면 그 메서드가 StoreError 를 던진다. before_update 로 경쟁을 흉내 낸다.
#    create_signed_download_url 은 객체가 없으면 None, 있으면 JWT 꼴 토큰을 단 가짜 서명 URL(받은 인자는 기록).
#    검토 행(analysis_reviews): get_review·insert_review(이미 있으면 None — on conflict do nothing)·update_review(version
#    조건, 안 맞으면 None)와 updated_at 갱신, 분석 FK·check 제약·jsonb 가 거절하는 값(NUL·짝 없는 서로게이트)을 흉내 낸다.
#    review_hooks 에 함수를 넣으면 검토 행을 쓰기 직전에 하나씩 꺼내 부른다(다른 요청이 끼어드는 경쟁 흉내).
#  - FakeUpstageServer 는 httpx.MockTransport 처리기다. 진짜 UpstageClient 를 그대로 쓰게 해서
#    요청 본문(config_id·include)까지 확인한다. 네트워크는 쓰지 않는다.
#  값은 모두 지어낸 가짜다(FAKE_*). JWT·Supabase 키 꼴 값은 fake_tokens 가 실행 중에 만든다.
# ==========================================================================

from __future__ import annotations

import copy
import json
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

import httpx
from fake_responses import build_response
from fake_tokens import fake_jwt, fake_supabase_secret

from imask_backend.store import StoreError

FAKE_UPSTAGE_KEY = "up-test-FAKE-KEY-0123456789"
FAKE_AGENT_ID = "agt-test-FAKE-AGENT-4242"
FAKE_CONFIG_ID = "7"
FAKE_SUPABASE_KEY = fake_supabase_secret()  # Supabase 새 형식 비밀 키 꼴(실행 중에 만든다)
UPSTAGE_BASE = "https://api.upstage.ai/v2"

FAKE_ENV = {
    "SUPABASE_URL": "https://fake-project.supabase.co",
    "SUPABASE_SECRET_KEY": FAKE_SUPABASE_KEY,
    "UPSTAGE_API_KEY": FAKE_UPSTAGE_KEY,
    "UPSTAGE_AGENT_ID": FAKE_AGENT_ID,
    "UPSTAGE_CONFIG_ID": FAKE_CONFIG_ID,
}
ALL_SECRETS = (FAKE_UPSTAGE_KEY, FAKE_AGENT_ID, FAKE_SUPABASE_KEY)

PDF_BYTES = b"%PDF-1.7\n% fake synthetic pdf\n"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 16


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class FakeStore:
    def __init__(self) -> None:
        self.analyses: dict[str, dict[str, Any]] = {}
        self.documents: dict[str, dict[str, Any]] = {}
        self.objects: dict[str, bytes] = {}
        self.fail: set[str] = set()
        self.calls: list[str] = []
        self.updates: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        self.before_update: Callable[[str, Mapping[str, Any]], None] | None = None
        self.fail_message: str | None = None  # 넣으면 StoreError 문구로 쓴다(가림 경계 시험용)
        self.signed_uploads: list[dict[str, str]] = []
        self.signed_downloads: list[tuple[str, int]] = []  # (path, expires_in)
        self.get_count = 0
        self.fail_get_calls: set[int] = set()  # n 번째 get_analysis 만 실패(예: 마지막 다시 읽기)
        self.reviews: dict[str, dict[str, Any]] = {}
        self.review_writes: list[tuple[str, str, dict[str, Any], int | None]] = []  # (메서드, 분석 id, 값, expect_version)
        self.review_hooks: list[Callable[[FakeStore, str], None]] = []  # 쓰기 직전에 하나씩(경쟁 흉내)
        self._in_review_hook = False

    def _call(self, name: str) -> None:
        self.calls.append(name)
        if name in self.fail:
            raise StoreError(self.fail_message or f"{name}: 가짜 실패")

    # --- 테스트 준비용 ----------------------------------------------------------

    def put(
        self,
        *,
        status: str = "queued",
        job_id: str | None = None,
        updated_at: str | None = None,
        mime_type: str = "application/pdf",
        filename: str = "묶음.pdf",
        storage_name: str = "document.pdf",
        content: bytes | None = PDF_BYTES,
        upstage_file_id: str | None = None,
        with_document: bool = True,
        **extra: Any,
    ) -> str:
        analysis_id = str(uuid.uuid4())
        stamp = now_iso()
        self.analyses[analysis_id] = {
            "id": analysis_id,
            "name": "가짜 분석",
            "status": status,
            "agent_id": FAKE_AGENT_ID if job_id else None,
            "upstage_job_id": job_id,
            "result": None,
            "error": None,
            "created_at": stamp,
            "updated_at": updated_at or stamp,
            **extra,
        }
        if with_document:
            path = f"analyses/{analysis_id}/{storage_name}"
            doc_id = str(uuid.uuid4())
            self.documents[doc_id] = {
                "id": doc_id,
                "analysis_id": analysis_id,
                "filename": filename,
                "storage_path": path,
                "size_bytes": len(content or b""),
                "mime_type": mime_type,
                "upstage_file_id": upstage_file_id,
                "created_at": stamp,
            }
            if content is not None:
                self.objects[path] = content
        return analysis_id

    def docs_of(self, analysis_id: str) -> list[dict[str, Any]]:
        return [d for d in self.documents.values() if d["analysis_id"] == analysis_id]

    # --- Store ----------------------------------------------------------------

    def insert_analysis(self, name: str) -> dict[str, Any]:
        self._call("insert_analysis")
        analysis_id = str(uuid.uuid4())
        stamp = now_iso()
        row = {
            "id": analysis_id,
            "name": name,
            "status": "queued",
            "agent_id": None,
            "upstage_job_id": None,
            "result": None,
            "error": None,
            "created_at": stamp,
            "updated_at": stamp,
        }
        self.analyses[analysis_id] = row
        return copy.deepcopy(row)

    def insert_document(
        self, analysis_id: str, *, filename: str, storage_path: str, size_bytes: int, mime_type: str
    ) -> dict[str, Any]:
        self._call("insert_document")
        doc_id = str(uuid.uuid4())
        row = {
            "id": doc_id,
            "analysis_id": analysis_id,
            "filename": filename,
            "storage_path": storage_path,
            "size_bytes": size_bytes,
            "mime_type": mime_type,
            "upstage_file_id": None,
            "created_at": now_iso(),
        }
        self.documents[doc_id] = row
        return copy.deepcopy(row)

    def delete_analysis(self, analysis_id: str) -> None:
        self._call("delete_analysis")
        self.analyses.pop(analysis_id, None)
        for doc_id in [d["id"] for d in self.docs_of(analysis_id)]:
            self.documents.pop(doc_id)

    def create_signed_upload_url(self, path: str) -> dict[str, str]:
        self._call("create_signed_upload_url")
        # 진짜처럼 JWT 꼴 토큰(가림 규칙에 걸리는 모양 — 정상 응답에서는 가리지 않아야 한다)
        token = fake_jwt({"fake": uuid.uuid4().hex})
        signed = {
            "signed_url": f"https://fake-project.supabase.co/storage/v1/object/upload/sign/documents/{path}?token={token}",
            "token": token,
            "path": path,
        }
        self.signed_uploads.append(signed)
        return dict(signed)

    def get_analysis(self, analysis_id: str) -> dict[str, Any] | None:
        self._call("get_analysis")
        self.get_count += 1
        if self.get_count in self.fail_get_calls:
            raise StoreError(f"get_analysis #{self.get_count}: 가짜 실패")
        row = self.analyses.get(analysis_id)
        if row is None:
            return None
        out = copy.deepcopy(row)
        out["documents"] = copy.deepcopy(sorted(self.docs_of(analysis_id), key=lambda d: d["created_at"]))
        return out

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
        self._call("update_analysis")
        if self.before_update is not None:
            hook, self.before_update = self.before_update, None
            hook(analysis_id, values)
        conditions = {"expect_status": expect_status, "expect_no_job": expect_no_job}
        self.updates.append((analysis_id, dict(values), conditions))
        row = self.analyses.get(analysis_id)
        if row is None:
            return None
        if expect_status is not None and row["status"] != expect_status:
            return None
        if expect_no_job and row["upstage_job_id"] is not None:
            return None
        # DB 처럼 JSON 으로 한 번 오간 값을 저장한다(직렬화할 수 없는 값이 있으면 여기서 실패)
        row.update(json.loads(json.dumps(dict(values), ensure_ascii=False)))
        row["updated_at"] = now_iso()
        return copy.deepcopy(row)

    def update_document(self, document_id: str, values: Mapping[str, Any]) -> None:
        self._call("update_document")
        self.documents[document_id].update(values)

    def download(self, path: str) -> bytes | None:
        self._call("download")
        return self.objects.get(path)

    def create_signed_download_url(self, path: str, expires_in: int) -> str | None:
        self._call("create_signed_download_url")
        self.signed_downloads.append((path, expires_in))
        if path not in self.objects:
            return None
        token = fake_jwt({"fake": uuid.uuid4().hex, "url": path})
        return f"https://fake-project.supabase.co/storage/v1/object/sign/documents/{path}?token={token}"

    # --- 검토 행(analysis_reviews) ------------------------------------------------

    def put_review(self, analysis_id: str, **values: Any) -> dict[str, Any]:
        """테스트 준비용: 검토 행을 바로 넣는다(검사 없음 — 틀린 모양도 넣을 수 있다)."""
        stamp = now_iso()
        row = {**_review_defaults(), "analysis_id": analysis_id, "version": 1, "created_at": stamp, "updated_at": stamp}
        row.update(values)
        self.reviews[analysis_id] = row
        return copy.deepcopy(row)

    def get_review(self, analysis_id: str) -> dict[str, Any] | None:
        self._call("get_review")
        row = self.reviews.get(analysis_id)
        return copy.deepcopy(row) if row is not None else None

    def _before_review_write(self, analysis_id: str) -> None:
        # 훅 안에서 다른 요청이 쓰는 동안에는 다음 훅을 꺼내지 않는다(끼어드는 요청 하나 = 훅 하나)
        if self.review_hooks and not self._in_review_hook:
            hook = self.review_hooks.pop(0)
            self._in_review_hook = True
            try:
                hook(self, analysis_id)
            finally:
                self._in_review_hook = False

    def insert_review(self, values: Mapping[str, Any]) -> dict[str, Any] | None:
        self._call("insert_review")
        analysis_id = str(values.get("analysis_id"))
        self._before_review_write(analysis_id)
        self.review_writes.append(("insert_review", analysis_id, copy.deepcopy(dict(values)), None))
        if analysis_id not in self.analyses:
            raise StoreError("insert_review: 외래 키 위반(가짜)")
        if analysis_id in self.reviews:
            return None  # on conflict do nothing
        stamp = now_iso()
        row = {**_review_defaults(), **_as_db_json(values), "created_at": stamp, "updated_at": stamp}
        _check_review(row)
        self.reviews[analysis_id] = row
        return copy.deepcopy(row)

    def update_review(
        self, analysis_id: str, values: Mapping[str, Any], *, expect_version: int
    ) -> dict[str, Any] | None:
        self._call("update_review")
        self._before_review_write(analysis_id)
        self.review_writes.append(("update_review", analysis_id, copy.deepcopy(dict(values)), expect_version))
        row = self.reviews.get(analysis_id)
        if row is None or row.get("version") != expect_version:
            return None
        merged = {**row, **_as_db_json(values), "updated_at": now_iso()}
        _check_review(merged)
        self.reviews[analysis_id] = merged
        return copy.deepcopy(merged)


def _review_defaults() -> dict[str, Any]:
    return {
        "status": "needed",
        "memo": "",
        "memo_at": None,
        "reviewer": "",
        "reviewed_at": None,
        "completion_note": "",
        "findings": {},
        "history": [],
    }


def _strings(value: Any) -> list[str]:
    """값 안의 모든 문자열(dict 키 포함) — 반복문."""
    out: list[str] = []
    stack = [value]
    while stack:
        node = stack.pop()
        if isinstance(node, str):
            out.append(node)
        elif isinstance(node, Mapping):
            for key, child in node.items():
                out.append(str(key))
                stack.append(child)
        elif isinstance(node, (list, tuple)):
            stack.extend(node)
    return out


def _as_db_json(values: Mapping[str, Any]) -> dict[str, Any]:
    """jsonb·text 처럼 저장한다: NUL·짝 없는 서로게이트는 Postgres 가 거절한다(StoreError). JSON 으로 한 번 오간 값."""
    for text in _strings(values):
        if "\x00" in text or any("\ud800" <= ch <= "\udfff" for ch in text):
            raise StoreError("검토 행 쓰기: jsonb 가 거절하는 문자(가짜)")
    return json.loads(json.dumps(dict(values), ensure_ascii=False))


def _check_review(row: Mapping[str, Any]) -> None:
    """마이그레이션의 not null·check 제약을 흉내 낸다."""
    version = row.get("version")
    ok = (
        row.get("status") in ("needed", "done")
        and isinstance(row.get("findings"), dict)
        and isinstance(row.get("history"), list)
        and isinstance(version, int)
        and not isinstance(version, bool)
        and version >= 1
        and all(isinstance(row.get(name), str) for name in ("memo", "reviewer", "completion_note"))
    )
    if not ok:
        raise StoreError("검토 행 쓰기: 제약 위반(가짜)")


class FakeUpstageServer:
    """httpx.MockTransport 처리기 — Upstage Agent API 의 네 경로를 흉내 낸다."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.files: dict[str, tuple[str, bytes]] = {}
        self.deleted: list[str] = []
        self.job_bodies: list[dict[str, Any]] = []
        self.create_status = "in_progress"
        self.create_extra: dict[str, Any] = {}
        self.last_status: str | None = "in_progress"
        self.last_extra: dict[str, Any] = {}
        self.full_response: dict[str, Any] = build_response(
            types=("loan_application", "consent_form", "income_proof", "power_of_attorney", "debt_transaction", "Other")
        )
        # (메서드, 경로 종류) → (상태 코드, 본문) 또는 예외
        self.errors: dict[tuple[str, str], Any] = {}
        self._counter = 0

    def _next(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}_fake{self._counter}"

    def calls(self, method: str | None = None, kind: str | None = None) -> list[httpx.Request]:
        return [r for r in self.requests if (method is None or r.method == method) and (kind is None or _kind(r) == kind)]

    def handle(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.requests.append(request)
        kind = _kind(request)
        injected = self.errors.get((request.method, kind))
        if isinstance(injected, BaseException):  # KeyboardInterrupt 도 주입할 수 있게
            raise injected
        if injected is not None:
            status, body = injected
            return httpx.Response(status, json=body)

        if request.method == "POST" and kind == "files":
            file_id = self._next("file")
            self.files[file_id] = (_multipart_filename(request), request.content)
            return httpx.Response(200, json={"id": file_id, "object": "file"})
        if request.method == "POST" and kind == "responses":
            body = json.loads(request.content)
            self.job_bodies.append(body)
            job = {"id": self._next("job"), "object": "response", "status": self.create_status, "model": body["model"]}
            job.update(self.create_extra)
            return httpx.Response(200, json=job)
        if request.method == "GET" and kind == "response":
            job_id = request.url.path.rsplit("/", 1)[-1]
            include = request.url.query.decode()
            if include == "include[]=all":
                body = {**copy.deepcopy(self.full_response), "id": job_id, "model": FAKE_AGENT_ID}
                return httpx.Response(200, json=body)
            body = {"id": job_id, "object": "response", "model": FAKE_AGENT_ID, "status": self.last_status, "output": []}
            body.update(self.last_extra)
            return httpx.Response(200, json=body)
        if request.method == "DELETE" and kind == "file":
            file_id = request.url.path.rsplit("/", 1)[-1]
            if file_id in self.deleted or file_id not in self.files:
                return httpx.Response(404, json={"error": {"message": "not found"}})
            self.deleted.append(file_id)
            return httpx.Response(200, json={"id": file_id, "deleted": True})
        if request.method == "GET" and kind == "file":
            file_id = request.url.path.rsplit("/", 1)[-1]
            return httpx.Response(404 if file_id in self.deleted else 200, json={"id": file_id})
        return httpx.Response(404, json={"error": {"message": "unknown path"}})


def _kind(request: httpx.Request) -> str:
    parts = [p for p in request.url.path.split("/") if p]
    # /v2/files, /v2/files/{id}, /v2/responses, /v2/responses/{id}
    tail = parts[1:] if parts and parts[0] == "v2" else parts
    if tail == ["files"]:
        return "files"
    if len(tail) == 2 and tail[0] == "files":
        return "file"
    if tail == ["responses"]:
        return "responses"
    if len(tail) == 2 and tail[0] == "responses":
        return "response"
    return "other"


def _multipart_filename(request: httpx.Request) -> str:
    marker = b'filename="'
    content = request.content
    start = content.find(marker)
    if start < 0:
        return ""
    start += len(marker)
    return content[start : content.find(b'"', start)].decode("utf-8", "replace")
