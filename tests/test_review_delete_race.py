# ==========================================================================
#  검토 동작의 삭제 경합 — 처리 도중 분석이 지워졌으면 12종 모두 404 (review-items BRIEF-F §5F F1, 네트워크 없음)
#  - 규칙: 한 시도에서 읽은 검토 행이 None 이고 그 시도가 쓰지 않고 끝나면(상태 409 — StateConflict · 바뀐 것 없음 200)
#    분석을 값 없이 다시 읽어(_analysis_gone) 없으면 404, 있거나 다시 읽기가 저장소 오류면 원래 결과. 쓰는 동작은 기존
#    경로(insert 외래 키 위반 → 다시 읽기 → 404). 검토 행이 있던 시도는 다시 읽지 않는다.
#  - 경로 × 동작 표(FakeStore): 처음 읽기 전 삭제 · UPDATE 직전 삭제 · INSERT 직전 삭제 · 경쟁 패배 뒤(2·3번째) 다시 읽기 전
#    삭제 · 마지막(3번째) UPDATE 직전 삭제 · 검토 행 없음(분석 있음) · 삭제 뒤 다시 읽기 저장소 오류 · 검토 행 없음 + 다시 읽기
#    저장소 오류 — × 동작 14가지(12종 +
#    set_status 두 방향 · reclassify 바뀜/그대로). 결과와 저장소 호출(분석 읽기 수·검토 행 쓰기 순서·남은 행)을 함께 본다.
#  - 검토 행이 있던 시도의 409·200(처음 읽기·경쟁 패배 뒤 다시 읽기)은 분석을 다시 읽지 않는다(호출 횟수), 409 는 모두 StateConflict.
#  - 실제 SupabaseStore + 가짜 fluent 클라이언트(대본) + HTTP: 대표 경우의 응답·호출 순서와 로그·응답에 값(분석 id·처리자·글·
#    탐지 항목 id·검토사항 id·바깥 오류 원문) 없음. 'imask' 로거는 propagate=False 라 직접 붙인 핸들러(imask_log)로 잡는다.
# ==========================================================================

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from api_fakes import FakeStore
from fake_exports import ANALYSIS_ID, CREATED_AT, export_body, put_analysis
from fake_findings import stored_result
from fake_items import Spec, bundle_result, rule
from fastapi.testclient import TestClient
from shared_ctx import install
from test_review_quiet_reads import QUIET_READ, ScriptedClient, UpstreamError, imask_log

from api.index import app, get_store
from imask_backend import reviews
from imask_backend.analyses import ApiError
from imask_backend.fields import CATS
from imask_backend.reviews import FP_REASONS, apply_review_action, review_scope, row_view, storage_key, validate_action
from imask_backend.store import StoreError, SupabaseStore

CLOCK = datetime(2026, 11, 4, 1, 2, 3, tzinfo=UTC)

MSG_NOT_FOUND = "분석 건을 찾을 수 없습니다."
MSG_LOCKED = "검토를 완료한 분석은 바꿀 수 없습니다."
MSG_STATE = "탐지 항목 상태가 바뀌었습니다. 새로 고친 뒤 다시 시도해 주세요."
MSG_ALREADY_DONE = "이미 검토를 완료했습니다."
MSG_NOT_DONE = "검토를 완료한 분석만 다시 열 수 있습니다."
MSG_ITEM_STATE = "검토사항 상태가 바뀌었습니다. 새로 고친 뒤 다시 시도해 주세요."
GONE = (404, MSG_NOT_FOUND)

ACTOR_SENTINEL = "처리자센티널Q7"
TEXT_SENTINEL = "처리내용센티널N2"
FIELD_SENTINEL = "필드센티널F3"
RULE_SENTINEL = "규칙센티널R5"
OUTSIDE_SENTINEL = "OUTSIDE-ORIGINAL-ERROR-9f3k"
SENTINELS = (ANALYSIS_ID, ACTOR_SENTINEL, TEXT_SENTINEL, FIELD_SENTINEL, RULE_SENTINEL, OUTSIDE_SENTINEL)

