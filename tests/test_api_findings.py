# ==========================================================================
#  조회 응답의 documents·findings·overall 과 ?include=stages, 원본 파일 주소 GET /analyses/{id}/file
#  (T1 findings-api). 저장소는 메모리 가짜(FakeStore), Upstage 는 진짜 클라이언트 + 가짜 서버. 네트워크 없음.
# ==========================================================================

from __future__ import annotations

import copy
import json
import logging
import random
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from api_fakes import (
    ALL_SECRETS,
    FAKE_ACCESS_CODE,
    FAKE_ENV,
    FakeStore,
    FakeUpstageServer,
)
from fake_findings import (
    EXPECTED_BOXED,
    EXPECTED_FINDINGS,
    VALUES,
    build_findings_response,
    rect,
    stored_result,
)
from fastapi.testclient import TestClient
from view_contract import assert_view

from api.index import app, get_store, get_upstage
from imask_backend import analyses as analyses_module
from imask_backend import findings as findings_module
from imask_backend import textsafe
from imask_backend.analyses import MAX_STAGES_DEPTH, nesting_exceeds
from imask_backend.results import parse_stages
from imask_backend.settings import get_settings, load_settings
from imask_backend.upstage import UpstageClient

CODE = {"X-Demo-Code": FAKE_ACCESS_CODE}
VIEW_KEYS = {"format", "job", "summary", "documents", "findings", "overall"}
MSG_NOT_FOUND = "분석 건을 찾을 수 없습니다."
MSG_ORIGINAL_MISSING = "원본 파일을 찾을 수 없습니다."
MSG_LINK_FAILED = "원본 파일 주소를 만들지 못했습니다. 잠시 후 다시 시도해 주세요."


@dataclass
class Ctx:
    client: TestClient
    store: FakeStore
    server: FakeUpstageServer

    def get(self, analysis_id: str, params: Any = None) -> httpx.Response:
        return self.client.get(f"/api/py/analyses/{analysis_id}", headers=CODE, params=params)

    def file(self, analysis_id: str, headers: Any = None) -> httpx.Response:
        return self.client.get(f"/api/py/analyses/{analysis_id}/file", headers=CODE if headers is None else headers)


@pytest.fixture
def ctx() -> Iterator[Ctx]:
    settings = load_settings(dict(FAKE_ENV))
    store = FakeStore()
    server = FakeUpstageServer()
    server.full_response = build_findings_response()

    def upstage_override() -> Iterator[Any]:
        made: list[UpstageClient] = []

        def factory() -> UpstageClient:
            if not made:
                made.append(UpstageClient.from_settings(settings.upstage(), transport=httpx.MockTransport(server.handle)))
            return made[0]

        yield factory

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_upstage] = upstage_override
    with TestClient(app) as client:
        yield Ctx(client, store, server)
    app.dependency_overrides.clear()


def _done(ctx: Ctx, **kw: Any) -> str:
    return ctx.store.put(status="done", job_id="job_done", result=kw.pop("result", None) or stored_result(), **kw)


def _clean(text: str) -> None:
    for secret in ALL_SECRETS:
        assert secret not in text


# --- 조회 응답 -----------------------------------------------------------------------


def test_done_result_has_view_without_stages_or_response(ctx: Ctx) -> None:
    analysis_id = _done(ctx)
    response = ctx.get(analysis_id)
    assert response.status_code == 200
    result = response.json()["result"]
    assert set(result) == VIEW_KEYS
    assert_view(result)
    assert len(result["documents"]) == 6
    assert len(result["findings"]) == EXPECTED_FINDINGS
    assert sum(1 for f in result["findings"] if f["boxes"]) == EXPECTED_BOXED
    assert result["overall"]["level"] == "상" and result["overall"]["next_stage"] == "권장_조치"
    assert result["summary"]["document_count"] == 6  # 저장된 요약은 그대로
    assert ctx.server.requests == []  # done 은 Upstage 를 부르지 않는다
    assert ctx.store.updates == []  # 저장 형식은 바꾸지 않는다(조회할 때 계산)
    _clean(response.text)


