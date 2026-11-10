# ==========================================================================
#  공유 목록·삭제·다시 분석 API 테스트의 공용 준비 (네트워크 없음)
#  - 저장소는 FakeStore(get_store 바꿔 끼움). Upstage 의존성(get_upstage·get_upstage_cleanup)은 **바꿔 끼우지 않고**
#    api.index.UpstageClient 를 기록용 하위 클래스로 바꾼다 — 진짜 의존성 코드가 만든 클라이언트가 가짜 서버(MockTransport)로
#    가고, 만들 때 받은 timeout 을 남긴다(삭제 정리는 짧은 시간 제한 CLEANUP_TIMEOUT 인지 확인).
#  - 값은 모두 가짜(api_fakes). 처리자 이름은 fake_reviews.ACTOR.
# ==========================================================================

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from api_fakes import FAKE_ENV, FakeStore, FakeUpstageServer
from fake_reviews import ACTOR
from fastapi.testclient import TestClient

from api import index as api_index
from api.index import app, get_store
from imask_backend.settings import get_settings, load_settings
from imask_backend.upstage import UpstageClient

ANALYSIS_KEYS = {
    "id",
    "name",
    "status",
    "upstage_job_id",
    "error",
    "result",
    "created_at",
    "updated_at",
    "started_at",
    "documents",
    "upstage_status",
    "poll_error",
    "review",
}
ITEM_KEYS = {"id", "name", "status", "error", "created_at", "updated_at", "started_at", "documents", "risk_level", "review", "document_count"}
LIST_DOC_KEYS = {"filename", "size_bytes", "mime_type"}

MSG_FORMAT = "요청 형식이 올바르지 않습니다."
MSG_BAD_ACTOR = "처리자 이름이 올바르지 않습니다."
MSG_TOO_LARGE = "요청 본문이 너무 큽니다."
MSG_NOT_FOUND = "분석 건을 찾을 수 없습니다."
MSG_BUSY = "이미 분석하고 있습니다."
MSG_ONLY_FAILED = "실패한 분석만 다시 분석할 수 있습니다."
MSG_RETRY_CONFLICT = "다른 요청과 겹쳐 다시 분석하지 못했습니다. 잠시 후 다시 시도해 주세요."
MSG_DELETE_FILES = "원본 파일을 지우지 못했습니다. 잠시 후 다시 시도해 주세요."
MSG_DELETE_ROW = "분석을 지우지 못했습니다. 잠시 후 다시 시도해 주세요."
MSG_STORE = "데이터 저장소에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요."
MSG_FILE_MISSING = "업로드된 파일을 찾을 수 없습니다. 파일을 다시 올려 주세요."
RETRY_CHANGE = "같은 파일로 다시 분석 요청"


@dataclass
class Ctx:
    client: TestClient
    store: FakeStore
    server: FakeUpstageServer
    # 만든 Upstage 클라이언트마다 생성자가 받은 timeout(없으면 None — 기본 DEFAULT_TIMEOUT)
    made: list[Any] = field(default_factory=list)
    clients: list[UpstageClient] = field(default_factory=list)

    # --- 요청 ---------------------------------------------------------------------------
    def list(self, query: str = "") -> httpx.Response:
        return self.client.get("/api/py/analyses" + query)

    def delete(self, analysis_id: str, content: bytes | None = None) -> httpx.Response:
        return self.client.request("DELETE", f"/api/py/analyses/{analysis_id}", content=content)

    def retry(self, analysis_id: str, body: Any = None, **kw: Any) -> httpx.Response:
        payload = {"actor": ACTOR} if body is None else body
        content = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=True).encode("ascii")
        headers = {"content-type": "application/json", **kw.pop("headers", {})}
        return self.client.post(f"/api/py/analyses/{analysis_id}/retry", content=content, headers=headers, **kw)

    def get(self, analysis_id: str) -> httpx.Response:
        return self.client.get(f"/api/py/analyses/{analysis_id}")

    def start(self, analysis_id: str) -> httpx.Response:
        return self.client.post(f"/api/py/analyses/{analysis_id}/start")

    def create(self, **overrides: Any) -> httpx.Response:
        body = {"name": "합성 묶음", "filename": "묶음.pdf", "size": 322053, "mime_type": "application/pdf", **overrides}
        return self.client.post("/api/py/analyses", json=body)

    def act(self, analysis_id: str, kind: str, **fields: Any) -> httpx.Response:
        return self.client.post(f"/api/py/analyses/{analysis_id}/review-actions", json={"type": kind, "actor": ACTOR, **fields})

    # --- 확인 ---------------------------------------------------------------------------
    def no_upstage(self) -> None:
        assert self.made == [] and self.server.requests == []


def install(monkeypatch: pytest.MonkeyPatch, env: dict[str, str] | None = None) -> Ctx:
    """앱 의존성을 가짜로(저장소·설정) 바꾸고 Upstage 클라이언트를 기록용으로 바꾼다. TestClient 는 부르는 쪽이 연다."""
    settings = load_settings(dict(FAKE_ENV) if env is None else env)
    store = FakeStore()
    server = FakeUpstageServer()
    ctx = Ctx(client=None, store=store, server=server)  # type: ignore[arg-type]

    class Recording(UpstageClient):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            ctx.made.append(kwargs.get("timeout"))
            kwargs["transport"] = httpx.MockTransport(server.handle)
            super().__init__(*args, **kwargs)
            ctx.clients.append(self)

    monkeypatch.setattr(api_index, "UpstageClient", Recording)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_store] = lambda: store
    return ctx


@pytest.fixture
def ctx(monkeypatch: pytest.MonkeyPatch) -> Iterator[Ctx]:
    context = install(monkeypatch)
    try:
        with TestClient(app) as client:
            context.client = client
            yield context
    finally:
        app.dependency_overrides.clear()


def logic_factory(ctx: Ctx) -> Any:
    """업무 로직을 직접 부를 때(겹친 요청 흉내) 쓰는 Upstage 팩토리 — 같은 가짜 서버로."""
    made: list[UpstageClient] = []

    def factory() -> UpstageClient:
        if not made:
            made.append(UpstageClient(FAKE_ENV["UPSTAGE_API_KEY"], transport=httpx.MockTransport(ctx.server.handle)))
        return made[0]

    return factory
