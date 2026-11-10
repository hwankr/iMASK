# ==========================================================================
#  FastAPI 경로 — POST /api/py/analyses/{id}/review-actions 의 type 'log_export'(내보내기 기록, live-report BRIEF §5.6)
#  (네트워크 없음 — FakeStore, Upstage 클라이언트는 기록용 가짜)
#  - 응답 {"analysis": AnalysisOut(조회와 같은 모양), "changed": true}, review.history 마지막 = 새 export 줄, 다시 조회해도 같음
#  - 잠김과 무관(검토 완료 뒤에도 200, 다른 열 그대로), at 이 줄지 않음, analyses 행·Upstage 를 건드리지 않음(설정 없어도 200)
#  - 오류 순서: 413(65,537 바이트 — Content-Length 없이도) → 400 모양 → 400 처리자 → 404 → 409 검토할 수 없음
#    → 400 이 분석의 이름 아님 → 409 이력 1000줄 → 409 경쟁 3번 / 경쟁 중 지워짐 404, 저장소 오류 502
#  - 원시 JSON 본문(10**400·1e400·1.0·같은 키·깊은 중첩·이스케이프한 줄바꿈·NUL·서로게이트) → 400, 로그에 값이 없음
# ==========================================================================

from __future__ import annotations

import copy
import json
import logging
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from api_fakes import FAKE_ENV
from fake_exports import (
    ANALYSIS_ID,
    CSV_NAME,
    JSON_NAME,
    MSG_BAD_ACTOR,
    MSG_CONFLICT,
    MSG_FORMAT,
    MSG_HISTORY_FULL,
    MSG_NOT_FOUND,
    MSG_NOT_REVIEWABLE,
    MSG_STORE,
    MSG_TOO_LARGE,
    OTHER_ID,
    UNTOUCHED,
    export_body,
    put_analysis,
)
from fake_reviews import ACTOR, SMALL, custom_result
from fastapi.testclient import TestClient
from shared_ctx import ANALYSIS_KEYS, Ctx, ctx, install  # noqa: F401

from api.index import app
from imask_backend.reviews import MAX_BODY_BYTES, review_scope, row_view

REVIEW_KEYS = {"status", "memo", "memo_at", "reviewer", "reviewed_at", "completion_note", "findings", "items", "history", "version"}
LINE_KEYS = {"id", "at", "actor", "kind", "target", "change", "reason"}
PATH = f"/api/py/analyses/{ANALYSIS_ID}/review-actions"


def post(ctx: Ctx, body: Any, *, analysis_id: str = ANALYSIS_ID, **kw: Any) -> httpx.Response:
    content = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=True).encode("ascii")
    headers = {"content-type": "application/json", **kw.pop("headers", {})}
    return ctx.client.post(f"/api/py/analyses/{analysis_id}/review-actions", content=content, headers=headers, **kw)


def detail(response: httpx.Response) -> tuple[int, Any]:
    return response.status_code, response.json()


def finding_ids(ctx: Ctx, analysis_id: str = ANALYSIS_ID) -> dict[str, str]:
    row = ctx.store.get_analysis(analysis_id)
    assert row is not None
    scope = review_scope(row, row_view(row))
    assert scope is not None
    return {t.num: t.id for t in scope.targets}


def filler(count: int, at: str = "2026-11-05T00:00:00+00:00") -> list[dict[str, str]]:
    return [{"id": f"H{i}", "at": at, "actor": "가", "kind": "memo", "target": "분석 건", "change": "c", "reason": ""} for i in range(1, count + 1)]


@pytest.fixture
def done(ctx: Ctx) -> Ctx:  # noqa: F811 — shared_ctx 의 ctx 픽스처
    put_analysis(ctx.store)
    return ctx


# --- 응답 모양 ------------------------------------------------------------------------------------


