# ==========================================================================
#  FastAPI 경로 — POST /api/py/analyses/{id}/review-actions 와 조회 응답의 review 블록 (네트워크 없음)
#  - 응답 모양({"analysis", "changed"} — 조회와 같은 AnalysisOut), 조회 review 블록(기본값·null 대체·검토할 수 없음)
#  - Upstage 를 부르지 않음(설정이 없어도 동작), 저장소 오류 502, analyses.updated_at 그대로
#  - 본문 경계: 413(Content-Length·chunked·스트림 도중 끊기)·경계값 65,536, 400(JSON 아님·UTF-8 아님·같은 키·최상위·깊은 중첩),
#    오류 순서(413 → 400 → 404 분석 → 409 → 404 항목 → 409 잠김)
#  - 항목 id 에 짝 없는 서로게이트·NUL·따옴표·역슬래시·한글·이모지 → 저장 키는 ASCII escape, 응답은 원래 id
# ==========================================================================

from __future__ import annotations

import asyncio
import copy
import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from api_fakes import FAKE_ENV, FAKE_SUPABASE_KEY, FakeStore, FakeUpstageServer
from fake_findings import stored_result
from fake_reviews import ACTOR, SMALL, custom_result
from fastapi.testclient import TestClient

from api import index as api_index
from api.index import app, get_store, get_upstage
from imask_backend import reviews
from imask_backend.reviews import MAX_BODY_BYTES, review_scope, row_view, storage_key
from imask_backend.settings import get_settings, load_settings
from imask_backend.store import StoreError, SupabaseStore
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
    "started_at",  # 마지막으로 시작한 시각(shared-analyses BRIEF §5.1 — 문자열 또는 null)
    "documents",
    "upstage_status",
    "poll_error",
    "review",
}
REVIEW_KEYS = {"status", "memo", "memo_at", "reviewer", "reviewed_at", "completion_note", "findings", "items", "history", "version"}
MSG_FORMAT = "요청 형식이 올바르지 않습니다."
MSG_TOO_LARGE = "요청 본문이 너무 큽니다."
MSG_NOT_FOUND = "분석 건을 찾을 수 없습니다."
MSG_NO_FINDING = "탐지 항목을 찾을 수 없습니다."
MSG_NOT_REVIEWABLE = "검토할 수 없는 분석입니다."
MSG_STORE = "데이터 저장소에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요."


@dataclass
class Ctx:
    client: TestClient
    store: FakeStore
    server: FakeUpstageServer
    made: list[UpstageClient]

    def done(self, result: Any = None) -> str:
        return self.store.put(status="done", job_id="job_done", result=result if result is not None else custom_result(SMALL))

    def ids(self, analysis_id: str) -> dict[str, str]:
        row = self.store.get_analysis(analysis_id)
        assert row is not None
        scope = review_scope(row, row_view(row))
        assert scope is not None
        return {t.num: t.id for t in scope.targets}

    def post(self, analysis_id: str, body: Any, **kw: Any) -> httpx.Response:
        content = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=True).encode("ascii")
        headers = {"content-type": "application/json", **kw.pop("headers", {})}
        return self.client.post(f"/api/py/analyses/{analysis_id}/review-actions", content=content, headers=headers, **kw)

    def act(self, analysis_id: str, kind: str, **fields: Any) -> httpx.Response:
        return self.post(analysis_id, {"type": kind, "actor": ACTOR, **fields})

    def get(self, analysis_id: str) -> httpx.Response:
        return self.client.get(f"/api/py/analyses/{analysis_id}")


def _install(env: dict[str, str]) -> tuple[FakeStore, FakeUpstageServer, list[UpstageClient]]:
    settings = load_settings(env)
    store = FakeStore()
    server = FakeUpstageServer()
    made: list[UpstageClient] = []

    def upstage_override() -> Iterator[Any]:
        def factory() -> UpstageClient:
            if not made:
                made.append(UpstageClient.from_settings(settings.upstage(), transport=httpx.MockTransport(server.handle)))
            return made[0]

        yield factory

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_upstage] = upstage_override
    return store, server, made


@pytest.fixture
def ctx() -> Iterator[Ctx]:
    store, server, made = _install(dict(FAKE_ENV))
    with TestClient(app) as client:
        yield Ctx(client, store, server, made)
    app.dependency_overrides.clear()


def _no_upstage(ctx: Ctx) -> None:
    assert ctx.made == [] and ctx.server.requests == []


# --- 응답 모양 ------------------------------------------------------------------------------


