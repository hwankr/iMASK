# ==========================================================================
#  검토 동작 경로의 분석 행 읽기는 값 없는 저장소 오류 (live-report V-T1-1 M1, 네트워크 없음)
#  - 진짜 SupabaseStore 에 예외만 던지는(또는 정해 둔 행을 돌려주는) 가짜 fluent 클라이언트를 넣는다.
#    바깥 예외의 message·details·hint·str 에 sentinel 네 가지(합성 분석 id·처리자·파일 이름·바깥 오류 식별 문구)를 넣고
#    ① 처음 읽기 실패(502) ② 검토 행 쓰기 저장소 오류 뒤 다시 읽기 실패(502) ③ 경쟁 3번 뒤 다시 읽기 실패(409) 를
#    log_export 와 save_memo 로 본다.
#  - 'imask' 로거는 propagate=False 라 root caplog 로는 잡히지 않는다 → 핸들러를 imask 로거에 직접 붙이고,
#    값 없는 문구가 실제로 잡혔음을 먼저 확인한 뒤 sentinel 이 하나도 없음을 확인한다. StoreError 문구도 같다.
#  - 다른 경로(조회 GET 등)는 그대로: get_analysis 기본값(quiet=False)은 지금의 _error 문구 꼴, FakeStore 기록으로
#    검토 동작만 quiet=True 로 읽는지 확인한다.
# ==========================================================================

from __future__ import annotations

import copy
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from api_fakes import FakeStore
from fake_exports import ANALYSIS_ID, CREATED_AT, CSV_NAME, MSG_CONFLICT, MSG_STORE, export_body, put_analysis
from fake_reviews import SMALL, custom_result
from fastapi.testclient import TestClient
from shared_ctx import Ctx, ctx, install  # noqa: F401

from api.index import app, get_store
from imask_backend.analyses import ApiError
from imask_backend.reviews import apply_review_action, validate_action
from imask_backend.store import StoreError, SupabaseStore

ACTOR_SENTINEL = "처리자센티널Q7"
OUTSIDE_SENTINEL = "OUTSIDE-ORIGINAL-ERROR-9f3k"
MEMO_SENTINEL = "메모센티널M1"
SENTINELS = (ANALYSIS_ID, ACTOR_SENTINEL, CSV_NAME, OUTSIDE_SENTINEL)
QUIET_READ = "분석 읽기: UpstreamError (XX000)"


class UpstreamError(Exception):
    """PostgREST APIError 꼴 — message·code·details·hint 와 str 에 값이 섞여 있다."""

    def __init__(self) -> None:
        text = f"GET /rest/v1/analyses?id=eq.{ANALYSIS_ID} actor={ACTOR_SENTINEL} file={CSV_NAME} memo={MEMO_SENTINEL} {OUTSIDE_SENTINEL}"
        super().__init__(text)
        self.message = text
        self.code = "XX000"
        self.details = text
        self.hint = OUTSIDE_SENTINEL
        self.status = 500


class _Response:
    def __init__(self, data: Any) -> None:
        self.data = data


class _Query:
    """supabase-py 쿼리 빌더 흉내 — 마지막 동작(select·update·upsert)으로 정해 둔 결과를 꺼낸다."""

    def __init__(self, client: ScriptedClient, table: str) -> None:
        self.client = client
        self.table = table
        self.op = "select"

    def select(self, *_a: Any, **_k: Any) -> _Query:
        return self

    def update(self, *_a: Any, **_k: Any) -> _Query:
        self.op = "update"
        return self

    def upsert(self, *_a: Any, **_k: Any) -> _Query:
        self.op = "upsert"
        return self

    def eq(self, *_a: Any) -> _Query:
        return self

    def limit(self, *_a: Any) -> _Query:
        return self

    def execute(self) -> _Response:
        return self.client.run(self.table, self.op)


class ScriptedClient:
    """(테이블, 동작) → 결과 목록(행 목록 또는 예외). 네트워크 없음."""

    def __init__(self, script: dict[tuple[str, str], list[Any]]) -> None:
        self.script = {key: list(values) for key, values in script.items()}
        self.ran: list[tuple[str, str]] = []

    def table(self, name: str) -> _Query:
        return _Query(self, name)

    def run(self, table: str, op: str) -> _Response:
        self.ran.append((table, op))
        outcome = self.script[(table, op)].pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return _Response(copy.deepcopy(outcome))


def _analysis_row() -> dict[str, Any]:
    return {
        "id": ANALYSIS_ID,
        "name": "합성 묶음",
        "status": "done",
        "agent_id": None,
        "upstage_job_id": "job_done",
        "result": custom_result(SMALL),
        "error": None,
        "created_at": CREATED_AT,
        "updated_at": "2026-11-04T15:05:00+00:00",
        "started_at": CREATED_AT,
        "documents": [
            {
                "id": "d1",
                "analysis_id": ANALYSIS_ID,
                "filename": "묶음.pdf",
                "storage_path": "p",
                "size_bytes": 10,
                "mime_type": "application/pdf",
                "upstage_file_id": None,
                "created_at": CREATED_AT,
            }
        ],
    }