@pytest.mark.parametrize(
    "params",
    [{"include": "stages"}, {"include": "foo,stages"}, [("include", "foo"), ("include", "stages")], {"include": " STAGES "}],
)
def test_include_stages(ctx: Ctx, params: Any) -> None:
    analysis_id = _done(ctx)
    result = ctx.get(analysis_id, params=params).json()["result"]
    assert set(result) == VIEW_KEYS | {"stages"}
    assert result["stages"] == ctx.store.analyses[analysis_id]["result"]["stages"]
    assert "response" not in result


@pytest.mark.parametrize("params", [{"include": "foo"}, {"include": ""}, {"include": "stage"}, {"include": ",,"}])
def test_unknown_include_is_ignored(ctx: Ctx, params: Any) -> None:
    analysis_id = _done(ctx)
    response = ctx.get(analysis_id, params=params)
    assert response.status_code == 200
    assert set(response.json()["result"]) == VIEW_KEYS


def test_default_response_is_much_smaller_than_with_stages(ctx: Ctx) -> None:
    analysis_id = _done(ctx)
    small = len(ctx.get(analysis_id).content)
    big = len(ctx.get(analysis_id, params={"include": "stages"}).content)
    assert small < big


def test_old_result_with_stages_only_still_gets_view(ctx: Ctx) -> None:
    analysis_id = _done(ctx, result=stored_result(keep_response=False))
    result = ctx.get(analysis_id).json()["result"]
    assert len(result["findings"]) == EXPECTED_FINDINGS
    staged = ctx.get(analysis_id, params={"include": "stages"}).json()["result"]
    assert staged["stages"] and staged["stages"][0]["name"] == "step_1_parse"


def test_include_stages_parses_response_when_stages_missing(ctx: Ctx) -> None:
    result = stored_result()
    result.pop("stages")
    analysis_id = _done(ctx, result=result)
    staged = ctx.get(analysis_id, params={"include": "stages"}).json()["result"]
    assert [s["name"] for s in staged["stages"]][:2] == ["step_1_parse", "step_2_classify"]


def test_running_poll_that_completes_returns_view(ctx: Ctx) -> None:
    ctx.server.files["file_up1"] = ("document.pdf", b"")
    analysis_id = ctx.store.put(status="running", job_id="job_up1", upstage_file_id="file_up1")
    ctx.server.last_status = "completed"
    body = ctx.get(analysis_id).json()
    assert body["status"] == "done"
    assert set(body["result"]) == VIEW_KEYS
    assert len(body["result"]["findings"]) == EXPECTED_FINDINGS
    stored = ctx.store.analyses[analysis_id]["result"]
    assert set(stored) == {"format", "job", "summary", "stages", "response"}  # DB 저장 형식은 그대로


def test_view_failure_does_not_make_500(ctx: Ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: Any) -> Any:
        raise ValueError("boom")

    monkeypatch.setattr(findings_module, "_documents", boom)
    analysis_id = _done(ctx)
    response = ctx.get(analysis_id)
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["documents"] == [] and result["findings"] == []
    assert result["overall"] == {"level": None, "text": "", "next_stage": None, "next_text": ""}


@pytest.mark.parametrize("result", [{"format": "imask-upstage-v1", "response": [1, 2]}, {"stages": "x"}, {}])
def test_odd_stored_results_are_200(ctx: Ctx, result: Any) -> None:
    analysis_id = _done(ctx, result=result)
    response = ctx.get(analysis_id)
    assert response.status_code == 200
    assert_view(response.json()["result"])


def test_create_and_start_responses_have_no_result(ctx: Ctx) -> None:
    body = {"filename": "묶음.pdf", "size": 10, "mime_type": "application/pdf"}
    created = ctx.client.post("/api/py/analyses", json=body, headers=CODE).json()
    assert created["analysis"]["result"] is None


# --- 원본 파일 주소 -------------------------------------------------------------------