def test_export_returns_the_get_shape_with_one_new_line(done: Ctx) -> None:
    before = done.get(ANALYSIS_ID).json()
    response = post(done, export_body())
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"analysis", "changed"} and body["changed"] is True
    analysis = body["analysis"]
    assert set(analysis) == ANALYSIS_KEYS and set(analysis["review"]) == REVIEW_KEYS
    assert "stages" not in analysis["result"] and "response" not in analysis["result"]
    review = analysis["review"]
    assert review["version"] == 1 and review["status"] == "needed"
    assert [h["id"] for h in review["history"]] == ["S1", "S2", "H1"]
    line = review["history"][-1]
    assert set(line) == LINE_KEYS
    assert {k: v for k, v in line.items() if k != "at"} == {
        "id": "H1",
        "actor": ACTOR,
        "kind": "export",
        "target": CSV_NAME,
        "change": "CSV · 6KB · 다운로드 요청",
        "reason": "민감한 값 마스킹",
    }
    assert line == done.store.reviews[ANALYSIS_ID]["history"][-1]
    # 분석 정보는 조회와 같다(review 만 새 값)
    assert {k: v for k, v in analysis.items() if k != "review"} == {k: v for k, v in before.items() if k != "review"}
    got = done.get(ANALYSIS_ID).json()
    assert got == analysis
    done.no_upstage()


def test_export_after_review_completion_is_200_and_keeps_every_other_column(done: Ctx) -> None:
    ids = finding_ids(done)
    assert done.act(ANALYSIS_ID, "mark_false_positive", finding_id=ids["D1-02"], reason_type="기타", note="사유").status_code == 200
    assert done.act(ANALYSIS_ID, "save_finding_memo", finding_id=ids["D1-01"], text="항목 메모").status_code == 200
    assert done.act(ANALYSIS_ID, "save_memo", text="검토 메모").status_code == 200
    assert done.act(ANALYSIS_ID, "complete_review", note="완료 메모").status_code == 200
    before_row = copy.deepcopy(done.store.reviews[ANALYSIS_ID])
    before_block = done.get(ANALYSIS_ID).json()["review"]

    response = post(done, export_body(format="json", size=22021, state="saved", file_name=JSON_NAME))
    assert response.status_code == 200 and response.json()["changed"] is True
    review = response.json()["analysis"]["review"]
    after_row = done.store.reviews[ANALYSIS_ID]
    assert {k: after_row[k] for k in UNTOUCHED} == {k: before_row[k] for k in UNTOUCHED}
    assert after_row["version"] == before_row["version"] + 1 == 5
    assert after_row["history"][:-1] == before_row["history"]
    assert {k: review[k] for k in UNTOUCHED} == {k: before_block[k] for k in UNTOUCHED}
    assert review["history"][:-1] == before_block["history"]
    last = review["history"][-1]
    assert (last["id"], last["kind"], last["target"], last["change"], last["reason"]) == (
        "H5",
        "export",
        JSON_NAME,
        "JSON · 22KB · 저장 완료",
        "민감한 값 마스킹",
    )
    # 다른 동작은 여전히 잠김
    locked = done.act(ANALYSIS_ID, "save_memo", text="x")
    assert detail(locked) == (409, {"detail": "검토를 완료한 분석은 바꿀 수 없습니다."})


def test_export_time_never_goes_before_the_last_line(done: Ctx) -> None:
    later = "2099-01-01T00:00:00+00:00"
    done.store.put_review(ANALYSIS_ID, history=filler(1, later), version=1)
    line = post(done, export_body()).json()["analysis"]["review"]["history"][-1]
    assert line["id"] == "H2" and line["at"] == later


def test_export_needs_no_upstage_settings_and_never_writes_the_analysis_row(monkeypatch: pytest.MonkeyPatch) -> None:
    env = {k: v for k, v in FAKE_ENV.items() if not k.startswith("UPSTAGE_")}
    context = install(monkeypatch, env)
    try:
        with TestClient(app) as client:
            context.client = client
            put_analysis(context.store)
            before = copy.deepcopy(context.store.analyses[ANALYSIS_ID])
            for body in (export_body(), export_body(format="json", size=5172, file_name=JSON_NAME), export_body(state="saved")):
                response = post(context, body)
                assert response.status_code == 200 and response.json()["changed"] is True
                assert response.json()["analysis"]["updated_at"] == before["updated_at"]
            assert context.store.analyses[ANALYSIS_ID] == before
            assert context.store.updates == [] and "update_analysis" not in context.store.calls
            assert context.store.reviews[ANALYSIS_ID]["version"] == 3
    finally:
        app.dependency_overrides.clear()
    context.no_upstage()


# --- 413 → 400 ------------------------------------------------------------------------------------


