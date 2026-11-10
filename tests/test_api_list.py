# ==========================================================================
#  GET /api/py/analyses — 공유 목록 (shared-analyses BRIEF §5.2, 네트워크 없음)
#  - limit 표(없음 → 100, 1·200·007 통과 / 빈 값·0·201·부호·공백·소수점·지수·밑줄·문자·4자리 이상·4300자리·두 번 → 400)
#  - 응답 키(항목·문서 셋 키), DB 순서, 문서 만든 순, risk_level(문자열만), review 규칙 표(목록·상세 어긋남 사례 포함)
#  - 행 하나 예외 격리, 짝 없는 서로게이트 이름(ASCII escape), Upstage 안 부름, 쓰기 없음, 저장소 오류 502
# ==========================================================================

from __future__ import annotations

import copy
import json
import logging
import uuid
from typing import Any

import pytest
from api_fakes import FAKE_ENV
from fake_findings import stored_result
from fake_reviews import SMALL, custom_result
from fastapi.testclient import TestClient
from shared_ctx import ITEM_KEYS, LIST_DOC_KEYS, MSG_FORMAT, MSG_STORE, Ctx, ctx, install  # noqa: F401

from api.index import app
from imask_backend import manage
from imask_backend.manage import list_item, list_review


def _put(ctx: Ctx, created_at: str, **kw: Any) -> str:
    analysis_id = ctx.store.put(**kw)
    ctx.store.analyses[analysis_id]["created_at"] = created_at
    return analysis_id


# --- limit -----------------------------------------------------------------------------------


@pytest.mark.parametrize(("query", "limit"), [("", 100), ("?limit=1", 1), ("?limit=200", 200), ("?limit=007", 7), ("?limit=7", 7)])
def test_limit_values_that_are_accepted(ctx: Ctx, query: str, limit: int) -> None:
    response = ctx.list(query)
    assert response.status_code == 200 and response.json() == {"analyses": []}
    assert ctx.store.list_limits == [limit]


@pytest.mark.parametrize(
    "query",
    [
        "?limit=",
        "?limit",
        "?limit=0",
        "?limit=000",
        "?limit=201",
        "?limit=999",
        "?limit=-1",
        "?limit=%2B5",  # +5
        "?limit=+5",  # 질의의 + 는 공백 → ' 5'
        "?limit=%205",
        "?limit=5%20",
        "?limit=5%0A",
        "?limit=1.0",
        "?limit=1e2",
        "?limit=1_0",
        "?limit=abc",
        "?limit=0x10",
        "?limit=%EF%BC%95",  # 전각 숫자 5
        "?limit=%D9%A5",  # 아랍 숫자 5(\d 는 받지만 [0-9] 는 아니다)
        "?limit=1000",
        "?limit=0100",
        "?limit=" + "9" * 4300,
        "?limit=5&limit=5",
        "?limit=5&limit=",
    ],
)
def test_limit_values_that_are_400(ctx: Ctx, query: str) -> None:
    response = ctx.list(query)
    assert (response.status_code, response.json()) == (400, {"detail": MSG_FORMAT})
    assert ctx.store.calls == [] and ctx.store.list_limits == []


def test_other_query_names_are_ignored(ctx: Ctx) -> None:
    assert ctx.list("?foo=1&limit=3&LIMIT=abc&Limit=-1&include=stages").status_code == 200
    assert ctx.store.list_limits == [3]


def test_parse_limit_directly() -> None:
    assert manage.parse_limit([]) == 100
    assert manage.parse_limit(["200"]) == 200
    for bad in (["201"], ["0"], ["1", "2"], [" 1"], ["1 "], ["٥"], ["12345"]):
        with pytest.raises(manage.ApiError) as info:
            manage.parse_limit(bad)
        assert (info.value.status_code, info.value.detail) == (400, MSG_FORMAT)


def test_limit_cuts_the_list_after_ordering(ctx: Ctx) -> None:
    ids = [_put(ctx, f"2026-11-04T00:00:0{i}+00:00") for i in range(5)]
    body = ctx.list("?limit=2").json()
    assert [item["id"] for item in body["analyses"]] == [ids[4], ids[3]]


# --- 응답 모양 ---------------------------------------------------------------------------------