def test_post_returns_the_same_analysis_shape_as_get(ctx: Ctx) -> None:
    analysis_id = ctx.done(stored_result())
    first = ctx.ids(analysis_id)["D1-01"]
    response = ctx.act(analysis_id, "set_status", finding_id=first, status="confirmed", reason="확인")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"analysis", "changed"} and body["changed"] is True
    analysis = body["analysis"]
    assert set(analysis) == ANALYSIS_KEYS and set(analysis["review"]) == REVIEW_KEYS
    assert analysis["upstage_status"] is None and analysis["poll_error"] is None
    assert "stages" not in analysis["result"] and "response" not in analysis["result"]
    assert len(analysis["result"]["findings"]) == 29 and analysis["result"]["findings"][0]["id"] == first
    review = analysis["review"]
    assert review["version"] == 1 and review["status"] == "needed"
    assert review["findings"][first]["status"] == "confirmed"
    assert [h["id"] for h in review["history"]] == ["S1", "S2", "H1"]
    # 검토사항 6건(review-items §5.5 — lowconf 4·nolocation 1·other 1, tests/test_items.py 가 내용을 본다)
    assert review["history"][1]["change"] == "분석 완료 · 탐지 29건 · 위험등급 상 · 검토사항 6건"
    assert review["history"][2]["target"] == "D1-01 이름" and review["history"][2]["change"] == "미확인 → 확인함"
    # 다시 조회해도 같은 값(새로 고침·다른 브라우저)
    got = ctx.get(analysis_id)
    assert got.status_code == 200 and got.json() == analysis
    _no_upstage(ctx)


def test_get_of_done_analysis_without_row_has_the_default_block(ctx: Ctx) -> None:
    analysis_id = ctx.done()
    body = ctx.get(analysis_id).json()
    row = ctx.store.analyses[analysis_id]
    assert body["review"] == {
        "status": "needed",
        "memo": "",
        "memo_at": None,
        "reviewer": "",
        "reviewed_at": None,
        "completion_note": "",
        "findings": {},
        "items": {},
        "history": [
            {"id": "S1", "at": row["created_at"], "actor": "시스템", "kind": "request", "target": "분석 건", "change": "파일 1개 분석 요청", "reason": ""},
            {"id": "S2", "at": row["updated_at"], "actor": "시스템", "kind": "ai", "target": "분석 건", "change": "분석 완료 · 탐지 4건 · 위험등급 미평가 · 검토사항 0건", "reason": ""},
        ],
        "version": 0,
    }
    assert ctx.store.reviews == {}  # 조회는 쓰지 않는다
    _no_upstage(ctx)


@pytest.mark.parametrize(
    ("status", "result"),
    [("queued", None), ("failed", None), ("done", None), ("done", {"format": "imask-upstage-v1", "stages": []}), ("done", custom_result(SMALL, pageless_classify=True))],
    ids=["queued", "failed", "done_without_result", "done_old_format", "done_pageless"],
)
def test_get_of_unreviewable_analysis_has_null_review_without_reading(ctx: Ctx, status: str, result: Any) -> None:
    analysis_id = ctx.store.put(status=status, result=result)
    response = ctx.get(analysis_id)
    assert response.status_code == 200 and response.json()["review"] is None
    assert "get_review" not in ctx.store.calls
    post = ctx.act(analysis_id, "save_memo", text="m")
    assert (post.status_code, post.json()) == (409, {"detail": MSG_NOT_REVIEWABLE})


def test_get_of_running_analysis_polls_upstage_but_reads_no_review(ctx: Ctx) -> None:
    analysis_id = ctx.store.put(status="running", job_id="job_1")
    body = ctx.get(analysis_id).json()
    assert body["review"] is None and body["upstage_status"] == "in_progress"
    assert "get_review" not in ctx.store.calls
    assert ctx.act(analysis_id, "save_memo", text="m").status_code == 409


def test_create_and_start_responses_have_null_review(ctx: Ctx) -> None:
    created = ctx.client.post("/api/py/analyses", json={"name": "n", "filename": "a.pdf", "size": 100, "mime_type": "application/pdf"})
    assert created.status_code == 201 and created.json()["analysis"]["review"] is None
    started = ctx.client.post(f"/api/py/analyses/{created.json()['analysis']['id']}/start")
    assert started.status_code == 200 and started.json()["review"] is None
    assert "get_review" not in ctx.store.calls


def test_review_read_failure_keeps_the_analysis_200_with_null_review(ctx: Ctx, caplog: pytest.LogCaptureFixture) -> None:
    analysis_id = ctx.done()
    ctx.store.fail.add("get_review")
    ctx.store.fail_message = f"relation analysis_reviews does not exist {analysis_id}"
    with caplog.at_level(logging.DEBUG, logger="imask"):
        response = ctx.get(analysis_id)
    assert response.status_code == 200
    body = response.json()
    assert body["review"] is None and body["status"] == "done" and len(body["result"]["findings"]) == 4
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "review 를 null 로" in logged
    assert analysis_id not in logged and "relation" not in logged  # 값 없는 경고