WRITE = "changed"  # 검토 행이 없을 때(분석 있음) 쓰기로 가는 동작의 결과 — 200 changed true
SAME = "unchanged"  # 200 changed false


def _value_free(text: str) -> None:
    for value in SENTINELS:
        assert value not in text, "로그·오류 문구에 값이 섞였다"


# --- 준비: 완료 분석(stored_result — 탐지 29 · 검토사항 6)의 첫 탐지 항목·둘째 탐지 항목·첫 검토사항 -----------------------------


def _scope_of(result: dict[str, Any]) -> reviews.ReviewScope:
    row = {"status": "done", "result": result, "documents": []}
    scope = review_scope(row, row_view(row))
    assert scope is not None
    return scope


_SCOPE = _scope_of(stored_result())
F1, F2 = _SCOPE.targets[0], _SCOPE.targets[1]
ITEM = _SCOPE.items[0]
OTHER_CAT = next(c for c in CATS if c != F1.category)  # AI 값과 다른 정보 종류


@dataclass(frozen=True)
class Case:
    """동작 하나: 본문(처리자 뺌), 검토 행이 있으면 쓰기로 가는 저장 값(put_review), 검토 행이 없을 때(분석 있음)의 원래 결과."""

    body: dict[str, Any]
    row: dict[str, Any] = field(default_factory=dict)
    no_row: Any = WRITE  # WRITE · SAME · (409, 문구)


CASES: dict[str, Case] = {
    "set_status(confirmed)": Case({"type": "set_status", "finding_id": F1.id, "status": "confirmed", "reason": ""}),
    "set_status(open)": Case(
        {"type": "set_status", "finding_id": F1.id, "status": "open", "reason": ""},
        {"findings": {F1.key: {"status": "confirmed"}}},
        (409, MSG_STATE),
    ),
    "confirm_many": Case({"type": "confirm_many", "finding_ids": [F1.id, F2.id]}),
    "mark_false_positive": Case({"type": "mark_false_positive", "finding_id": F1.id, "reason_type": FP_REASONS[0], "note": ""}),
    "restore": Case(
        {"type": "restore", "finding_id": F1.id, "note": ""},
        {"findings": {F1.key: {"status": "false_positive", "fp_type": FP_REASONS[0]}}},
        (409, MSG_STATE),
    ),
    "reclassify(바뀜)": Case({"type": "reclassify", "finding_id": F1.id, "reason": "", "category": OTHER_CAT}),
    # 검토 행에는 다른 종류로 저장돼 있어 AI 값으로 되돌리는 요청(쓰기) — 검토 행이 없으면 AI 값 그대로라 바뀐 것 없음
    "reclassify(그대로)": Case(
        {"type": "reclassify", "finding_id": F1.id, "reason": "", "category": F1.category},
        {"findings": {F1.key: {"status": "reclassified", "category": OTHER_CAT}}},
        SAME,
    ),
    "save_finding_memo": Case({"type": "save_finding_memo", "finding_id": F1.id, "text": "m"}),
    "save_memo": Case({"type": "save_memo", "text": "m"}),
    "complete_review": Case({"type": "complete_review", "note": ""}),
    "reopen_review": Case({"type": "reopen_review", "reason": ""}, {"status": "done"}, (409, MSG_NOT_DONE)),
    "log_export": Case({k: v for k, v in export_body().items() if k != "actor"}),
    "resolve_item": Case({"type": "resolve_item", "item_id": ITEM.id, "note": ""}),
    "reopen_item": Case({"type": "reopen_item", "item_id": ITEM.id}, {"items": {ITEM.key: {"resolved": True}}}, (409, MSG_ITEM_STATE)),
}