def _review_row(version: int) -> dict[str, Any]:
    return {
        "analysis_id": ANALYSIS_ID,
        "status": "needed",
        "memo": "",
        "memo_at": None,
        "reviewer": "",
        "reviewed_at": None,
        "completion_note": "",
        "findings": {},
        "history": [],
        "version": version,
        "created_at": CREATED_AT,
        "updated_at": CREATED_AT,
    }


# 시나리오 → (가짜 클라이언트 대본, 기대 HTTP 상태·본문, 로그에 꼭 있어야 하는 값 없는 문구)
def _first_read() -> dict[tuple[str, str], list[Any]]:
    return {("analyses", "select"): [UpstreamError()]}


def _write_error_then_reread() -> dict[tuple[str, str], list[Any]]:
    return {
        ("analyses", "select"): [[_analysis_row()], UpstreamError()],
        ("analysis_reviews", "select"): [[]],
        ("analysis_reviews", "upsert"): [UpstreamError()],
    }


def _three_races_then_reread() -> dict[tuple[str, str], list[Any]]:
    return {
        ("analyses", "select"): [[_analysis_row()], UpstreamError()],
        ("analysis_reviews", "select"): [[_review_row(1)], [_review_row(2)], [_review_row(3)]],
        ("analysis_reviews", "update"): [[], [], []],
    }


SCENARIOS: dict[str, tuple[Callable[[], dict[tuple[str, str], list[Any]]], int, str, tuple[str, ...]]] = {
    "first_read": (_first_read, 502, MSG_STORE, (QUIET_READ,)),
    "write_error_then_reread": (_write_error_then_reread, 502, MSG_STORE, ("검토 행 만들기: UpstreamError (XX000)", QUIET_READ)),
    "three_races_then_reread": (_three_races_then_reread, 409, MSG_CONFLICT, (QUIET_READ,)),
}
BODIES: dict[str, dict[str, Any]] = {
    "log_export": export_body(actor=ACTOR_SENTINEL),
    "save_memo": {"type": "save_memo", "actor": ACTOR_SENTINEL, "text": MEMO_SENTINEL},
}


class _Collect(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.lines: list[str] = []
        self.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))  # 예외가 붙어 있으면 traceback 도 글로 들어간다


@contextmanager
def imask_log() -> Iterator[_Collect]:
    """'imask' 로거(propagate=False)에 직접 붙인 핸들러로 모든 로그를 모은다."""
    logger = logging.getLogger("imask")
    handler = _Collect()
    level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        yield handler
    finally:
        logger.removeHandler(handler)
        logger.setLevel(level)


def _assert_value_free(text: str) -> None:
    for value in (*SENTINELS, MEMO_SENTINEL):
        assert value not in text, "로그·오류 문구에 값이 섞였다"


def test_the_direct_handler_catches_imask_logs() -> None:
    # imask 로거는 propagate=False(api.index _setup_logging) — root 핸들러에 기대지 않고 직접 붙인 핸들러로 잡는다
    assert logging.getLogger("imask").propagate is False
    store = SupabaseStore(ScriptedClient(_first_read()))
    with imask_log() as log, pytest.raises(StoreError):
        store.get_analysis(ANALYSIS_ID, quiet=True)
    assert [line for line in log.lines if QUIET_READ in line] == [f"imask.store WARNING {QUIET_READ}"]


@pytest.mark.parametrize("kind", list(BODIES))
@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_review_action_store_errors_over_http_are_value_free(monkeypatch: pytest.MonkeyPatch, scenario: str, kind: str) -> None:
    script, status, message, expected_lines = SCENARIOS[scenario]
    client = ScriptedClient(script())
    database = SupabaseStore(client)
    context = install(monkeypatch)
    app.dependency_overrides[get_store] = lambda: database
    try:
        with TestClient(app) as http, imask_log() as log:
            response = http.post(f"/api/py/analyses/{ANALYSIS_ID}/review-actions", json=BODIES[kind])
    finally:
        app.dependency_overrides.clear()
    assert (response.status_code, response.json()) == (status, {"detail": message})
    assert all(not values for values in client.script.values()), "대본을 끝까지 썼다(다시 읽기까지 갔다)"
    text = "\n".join(log.lines)
    for line in expected_lines:  # 먼저 값 없는 문구가 실제로 잡혔는지
        assert line in text
    if status == 502:
        assert "저장소 오류:" in text  # api 의 StoreError 처리기 로그도 잡혔다
    _assert_value_free(text)
    _assert_value_free(response.text)
    context.no_upstage()