def test_view_is_built_once_per_request(ctx: Ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    from imask_backend import analyses as analyses_module
    from imask_backend import findings as findings_module

    calls: list[int] = []

    def counted(result: Any) -> dict[str, Any]:
        calls.append(1)
        return findings_module.build_view(result)

    monkeypatch.setattr(analyses_module, "build_view", counted)
    monkeypatch.setattr(reviews, "build_view", counted)
    analysis_id = ctx.done()
    assert ctx.get(analysis_id).status_code == 200 and len(calls) == 1
    first = ctx.ids(analysis_id)["D1-01"]
    calls.clear()
    assert ctx.act(analysis_id, "save_finding_memo", finding_id=first, text="m").status_code == 200 and len(calls) == 1


def test_reclassify_without_change_is_200_changed_false(ctx: Ctx) -> None:
    analysis_id = ctx.done()
    first = ctx.ids(analysis_id)["D1-01"]
    response = ctx.act(analysis_id, "reclassify", finding_id=first, category="이름", subject=None, reason="")
    assert response.status_code == 200
    assert response.json()["changed"] is False and response.json()["analysis"]["review"]["version"] == 0
    assert ctx.store.review_writes == []


# --- Upstage·analyses 행 --------------------------------------------------------------------------


def test_review_actions_and_reads_need_no_upstage_settings() -> None:
    env = {k: v for k, v in FAKE_ENV.items() if not k.startswith("UPSTAGE_")}
    store, server, made = _install(env)

    def boom() -> Iterator[Any]:
        def factory() -> UpstageClient:
            raise AssertionError("완료 분석 조회가 Upstage 클라이언트를 만들었다")

        yield factory

    try:
        with TestClient(app) as client:
            analysis_id = store.put(status="done", job_id="j", result=custom_result(SMALL))
            response = client.post(
                f"/api/py/analyses/{analysis_id}/review-actions", json={"type": "save_memo", "actor": ACTOR, "text": "m"}
            )
            assert response.status_code == 200 and response.json()["changed"] is True
            app.dependency_overrides[get_upstage] = boom  # 조회(완료 분석)는 의존성을 만들어도 팩토리를 부르지 않는다
            assert client.get(f"/api/py/analyses/{analysis_id}").status_code == 200
    finally:
        app.dependency_overrides.clear()
    assert made == [] and server.requests == []


def test_every_action_over_http_leaves_the_analysis_row_and_upstage_alone(ctx: Ctx) -> None:
    analysis_id = ctx.done()
    ids = ctx.ids(analysis_id)
    before = copy.deepcopy(ctx.store.analyses[analysis_id])
    get_before = ctx.get(analysis_id).json()
    steps = [
        ("set_status", {"finding_id": ids["D1-01"], "status": "confirmed", "reason": ""}),
        ("set_status", {"finding_id": ids["D1-01"], "status": "open", "reason": "취소"}),
        ("confirm_many", {"finding_ids": [ids["D1-02"], ids["D1-03"]]}),
        ("mark_false_positive", {"finding_id": ids["D2-01"], "reason_type": "기타", "note": ""}),
        ("restore", {"finding_id": ids["D2-01"], "note": ""}),
        ("reclassify", {"finding_id": ids["D2-01"], "exposure": "마스킹됨", "reason": ""}),
        ("save_finding_memo", {"finding_id": ids["D2-01"], "text": "m"}),
        ("save_memo", {"text": "m"}),
        ("complete_review", {"note": ""}),
        ("reopen_review", {"reason": ""}),
    ]
    for kind, fields in steps:
        response = ctx.act(analysis_id, kind, **fields)
        assert response.status_code == 200, (kind, response.text)
        assert response.json()["analysis"]["updated_at"] == before["updated_at"]
    assert ctx.store.analyses[analysis_id] == before
    assert ctx.store.updates == [] and "update_analysis" not in ctx.store.calls
    get_after = ctx.get(analysis_id).json()
    assert (get_after["created_at"], get_after["updated_at"]) == (get_before["created_at"], get_before["updated_at"])
    assert get_after["review"]["version"] == len(steps)
    assert [h["kind"] for h in get_after["review"]["history"]] == ["request", "ai", "confirm", "unconfirm", "confirm", "fp", "restore", "reclass", "fmemo", "memo", "complete", "reopen"]
    _no_upstage(ctx)


# --- 저장소 오류·404·409 -------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["get_analysis", "get_review", "insert_review"])
def test_store_errors_are_502(ctx: Ctx, method: str) -> None:
    analysis_id = ctx.done()
    ctx.store.fail.add(method)
    response = ctx.act(analysis_id, "save_memo", text="m")
    assert (response.status_code, response.json()) == (502, {"detail": MSG_STORE})


def test_update_store_error_is_502(ctx: Ctx) -> None:
    analysis_id = ctx.done()
    assert ctx.act(analysis_id, "save_memo", text="a").status_code == 200
    ctx.store.fail.add("update_review")
    assert ctx.act(analysis_id, "save_memo", text="b").status_code == 502


@pytest.mark.parametrize("analysis_id", ["not-a-uuid", "00000000-0000-4000-8000-000000000000"])
def test_unknown_analysis_is_404(ctx: Ctx, analysis_id: str) -> None:
    response = ctx.act(analysis_id, "save_memo", text="m")
    assert (response.status_code, response.json()) == (404, {"detail": MSG_NOT_FOUND})


def test_unknown_or_hidden_findings_are_404_and_nothing_is_saved(ctx: Ctx) -> None:
    analysis_id = ctx.done(custom_result([{"applicant_name": "김가짜"}], unpaged={"applicant_rrn": "900101-1234567"}))
    ok = ctx.ids(analysis_id)["D1-01"]
    for fid in ("0:없는 키", "1:applicant_rrn", "0:applicant_name ", "applicant_name", "D1-01"):
        response = ctx.act(analysis_id, "save_finding_memo", finding_id=fid, text="m")
        assert (response.status_code, response.json()) == (404, {"detail": MSG_NO_FINDING}), fid
    response = ctx.act(analysis_id, "confirm_many", finding_ids=[ok, "1:applicant_rrn"])
    assert (response.status_code, response.json()) == (404, {"detail": MSG_NO_FINDING})
    assert ctx.store.review_writes == [] and ctx.store.reviews == {}


def test_error_order(ctx: Ctx) -> None:
    missing = "00000000-0000-4000-8000-000000000000"
    # 413 → 400: 너무 큰 쓰레기 본문은 413
    assert ctx.post(missing, b"x" * (MAX_BODY_BYTES + 1)).status_code == 413
    # 400 → 404 분석: 없는 분석이어도 본문이 틀리면 400
    assert ctx.post(missing, {"type": "save_memo", "actor": ACTOR}).json() == {"detail": MSG_FORMAT}
    assert ctx.post(missing, {"type": "save_memo", "actor": "", "text": "m"}).json() == {"detail": "처리자 이름이 올바르지 않습니다."}
    # 404 분석 → 409: 없는 분석
    assert ctx.act(missing, "set_status", finding_id="0:x", status="confirmed", reason="").json() == {"detail": MSG_NOT_FOUND}
    # 409 검토할 수 없음 → 404 항목
    queued = ctx.store.put(status="queued")
    assert ctx.act(queued, "set_status", finding_id="0:x", status="confirmed", reason="").json() == {"detail": MSG_NOT_REVIEWABLE}
    # 404 항목 → 409 잠김
    analysis_id = ctx.done()
    assert ctx.act(analysis_id, "complete_review", note="").status_code == 200
    assert ctx.act(analysis_id, "set_status", finding_id="0:x", status="confirmed", reason="").json() == {"detail": MSG_NO_FINDING}
    first = ctx.ids(analysis_id)["D1-01"]
    response = ctx.act(analysis_id, "set_status", finding_id=first, status="confirmed", reason="")
    assert (response.status_code, response.json()) == (409, {"detail": "검토를 완료한 분석은 바꿀 수 없습니다."})


# --- 본문 경계 -----------------------------------------------------------------------------------


def _padded(body: dict[str, Any], size: int) -> bytes:
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    return raw + b" " * (size - len(raw))


def test_body_of_exactly_the_limit_is_accepted(ctx: Ctx) -> None:
    analysis_id = ctx.done()
    raw = _padded({"type": "save_memo", "actor": ACTOR, "text": "m"}, MAX_BODY_BYTES)
    assert len(raw) == 65_536
    response = ctx.post(analysis_id, raw)
    assert response.status_code == 200 and response.json()["changed"] is True


def test_body_over_the_limit_is_413(ctx: Ctx) -> None:
    analysis_id = ctx.done()
    raw = _padded({"type": "save_memo", "actor": ACTOR, "text": "m"}, MAX_BODY_BYTES + 1)
    response = ctx.post(analysis_id, raw)
    assert (response.status_code, response.json()) == (413, {"detail": MSG_TOO_LARGE})
    assert ctx.store.reviews == {} and "get_analysis" not in ctx.store.calls


def test_chunked_body_without_content_length_is_413(ctx: Ctx) -> None:
    analysis_id = ctx.done()

    def chunks() -> Iterator[bytes]:
        yield b'{"type":"save_memo","actor":"a","text":"m"'
        for _ in range(80):
            yield b" " * 1024
        yield b"}"

    request = ctx.client.build_request(
        "POST", f"/api/py/analyses/{analysis_id}/review-actions", content=chunks(), headers={"content-type": "application/json"}
    )
    assert "content-length" not in request.headers and request.headers.get("transfer-encoding") == "chunked"
    response = ctx.client.send(request)
    assert (response.status_code, response.json()) == (413, {"detail": MSG_TOO_LARGE})
    assert ctx.store.reviews == {}


def test_small_chunked_body_is_read_in_full(ctx: Ctx) -> None:
    analysis_id = ctx.done()
    parts = [b'{"type":"save_memo",', b'"actor":"a",', b'"text":"\xec\xa1\xb0', b'\xea\xb0\x81"}']  # UTF-8 글자가 조각 경계에 걸쳐도
    response = ctx.client.post(
        f"/api/py/analyses/{analysis_id}/review-actions", content=iter(parts), headers={"content-type": "application/json"}
    )
    assert response.status_code == 200 and ctx.store.reviews[analysis_id]["memo"] == "조각"


def test_big_content_length_is_413_before_reading(ctx: Ctx) -> None:
    analysis_id = ctx.done()
    for length in (str(MAX_BODY_BYTES + 1), "9" * 30, "0" * 20 + str(MAX_BODY_BYTES + 1), "1" + "0" * 5000):
        sent, calls = _raw_post(analysis_id, [b"{}"], headers=[(b"content-length", length.encode())])
        assert _status(sent) == 413 and calls == 0, length[:30]


def test_leading_zeros_in_content_length_do_not_change_the_result(ctx: Ctx) -> None:
    # V-T1-1 m1: 앞 0 이 붙어도 값은 같다 — 작은 본문은 200(실제 바이트 검사는 그대로)
    body = json.dumps({"type": "save_memo", "actor": ACTOR, "text": "m"}, ensure_ascii=False).encode("utf-8")
    for length in (str(len(body)), "0" * 20 + str(len(body)), "0" * 5000 + str(len(body))):
        analysis_id = ctx.done()
        sent, _ = _raw_post(analysis_id, [body], headers=[(b"content-length", length.encode())])
        assert _status(sent) == 200 and ctx.store.reviews[analysis_id]["memo"] == "m", length[:30]


def test_limit_value_with_leading_zeros_is_still_accepted(ctx: Ctx) -> None:
    raw = _padded({"type": "save_memo", "actor": ACTOR, "text": "m"}, MAX_BODY_BYTES)
    analysis_id = ctx.done()
    sent, _ = _raw_post(analysis_id, [raw], headers=[(b"content-length", ("000" + str(MAX_BODY_BYTES)).encode())])
    assert _status(sent) == 200


def test_falsely_small_content_length_is_413_by_the_bytes_actually_read(ctx: Ctx) -> None:
    analysis_id = ctx.done()
    for length in ("10", "0", "0000"):
        sent, calls = _raw_post(analysis_id, None, headers=[(b"content-length", length.encode())], endless=b" " * 1024)
        assert _status(sent) == 413 and calls <= MAX_BODY_BYTES // 1024 + 2, length
    assert ctx.store.reviews == {}


@pytest.mark.parametrize(
    ("length", "too_large"),
    [
        (None, False),
        ("", False),
        ("abc", False),
        ("-1", False),
        ("1e9", False),
        (" 70000", False),  # 숫자만이 아니면 헤더로 판단하지 않는다(실제 바이트로)
        ("0", False),
        ("000", False),
        ("65536", False),
        ("0065536", False),
        ("65537", True),
        ("00000000000000000000065537", True),
        ("99999", True),
        ("100000", True),
        ("9" * 30, True),
        ("0" * 30, False),
    ],
)
def test_declared_too_large(length: str | None, too_large: bool) -> None:
    assert api_index._declared_too_large(length, MAX_BODY_BYTES) is too_large  # noqa: SLF001


def _raw_post(analysis_id: str, chunks: list[bytes] | None, headers: list[tuple[bytes, bytes]] | None = None, endless: bytes | None = None) -> tuple[list[dict[str, Any]], int]:
    """앱을 ASGI 로 직접 부른다 — 조각을 몇 번 받았는지 센다(endless 면 끝없이 more_body)."""
    calls = 0
    queue = list(chunks or [])

    async def receive() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if calls > 10_000:
            return {"type": "http.disconnect"}
        if endless is not None:
            return {"type": "http.request", "body": endless, "more_body": True}
        body = queue.pop(0) if queue else b""
        return {"type": "http.request", "body": body, "more_body": bool(queue)}

    sent: list[dict[str, Any]] = []

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    path = f"/api/py/analyses/{analysis_id}/review-actions"
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"testserver"), (b"content-type", b"application/json"), *(headers or [])],
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    }
    asyncio.run(app(scope, receive, send))
    return sent, calls