def test_cases_cover_all_twelve_actions() -> None:
    assert {case.body["type"] for case in CASES.values()} == set(reviews.ACTION_FIELDS)


def _run(store: FakeStore, case: Case, actor: str = ACTOR_SENTINEL) -> Any:
    """동작 하나 → (상태, 문구) · 'changed' · 'unchanged' · 'store'(StoreError — 문구에 값 없음을 확인)."""
    action = validate_action({"actor": actor, **case.body})
    try:
        out = apply_review_action(store, ANALYSIS_ID, action, now=CLOCK)
    except ApiError as exc:
        _value_free(exc.detail)
        return (exc.status_code, exc.detail)
    except StoreError as exc:
        _value_free(exc.message + repr(exc) + str(exc))
        return "store"
    return WRITE if out.changed else SAME


# --- 경로(FakeStore) -----------------------------------------------------------------------------------------------------------


def _delete(store: FakeStore, analysis_id: str) -> None:
    assert store.delete_analysis(analysis_id) == 1  # 검토 행도 cascade 로 사라진다


def _other_writer(store: FakeStore, analysis_id: str) -> None:
    """다른 요청이 먼저 검토 행을 썼다(version 이 올라 내 조건부 UPDATE 가 0행) — 내 항목은 건드리지 않는다."""
    row = store.reviews[analysis_id]
    row["version"] += 1
    row["memo"] = "다른 요청"


def _delete_before_review_read(store: FakeStore, nth: int) -> None:
    """n 번째 검토 행 읽기 직전에 분석을 지운다(분석 읽기 뒤·검토 행 읽기 전 — 1 이면 처음 읽기 전)."""
    original = store.get_review
    seen = 0

    def wrapped(analysis_id: str) -> dict[str, Any] | None:
        nonlocal seen
        seen += 1
        if seen == nth:
            _delete(store, analysis_id)
        return original(analysis_id)

    store.get_review = wrapped  # type: ignore[method-assign]


PATHS = (
    "처음읽기전삭제",
    "UPDATE직전삭제",
    "INSERT직전삭제",
    "경쟁패배뒤삭제_2번째시도",
    "경쟁패배뒤삭제_3번째시도",
    "마지막UPDATE직전삭제",
    "검토행없음_분석있음",
    "삭제뒤다시읽기오류",
    "검토행없음_다시읽기오류",
)
GONE_PATHS = ("처음읽기전삭제", "UPDATE직전삭제", "경쟁패배뒤삭제_2번째시도", "경쟁패배뒤삭제_3번째시도", "마지막UPDATE직전삭제")
WITH_ROW = (*GONE_PATHS, "삭제뒤다시읽기오류")  # 동작 전에 (쓰기로 가는) 검토 행이 있는 경로


def _store_for(path: str, case: Case) -> FakeStore:
    store = FakeStore()
    put_analysis(store, result=stored_result())
    if path in WITH_ROW:
        store.put_review(ANALYSIS_ID, **case.row)
    if path in ("처음읽기전삭제", "삭제뒤다시읽기오류"):
        _delete_before_review_read(store, 1)
    elif path in ("UPDATE직전삭제", "INSERT직전삭제"):
        store.review_hooks = [_delete]
    elif path == "경쟁패배뒤삭제_2번째시도":
        store.review_hooks = [_other_writer]
        _delete_before_review_read(store, 2)
    elif path == "경쟁패배뒤삭제_3번째시도":
        store.review_hooks = [_other_writer, _other_writer]
        _delete_before_review_read(store, 3)
    elif path == "마지막UPDATE직전삭제":  # 두 번 진 뒤 세 번째(마지막) UPDATE 직전에 삭제 → 루프 끝의 다시 읽기(②)
        store.review_hooks = [_other_writer, _other_writer, _delete]
    if path in ("삭제뒤다시읽기오류", "검토행없음_다시읽기오류"):
        store.fail_get_calls = {2}  # 동작의 두 번째 분석 읽기(값 없는 다시 읽기)만 저장소 오류
    return store