def test_items_have_exactly_the_contract_keys_in_db_order(ctx: Ctx) -> None:
    older = _put(ctx, "2026-11-01T00:00:00+00:00", status="failed", error="실패 이유")
    newer = _put(ctx, "2026-11-03T00:00:00+00:00", status="done", job_id="job_1", result=custom_result(SMALL, summary={"document_count": 2, "risk_level": "상"}))
    # 같은 created_at 이면 id desc
    same_a = _put(ctx, "2026-11-02T00:00:00+00:00")
    same_b = _put(ctx, "2026-11-02T00:00:00+00:00")
    tie = sorted([same_a, same_b], reverse=True)
    response = ctx.list()
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"analyses"}
    items = body["analyses"]
    assert [item["id"] for item in items] == [newer, *tie, older]
    for item in items:
        assert set(item) == ITEM_KEYS
        for doc in item["documents"]:
            assert set(doc) == LIST_DOC_KEYS
    first = items[0]
    row = ctx.store.analyses[newer]
    assert first == {
        "id": newer,
        "name": "가짜 분석",
        "status": "done",
        "error": None,
        "created_at": "2026-11-03T00:00:00+00:00",
        "updated_at": row["updated_at"],
        "started_at": None,
        "documents": [{"filename": "묶음.pdf", "size_bytes": len(b"%PDF-1.7\n% fake synthetic pdf\n"), "mime_type": "application/pdf"}],
        "risk_level": "상",
        "review": "needed",
        "document_count": 2,
    }
    assert items[-1]["error"] == "실패 이유" and items[-1]["review"] == "none" and items[-1]["risk_level"] is None
    assert items[-1]["document_count"] is None


def test_list_never_carries_internal_columns_or_the_result(ctx: Ctx) -> None:
    analysis_id = ctx.store.put(status="done", job_id="job_secret_1", upstage_file_id="file_secret_1", result=stored_result())
    ctx.store.analyses[analysis_id]["agent_id"] = "agt-test-FAKE-AGENT-4242"
    text = ctx.list().text
    for leaked in ("job_secret_1", "file_secret_1", "agt-test", "storage_path", "analyses/", "upstage", "findings", "stages", "\"result\""):
        assert leaked not in text


def test_documents_are_sorted_by_creation_and_reduced_to_three_keys(ctx: Ctx) -> None:
    analysis_id = ctx.store.put(filename="첫째.pdf")
    (first_doc,) = ctx.store.docs_of(analysis_id)
    first_doc["created_at"] = "2026-11-04T00:00:01+00:00"
    extra = [
        {"id": "00000000-0000-4000-8000-00000000000b", "created_at": "2026-11-04T00:00:02+00:00", "filename": "셋째.png", "mime_type": "image/png"},
        {"id": "00000000-0000-4000-8000-00000000000a", "created_at": "2026-11-04T00:00:02+00:00", "filename": "둘째.jpg", "mime_type": "image/jpeg"},
    ]
    for doc in extra:
        ctx.store.documents[doc["id"]] = {
            **doc,
            "analysis_id": analysis_id,
            "storage_path": f"analyses/{analysis_id}/x",
            "size_bytes": 5,
            "upstage_file_id": "file_x",
        }
    (item,) = ctx.list().json()["analyses"]
    assert [d["filename"] for d in item["documents"]] == ["첫째.pdf", "둘째.jpg", "셋째.png"]
    assert item["documents"][1] == {"filename": "둘째.jpg", "size_bytes": 5, "mime_type": "image/jpeg"}


@pytest.mark.parametrize("documents", [None, "x", 5, {"filename": "a"}])
def test_documents_that_are_not_a_list_become_empty(documents: Any) -> None:
    assert list_item({"id": "a", "documents": documents})["documents"] == []


def test_non_object_documents_are_dropped() -> None:
    item = list_item({"id": "a", "documents": [None, "x", {"filename": "a.pdf", "size_bytes": 1, "mime_type": "application/pdf", "extra": 1}]})
    assert item["documents"] == [{"filename": "a.pdf", "size_bytes": 1, "mime_type": "application/pdf"}]


@pytest.mark.parametrize(
    ("summary", "expected"),
    [
        ({"risk_level": "상"}, "상"),
        ({"risk_level": "중"}, "중"),
        ({"risk_level": " 하 "}, " 하 "),  # 문자열은 그대로(화면이 상·중·하만 읽는다)
        ({"risk_level": 3}, "3"),  # Postgres ->> 는 숫자도 글자로 준다
        ({"risk_level": True}, "true"),
        ({"risk_level": {"a": 1}}, '{"a": 1}'),
        ({"risk_level": None}, None),
        ({}, None),
    ],
)
def test_risk_level_comes_from_the_json_path_text(ctx: Ctx, summary: dict[str, Any], expected: Any) -> None:
    ctx.store.put(status="done", job_id="j", result={"format": "imask-upstage-v1", "summary": summary})
    assert ctx.list().json()["analyses"][0]["risk_level"] == expected