def _status(sent: list[dict[str, Any]]) -> int:
    return next(m for m in sent if m["type"] == "http.response.start")["status"]


def test_endless_stream_is_cut_off_right_after_the_limit(ctx: Ctx) -> None:
    analysis_id = ctx.done()
    sent, calls = _raw_post(analysis_id, None, endless=b" " * 1024)
    assert _status(sent) == 413
    assert calls <= MAX_BODY_BYTES // 1024 + 2  # 한도를 넘은 조각에서 바로 멈춘다(끝까지 읽지 않음)
    assert ctx.store.reviews == {}


def test_client_disconnect_while_reading_is_400(ctx: Ctx) -> None:
    analysis_id = ctx.done()
    calls = 0

    async def receive() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"type": "http.request", "body": b'{"type":', "more_body": True}
        return {"type": "http.disconnect"}

    sent: list[dict[str, Any]] = []

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    path = f"/api/py/analyses/{analysis_id}/review-actions"
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST", "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": b"", "root_path": "", "headers": [(b"host", b"testserver")], "client": ("127.0.0.1", 1), "server": ("testserver", 80)}
    asyncio.run(app(scope, receive, send))
    statuses = [m["status"] for m in sent if m["type"] == "http.response.start"]
    assert statuses == [400]  # 처리하지 못한 오류(500)가 아니다
    assert ctx.store.reviews == {}