def _padded(body: dict[str, Any], size: int) -> bytes:
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    assert len(raw) <= size
    return raw + b" " * (size - len(raw))


def test_body_of_exactly_the_limit_is_accepted(done: Ctx) -> None:
    raw = _padded(export_body(), MAX_BODY_BYTES)
    assert len(raw) == 65_536
    assert post(done, raw).status_code == 200


def test_body_one_byte_over_the_limit_is_413_before_anything(done: Ctx) -> None:
    raw = _padded(export_body(), MAX_BODY_BYTES + 1)
    assert len(raw) == 65_537
    assert detail(post(done, raw)) == (413, {"detail": MSG_TOO_LARGE})
    # 틀린 본문·없는 분석이어도 413 이 먼저
    assert post(done, b"x" * (MAX_BODY_BYTES + 1), analysis_id="not-a-uuid").status_code == 413
    assert done.store.calls == [] and done.store.reviews == {}


def test_chunked_body_over_the_limit_without_content_length_is_413(done: Ctx) -> None:
    raw = _padded(export_body(), MAX_BODY_BYTES + 1)

    def chunks() -> Iterator[bytes]:
        for start in range(0, len(raw), 4096):
            yield raw[start : start + 4096]

    request = done.client.build_request("POST", PATH, content=chunks(), headers={"content-type": "application/json"})
    assert "content-length" not in request.headers
    response = done.client.send(request)
    assert detail(response) == (413, {"detail": MSG_TOO_LARGE})
    assert done.store.calls == []


def test_small_chunked_body_is_read_in_full(done: Ctx) -> None:
    raw = json.dumps(export_body(), ensure_ascii=False).encode("utf-8")
    cut = raw.index("검".encode()) + 1  # UTF-8 글자 가운데에서 자른다
    response = done.client.post(PATH, content=iter([raw[:cut], raw[cut:]]), headers={"content-type": "application/json"})
    assert response.status_code == 200 and done.store.reviews[ANALYSIS_ID]["history"][-1]["target"] == CSV_NAME


def _raw(size: str = "6127", name: str = CSV_NAME, *, extra: str = "") -> bytes:
    text = '{"type":"log_export","actor":"김검토","format":"csv","size":' + size + ',"state":"handed","file_name":"' + name + '"' + extra + "}"
    return text.encode("utf-8")


@pytest.mark.parametrize(
    "raw",
    [
        _raw("1" + "0" * 400),
        _raw("1e400"),
        _raw("1.0"),
        _raw('"1"'),
        _raw("true"),
        _raw("null"),
        _raw("0"),
        _raw("-1"),
        _raw("104857601"),
        _raw("NaN"),
        _raw("1" * 5000),
        _raw(extra=',"size":6127'),
        _raw(extra=',"extra":1'),
        _raw(name=CSV_NAME + "\\n"),
        _raw(name=CSV_NAME + "\\u0000"),
        _raw(name=CSV_NAME + "\\ud800"),
        _raw(name=" " + CSV_NAME),
        _raw(name=JSON_NAME),
        _raw(name="iMASK_IM-20261105-7b94_검토결과_탐지항목.csv"),
        _raw(name="iMASK_IM-２０２６1105-7B94_검토결과_탐지항목.csv"),
        _raw(name="../" + CSV_NAME),
        b'{"type":"log_export","actor":"a","format":"csv","size":6127,"state":"handed","file_name":' + b"[" * 30_000 + b"]" * 30_000 + b"}",
        b'{"type":"log_export","actor":"a","format":"csv","size":6127,"state":"handed","file_name":' + b'{"a":' * 10_000 + b"1" + b"}" * 10_000 + b"}",
        b"\xff" + _raw(),
    ],
)
def test_bad_raw_bodies_are_400_without_reading_the_store(done: Ctx, raw: bytes) -> None:
    assert len(raw) <= MAX_BODY_BYTES or raw.startswith(b"\xff")
    response = post(done, raw)
    if len(raw) > MAX_BODY_BYTES:
        assert response.status_code == 413
    else:
        assert detail(response) == (400, {"detail": MSG_FORMAT})
    assert done.store.calls == []


def test_deep_nesting_over_the_limit_is_413_never_500(done: Ctx) -> None:
    raw = b'{"type":"log_export","file_name":' + b"[" * 70_000
    assert post(done, raw).status_code == 413