@pytest.mark.parametrize("status", ["queued", "running", "done", "failed"])
def test_file_link(ctx: Ctx, status: str, caplog: pytest.LogCaptureFixture) -> None:
    analysis_id = ctx.store.put(status=status, job_id=None if status == "queued" else "job_x", filename="대출 서류.pdf")
    with caplog.at_level(logging.DEBUG):
        response = ctx.file(analysis_id)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"url", "mime_type", "filename"}
    assert body["mime_type"] == "application/pdf"
    assert body["filename"] == "대출 서류.pdf"  # 원래 이름
    path = f"analyses/{analysis_id}/document.pdf"
    assert body["url"].startswith(f"https://fake-project.supabase.co/storage/v1/object/sign/documents/{path}?token=")
    assert response.headers["cache-control"] == "no-store"
    assert ctx.store.signed_downloads == [(path, 600)]  # 10분
    assert ctx.server.requests == []  # running 이어도 Upstage 를 부르지 않는다
    assert ctx.store.updates == []
    token = body["url"].split("token=", 1)[1]
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert token not in logged and body["url"] not in logged  # 서명 URL 을 로그에 남기지 않는다
    _clean(response.text)


@pytest.mark.parametrize("headers", [{}, {"X-Demo-Code": "wrong"}])
def test_file_link_needs_access_code(ctx: Ctx, headers: dict[str, str]) -> None:
    analysis_id = ctx.store.put()
    response = ctx.file(analysis_id, headers=headers)
    assert response.status_code == 401
    assert response.json() == {"detail": "접근 코드가 맞지 않습니다."}
    assert ctx.store.signed_downloads == []


@pytest.mark.parametrize("analysis_id", ["not-a-uuid", str(uuid.uuid4())])
def test_file_link_unknown_analysis_is_404(ctx: Ctx, analysis_id: str) -> None:
    response = ctx.file(analysis_id)
    assert response.status_code == 404
    assert response.json() == {"detail": MSG_NOT_FOUND}


def test_file_link_without_document_row_is_404(ctx: Ctx) -> None:
    analysis_id = ctx.store.put(with_document=False)
    response = ctx.file(analysis_id)
    assert response.status_code == 404
    assert response.json() == {"detail": MSG_ORIGINAL_MISSING}
    assert ctx.store.signed_downloads == []


@pytest.mark.parametrize("path", ["", "   ", None])
def test_file_link_with_empty_storage_path_is_404(ctx: Ctx, path: Any) -> None:
    analysis_id = ctx.store.put()
    (doc,) = ctx.store.docs_of(analysis_id)
    doc["storage_path"] = path
    response = ctx.file(analysis_id)
    assert response.status_code == 404
    assert response.json() == {"detail": MSG_ORIGINAL_MISSING}
    assert ctx.store.signed_downloads == []


def test_file_link_with_missing_object_is_404(ctx: Ctx) -> None:
    analysis_id = ctx.store.put(content=None)  # 문서 행은 있지만 Storage 에 객체가 없다
    response = ctx.file(analysis_id)
    assert response.status_code == 404
    assert response.json() == {"detail": MSG_ORIGINAL_MISSING}
    assert len(ctx.store.signed_downloads) == 1


def test_file_link_store_error_is_502(ctx: Ctx) -> None:
    analysis_id = ctx.store.put()
    ctx.store.fail.add("create_signed_download_url")
    response = ctx.file(analysis_id)
    assert response.status_code == 502
    assert response.json() == {"detail": MSG_LINK_FAILED}


def test_file_link_read_error_is_store_502(ctx: Ctx) -> None:
    analysis_id = ctx.store.put()
    ctx.store.fail.add("get_analysis")
    response = ctx.file(analysis_id)
    assert response.status_code == 502
    assert response.json() == {"detail": "데이터 저장소에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요."}



# --- T1-fix2 B1: ?include=stages 의 깊은 중첩·파싱 실패 → 500 이 아니라 stages: [] ----------------------

DEEP_TEXT = "[" * 300 + "0" + "]" * 300  # 저장 JSON 은 얕고, content.text 를 풀면 300단 목록
UNPARSEABLE_TEXT = "[" * 100_000  # json.loads 가 RecursionError(→ parse_stages 자체가 실패)


def _response_only(text: str) -> dict[str, Any]:
    """저장된 stages 없이 response 만 있는(예전 꼴이 아닌) 결과 — content.text 가 text."""
    item = {"model": "Information Extract - 민감정보_추출", "status": "completed", "content": [{"type": "output_text", "text": text}]}
    return {"format": "imask-upstage-v1", "job": {}, "summary": {}, "response": {"output": [item]}}