def _expected(path: str, case: Case) -> Any:
    writes = case.no_row == WRITE
    if path in GONE_PATHS:
        return GONE
    if path == "INSERT직전삭제":
        return GONE if writes else case.no_row  # 쓰지 않는 동작은 INSERT 에 닿지 않는다(검토 행 없음 → 분석 있음 → 원래 결과)
    if path == "삭제뒤다시읽기오류":
        return "store" if writes else case.no_row  # 지워졌는지 확실하지 않음 → 원래 결과(쓰기 동작은 원래 저장소 오류 502)
    return case.no_row  # 검토 행 없음(분석 있음) — 다시 읽기 오류여도 원래 결과


def _expected_writes(path: str, case: Case) -> list[str]:
    insert = ["insert_review"] if case.no_row == WRITE else []
    if path in ("UPDATE직전삭제", "경쟁패배뒤삭제_2번째시도"):
        return ["update_review", *insert]
    if path == "경쟁패배뒤삭제_3번째시도":
        return ["update_review", "update_review", *insert]
    if path == "마지막UPDATE직전삭제":
        return ["update_review"] * 3
    return insert


def _expected_reads(path: str, case: Case) -> int:
    """분석 읽기 수 — 처음 1 + 값 없는 다시 읽기 1(쓰기 오류 뒤 또는 검토 행이 None 인 시도의 409·200). 그 밖은 처음 1 뿐."""
    if path in ("검토행없음_분석있음", "검토행없음_다시읽기오류") and case.no_row == WRITE:
        return 1
    return 2


@pytest.mark.parametrize("name", list(CASES))
@pytest.mark.parametrize("path", PATHS)
def test_path_by_action(path: str, name: str) -> None:
    case = CASES[name]
    store = _store_for(path, case)
    with imask_log() as log:
        outcome = _run(store, case)
    assert outcome == _expected(path, case)
    assert [w[0] for w in store.review_writes] == _expected_writes(path, case)
    assert store.analysis_reads == [True] * _expected_reads(path, case)  # 모두 값 없는 읽기(quiet)
    assert store.updates == []  # analyses 행은 쓰지 않는다
    if path in GONE_PATHS or path == "삭제뒤다시읽기오류" or (path == "INSERT직전삭제" and case.no_row == WRITE):
        assert ANALYSIS_ID not in store.analyses and store.reviews == {}  # 지워졌고 검토 행도 새로 생기지 않았다
    if path == "INSERT직전삭제" and case.no_row != WRITE:
        assert len(store.review_hooks) == 1 and ANALYSIS_ID in store.analyses  # INSERT 에 닿지 않아 삭제 훅이 남았다
    _value_free("\n".join(log.lines))


def test_the_four_kinds_that_used_to_answer_409_or_200_are_404_on_both_first_read_and_reread() -> None:
    # BRIEF-F §5F F1 이 이름을 든 네 가지(예전: 409 · 409 · 409 · 200 changed false) — 위 표의 요약
    for name in ("reopen_review", "set_status(open)", "restore", "reclassify(그대로)"):
        for path in ("처음읽기전삭제", "UPDATE직전삭제"):
            assert _run(_store_for(path, CASES[name]), CASES[name]) == GONE, (name, path)


# --- 검토 행이 있던 시도의 409·200 은 다시 읽지 않는다 -------------------------------------------------------------------------------