@pytest.mark.parametrize("result", [None, {"format": "x"}, {"summary": None}, {"summary": "상"}])
def test_risk_level_without_summary_is_null(ctx: Ctx, result: Any) -> None:
    ctx.store.put(status="done", job_id="j", result=result)
    item = ctx.list().json()["analyses"][0]
    assert item["risk_level"] is None and item["review"] == "none"


@pytest.mark.parametrize("value", [3, 1.5, True, None, {"a": 1}, ["상"]])
def test_non_string_risk_level_values_become_null(value: Any) -> None:
    # PostgREST ->> 는 늘 글자 또는 null 이지만, 다른 모양이 와도 문자열만 내보낸다
    assert list_item({"id": "a", "status": "done", "risk_level": value})["risk_level"] is None


# --- review 규칙 ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "count", "embedded", "expected"),
    [
        ("done", 1, {"status": "done"}, "done"),
        ("done", 1, {"status": "needed"}, "needed"),
        ("done", 1, None, "needed"),
        ("done", 1, {"status": "weird"}, "needed"),
        ("done", 1, {"status": None}, "needed"),
        ("done", 1, {}, "needed"),
        ("done", 1, "done", "needed"),
        ("done", 1, [{"status": "done"}], "done"),
        ("done", 1, [], "needed"),
        ("done", 1, [5, {"status": "done"}, {"status": "needed"}], "done"),
        ("done", 1, [{"status": "needed"}, {"status": "done"}], "needed"),
        ("done", 6, {"status": "done"}, "done"),
        ("done", 0, {"status": "done"}, "none"),
        ("done", -1, {"status": "done"}, "none"),
        ("done", None, {"status": "done"}, "none"),
        ("done", True, {"status": "done"}, "none"),
        ("done", False, None, "none"),
        ("done", "1", {"status": "done"}, "none"),
        ("done", 1.0, {"status": "done"}, "none"),
        ("done", {"n": 1}, None, "none"),
        ("queued", 1, {"status": "done"}, "none"),
        ("running", 1, {"status": "done"}, "none"),
        ("failed", 1, {"status": "done"}, "none"),
        ("partial", 1, {"status": "done"}, "none"),
        (None, 1, None, "none"),
    ],
)
def test_review_rule_table(status: Any, count: Any, embedded: Any, expected: str) -> None:
    assert list_review(status, count, embedded) == expected


@pytest.mark.parametrize("as_list", [False, True])
def test_review_over_http_uses_the_one_to_one_review_row(ctx: Ctx, as_list: bool) -> None:
    ctx.store.review_embed_as_list = as_list
    result = custom_result(SMALL, summary={"document_count": 2})
    done_reviewed = _put(ctx, "2026-11-04T00:00:03+00:00", status="done", job_id="j1", result=result)
    ctx.store.put_review(done_reviewed, status="done")
    done_open = _put(ctx, "2026-11-04T00:00:02+00:00", status="done", job_id="j2", result=result)
    ctx.store.put_review(done_open, status="needed")
    done_no_row = _put(ctx, "2026-11-04T00:00:01+00:00", status="done", job_id="j3", result=result)
    queued = _put(ctx, "2026-11-04T00:00:00+00:00")
    reviews = {item["id"]: item["review"] for item in ctx.list().json()["analyses"]}
    assert reviews == {done_reviewed: "done", done_open: "needed", done_no_row: "needed", queued: "none"}


def test_list_and_detail_disagree_when_counted_documents_have_no_pages(ctx: Ctx) -> None:
    # 알려진 차이(BRIEF §5.2 — 고치지 않음): 요약의 서류 수 ≥ 1 인데 쪽 범위가 없어 화면용 유효 서류가 0개
    # → 목록은 'needed', 상세는 review null(검토할 수 없음)
    result = custom_result(SMALL, pageless_classify=True, summary={"document_count": 2})
    analysis_id = ctx.store.put(status="done", job_id="j", result=result)
    assert ctx.list().json()["analyses"][0]["review"] == "needed"
    detail = ctx.get(analysis_id).json()
    assert detail["review"] is None
    assert detail["result"]["documents"] and all(d["page_start"] is None for d in detail["result"]["documents"])


def test_list_and_detail_disagree_the_other_way_when_the_summary_has_no_count(ctx: Ctx) -> None:
    # 반대 방향도 생길 수 있다: 저장된 요약에 서류 수가 없는데(손으로 만든·옛 결과) 화면용 유효 서류는 있음
    # → 목록 'none', 상세는 review 객체
    analysis_id = ctx.store.put(status="done", job_id="j", result=custom_result(SMALL, summary={}))
    assert ctx.list().json()["analyses"][0]["review"] == "none"
    assert ctx.get(analysis_id).json()["review"] is not None