# --- 오류 순서 ------------------------------------------------------------------------------------


def test_error_order(done: Ctx) -> None:
    missing = "00000000-0000-4000-8000-000000000000"
    wrong_name = "iMASK_IM-20261104-7B94_검토결과_탐지항목.csv"  # UTC 날짜 — 이 분석의 이름이 아니다
    # 413 → 400 모양
    assert post(done, b"x" * (MAX_BODY_BYTES + 1), analysis_id=missing).status_code == 413
    # 400 모양 → 400 처리자: 처리자도 틀리고 모양도 틀리면 형식
    assert detail(post(done, export_body(actor="", size=0), analysis_id=missing)) == (400, {"detail": MSG_FORMAT})
    assert detail(post(done, export_body(actor="", file_name=CSV_NAME + "\n"), analysis_id=missing)) == (400, {"detail": MSG_FORMAT})
    # 400 처리자 → 404: 없는 분석이어도 처리자가 틀리면 400
    assert detail(post(done, export_body(actor=" 김"), analysis_id=missing)) == (400, {"detail": MSG_BAD_ACTOR})
    assert detail(post(done, export_body(actor="a" * 41), analysis_id="not-a-uuid")) == (400, {"detail": MSG_BAD_ACTOR})
    # 404 → 409: 없는 분석·uuid 아님(이름이 틀려도 404)
    for analysis_id in (missing, "not-a-uuid"):
        assert detail(post(done, export_body(file_name=wrong_name), analysis_id=analysis_id)) == (404, {"detail": MSG_NOT_FOUND})
    # 409 검토할 수 없음 → 400 이름: 대기 분석에 틀린 이름
    put_analysis(done.store, analysis_id=OTHER_ID, status="queued")
    assert detail(post(done, export_body(file_name=wrong_name), analysis_id=OTHER_ID)) == (409, {"detail": MSG_NOT_REVIEWABLE})
    # 400 이름 → 409 이력: 이력이 가득 차도 이름이 틀리면 400
    done.store.put_review(ANALYSIS_ID, history=filler(1000), version=1000)
    assert detail(post(done, export_body(file_name=wrong_name))) == (400, {"detail": MSG_FORMAT})
    assert detail(post(done, export_body())) == (409, {"detail": MSG_HISTORY_FULL})
    assert done.store.review_writes == []


@pytest.mark.parametrize(
    ("status", "result"),
    [
        ("queued", None),
        ("running", None),
        ("failed", None),
        ("done", None),
        ("done", custom_result(SMALL, pageless_classify=True)),
    ],
    ids=["queued", "running", "failed", "done_without_result", "done_zero_documents"],
)
def test_unreviewable_is_409(ctx: Ctx, status: str, result: Any) -> None:  # noqa: F811
    put_analysis(ctx.store, status=status, result=result, with_result=False)
    assert detail(post(ctx, export_body())) == (409, {"detail": MSG_NOT_REVIEWABLE})
    assert "get_review" not in ctx.store.calls and ctx.store.review_writes == []
    ctx.no_upstage()


def test_names_of_other_analyses_are_400(done: Ctx) -> None:
    put_analysis(done.store, analysis_id=OTHER_ID, created_at="2026-11-04T14:59:59.999999Z")
    other_name = "iMASK_IM-20261104-3C1D_검토결과_탐지항목.csv"
    for name in (
        other_name,  # 다른 분석의 이름
        "iMASK_IM-20261104-7B94_검토결과_탐지항목.csv",  # 날짜만 다름(UTC 날짜)
        "iMASK_IM-20261106-7B94_검토결과_탐지항목.csv",
        "iMASK_IM-20261105-7B95_검토결과_탐지항목.csv",  # id 4자만 다름
    ):
        assert detail(post(done, export_body(file_name=name))) == (400, {"detail": MSG_FORMAT}), name
    assert detail(post(done, export_body(), analysis_id=OTHER_ID)) == (400, {"detail": MSG_FORMAT})
    assert done.store.review_writes == []
    # 각자의 이름은 된다
    assert post(done, export_body(file_name=other_name), analysis_id=OTHER_ID).status_code == 200
    assert post(done, export_body()).status_code == 200