@pytest.mark.parametrize(
    ("raw", "status"),
    [
        (b"[" * 32_768 + b"]" * 32_768, 400),  # 깊이 32,768(본문 한도 안) — RecursionError 가 500 이 되지 않게
        (b"[" * MAX_BODY_BYTES, 400),  # 한도 안에서 가장 깊게(닫지 않음)
        (b'{"a":' * 10_000 + b"1" + b"}" * 10_000, 400),  # 60,001 바이트
        (b"[" * 100_000 + b"]" * 100_000, 413),  # 깊이 10만은 본문 한도를 넘는다
        (b"[" * 100_000, 413),
    ],
    ids=["deep_closed", "deep_unclosed", "deep_object", "depth_100k_closed", "depth_100k_unclosed"],
)
def test_deep_nesting_is_400_or_413_never_500(ctx: Ctx, raw: bytes, status: int) -> None:
    analysis_id = ctx.done()
    response = ctx.post(analysis_id, raw)
    assert response.status_code == status
    assert response.json() == {"detail": MSG_FORMAT if status == 400 else MSG_TOO_LARGE}


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"not json",
        b'{"type":"save_memo","actor":"a","text":"m"',
        b'{"type":"save_memo","actor":"a","text":"\xff"}',
        b'{"type":"save_memo","actor":"a","text":"\xed\xa0\x80"}',  # UTF-8 로 인코딩한 서로게이트(UTF-8 아님)
        b'{"type":"save_memo","type":"save_memo","actor":"a","text":"m"}',
        b'[{"type":"save_memo","actor":"a","text":"m"}]',
        b'"save_memo"',
        b"null",
        b'{"type":"save_memo","actor":"a","text":"m","extra":null}',
        b'{"type":"save_memo","actor":"a"}',
        b'{"type":"save_memo","actor":"a","text":5}',
        b'{"type":"confirm_many","actor":"a","finding_ids":[]}',
        b'{"type":"confirm_many","actor":"a","finding_ids":["x","x"]}',
        b'{"type":"nope","actor":"a"}',
    ],
)
def test_bad_bodies_are_400(ctx: Ctx, raw: bytes) -> None:
    analysis_id = ctx.done()
    response = ctx.post(analysis_id, raw)
    assert (response.status_code, response.json()) == (400, {"detail": MSG_FORMAT})