ROW_CONFLICTS: dict[str, tuple[dict[str, Any], dict[str, Any], Any]] = {
    # 이름 → (본문, 검토 행 저장 값, 결과)
    "set_status(open)_미확인": ({**CASES["set_status(open)"].body}, {"memo": "m"}, (409, MSG_STATE)),
    "set_status(confirmed)_확인함": (
        {**CASES["set_status(confirmed)"].body},
        {"findings": {F1.key: {"status": "confirmed"}}},
        (409, MSG_STATE),
    ),
    "mark_false_positive_이미오탐": (
        {**CASES["mark_false_positive"].body},
        {"findings": {F1.key: {"status": "false_positive"}}},
        (409, MSG_STATE),
    ),
    "restore_오탐아님": ({**CASES["restore"].body}, {"memo": "m"}, (409, MSG_STATE)),
    "reclassify_그대로": ({**CASES["reclassify(그대로)"].body}, {"memo": "m"}, SAME),
    "confirm_many_모두확인함": (
        {**CASES["confirm_many"].body},
        {"findings": {F1.key: {"status": "confirmed"}, F2.key: {"status": "confirmed"}}},
        SAME,
    ),
    "complete_review_이미완료": ({**CASES["complete_review"].body}, {"status": "done"}, (409, MSG_ALREADY_DONE)),
    "reopen_review_완료전": ({**CASES["reopen_review"].body}, {"memo": "m"}, (409, MSG_NOT_DONE)),
    "resolve_item_이미해결": ({**CASES["resolve_item"].body}, {"items": {ITEM.key: {"resolved": True}}}, (409, MSG_ITEM_STATE)),
    "reopen_item_미해결": ({**CASES["reopen_item"].body}, {"memo": "m"}, (409, MSG_ITEM_STATE)),
    "잠김_set_status": ({**CASES["set_status(confirmed)"].body}, {"status": "done"}, (409, MSG_LOCKED)),
    "잠김_resolve_item": ({**CASES["resolve_item"].body}, {"status": "done"}, (409, MSG_LOCKED)),
}


@pytest.mark.parametrize("name", list(ROW_CONFLICTS))
def test_a_conflict_or_no_change_with_a_review_row_does_not_reread(name: str) -> None:
    body, row, expected = ROW_CONFLICTS[name]
    store = FakeStore()
    put_analysis(store, result=stored_result())
    store.put_review(ANALYSIS_ID, **row)
    action = validate_action({"actor": ACTOR_SENTINEL, **body})
    if expected == SAME:
        assert apply_review_action(store, ANALYSIS_ID, action, now=CLOCK).changed is False
    else:
        with pytest.raises(reviews.StateConflict) as info:  # _compute 의 409 는 모두 한 예외 종류
            apply_review_action(store, ANALYSIS_ID, action, now=CLOCK)
        assert (info.value.status_code, info.value.detail) == expected
    assert store.analysis_reads == [True]  # 처음 읽기 하나뿐
    assert store.review_writes == []


@pytest.mark.parametrize("name", ["set_status(open)", "restore", "reopen_review", "reopen_item", "reclassify(그대로)"])
def test_a_conflict_after_a_lost_race_with_a_row_does_not_reread(name: str) -> None:
    # 경쟁 패배 뒤 다시 읽은 검토 행이 있으면(다른 요청이 먼저 같은 결과를 만듦) 다시 읽지 않고 원래 결과
    case = CASES[name]
    store = FakeStore()
    put_analysis(store, result=stored_result())
    store.put_review(ANALYSIS_ID, **case.row)

    def undo(store: FakeStore, analysis_id: str) -> None:  # 다른 요청이 내 동작과 같은 결과를 먼저 썼다
        row = store.reviews[analysis_id]
        row.update({"version": row["version"] + 1, "status": "needed", "findings": {}, "items": {}})

    store.review_hooks = [undo]
    assert _run(store, case) == case.no_row
    assert store.analysis_reads == [True]
    assert [w[0] for w in store.review_writes] == ["update_review"]


def test_the_old_item_only_class_is_merged() -> None:
    assert issubclass(reviews.StateConflict, ApiError)
    assert not hasattr(reviews, "ItemStateConflict")  # T1-fix1 의 검토사항 전용 예외를 한 장치로 합쳤다