@pytest.mark.parametrize("created_at", [None, "", "garbage", "2026-11-04T15:00:00", "2026-11-04T15:00:00+00"])
def test_row_with_unreadable_created_at_is_400(ctx: Ctx, created_at: Any) -> None:  # noqa: F811
    put_analysis(ctx.store, created_at=created_at)
    assert detail(post(ctx, export_body())) == (400, {"detail": MSG_FORMAT})
    assert ctx.store.review_writes == []


@pytest.mark.parametrize("zone", ["+00:60", "-00:60", "+01:99", "+24:00", "+23:60"])
def test_out_of_range_time_zones_have_no_name_and_write_nothing(ctx: Ctx, zone: str) -> None:  # noqa: F811
    # V-T1-1 m1: 파이썬이 보정해 읽던 날짜(예: +00:60 → +01:00 → 서울 11-04)의 이름도, 다음 날 이름도 400
    put_analysis(ctx.store, created_at="2026-11-04T15:00:00" + zone)
    for day in ("20261104", "20261105"):
        response = post(ctx, export_body(file_name=f"iMASK_IM-{day}-7B94_검토결과_탐지항목.csv"))
        assert detail(response) == (400, {"detail": MSG_FORMAT}), (zone, day)
    assert ctx.store.review_writes == [] and ctx.store.reviews == {}


@pytest.mark.parametrize(
    ("created_at", "day"),
    [("2026-11-04T00:00:00+23:59", "20261103"), ("2026-11-04T00:00:00-23:59", "20261105"), ("2026-11-04T05:30:00.123456+00:00", "20261104")],
)
def test_in_range_time_zones_still_work(ctx: Ctx, created_at: str, day: str) -> None:  # noqa: F811
    put_analysis(ctx.store, created_at=created_at)
    response = post(ctx, export_body(file_name=f"iMASK_IM-{day}-7B94_검토결과_탐지항목.csv"))
    assert response.status_code == 200 and response.json()["changed"] is True


def test_history_limit_is_409(done: Ctx) -> None:
    done.store.put_review(ANALYSIS_ID, history=filler(999), version=999, status="done")
    assert post(done, export_body()).status_code == 200
    assert len(done.store.reviews[ANALYSIS_ID]["history"]) == 1000
    assert detail(post(done, export_body())) == (409, {"detail": MSG_HISTORY_FULL})
    assert done.store.reviews[ANALYSIS_ID]["version"] == 1000


def _bump(store: Any, analysis_id: str) -> None:
    store.reviews[analysis_id]["version"] += 1


def test_three_lost_races_are_409(done: Ctx, caplog: pytest.LogCaptureFixture) -> None:
    done.store.put_review(ANALYSIS_ID)
    done.store.review_hooks = [_bump, _bump, _bump]
    with caplog.at_level(logging.DEBUG, logger="imask"):
        response = post(done, export_body())
    assert detail(response) == (409, {"detail": MSG_CONFLICT})
    assert done.store.reviews[ANALYSIS_ID]["history"] == []
    logged = "\n".join(r.getMessage() for r in caplog.records)
    for value in (CSV_NAME, ACTOR, ANALYSIS_ID):
        assert value not in logged


def test_two_lost_races_then_win(done: Ctx) -> None:
    done.store.put_review(ANALYSIS_ID)
    done.store.review_hooks = [_bump, _bump]
    response = post(done, export_body())
    assert response.status_code == 200 and response.json()["analysis"]["review"]["history"][-1]["id"] == "H4"


def test_deleted_during_the_race_is_404(done: Ctx) -> None:
    done.store.put_review(ANALYSIS_ID)

    def bump_and_delete(store: Any, analysis_id: str) -> None:
        _bump(store, analysis_id)
        store.analyses.pop(analysis_id)

    done.store.review_hooks = [_bump, _bump, bump_and_delete]
    assert detail(post(done, export_body())) == (404, {"detail": MSG_NOT_FOUND})


@pytest.mark.parametrize("existing", [False, True])
def test_deleted_right_before_the_write_is_404(done: Ctx, existing: bool) -> None:
    if existing:
        done.store.put_review(ANALYSIS_ID)
    done.store.review_hooks = [lambda store, aid: store.delete_analysis(aid)]
    assert detail(post(done, export_body())) == (404, {"detail": MSG_NOT_FOUND})
    assert ANALYSIS_ID not in done.store.reviews