@pytest.mark.parametrize(
    ("text", "detail"),
    [
        ("가" * 500, None),
        ("😀" * 500, None),
        ("줄\n바꿈\t탭", None),
        ("가" * 501, "메모·사유는 500자 이하로 적어 주세요."),
        ("\x00", "메모·사유에 쓸 수 없는 문자가 있습니다."),
        ("앞\ud800뒤", "메모·사유에 쓸 수 없는 문자가 있습니다."),
    ],
)
def test_text_boundaries_over_http(ctx: Ctx, text: str, detail: str | None) -> None:
    analysis_id = ctx.done()
    response = ctx.act(analysis_id, "save_memo", text=text)  # ensure_ascii=True — 서로게이트는 "\ud800" escape 로 간다
    if detail is None:
        assert response.status_code == 200 and ctx.store.reviews[analysis_id]["memo"] == text
    else:
        assert (response.status_code, response.json()) == (400, {"detail": detail})
        assert ctx.store.reviews == {}


@pytest.mark.parametrize("actor", ["", "a" * 41, " 김검토", "김검토 ", "김\n검토", "김\ud800"])
def test_bad_actor_over_http(ctx: Ctx, actor: str) -> None:
    analysis_id = ctx.done()
    response = ctx.post(analysis_id, {"type": "save_memo", "actor": actor, "text": "m"})
    assert (response.status_code, response.json()) == (400, {"detail": "처리자 이름이 올바르지 않습니다."})


def test_bad_request_message_is_shared() -> None:
    assert api_index.MSG_BAD_REQUEST == reviews.MSG_BAD_REQUEST == MSG_FORMAT


# --- 짝 없는 서로게이트·NUL·따옴표가 든 항목 id -------------------------------------------------------------

# 짝 없는 서로게이트(맨 것·글자 사이), NUL, 따옴표, 역슬래시, 역슬래시로 쓴 '\ud800' 글자 6개(맨 서로게이트와 저장 키가
# 달라야 한다), 한글, 이모지. 표에 없는 키라 정보 종류는 모두 '기타 개인정보'.
ODD_KEYS = ("\ud800", "이름\ud800", "nul\x00키", 'quote"key', "back\\slash", "\\ud800", "한글키", "이모지😀", "\udfff")


def test_odd_finding_ids_get_ascii_storage_keys_and_come_back_unchanged(ctx: Ctx) -> None:
    data = {key: f"값{i}" for i, key in enumerate(ODD_KEYS)}
    analysis_id = ctx.done(custom_result([data]))
    ids = ctx.ids(analysis_id)
    assert list(ids.values()) == [f"0:{key}" for key in ODD_KEYS]
    for i, (num, fid) in enumerate(ids.items()):
        response = ctx.act(analysis_id, "save_finding_memo", finding_id=fid, text=f"메모{i}")
        assert response.status_code == 200, num
        assert response.content.isascii()  # 결과·검토 블록에 서로게이트 id 가 있어 늘 ASCII escape JSON
        assert json.loads(response.content)["analysis"]["review"]["findings"][fid]["memo"] == f"메모{i}"

    stored = ctx.store.reviews[analysis_id]["findings"]
    assert list(stored) == [storage_key(fid) for fid in ids.values()]
    assert all(key.isascii() for key in stored) and len(set(stored)) == len(ODD_KEYS)
    assert storage_key("0:\ud800") == "0:\\ud800" and storage_key("0:\\ud800") == "0:\\\\ud800"
    assert stored["0:\\ud800"]["memo"] == "메모0" and stored["0:\\\\ud800"]["memo"] == "메모5"  # 섞이지 않는다

    response = ctx.get(analysis_id)
    assert response.status_code == 200 and response.content.isascii()
    review = json.loads(response.content)["review"]
    assert list(review["findings"]) == list(ids.values())  # 원래 id 그대로(화면 순서)
    assert [review["findings"][fid]["memo"] for fid in ids.values()] == [f"메모{i}" for i in range(len(ODD_KEYS))]
    targets = [h["target"] for h in review["history"][2:]]
    assert targets == [f"D1-{i:02d} 기타 개인정보" for i in range(1, len(ODD_KEYS) + 1)]  # fmemo target = 번호 + 정보 종류