def test_real_results_count_the_same_documents_as_the_detail(ctx: Ctx) -> None:
    # 실제 저장 형식(요약을 같은 단계에서 계산)에서는 목록과 상세가 같다
    analysis_id = ctx.store.put(status="done", job_id="j", result=stored_result())
    assert ctx.list().json()["analyses"][0]["review"] == "needed"
    assert ctx.get(analysis_id).json()["review"]["status"] == "needed"
    ctx.store.put_review(analysis_id, status="done")
    assert ctx.list().json()["analyses"][0]["review"] == "done"
    assert ctx.get(analysis_id).json()["review"]["status"] == "done"


# --- 견고함 ------------------------------------------------------------------------------------


def test_one_broken_row_is_dropped_with_a_value_free_warning(ctx: Ctx, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    good = ctx.store.put()
    bad = ctx.store.put()
    ctx.store.analyses[bad]["name"] = "비밀이름-표식"
    original = manage.list_item

    def flaky(row: Any) -> dict[str, Any]:
        if isinstance(row, dict) and row.get("id") == bad:
            raise ValueError(f"boom {row['name']}")
        return original(row)

    monkeypatch.setattr(manage, "list_item", flaky)
    with caplog.at_level(logging.DEBUG, logger="imask"):
        response = ctx.list()
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["analyses"]] == [good]
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "목록 행 하나를 만들지 못해" in logged and "ValueError" in logged
    assert bad not in logged and "비밀이름" not in logged


def test_rows_that_are_not_objects_are_dropped(ctx: Ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    good = ctx.store.put()
    rows = ctx.store.list_analyses(100)
    ctx.store.calls.clear()
    monkeypatch.setattr(ctx.store, "list_analyses", lambda limit: [None, "x", 5, [], *rows])
    assert [item["id"] for item in ctx.list().json()["analyses"]] == [good]


def test_unpaired_surrogate_name_is_sent_as_ascii_escaped_json(ctx: Ctx) -> None:
    analysis_id = ctx.store.put(status="failed")
    ctx.store.analyses[analysis_id]["name"] = "이름\ud800끝"
    ctx.store.analyses[analysis_id]["error"] = "오류\udfff"
    response = ctx.list()
    assert response.status_code == 200 and response.headers["content-type"] == "application/json"
    raw = response.content
    assert raw.isascii() and b"\\ud800" in raw and b"\\udfff" in raw
    (item,) = json.loads(raw)["analyses"]
    assert item["name"] == "이름\ud800끝" and item["error"] == "오류\udfff"


def test_clean_names_keep_the_normal_utf8_body(ctx: Ctx) -> None:
    ctx.store.put()
    raw = ctx.list().content
    assert "가짜 분석".encode() in raw


def test_list_needs_no_upstage_settings_and_makes_no_client(monkeypatch: pytest.MonkeyPatch) -> None:
    env = {k: v for k, v in FAKE_ENV.items() if not k.startswith("UPSTAGE_")}
    context = install(monkeypatch, env)
    try:
        with TestClient(app) as client:
            context.store.put(status="running", job_id="job_1")
            response = client.get("/api/py/analyses")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200 and response.json()["analyses"][0]["status"] == "running"
    context.no_upstage()


def test_list_reads_once_and_writes_nothing(ctx: Ctx) -> None:
    ids = [ctx.store.put(status=s, job_id="j" if s != "queued" else None) for s in ("queued", "running", "done", "failed")]
    ctx.store.put_review(ids[2], status="done")
    before = (copy.deepcopy(ctx.store.analyses), copy.deepcopy(ctx.store.documents), copy.deepcopy(ctx.store.reviews), dict(ctx.store.objects))
    assert ctx.list().status_code == 200
    assert ctx.store.calls == ["list_analyses"]
    assert ctx.store.updates == [] and ctx.store.review_writes == [] and ctx.store.removed == []
    assert (ctx.store.analyses, ctx.store.documents, ctx.store.reviews, ctx.store.objects) == before
    ctx.no_upstage()  # 분석 중 행이 있어도 Upstage 를 부르지 않는다


def test_store_error_is_502(ctx: Ctx) -> None:
    ctx.store.fail.add("list_analyses")
    response = ctx.list()
    assert (response.status_code, response.json()) == (502, {"detail": MSG_STORE})


def test_other_methods_on_the_list_path_are_405(ctx: Ctx) -> None:
    assert ctx.client.request("DELETE", "/api/py/analyses").status_code == 405


def test_unknown_id_path_is_not_the_list(ctx: Ctx) -> None:
    assert ctx.get(str(uuid.uuid4())).status_code == 404