# --- 실제 SupabaseStore + 가짜 fluent 클라이언트(대본) + HTTP ------------------------------------------------------------------------

A, R, RU, RI = ("analyses", "select"), ("analysis_reviews", "select"), ("analysis_reviews", "update"), ("analysis_reviews", "upsert")


class ForeignKeyError(Exception):
    """PostgREST APIError 꼴의 외래 키 위반(23503) — message·details·hint·str 에 값이 섞여 있다."""

    def __init__(self) -> None:
        text = f"insert on analysis_reviews violates foreign key (analysis_id)=({ANALYSIS_ID}) actor={ACTOR_SENTINEL} {OUTSIDE_SENTINEL}"
        super().__init__(text)
        self.message = text
        self.code = "23503"
        self.details = text
        self.hint = OUTSIDE_SENTINEL


def _sentinel_result() -> dict[str, Any]:
    # 탐지 항목 id 에 FIELD_SENTINEL, 검토사항 id 에 RULE_SENTINEL 이 들어간다
    fields = {"applicant_name": ("값", None, "high"), FIELD_SENTINEL: ("값2", 1, "high")}
    return bundle_result([Spec("loan_application", (1, 1), fields, validate=("red", [rule(name=RULE_SENTINEL)]))])


_HTTP_SCOPE = _scope_of(_sentinel_result())
HF = next(t for t in _HTTP_SCOPE.targets if FIELD_SENTINEL in t.id)
HTTP_OTHER_CAT = next(c for c in CATS if c != HF.category)
assert any(RULE_SENTINEL in item.id for item in _HTTP_SCOPE.items)


def _analysis_row() -> dict[str, Any]:
    return {
        "id": ANALYSIS_ID,
        "name": "합성 묶음",
        "status": "done",
        "agent_id": None,
        "upstage_job_id": "job_done",
        "result": _sentinel_result(),
        "error": None,
        "created_at": CREATED_AT,
        "updated_at": "2026-11-04T15:05:00+00:00",
        "started_at": CREATED_AT,
        "documents": [],
    }


def _review_row(**values: Any) -> dict[str, Any]:
    return {
        "analysis_id": ANALYSIS_ID,
        "status": "needed",
        "memo": "",
        "memo_at": None,
        "reviewer": "",
        "reviewed_at": None,
        "completion_note": "",
        "findings": {},
        "items": {},
        "history": [],
        "version": 1,
        "created_at": "2026-11-04T15:06:00+00:00",
        "updated_at": "2026-11-04T15:06:00+00:00",
        **values,
    }


CONFIRMED = {"findings": {storage_key(HF.id): {"status": "confirmed"}}}
RECLASSIFIED = {"findings": {storage_key(HF.id): {"status": "reclassified", "category": HTTP_OTHER_CAT}}}

BODIES: dict[str, dict[str, Any]] = {
    "reopen_review": {"type": "reopen_review", "reason": TEXT_SENTINEL},
    "set_status(open)": {"type": "set_status", "finding_id": HF.id, "status": "open", "reason": TEXT_SENTINEL},
    "restore": {"type": "restore", "finding_id": HF.id, "note": TEXT_SENTINEL},
    "reclassify(그대로)": {"type": "reclassify", "finding_id": HF.id, "reason": TEXT_SENTINEL, "category": HF.category},
    "save_memo": {"type": "save_memo", "text": TEXT_SENTINEL},
}