def test_fp_targets_use_labels_with_replacement_characters(ctx: Ctx) -> None:
    analysis_id = ctx.done(custom_result([{"이름\ud800": "값", "nul\x00키": "값"}]))
    ids = list(ctx.ids(analysis_id).values())
    for fid in ids:
        assert ctx.act(analysis_id, "mark_false_positive", finding_id=fid, reason_type="기타", note="").status_code == 200
    history = ctx.store.reviews[analysis_id]["history"]
    assert [h["target"] for h in history] == ["D1-01 이름�", "D1-02 nul�키"]


def test_clean_unicode_ids_keep_the_normal_utf8_response(ctx: Ctx) -> None:
    analysis_id = ctx.done(custom_result([{"한글키": "값", "이모지😀": "값"}]))
    fid = ctx.ids(analysis_id)["D1-02"]
    response = ctx.act(analysis_id, "save_finding_memo", finding_id=fid, text="메모")
    assert response.status_code == 200 and not response.content.isascii()
    assert response.json()["analysis"]["review"]["findings"][fid]["memo"] == "메모"
    assert list(ctx.store.reviews[analysis_id]["findings"]) == [storage_key(fid)] == ["0:\\uc774\\ubaa8\\uc9c0\\ud83d\\ude00"]


# --- 검토 저장소 오류의 로그에 값이 없음(V-T1-1 M1) — 진짜 SupabaseStore + MockTransport -----------------------

MEMO_MARKER = "SYNTHETIC-REVIEW-MEMO-MARKER"
SUPABASE_DEPRECATION = pytest.mark.filterwarnings("ignore::DeprecationWarning:supabase._sync.client")