@pytest.mark.parametrize("kind", list(BODIES))
@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_review_action_store_errors_in_the_logic_are_value_free(scenario: str, kind: str) -> None:
    script, status, _message, expected_lines = SCENARIOS[scenario]
    database = SupabaseStore(ScriptedClient(script()))
    action = validate_action(BODIES[kind])
    with imask_log() as log:
        if status == 502:
            with pytest.raises(StoreError) as info:
                apply_review_action(database, ANALYSIS_ID, action)
            error = info.value
            assert error.message == expected_lines[0]  # 처음 읽기면 분석 읽기, 쓰기 오류면 검토 행 문구(원래 오류)
            assert error.__cause__ is None and error.__suppress_context__
            _assert_value_free(error.message + repr(error) + str(error))
        else:
            with pytest.raises(ApiError) as api_error:
                apply_review_action(database, ANALYSIS_ID, action)
            assert (api_error.value.status_code, api_error.value.detail) == (409, MSG_CONFLICT)
    text = "\n".join(log.lines)
    for line in expected_lines:
        assert line in text
    _assert_value_free(text)


def test_quiet_read_error_keeps_only_a_short_alphanumeric_code() -> None:
    class Odd(UpstreamError):
        def __init__(self) -> None:
            super().__init__()
            self.code = f"XX000 {OUTSIDE_SENTINEL}"  # 영숫자가 아닌 코드는 버린다

    store = SupabaseStore(ScriptedClient({("analyses", "select"): [Odd()]}))
    with imask_log() as log, pytest.raises(StoreError) as info:
        store.get_analysis(ANALYSIS_ID, quiet=True)
    assert info.value.message == "분석 읽기: Odd"  # HTTP 상태도 넣지 않는다(검토 행과 같은 수준)
    assert log.lines and all(OUTSIDE_SENTINEL not in line for line in log.lines)


def test_default_analysis_read_error_is_unchanged() -> None:
    # 다른 경로(조회·시작·다시 분석·삭제)는 기본값 그대로 — 지금의 _error 꼴(예외 종류 뒤에 가린 짧은 이유)
    store = SupabaseStore(ScriptedClient({("analyses", "select"): [UpstreamError()]}))
    with imask_log() as log, pytest.raises(StoreError) as info:
        store.get_analysis(ANALYSIS_ID)
    assert info.value.message.startswith("분석 읽기: UpstreamError: ")
    assert info.value.message != QUIET_READ and any(line.endswith(info.value.message) for line in log.lines)


def test_quiet_read_success_returns_the_same_row() -> None:
    script = {("analyses", "select"): [[_analysis_row()], [_analysis_row()], []]}
    store = SupabaseStore(ScriptedClient(script))
    assert store.get_analysis(ANALYSIS_ID, quiet=True) == store.get_analysis(ANALYSIS_ID)
    assert store.get_analysis(ANALYSIS_ID, quiet=True) is None


# --- 검토 동작만 quiet 로 읽는다(FakeStore 기록) ------------------------------------------------------


def test_only_review_actions_read_the_analysis_quietly(ctx: Ctx) -> None:  # noqa: F811
    put_analysis(ctx.store)
    assert ctx.get(ANALYSIS_ID).status_code == 200
    assert ctx.store.analysis_reads and not any(ctx.store.analysis_reads)  # 조회는 기본값(quiet 아님)
    ctx.store.analysis_reads.clear()
    assert ctx.act(ANALYSIS_ID, "save_memo", text="m").status_code == 200
    assert ctx.act(ANALYSIS_ID, "log_export", **{k: v for k, v in export_body().items() if k not in ("type", "actor")}).status_code == 200
    assert ctx.act(ANALYSIS_ID, "complete_review", note="").status_code == 200
    assert ctx.store.analysis_reads == [True, True, True]
    # 지워졌는지 다시 읽기도 quiet
    ctx.store.analysis_reads.clear()
    ctx.store.review_hooks = [lambda store, aid: store.delete_analysis(aid)]
    assert ctx.act(ANALYSIS_ID, "log_export", **{k: v for k, v in export_body().items() if k not in ("type", "actor")}).status_code == 404
    assert ctx.store.analysis_reads == [True, True]


def test_other_routes_keep_the_default_read(ctx: Ctx) -> None:  # noqa: F811
    failed = ctx.store.put(status="failed", error="e")
    ctx.store.objects[ctx.store.docs_of(failed)[0]["storage_path"]] = b"%PDF-1.7\n"
    assert ctx.retry(failed).status_code == 200
    queued = ctx.create().json()["analysis"]["id"]
    ctx.start(queued)
    assert ctx.client.get(f"/api/py/analyses/{queued}/file").status_code in (200, 404)
    assert ctx.delete(failed).status_code == 204
    assert ctx.store.analysis_reads and not any(ctx.store.analysis_reads)


def test_fake_store_failure_on_a_quiet_read_is_still_502(ctx: Ctx) -> None:  # noqa: F811
    put_analysis(ctx.store)
    ctx.store.fail.add("get_analysis")
    response = ctx.act(ANALYSIS_ID, "log_export", **{k: v for k, v in export_body().items() if k not in ("type", "actor")})
    assert (response.status_code, response.json()) == (502, {"detail": MSG_STORE})
    assert ctx.store.analysis_reads == [True]
    assert FakeStore  # 가짜 저장소도 quiet 키워드를 받는다