@pytest.mark.parametrize("method", ["get_analysis", "get_review", "insert_review"])
def test_store_errors_are_502_without_values_in_logs(done: Ctx, method: str, caplog: pytest.LogCaptureFixture) -> None:
    done.store.fail.add(method)
    with caplog.at_level(logging.DEBUG, logger="imask"):
        response = post(done, export_body())
    assert detail(response) == (502, {"detail": MSG_STORE})
    logged = "\n".join(r.getMessage() for r in caplog.records)
    for value in (CSV_NAME, ACTOR):
        assert value not in logged


def test_update_store_error_is_502(done: Ctx) -> None:
    assert post(done, export_body()).status_code == 200
    done.store.fail.add("update_review")
    assert detail(post(done, export_body())) == (502, {"detail": MSG_STORE})


def test_other_nine_actions_still_work_alongside(done: Ctx) -> None:
    ids = finding_ids(done)
    steps = [
        ("set_status", {"finding_id": ids["D1-01"], "status": "confirmed", "reason": ""}),
        ("log_export", {"format": "csv", "size": 6127, "state": "handed", "file_name": CSV_NAME}),
        ("confirm_many", {"finding_ids": [ids["D1-02"]]}),
        ("complete_review", {"note": ""}),
        ("log_export", {"format": "json", "size": 22021, "state": "saved", "file_name": JSON_NAME}),
        ("reopen_review", {"reason": ""}),
        ("save_memo", {"text": "m"}),
    ]
    for kind, fields in steps:
        response = done.act(ANALYSIS_ID, kind, **fields)
        assert response.status_code == 200 and response.json()["changed"] is True, (kind, response.text)
    history = done.get(ANALYSIS_ID).json()["review"]["history"]
    assert [h["kind"] for h in history] == ["request", "ai", "confirm", "export", "confirm", "complete", "export", "reopen", "memo"]


# --- 분석 번호 머리글자 DG- → IM-(web-polish T2) ---------------------------------------------------------------------


def test_new_export_records_accept_only_the_im_prefix(done: Ctx) -> None:
    from imask_backend.exports import FILE_NAME_RE, LEGACY_FILE_NAME_RE

    legacy = CSV_NAME.replace("iMASK_IM-", "iMASK_DG-", 1)
    assert CSV_NAME.startswith("iMASK_IM-") and FILE_NAME_RE.fullmatch(CSV_NAME) and LEGACY_FILE_NAME_RE.fullmatch(legacy)
    assert not FILE_NAME_RE.fullmatch(legacy)
    response = post(done, export_body(file_name=legacy))
    assert detail(response) == (400, {"detail": MSG_FORMAT})
    assert ANALYSIS_ID not in done.store.reviews  # 쓰지 않았다
    assert post(done, export_body()).status_code == 200


def test_stored_legacy_export_line_is_read_back_unchanged(done: Ctx) -> None:
    legacy = JSON_NAME.replace("iMASK_IM-", "iMASK_DG-", 1)
    old_line = {
        "id": "H1",
        "at": "2026-11-05T01:00:00+00:00",
        "actor": ACTOR,
        "kind": "export",
        "target": legacy,
        "change": "JSON · 22KB · 저장 완료",
        "reason": "민감한 값 마스킹",
    }
    reopen = {**old_line, "id": "H2", "kind": "reopen", "target": "분석 건", "change": "검토 완료 → 검토 필요", "reason": "옛 글"}
    done.store.put_review(ANALYSIS_ID, history=[old_line, reopen], version=2)
    history = done.get(ANALYSIS_ID).json()["review"]["history"]
    assert [h["id"] for h in history] == ["S1", "S2", "H1", "H2"]
    assert history[2] == old_line  # 옛 이름 그대로(읽을 때 고쳐 쓰지 않는다)
    assert history[3]["change"] == "검토 완료 → 검토 필요"  # 저장된 옛 검토 상태 글도 그대로
    # 그 뒤 새 기록은 IM- 이름으로 이어진다
    response = post(done, export_body())
    assert response.status_code == 200
    assert [h["target"] for h in response.json()["analysis"]["review"]["history"] if h["kind"] == "export"] == [legacy, CSV_NAME]