# 이름 → (동작, 대본, (상태, 응답 — 문구 또는 changed), 저장소 호출 순서, 값 없는 다시 읽기 오류 문구가 로그에 있어야 함)
HTTP_RACES: dict[str, tuple[str, Callable[[], dict[Any, list[Any]]], tuple[int, Any], list[tuple[str, str]], bool]] = {
    "reopen_review_처음읽기전삭제": (
        "reopen_review",
        lambda: {A: [[_analysis_row()], []], R: [[]]},
        GONE,
        [A, R, A],
        False,
    ),
    "reopen_review_UPDATE직전삭제": (
        "reopen_review",
        lambda: {A: [[_analysis_row()], []], R: [[_review_row(status="done")], []], RU: [[]]},
        GONE,
        [A, R, RU, R, A],
        False,
    ),
    "set_status(open)_UPDATE직전삭제": (
        "set_status(open)",
        lambda: {A: [[_analysis_row()], []], R: [[_review_row(**CONFIRMED)], []], RU: [[]]},
        GONE,
        [A, R, RU, R, A],
        False,
    ),
    "restore_처음읽기전삭제": ("restore", lambda: {A: [[_analysis_row()], []], R: [[]]}, GONE, [A, R, A], False),
    "reclassify(그대로)_UPDATE직전삭제": (
        "reclassify(그대로)",
        lambda: {A: [[_analysis_row()], []], R: [[_review_row(**RECLASSIFIED)], []], RU: [[]]},
        GONE,
        [A, R, RU, R, A],
        False,
    ),
    "save_memo_UPDATE직전삭제_FK": (
        "save_memo",
        lambda: {A: [[_analysis_row()], []], R: [[_review_row()], []], RU: [[]], RI: [ForeignKeyError()]},
        GONE,
        [A, R, RU, R, RI, A],
        False,
    ),
    "reopen_review_검토행없음_분석있음": (
        "reopen_review",
        lambda: {A: [[_analysis_row()], [_analysis_row()]], R: [[]]},
        (409, MSG_NOT_DONE),
        [A, R, A],
        False,
    ),
    "reclassify(그대로)_검토행없음_분석있음": (
        "reclassify(그대로)",
        lambda: {A: [[_analysis_row()], [_analysis_row()]], R: [[]]},
        (200, False),
        [A, R, A],
        False,
    ),
    "reopen_review_검토행있음_다시읽지않음": (
        "reopen_review",
        lambda: {A: [[_analysis_row()]], R: [[_review_row()]]},
        (409, MSG_NOT_DONE),
        [A, R],
        False,
    ),
    "reopen_review_삭제뒤다시읽기오류": (
        "reopen_review",
        lambda: {A: [[_analysis_row()], UpstreamError()], R: [[]]},
        (409, MSG_NOT_DONE),
        [A, R, A],
        True,
    ),
    "reclassify(그대로)_삭제뒤다시읽기오류": (
        "reclassify(그대로)",
        lambda: {A: [[_analysis_row()], UpstreamError()], R: [[_review_row(**RECLASSIFIED)], []], RU: [[]]},
        (200, False),
        [A, R, RU, R, A],
        True,
    ),
}


@pytest.mark.parametrize("name", list(HTTP_RACES))
def test_delete_races_with_supabase_store_over_http(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    kind, script, (status, expected), ran, reread_error = HTTP_RACES[name]
    client = ScriptedClient(script())
    database = SupabaseStore(client)
    context = install(monkeypatch)
    app.dependency_overrides[get_store] = lambda: database
    try:
        with TestClient(app) as http, imask_log() as log:
            response = http.post(f"/api/py/analyses/{ANALYSIS_ID}/review-actions", json={"actor": ACTOR_SENTINEL, **BODIES[kind]})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == status
    if status == 200:
        assert response.json()["changed"] is expected
    else:
        assert response.json() == {"detail": expected}
        _value_free(response.text)
    assert client.ran == ran  # 다시 읽기는 검토 행이 None 인 시도에서만
    assert all(not values for values in client.script.values()), "대본을 끝까지 썼다"
    text = "\n".join(log.lines)
    if reread_error:
        assert QUIET_READ in text  # 값 없는 다시 읽기 오류 문구는 잡혔다
    if RI in ran:
        assert "검토 행 만들기: ForeignKeyError (23503)" in text
    _value_free(text)
    context.no_upstage()