def _nested(depth: int) -> Any:
    value: Any = 0
    for _ in range(depth):
        value = [value]
    return value


def test_deep_json_text_in_response_does_not_500(ctx: Ctx, caplog: pytest.LogCaptureFixture) -> None:
    analysis_id = _done(ctx, result=_response_only(DEEP_TEXT))
    plain = ctx.get(analysis_id)
    assert plain.status_code == 200
    assert_view(plain.json()["result"])
    with caplog.at_level(logging.WARNING, logger="imask"):
        staged = ctx.get(analysis_id, params={"include": "stages"})
    assert staged.status_code == 200
    assert staged.json()["result"]["stages"] == []
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "중첩이 한도(64)" in logged and "[[[" not in logged


def test_deeply_nested_saved_stages_do_not_500(ctx: Ctx) -> None:
    result = stored_result(keep_response=False)  # 예전 꼴: response 없이 stages 만
    result["stages"].append({"name": "가짜 단계", "key": None, "status": "completed", "data": _nested(150), "contents": []})
    analysis_id = _done(ctx, result=result)
    plain = ctx.get(analysis_id)
    assert plain.status_code == 200
    assert len(plain.json()["result"]["findings"]) == EXPECTED_FINDINGS  # view 는 그대로
    staged = ctx.get(analysis_id, params={"include": "stages"})
    assert staged.status_code == 200
    assert staged.json()["result"]["stages"] == []


def test_unparseable_response_does_not_500(ctx: Ctx, caplog: pytest.LogCaptureFixture) -> None:
    analysis_id = _done(ctx, result=_response_only(UNPARSEABLE_TEXT))
    with caplog.at_level(logging.WARNING, logger="imask"):
        plain = ctx.get(analysis_id)
        staged = ctx.get(analysis_id, params={"include": "stages"})
    assert plain.status_code == 200 and staged.status_code == 200
    assert plain.json()["result"]["findings"] == [] and plain.json()["result"]["documents"] == []
    assert staged.json()["result"]["stages"] == []
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "RecursionError" in logged and "[[[" not in logged


def test_normal_stages_pass_through_unchanged(ctx: Ctx) -> None:
    result = stored_result()
    analysis_id = _done(ctx, result=result)
    staged = ctx.get(analysis_id, params={"include": "stages"}).json()["result"]["stages"]
    assert staged == result["stages"] and len(staged) == len(result["stages"])


@pytest.mark.parametrize(
    ("value", "limit", "exceeds"),
    [
        (_nested(64), 64, False),  # 목록 64단(맨 바깥이 1단) — 한도 안
        (_nested(65), 64, True),  # 65단 — 한도 넘음
        ({"a": {"b": [{"c": 1}]}}, 4, False),
        ({"a": {"b": [{"c": []}]}}, 4, True),
        ("문자열", 0, False),
        (5, 0, False),
        ([], 1, False),
        ([[]], 1, True),
    ],
)
def test_nesting_exceeds(value: Any, limit: int, exceeds: bool) -> None:
    assert nesting_exceeds(value, limit) is exceeds


def test_real_shaped_stages_are_well_within_the_limit() -> None:
    stages = stored_result()["stages"]
    assert not nesting_exceeds(stages, 12)
    assert MAX_STAGES_DEPTH == 64



# --- T1-fix3 B2-R2: 값 변환 실패에도 항목은 남는다(API 기본·include) ------------------------------------