class _PostgrestErrors:
    """MockTransport 처리기: 메서드별로 응답을 정한다. 오류 본문(message·details·hint)에 메모 표식·분석 id·가짜 키를 넣는다."""

    def __init__(self, analysis_id: str) -> None:
        self.analysis_id = analysis_id
        self.replies: dict[str, tuple[int, Any]] = {}
        self.requests: list[httpx.Request] = []

    def error_body(self, code: str = "XX000") -> dict[str, Any]:
        leak = f"memo={MEMO_MARKER}; analysis_id={self.analysis_id}; key={FAKE_SUPABASE_KEY}"
        return {"code": code, "message": f"write failed: {leak}", "details": f"Failing row contains ({leak})", "hint": leak}

    def handle(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.requests.append(request)
        status, body = self.replies.get(request.method, (500, self.error_body()))
        if isinstance(body, BaseException):
            raise body
        return httpx.Response(status, json=body)


def _real_review_store(analysis_id: str) -> tuple[SupabaseStore, _PostgrestErrors]:
    database = SupabaseStore.from_settings(load_settings(dict(FAKE_ENV)))
    errors = _PostgrestErrors(analysis_id)
    database._client.postgrest.session._transport = httpx.MockTransport(errors.handle)  # noqa: SLF001 — 테스트에서만
    return database, errors


class _Hybrid:
    """분석 행은 FakeStore, 검토 행은 진짜 SupabaseStore(가짜 전송층)."""

    def __init__(self, fake: FakeStore, database: SupabaseStore) -> None:
        self.fake = fake
        self.database = database

    def get_analysis(self, analysis_id: str, *, quiet: bool = False) -> Any:
        return self.fake.get_analysis(analysis_id, quiet=quiet)

    def get_review(self, analysis_id: str) -> Any:
        return self.database.get_review(analysis_id)

    def insert_review(self, values: Any) -> Any:
        return self.database.insert_review(values)

    def update_review(self, analysis_id: str, values: Any, *, expect_version: int) -> Any:
        return self.database.update_review(analysis_id, values, expect_version=expect_version)


def _imask_log(caplog: pytest.LogCaptureFixture) -> str:
    return "\n".join(f"{r.name} {r.levelname} {r.getMessage()} {r.exc_text or ''}" for r in caplog.records)


def _assert_value_free(text: str, analysis_id: str) -> None:
    assert MEMO_MARKER not in text
    assert analysis_id not in text
    assert FAKE_SUPABASE_KEY not in text
    assert "write failed" not in text and "Failing row" not in text


@SUPABASE_DEPRECATION
@pytest.mark.parametrize("call", ["get", "insert", "update"])
def test_review_store_errors_carry_no_values(caplog: pytest.LogCaptureFixture, call: str) -> None:
    store = FakeStore()
    analysis_id = store.put(status="done", job_id="j", result=custom_result(SMALL))
    database, _ = _real_review_store(analysis_id)
    actions = {
        "get": ("검토 행 읽기", lambda: database.get_review(analysis_id)),
        "insert": ("검토 행 만들기", lambda: database.insert_review({"analysis_id": analysis_id, "memo": MEMO_MARKER, "version": 1})),
        "update": ("검토 행 갱신", lambda: database.update_review(analysis_id, {"memo": MEMO_MARKER, "version": 2}, expect_version=1)),
    }
    action, run = actions[call]
    with caplog.at_level(logging.DEBUG, logger="imask"), pytest.raises(StoreError) as info:
        run()
    assert info.value.message == f"{action}: APIError (XX000)"  # 동작 이름 + 예외 종류 + 영숫자 오류 코드만
    assert info.value.__cause__ is None and info.value.__suppress_context__
    _assert_value_free(info.value.message + repr(info.value), analysis_id)
    log = _imask_log(caplog)
    assert f"{action}: APIError (XX000)" in log
    _assert_value_free(log, analysis_id)


@SUPABASE_DEPRECATION
@pytest.mark.parametrize(
    ("code", "shown"),
    [("PGRST205", " (PGRST205)"), ("23514", " (23514)"), ("XX-000", ""), (f"23514 {MEMO_MARKER}", ""), ("A" * 17, ""), ("", "")],
)
def test_only_short_alphanumeric_error_codes_are_kept(caplog: pytest.LogCaptureFixture, code: str, shown: str) -> None:
    store = FakeStore()
    analysis_id = store.put(status="done", job_id="j", result=custom_result(SMALL))
    database, errors = _real_review_store(analysis_id)
    errors.replies["GET"] = (400, errors.error_body(code))
    with caplog.at_level(logging.DEBUG, logger="imask"), pytest.raises(StoreError) as info:
        database.get_review(analysis_id)
    assert info.value.message == f"검토 행 읽기: APIError{shown}"
    _assert_value_free(_imask_log(caplog), analysis_id)


@SUPABASE_DEPRECATION
def test_review_store_connection_error_has_no_url_or_values(caplog: pytest.LogCaptureFixture) -> None:
    store = FakeStore()
    analysis_id = store.put(status="done", job_id="j", result=custom_result(SMALL))
    database, errors = _real_review_store(analysis_id)
    errors.replies["GET"] = (0, httpx.ConnectError(f"down {analysis_id} {MEMO_MARKER}"))
    with caplog.at_level(logging.DEBUG, logger="imask"), pytest.raises(StoreError) as info:
        database.get_review(analysis_id)
    assert info.value.message == "검토 행 읽기: ConnectError"
    _assert_value_free(_imask_log(caplog), analysis_id)


@SUPABASE_DEPRECATION
def test_get_with_real_review_store_error_is_200_null_without_values(caplog: pytest.LogCaptureFixture) -> None:
    store = FakeStore()
    analysis_id = store.put(status="done", job_id="j", result=custom_result(SMALL))
    database, _ = _real_review_store(analysis_id)
    _install(dict(FAKE_ENV))
    app.dependency_overrides[get_store] = lambda: _Hybrid(store, database)
    try:
        with TestClient(app) as client, caplog.at_level(logging.DEBUG, logger="imask"):
            response = client.get(f"/api/py/analyses/{analysis_id}")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["review"] is None and response.json()["status"] == "done"
    log = _imask_log(caplog)
    assert "검토 행 읽기: APIError (XX000)" in log and "review 를 null 로" in log
    _assert_value_free(log, analysis_id)


@SUPABASE_DEPRECATION
@pytest.mark.parametrize("failing", ["get", "insert", "update"])
def test_post_with_real_review_store_error_is_502_without_values(caplog: pytest.LogCaptureFixture, failing: str) -> None:
    store = FakeStore()
    analysis_id = store.put(status="done", job_id="j", result=custom_result(SMALL))
    database, errors = _real_review_store(analysis_id)
    existing = {"analysis_id": analysis_id, "status": "needed", "memo": "", "memo_at": None, "reviewer": "", "reviewed_at": None, "completion_note": "", "findings": {}, "history": [], "version": 1}
    if failing == "insert":
        errors.replies["GET"] = (200, [])  # 행 없음 → 삽입이 실패
    elif failing == "update":
        errors.replies["GET"] = (200, [existing])  # 행 있음 → 갱신이 실패
    _install(dict(FAKE_ENV))
    app.dependency_overrides[get_store] = lambda: _Hybrid(store, database)
    try:
        with TestClient(app) as client, caplog.at_level(logging.DEBUG, logger="imask"):
            response = client.post(
                f"/api/py/analyses/{analysis_id}/review-actions", json={"type": "save_memo", "actor": ACTOR, "text": MEMO_MARKER}
            )
    finally:
        app.dependency_overrides.clear()
    assert (response.status_code, response.json()) == (502, {"detail": MSG_STORE})
    expected_method = {"get": "GET", "insert": "POST", "update": "PATCH"}[failing]
    assert errors.requests[-1].method == expected_method
    log = _imask_log(caplog)
    action = {"get": "검토 행 읽기", "insert": "검토 행 만들기", "update": "검토 행 갱신"}[failing]
    assert log.count(f"{action}: APIError (XX000)") == 2  # 저장소 경고 + api 502 경고 — 둘 다 값 없음
    _assert_value_free(log, analysis_id)