def test_value_conversion_failure_keeps_finding_in_api(ctx: Ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    target = VALUES[1]["staff_contact"]  # 1쪽에만 있는 값
    real = findings_module._value_text  # noqa: SLF001

    def flaky(raw: Any) -> str | None:
        if raw == target:
            raise ValueError("가짜 변환 실패")
        return real(raw)

    monkeypatch.setattr(findings_module, "_value_text", flaky)
    analysis_id = _done(ctx)
    for params in (None, {"include": "stages"}):
        response = ctx.get(analysis_id, params=params)
        assert response.status_code == 200
        result = response.json()["result"]
        assert_view(result)
        assert len(result["findings"]) == EXPECTED_FINDINGS
        kept = next(f for f in result["findings"] if f["id"] == "0:staff_contact")
        assert kept["value"] == target and kept["masked"] == "*" * len(target) and kept["boxes"] == []


# --- T1-fix5: 짝 없는 서로게이트가 든 응답만 ASCII escape JSON — 이름·값 원문 그대로(코디네이터 결정) -----------
# fix3 의 U+FFFD 치환·fix4 의 x�#2 이름 규칙을 대신한다. 이웃한 서로게이트 escape 는 따로 쓴 리터럴을 이어 붙인다
# (편집 도구가 한 리터럴의 짝 escape 를 실제 보충 평면 글자로 합칠 수 있어서).

HIGH = "\ud800"
LOW = "\udfff"
REPL = "�"


def _meta(i: int) -> dict[str, Any]:
    """키마다 다른 메타(쪽·좌표·신뢰도) — 원래 키로 찾았는지 구별된다."""
    return {"page": i + 1, "confidence": "high" if i % 2 == 0 else "low", "coordinates": rect(0.1 + 0.1 * i, 0.2), "word_coordinates": []}


def _extract_result(
    data: dict[str, Any],
    meta: dict[str, Any] | None = None,
    *,
    risk_items: list[dict[str, Any]] | None = None,
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """분류 1개(loan_application, 1쪽) + 추출 1개(+ 위험도) response-only 결과. text·additional_values 는 ASCII JSON."""

    def entry(text: str, extra: dict[str, Any]) -> dict[str, Any]:
        return {"type": "output_text", "text": text, "annotations": [], "additional_values": json.dumps(extra, ensure_ascii=True)}

    meta = {key: _meta(i) for i, key in enumerate(data)} if meta is None else meta
    output: list[dict[str, Any]] = [
        {
            "model": "step_2_classify",
            "step_type": "document-classify",
            "status": "completed",
            "content": [entry("loan_application", {"document_type": {"_value": "loan_application"}, "page_ranges": [[1, 1]]})],
        },
        {
            "model": "Information Extract - 민감정보_추출",
            "step_type": "information-extract",
            "status": "completed",
            "content": [entry(json.dumps(data, ensure_ascii=True), {"page_ranges": [[1, 1]], **meta})],
        },
    ]
    if risk_items is not None:
        output.append(
            {"model": "Instruct - 위험도_판정", "step_type": "instruct", "status": "completed", "content": [entry("## 판정", {"enum": "상", "items": risk_items})]}
        )
    return {"format": "imask-upstage-v1", "job": {}, "summary": summary or {}, "response": {"output": [*output]}}


def _both(ctx: Ctx, analysis_id: str) -> list[tuple[httpx.Response, Any]]:
    """기본·include 조회 → (응답, json.loads(본문))."""
    out = []
    for params in (None, {"include": "stages"}):
        response = ctx.get(analysis_id, params=params)
        assert response.status_code == 200
        out.append((response, json.loads(response.content)))
    return out


def _extract_stage(body: Any) -> dict[str, Any]:
    return next(s for s in body["result"]["stages"] if s["key"] == "민감정보_추출")


def _assert_original(body: Any, data: dict[str, Any]) -> list[dict[str, Any]]:
    """findings 의 field·id·value 가 원래 키·값 그대로인지, id 꼴·유일성까지."""
    found = body["result"]["findings"]
    kept = [k for k, v in data.items() if isinstance(v, str) and v.strip()]
    assert [f["field"] for f in found] == kept
    assert [f["value"] for f in found] == [data[k] for k in kept]
    assert len({f["id"] for f in found}) == len(found)
    assert all(f["id"] == f"{f['document_index']}:{f['field']}" for f in found)
    return found


def test_surrogate_values_and_keys_are_sent_escaped_and_unchanged(ctx: Ctx) -> None:
    data = {"applicant_name": "김" + HIGH + "가짜", "memo" + LOW: "값" + HIGH, "applicant_email": "smile😀@example.com"}
    analysis_id = _done(ctx, result=_extract_result(data))
    for response, body in _both(ctx, analysis_id):
        assert response.content.isascii()  # escape 경로
        assert response.headers["content-type"].startswith("application/json")
        assert_view(body["result"])
        found = _assert_original(body, data)
        assert next(f for f in found if f["field"] == "applicant_name")["masked"] == "김**짜"
    staged = _extract_stage(body)
    assert list(staged["data"]) == list(data) and staged["data"] == data  # 원래 키·값·순서 그대로
    assert list(staged["additional_values"]) == ["page_ranges", *data]
    assert list(staged["contents"][0]["data"]) == list(data)
    assert all(staged["data"][f["field"]] == f["value"] for f in body["result"]["findings"])


def test_clean_unicode_response_keeps_the_normal_path(ctx: Ctx) -> None:
    data = {"applicant_name": "김가짜", "memo": "이모지 😀 와 한글"}
    analysis_id = _done(ctx, result=_extract_result(data))
    for response, body in _both(ctx, analysis_id):
        assert not response.content.isascii()  # escape 경로를 타지 않는다(UTF-8 그대로)
        assert "이모지 😀 와 한글".encode() in response.content
        _assert_original(body, data)


def test_real_shaped_response_bytes_are_the_normal_serialization(ctx: Ctx) -> None:
    # 정상 경로 그대로: 본문 = analysis_out 을 FastAPI 기본(ensure_ascii=False, separators) 로 직렬화한 바이트
    analysis_id = _done(ctx)
    row = ctx.store.get_analysis(analysis_id)
    assert row is not None
    for params, include in ((None, False), ({"include": "stages"}, True)):
        response = ctx.get(analysis_id, params=params)
        expected = json.dumps(analyses_module.analysis_out(row, include_stages=include), ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        assert response.content == expected.encode("utf-8")


def test_escape_path_turns_nan_and_inf_into_null_like_the_normal_path(ctx: Ctx) -> None:
    result = stored_result()
    result["job"] = {**result["job"], "usage": {"nan": float("nan"), "inf": float("inf"), "minus_inf": float("-inf"), "n": 3}}
    plain_id = _done(ctx, result=copy.deepcopy(result))
    result["summary"] = {**result["summary"], "bad" + HIGH: 1}
    escaped_id = _done(ctx, result=result)
    plain = ctx.get(plain_id)
    escaped = ctx.get(escaped_id)
    assert plain.status_code == 200 and escaped.status_code == 200
    assert not plain.content.isascii() and escaped.content.isascii()
    expected = {"nan": None, "inf": None, "minus_inf": None, "n": 3}
    assert plain.json()["result"]["job"]["usage"] == expected  # 정상 경로(pydantic)도 null
    assert json.loads(escaped.content)["result"]["job"]["usage"] == expected
    assert json.loads(escaped.content)["result"]["summary"]["bad" + HIGH] == 1


def test_create_keeps_201_on_the_escape_path(ctx: Ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    real = ctx.store.insert_analysis

    def insert(name: str) -> dict[str, Any]:
        row = real(name)
        row["name"] = "가짜" + LOW + "분석"  # 저장소가 서로게이트 든 이름을 돌려준 경우
        return row

    monkeypatch.setattr(ctx.store, "insert_analysis", insert)
    body = {"filename": "묶음.pdf", "size": 10, "mime_type": "application/pdf"}
    response = ctx.client.post("/api/py/analyses", json=body, headers=CODE)
    assert response.status_code == 201
    assert response.content.isascii()
    loaded = json.loads(response.content)
    assert loaded["analysis"]["name"] == "가짜" + LOW + "분석"
    assert set(loaded["upload"]) == {"bucket", "path", "token", "signed_url"}


def test_start_uses_the_same_boundary(ctx: Ctx) -> None:
    analysis_id = ctx.store.put(name="시작" + HIGH)
    response = ctx.client.post(f"/api/py/analyses/{analysis_id}/start", headers=CODE)
    assert response.status_code == 200 and response.content.isascii()
    loaded = json.loads(response.content)
    assert loaded["name"] == "시작" + HIGH and loaded["status"] == "running"


def test_file_link_escape_path_keeps_no_store(ctx: Ctx) -> None:
    analysis_id = ctx.store.put(filename="원본" + LOW + ".pdf")
    response = ctx.file(analysis_id)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.content.isascii()
    loaded = json.loads(response.content)
    assert set(loaded) == {"url", "mime_type", "filename"} and loaded["filename"] == "원본" + LOW + ".pdf"


# --- V-T1-3·V-T1-4 재현 경우: 원래 키 그대로라 대응이 맞는다 ------------------------------------------------

COLLISIONS = [
    ["x" + HIGH, "x" + LOW],
    ["x" + REPL, "x" + HIGH],
    ["x" + HIGH, "x" + LOW, "x" + REPL + "#2"],
]


@pytest.mark.parametrize("keys", COLLISIONS, ids=["two_surrogates", "replacement_then_surrogate", "re_collision"])
def test_former_collisions_keep_every_name(ctx: Ctx, keys: list[str]) -> None:
    data = {key: f"가짜 값 {i}" for i, key in enumerate(keys)}
    analysis_id = _done(ctx, result=_extract_result(data))
    for _response, body in _both(ctx, analysis_id):
        found = _assert_original(body, data)
        assert len(found) == len(keys)
        for i, finding in enumerate(found):  # 메타는 원래 키별로
            assert (finding["page"], finding["confidence"]) == (i + 1, "high" if i % 2 == 0 else "low")
            assert finding["boxes"] == [rect(0.1 + 0.1 * i, 0.2)]
    staged = _extract_stage(body)
    assert staged["data"] == data and list(staged["additional_values"]) == ["page_ranges", *keys]
    assert all(staged["data"][f["field"]] == f["value"] for f in body["result"]["findings"])
    assert all(staged["additional_values"][f["field"]]["page"] == f["page"] for f in body["result"]["findings"])


def test_metadata_in_reverse_order(ctx: Ctx) -> None:
    keys = ["x" + HIGH, "x" + LOW]
    data = {key: f"가짜 값 {i}" for i, key in enumerate(keys)}
    meta = {key: _meta(i) for i, key in reversed(list(enumerate(keys)))}  # 순서만 반대
    analysis_id = _done(ctx, result=_extract_result(data, meta))
    for _response, body in _both(ctx, analysis_id):
        found = _assert_original(body, data)
        assert [f["page"] for f in found] == [1, 2] and [f["confidence"] for f in found] == ["high", "low"]
    staged = _extract_stage(body)
    assert list(staged["additional_values"]) == ["page_ranges", *reversed(keys)]  # 준 순서 그대로
    assert all(staged["additional_values"][f["field"]]["page"] == f["page"] for f in body["result"]["findings"])


def test_metadata_subset_and_meta_only_clean_name(ctx: Ctx) -> None:
    keys = ["x" + HIGH, "x" + LOW]
    data = {key: f"가짜 값 {i}" for i, key in enumerate(keys)}
    meta = {"x" + REPL: _meta(5), keys[1]: _meta(1)}  # 첫 키의 메타 없음 + 메타에만 있는 깨끗한 이름
    analysis_id = _done(ctx, result=_extract_result(data, meta))
    for _response, body in _both(ctx, analysis_id):
        first, second = _assert_original(body, data)
        assert (first["page"], first["boxes"], first["confidence"]) == (None, [], None)
        assert (second["page"], second["confidence"]) == (2, "low")
    staged = _extract_stage(body)
    assert list(staged["additional_values"]) == ["page_ranges", "x" + REPL, keys[1]]
    assert staged["additional_values"]["x" + REPL]["page"] == 6


def test_saved_stages_in_a_different_key_order(ctx: Ctx) -> None:
    keys = ["x" + HIGH, "x" + LOW, "y"]
    data = {key: f"가짜 값 {i}" for i, key in enumerate(keys)}
    result = _extract_result(data)
    stages = parse_stages(copy.deepcopy(result["response"]))
    extract = next(s for s in stages if s["key"] == "민감정보_추출")
    reordered = dict(reversed(list(extract["data"].items())))  # 저장된 stages 만 키 순서가 다르다
    extract["data"] = reordered
    extract["contents"][0]["data"] = reordered
    result["stages"] = stages
    analysis_id = _done(ctx, result=result)
    for _response, body in _both(ctx, analysis_id):
        _assert_original(body, data)  # findings 는 response 에서
    staged = _extract_stage(body)  # include 는 저장된 stages
    assert list(staged["data"]) == list(reversed(keys))
    assert all(staged["data"][f["field"]] == f["value"] for f in body["result"]["findings"])


def test_summary_names_and_counts_in_different_orders(ctx: Ctx) -> None:
    names = ["a" + HIGH, "a" + LOW]
    summary = {"stage_names": names, "stage_counts": {names[1]: 7, names[0]: 3}}
    analysis_id = _done(ctx, result=_extract_result({"y": "가짜"}, summary=summary))
    for _response, body in _both(ctx, analysis_id):
        got = body["result"]["summary"]
        assert got["stage_names"] == names
        assert [got["stage_counts"][name] for name in got["stage_names"]] == [3, 7]  # 이름별 개수가 맞다


def test_surrogate_field_gets_its_own_workflow_grade(ctx: Ctx) -> None:
    keys = ["x" + HIGH, "x" + LOW]
    data = {key: f"가짜 값 {i}" for i, key in enumerate(keys)}
    items = [{"branch_key": "0:loan_application", "field": keys[1], "grade": "상", "reason": "가짜 이유"}]
    analysis_id = _done(ctx, result=_extract_result(data, risk_items=items))
    for _response, body in _both(ctx, analysis_id):
        found = {f["field"]: f for f in _assert_original(body, data)}
        assert (found[keys[1]]["risk"], found[keys[1]]["risk_source"]) == ("high", "workflow")
        assert (found[keys[0]]["risk"], found[keys[0]]["risk_source"]) == ("unrated", None)


# --- M2-R4: 항목별 위험등급의 field·branch_key 는 다듬지 않고 정확히 비교한다 ---------------------------------


def test_risk_field_with_spaces_only_matches_that_key(ctx: Ctx) -> None:
    data = {"applicant_name": "김가짜", " applicant_name ": "이가짜"}
    items = [{"branch_key": "0:loan_application", "field": " applicant_name ", "grade": "상", "reason": "가짜 이유"}]
    analysis_id = _done(ctx, result=_extract_result(data, risk_items=items))
    for _response, body in _both(ctx, analysis_id):
        found = {f["field"]: f for f in _assert_original(body, data)}
        assert (found[" applicant_name "]["risk"], found[" applicant_name "]["risk_source"]) == ("high", "workflow")
        plain = found["applicant_name"]
        assert (plain["risk"], plain["risk_source"], plain["risk_reason"]) == ("unrated", None, None)


# --- 성질 테스트(씨앗 고정, API) --------------------------------------------------------------------------

API_SEED = 20261104
API_TRIALS = 60  # 씨앗 API_SEED 로 만든 무작위 키·값 추출 60개 × 기본·include 조회
API_PIECES = ("\ud800", "\udbff", "\udc00", "\udfff", REPL, "#2", "#3", "b", "한", " ")


def _api_text(rng: random.Random) -> str:
    out = rng.choice(("", "x", "가"))
    for _ in range(rng.randint(0, 3)):
        piece = rng.choice(API_PIECES)
        if out and "\ud800" <= out[-1] <= "\udbff" and "\udc00" <= piece[0] <= "\udfff":
            piece = "b"  # high 바로 뒤 low 는 JSON 을 오가며 한 글자로 합쳐지므로 만들지 않는다
        out += piece
    return out


def test_property_api_round_trip(ctx: Ctx) -> None:
    rng = random.Random(API_SEED)
    for _ in range(API_TRIALS):
        data = {_api_text(rng): rng.choice(("", "  ", "값")) + _api_text(rng) for _ in range(rng.randint(1, 6))}
        analysis_id = _done(ctx, result=_extract_result(data))
        for response, body in _both(ctx, analysis_id):
            surrogate = any(not textsafe.text_is_safe(t) for t in (*data, *data.values()))
            assert response.content.isascii() or not surrogate
            found = _assert_original(body, data)
            assert len(found) == sum(1 for v in data.values() if v.strip())
        assert _extract_stage(body)["data"] == data
