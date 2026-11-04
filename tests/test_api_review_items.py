# ==========================================================================
#  검토사항 해결·다시 열기(resolve_item·reopen_item)와 review.items (review-items BRIEF §5.4~5.6, 네트워크 없음)
#  - 업무 로직(apply_review_action + FakeStore): 쓰기 값·이력 줄(H{version}·kind·target·change·reason)·version 조건부 쓰기,
#    다시 열기 뒤 note·resolved_at·resolved_by 남음, 오류 순서(404 분석 → 409 검토할 수 없음 → 404 검토사항 → 409 잠김 →
#    409 검토사항 상태 → 409 이력 1000줄 → 409 경쟁 3번 / 지워졌으면 404), 저장소 오류, 저장 값 보존, 시각, 저장 키 충돌,
#    검토 완료 문구(남은 항목 둘·하나·없음), S2 문구, analyses 행을 쓰지 않음
#  - 조회 review.items: 지금 결과의 저장할 수 있는 검토사항 중 저장 값이 객체인 것만, 정규화, 사라진 id 무시, 키 순서
#  - 요청 본문: 정확한 필드·엄격한 타입·글 규칙·처리자 규칙·기존 경계(같은 키 두 번·NaN·깊은 중첩·413)
#  - API(TestClient + FakeStore): GET result.items·review.items, POST 200·400·404·409·502 문구와 순서, 응답 모양,
#    완료 → 잠김 409(두 동작) → 다시 열기 → 다시 해결, Upstage 를 부르지 않음
#  - 로그·StoreError 에 처리 내용·처리자·분석 id·항목 id·규칙 이름이 없음(imask 로거에 직접 붙인 핸들러 — 기존 방식)
# ==========================================================================

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from api_fakes import FakeStore
from fake_findings import stored_result
from fake_items import Spec, bundle_result, rule
from fake_reviews import ACTOR, SMALL, custom_result
from fastapi.testclient import TestClient
from shared_ctx import ANALYSIS_KEYS, Ctx, ctx, install  # noqa: F401
from test_review_quiet_reads import QUIET_READ, ScriptedClient, UpstreamError, imask_log

from api.index import app, get_store
from imask_backend import reviews
from imask_backend.analyses import ApiError
from imask_backend.reviews import (
    ACTION_FIELDS,
    LOCKED_ACTIONS,
    ActionOutcome,
    apply_review_action,
    parse_action,
    read_review,
    review_scope,
    row_view,
    storage_key,
    validate_action,
)
from imask_backend.store import StoreError, SupabaseStore

CLOCK = datetime(2026, 11, 4, 1, 2, 3, tzinfo=UTC)

MSG_FORMAT = "요청 형식이 올바르지 않습니다."
MSG_BAD_ACTOR = "처리자 이름이 올바르지 않습니다."
MSG_TOO_LONG = "메모·사유는 500자 이하로 적어 주세요."
MSG_BAD_CHAR = "메모·사유에 쓸 수 없는 문자가 있습니다."
MSG_TOO_LARGE = "요청 본문이 너무 큽니다."
MSG_NOT_FOUND = "분석 건을 찾을 수 없습니다."
MSG_NOT_REVIEWABLE = "검토할 수 없는 분석입니다."
MSG_NO_ITEM = "검토사항을 찾을 수 없습니다."
MSG_LOCKED = "검토를 완료한 분석은 바꿀 수 없습니다."
MSG_ITEM_STATE = "검토사항 상태가 바뀌었습니다. 새로 고친 뒤 다시 시도해 주세요."
MSG_HISTORY_FULL = "검토 이력이 너무 많아 더 저장할 수 없습니다."
MSG_CONFLICT = "다른 요청과 겹쳐 저장하지 못했습니다. 잠시 후 다시 시도해 주세요."
MSG_STORE = "데이터 저장소에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요."

REVIEW_KEYS = ["status", "memo", "memo_at", "reviewer", "reviewed_at", "completion_note", "findings", "items", "history", "version"]
ITEM_STATE_KEYS = ["resolved", "note", "resolved_at", "resolved_by"]
# stored_result()(예전 응답 모양)의 검토사항 — tests/test_items.py 가 내용을 본다
ITEM_IDS = ["lowconf:0", "nolocation:2:income_info", "lowconf:2", "lowconf:3", "lowconf:4", "other:5"]
LABELS = {"R-01": "인식 확인 필요", "R-02": "위치 확인 필요", "R-06": "기타 서류"}
UNRESOLVED = {"resolved": False, "note": "", "resolved_at": None, "resolved_by": ""}


def tick(minutes: int) -> datetime:
    return CLOCK + timedelta(minutes=minutes)


def iso(minutes: int) -> str:
    return tick(minutes).isoformat()


class Env:
    """분석 하나 + 동작 도우미. 화면 번호(R-01·D1-01)를 계약 id 로 바꿔 보낸다."""

    def __init__(self, store: FakeStore, analysis_id: str) -> None:
        self.store = store
        self.id = analysis_id
        row = store.get_analysis(analysis_id)
        assert row is not None
        scope = review_scope(row, row_view(row))
        assert scope is not None
        self.scope = scope
        self.items = {t.num: t.id for t in scope.items}
        self.findings = {t.num: t.id for t in scope.targets}

    def act(self, kind: str, *, at: int = 0, actor: str = ACTOR, **fields: Any) -> ActionOutcome:
        if "item_id" in fields:
            fields["item_id"] = self.items.get(fields["item_id"], fields["item_id"])
        if "finding_ids" in fields:
            fields["finding_ids"] = [self.findings.get(v, v) for v in fields["finding_ids"]]
        action = validate_action({"type": kind, "actor": actor, **fields})
        return apply_review_action(self.store, self.id, action, now=tick(at))

    def error(self, kind: str, **fields: Any) -> ApiError:
        with pytest.raises(ApiError) as info:
            self.act(kind, **fields)
        return info.value

    def row(self) -> dict[str, Any]:
        return self.store.reviews[self.id]

    def history(self) -> list[dict[str, Any]]:
        return self.row()["history"]

    def saved(self, num: str) -> dict[str, Any]:
        return self.row()["items"][storage_key(self.items[num])]

    def read(self) -> dict[str, Any] | None:
        row = self.store.get_analysis(self.id)
        assert row is not None
        return read_review(self.store, row, row_view(row))


def make_env(result: dict[str, Any] | None = None, store: FakeStore | None = None, status: str = "done") -> Env:
    store = store or FakeStore()
    analysis_id = store.put(status=status, job_id="job_done", result=result or stored_result())
    return Env(store, analysis_id)


@pytest.fixture
def env() -> Env:
    return make_env()


def line(version: int, minutes: int, kind: str, target: str, change: str, reason: str = "", actor: str = ACTOR) -> dict[str, str]:
    return {"id": f"H{version}", "at": iso(minutes), "actor": actor, "kind": kind, "target": target, "change": change, "reason": reason}


# --- 동작 표 ----------------------------------------------------------------------------------------------


def test_two_new_actions_are_in_the_table_and_locked() -> None:
    assert ACTION_FIELDS["resolve_item"] == ("item_id", "note")
    assert ACTION_FIELDS["reopen_item"] == ("item_id",)
    assert len(ACTION_FIELDS) == 12
    assert {"resolve_item", "reopen_item"} <= LOCKED_ACTIONS and "log_export" not in LOCKED_ACTIONS


def test_scope_lists_the_items_in_order(env: Env) -> None:
    assert list(env.items) == ["R-01", "R-02", "R-03", "R-04", "R-05", "R-06"]
    assert list(env.items.values()) == ITEM_IDS
    assert all(t.writable and t.key == storage_key(t.id) for t in env.scope.items)


# --- 해결·다시 열기 -----------------------------------------------------------------------------------------


def test_resolve_writes_the_item_one_history_line_and_version_one(env: Env) -> None:
    out = env.act("resolve_item", at=1, item_id="R-01", note="원본과 비교함")
    assert out.changed is True
    value = {"resolved": True, "note": "원본과 비교함", "resolved_at": iso(1), "resolved_by": ACTOR}
    assert env.row()["items"] == {storage_key("lowconf:0"): value}
    assert env.history() == [line(1, 1, "resolve", "R-01 인식 확인 필요", "미해결 → 해결", "원본과 비교함")]
    assert env.row()["version"] == 1
    (method, _, values, expect) = env.store.review_writes[0]
    assert method == "insert_review" and expect is None
    assert set(values) == {"analysis_id", "status", "memo", "memo_at", "reviewer", "reviewed_at", "completion_note", "findings", "items", "history", "version"}
    assert out.review["items"] == {"lowconf:0": value}
    assert list(out.review) == REVIEW_KEYS and list(out.review["items"]["lowconf:0"]) == ITEM_STATE_KEYS
    assert [h["id"] for h in out.review["history"]] == ["S1", "S2", "H1"]


def test_reopen_keeps_note_time_and_actor_and_writes_only_items(env: Env) -> None:
    env.act("resolve_item", at=1, item_id="R-02", note="직접 찾음")
    out = env.act("reopen_item", at=2, actor="다른 사람", item_id="R-02")
    assert env.saved("R-02") == {"resolved": False, "note": "직접 찾음", "resolved_at": iso(1), "resolved_by": ACTOR}
    assert env.history()[-1] == line(2, 2, "reopenItem", "R-02 위치 확인 필요", "해결 → 미해결", "", actor="다른 사람")
    (method, _, values, expect) = env.store.review_writes[-1]
    assert method == "update_review" and expect == 1 and set(values) == {"items", "history", "version"}
    assert out.review["items"]["nolocation:2:income_info"]["resolved"] is False and out.changed is True


def test_resolve_again_after_reopen(env: Env) -> None:
    env.act("resolve_item", at=1, item_id="R-06", note="a")
    env.act("reopen_item", at=2, item_id="R-06")
    env.act("resolve_item", at=3, actor="다른 사람", item_id="R-06", note="")
    assert env.saved("R-06") == {"resolved": True, "note": "", "resolved_at": iso(3), "resolved_by": "다른 사람"}
    assert [(h["id"], h["kind"], h["target"]) for h in env.history()] == [
        ("H1", "resolve", "R-06 기타 서류"),
        ("H2", "reopenItem", "R-06 기타 서류"),
        ("H3", "resolve", "R-06 기타 서류"),
    ]


def test_resolve_twice_and_reopen_an_open_item_are_state_conflicts(env: Env) -> None:
    err = env.error("reopen_item", item_id="R-01")
    assert (err.status_code, err.detail) == (409, MSG_ITEM_STATE)
    env.act("resolve_item", at=1, item_id="R-01", note="a")
    err = env.error("resolve_item", item_id="R-01", note="b")
    assert (err.status_code, err.detail) == (409, MSG_ITEM_STATE)
    assert len(env.history()) == 1 and env.saved("R-01")["note"] == "a"


@pytest.mark.parametrize("item_id", ["없는 id", "", "lowconf:9", "R-01", "LOWCONF:0", "lowconf:0 ", "0:applicant_name"])
def test_unknown_item_ids_are_404(env: Env, item_id: str) -> None:
    env.items.pop("R-01")  # 화면 번호를 바꿔 주지 않게 — 그대로 보낸다
    for kind, extra in (("resolve_item", {"note": ""}), ("reopen_item", {})):
        err = env.error(kind, item_id=item_id, **extra)
        assert (err.status_code, err.detail) == (404, MSG_NO_ITEM)
    assert env.store.review_writes == []


def test_both_actions_are_locked_after_complete_then_open_again(env: Env) -> None:
    env.act("resolve_item", at=1, item_id="R-01", note="")
    env.act("complete_review", at=2, note="")
    for kind, extra in (("resolve_item", {"item_id": "R-02", "note": ""}), ("reopen_item", {"item_id": "R-01"})):
        err = env.error(kind, **extra)
        assert (err.status_code, err.detail) == (409, MSG_LOCKED)
    env.act("reopen_review", at=3, reason="다시")
    env.act("reopen_item", at=4, item_id="R-01")
    env.act("resolve_item", at=5, item_id="R-02", note="")
    assert [h["kind"] for h in env.history()] == ["resolve", "complete", "reopen", "reopenItem", "resolve"]


# --- 오류 순서 -----------------------------------------------------------------------------------------------


def test_analysis_404_and_not_reviewable_409_come_first() -> None:
    store = FakeStore()
    action = validate_action({"type": "resolve_item", "actor": ACTOR, "item_id": "없음", "note": ""})
    with pytest.raises(ApiError) as info:
        apply_review_action(store, "7b944f1e-1234-4abc-8def-0123456789ab", action)
    assert (info.value.status_code, info.value.detail) == (404, MSG_NOT_FOUND)
    with pytest.raises(ApiError) as info:
        apply_review_action(store, "uuid 아님", action)
    assert info.value.status_code == 404
    for status in ("running", "failed", "queued"):
        running = store.put(status=status, job_id="j", result=stored_result())
        with pytest.raises(ApiError) as info:
            apply_review_action(store, running, action)
        assert (info.value.status_code, info.value.detail) == (409, MSG_NOT_REVIEWABLE)


def test_item_404_comes_before_locked(env: Env) -> None:
    env.act("complete_review", at=1, note="")
    assert env.error("resolve_item", item_id="없음", note="").detail == MSG_NO_ITEM
    assert env.error("reopen_item", item_id="없음").detail == MSG_NO_ITEM


def test_locked_comes_before_item_state(env: Env) -> None:
    env.act("complete_review", at=1, note="")
    assert env.error("reopen_item", item_id="R-01").detail == MSG_LOCKED  # 미해결에 reopen 이지만 잠김이 먼저


def test_item_state_comes_before_history_limit(env: Env) -> None:
    full = [line(i, 0, "memo", "분석 건", "x") for i in range(1, 1001)]
    env.store.put_review(env.id, history=full, version=1000, items={storage_key("lowconf:0"): {"resolved": True}})
    assert env.error("resolve_item", item_id="R-01", note="").detail == MSG_ITEM_STATE
    assert env.error("reopen_item", item_id="R-02").detail == MSG_ITEM_STATE
    err = env.error("reopen_item", item_id="R-01")
    assert (err.status_code, err.detail) == (409, MSG_HISTORY_FULL)
    err = env.error("resolve_item", item_id="R-02", note="")
    assert (err.status_code, err.detail) == (409, MSG_HISTORY_FULL)
    assert env.row()["version"] == 1000 and env.store.review_writes == []


# --- 경쟁 -------------------------------------------------------------------------------------------------------


def _other(kind: str, minutes: int, **fields: Any):  # noqa: ANN202 — 훅
    """다른 요청 하나(검토 행을 쓰기 직전에 끼어든다)."""

    def hook(store: FakeStore, analysis_id: str) -> None:
        Env(store, analysis_id).act(kind, at=minutes, actor="다른 사람", **fields)

    return hook


def test_race_rereads_and_applies_on_top(env: Env) -> None:
    env.store.review_hooks.append(_other("resolve_item", 1, item_id="R-02", note="다른 처리"))
    out = env.act("resolve_item", at=2, item_id="R-01", note="내 처리")
    assert out.changed and out.review["version"] == 2
    assert [(h["id"], h["actor"], h["target"]) for h in env.history()] == [
        ("H1", "다른 사람", "R-02 위치 확인 필요"),
        ("H2", ACTOR, "R-01 인식 확인 필요"),
    ]
    assert [w[0] for w in env.store.review_writes] == ["insert_review", "insert_review", "update_review"]
    assert env.saved("R-02")["note"] == "다른 처리" and env.saved("R-01")["note"] == "내 처리"


def test_race_on_the_same_item_turns_into_a_state_conflict(env: Env) -> None:
    env.store.review_hooks.append(_other("resolve_item", 1, item_id="R-01", note="먼저"))
    err = env.error("resolve_item", at=2, item_id="R-01", note="나중")
    assert (err.status_code, err.detail) == (409, MSG_ITEM_STATE)
    assert env.saved("R-01")["note"] == "먼저" and len(env.history()) == 1


def test_race_lost_three_times_is_409_and_nothing_of_mine_is_saved(env: Env) -> None:
    for minutes in (1, 2, 3):
        env.store.review_hooks.append(_other("save_memo", minutes, text=f"다른 {minutes}"))
    err = env.error("resolve_item", at=4, item_id="R-01", note="내 처리")
    assert (err.status_code, err.detail) == (409, MSG_CONFLICT)
    assert env.row()["items"] == {} and env.row()["version"] == 3
    mine = [w for w in env.store.review_writes if w[2]["history"][-1]["actor"] == ACTOR]
    assert [w[0] for w in mine] == ["insert_review", "update_review", "update_review"]


def test_analysis_deleted_during_the_race_is_404(env: Env) -> None:
    env.store.review_hooks = [lambda store, aid: store.delete_analysis(aid)]
    err = env.error("resolve_item", at=1, item_id="R-01", note="")
    assert (err.status_code, err.detail) == (404, MSG_NOT_FOUND)


# --- 삭제 경합(T1-fix1 — V-T1-1 M1): 검토 행이 없던 시도의 상태 409 는 분석을 다시 읽어 없으면 404 ---------------------------


def test_reopen_deleted_just_before_the_update_is_404(env: Env) -> None:
    env.act("resolve_item", at=1, item_id="R-01", note="")
    env.store.review_hooks = [lambda store, aid: store.delete_analysis(aid)]  # UPDATE 직전에 분석 삭제(검토 행 cascade)
    env.store.analysis_reads.clear()
    err = env.error("reopen_item", at=2, item_id="R-01")
    assert (err.status_code, err.detail) == (404, MSG_NOT_FOUND)
    assert [w[0] for w in env.store.review_writes][-1] == "update_review"  # 조건부 UPDATE 가 0행 → 다시 읽은 검토 행 None
    assert env.store.analysis_reads == [True, True]  # 처음 읽기 + 값 없는 다시 읽기(quiet)


def test_reopen_deleted_before_the_first_review_read_is_404(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    env.act("resolve_item", at=1, item_id="R-01", note="")
    original = env.store.get_review

    def disappeared(analysis_id: str) -> Any:
        env.store.delete_analysis(analysis_id)  # 분석 첫 조회 직후·첫 검토 행 조회 전에 삭제
        return original(analysis_id)

    monkeypatch.setattr(env.store, "get_review", disappeared)
    writes = len(env.store.review_writes)
    err = env.error("reopen_item", at=2, item_id="R-01")
    assert (err.status_code, err.detail) == (404, MSG_NOT_FOUND)
    assert len(env.store.review_writes) == writes  # 쓰기 시도 없음


def test_reopen_of_an_open_item_without_a_review_row_is_still_409(env: Env) -> None:
    # 분석은 있고 검토 행은 없음 → 미해결 항목의 reopen 은 다시 읽어 본 뒤에도 409 그대로
    env.store.analysis_reads.clear()
    err = env.error("reopen_item", item_id="R-01")
    assert (err.status_code, err.detail) == (409, MSG_ITEM_STATE)
    assert env.store.analysis_reads == [True, True] and env.store.review_writes == []


def test_state_conflict_with_a_review_row_is_409_without_a_reread(env: Env) -> None:
    env.act("save_memo", at=1, text="m")  # 검토 행 있음, 항목은 미해결
    env.act("resolve_item", at=2, item_id="R-02", note="")
    env.store.analysis_reads.clear()
    assert env.error("reopen_item", item_id="R-01").detail == MSG_ITEM_STATE
    assert env.error("resolve_item", item_id="R-02", note="").detail == MSG_ITEM_STATE
    assert env.store.analysis_reads == [True, True]  # 동작마다 처음 읽기 하나뿐(다시 읽기 없음)


def test_reopen_reread_store_error_keeps_the_409(env: Env) -> None:
    # 검토 행이 없는 미해결 reopen — 다시 읽기가 저장소 오류면 원래 오류(409) 그대로
    env.store.fail_get_calls = {env.store.get_count + 2}
    assert env.error("reopen_item", item_id="R-01").detail == MSG_ITEM_STATE
    # 삭제 경합 + 다시 읽기 저장소 오류도 409(지워졌는지 확실하지 않으므로)
    env.act("resolve_item", at=1, item_id="R-01", note="")
    env.store.review_hooks = [lambda store, aid: store.delete_analysis(aid)]
    env.store.fail_get_calls = {env.store.get_count + 2}
    err = env.error("reopen_item", at=2, item_id="R-01")
    assert (err.status_code, err.detail) == (409, MSG_ITEM_STATE)


def test_resolve_deleted_just_before_the_update_is_404(env: Env) -> None:
    # 검토 행이 있는 resolve: UPDATE 직전 삭제 → 0행 → 다시 읽은 행 None → 미해결이라 계산 통과 → insert FK 위반 → 404
    env.act("resolve_item", at=1, item_id="R-01", note="")
    env.store.review_hooks = [lambda store, aid: store.delete_analysis(aid)]
    err = env.error("resolve_item", at=2, item_id="R-02", note="")
    assert (err.status_code, err.detail) == (404, MSG_NOT_FOUND)
    assert [w[0] for w in env.store.review_writes][-2:] == ["update_review", "insert_review"]


def test_resolve_of_a_resolved_item_deleted_before_the_first_read_is_404(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    # 첫 검토 행 조회 전에 삭제: 행 None → 미해결이라 resolve 계산은 통과 → insert FK 위반 → 404(이미 있던 경로)
    env.act("resolve_item", at=1, item_id="R-01", note="")
    original = env.store.get_review

    def disappeared(analysis_id: str) -> Any:
        env.store.delete_analysis(analysis_id)
        return original(analysis_id)

    monkeypatch.setattr(env.store, "get_review", disappeared)
    assert env.error("resolve_item", at=2, item_id="R-01", note="").detail == MSG_NOT_FOUND


@pytest.mark.parametrize("method", ["get_review", "insert_review", "update_review"])
def test_store_errors_are_store_errors(env: Env, method: str) -> None:
    if method == "update_review":
        env.act("resolve_item", at=1, item_id="R-01", note="")
    env.store.fail.add(method)
    with pytest.raises(StoreError):
        env.act("resolve_item", at=2, item_id="R-02", note="")


# --- 저장 값 보존·시각·analyses ------------------------------------------------------------------------------------


def test_unknown_keys_other_items_and_gone_ids_are_kept(env: Env) -> None:
    saved = {
        storage_key("lowconf:0"): {"resolved": False, "extra": 1},
        storage_key("lowconf:2"): {"resolved": True, "note": "앞 처리", "resolved_at": iso(0), "resolved_by": "앞 사람"},
        "gone:9": {"resolved": True},  # 지금 결과에 없는 id(다시 분석 등)
        "junk": 5,
    }
    env.store.put_review(env.id, items=copy.deepcopy(saved))
    out = env.act("resolve_item", at=1, item_id="R-01", note="n")
    items = env.row()["items"]
    assert items[storage_key("lowconf:0")] == {"resolved": True, "extra": 1, "note": "n", "resolved_at": iso(1), "resolved_by": ACTOR}
    assert {k: v for k, v in items.items() if k != storage_key("lowconf:0")} == {k: v for k, v in saved.items() if k != storage_key("lowconf:0")}
    assert set(out.review["items"]) == {"lowconf:0", "lowconf:2"}  # 응답에서는 지금 결과의 객체 값만


def test_resolved_at_is_the_history_time_and_never_goes_back(env: Env) -> None:
    env.act("save_memo", at=10, text="m")
    env.act("resolve_item", at=5, item_id="R-01", note="")  # 시계가 뒤로 가도
    assert env.saved("R-01")["resolved_at"] == env.history()[-1]["at"] == iso(10)


def test_analyses_row_is_never_written(env: Env) -> None:
    before = copy.deepcopy(env.store.analyses[env.id])
    env.act("resolve_item", at=1, item_id="R-01", note="")
    env.act("reopen_item", at=2, item_id="R-01")
    env.act("complete_review", at=3, note="")
    assert env.store.updates == [] and env.store.analyses[env.id] == before


def test_reopen_item_never_takes_a_note() -> None:
    action = validate_action({"type": "reopen_item", "actor": ACTOR, "item_id": "x"})
    assert (action.item_id, action.text, action.finding_id) == ("x", "", None)


# --- 저장 키 충돌·저장할 수 없는 항목 -----------------------------------------------------------------------------------


def _with_extra_items(monkeypatch: pytest.MonkeyPatch, extra: list[dict[str, Any]]) -> None:
    original = reviews.build_view

    def patched(result: Any) -> dict[str, Any]:
        view = original(result)
        view["items"] = [*view["items"], *copy.deepcopy(extra)]
        return view

    monkeypatch.setattr(reviews, "build_view", patched)


def _extra(item_id: str, number: str, kind: str = "other", index: int = 0) -> dict[str, Any]:
    return {"id": item_id, "number": number, "type": kind, "document_index": index, "page": 1, "finding_id": None, "title": "t", "desc": "d", "next": "n", "evidence": []}


def test_colliding_storage_keys_make_the_later_item_unwritable(monkeypatch: pytest.MonkeyPatch) -> None:
    first, second = "x" + chr(0x1F600), "x" + "\ud83d" + "\ude00"  # 서로 다른 id → 같은 저장 키
    assert first != second and storage_key(first) == storage_key(second)
    _with_extra_items(monkeypatch, [_extra(first, "R-07"), _extra(second, "R-08"), _extra("lowconf:0", "R-09")])
    env = make_env()
    targets = env.scope.items
    assert [(t.num, t.writable) for t in targets[-3:]] == [("R-07", True), ("R-08", False), ("R-09", False)]
    assert env.scope.item_by_id[first].num == "R-07" and second not in env.scope.item_by_id
    action = validate_action({"type": "resolve_item", "actor": ACTOR, "item_id": second, "note": ""})
    with pytest.raises(ApiError) as info:
        apply_review_action(env.store, env.id, action, now=tick(1))
    assert (info.value.status_code, info.value.detail) == (404, MSG_NO_ITEM)
    # 같은 id 가 두 번이면 처음 것(R-01)이 받는다
    env.act("resolve_item", at=1, item_id="lowconf:0", note="")
    assert env.history()[-1]["target"] == "R-01 인식 확인 필요"
    block = env.read()
    assert block is not None and "분석 완료 · 탐지 29건 · 위험등급 높음 · 검토사항 9건" == block["history"][1]["change"]
    # 저장할 수 없는 항목은 미해결로 센다 — 해결할 수 있는 것을 모두 해결해도 R-08·R-09 가 남는다
    for t in env.scope.items:
        if t.writable and t.id != "lowconf:0":
            env.act("resolve_item", at=2, item_id=t.id, note="")
    env.act("confirm_many", at=3, finding_ids=list(env.findings))
    env.act("complete_review", at=4, note="")
    assert env.history()[-1]["change"] == "검토 필요 → 검토 완료 (남은 항목: 미해결 검토사항 2건)"


def test_items_outside_the_scope_rules_are_not_targets(monkeypatch: pytest.MonkeyPatch) -> None:
    bad = [
        _extra("a", "R-07", kind="모르는종류"),
        {**_extra("b", "R-08"), "id": 5},
        {**_extra("c", "R-09"), "number": 9},
        _extra("d", "R-10", index=99),  # 보이지 않는 서류
        {**_extra("e", "R-11"), "document_index": True},
        "항목 아님",
        _extra("f", "R-12", kind="weaklink"),  # 표 안의 종류면 대상
    ]
    _with_extra_items(monkeypatch, bad)
    env = make_env()
    assert [t.id for t in env.scope.items] == [*ITEM_IDS, "f"]
    assert env.scope.items[-1].label == "연결 근거 부족"


# --- 검토 완료 문구·S2 ------------------------------------------------------------------------------------------------


def test_complete_lists_open_findings_and_open_items(env: Env) -> None:
    env.act("complete_review", at=1, note="끝")
    assert env.history()[-1] == line(1, 1, "complete", "분석 건", "검토 필요 → 검토 완료 (남은 항목: 미확인 탐지 29건, 미해결 검토사항 6건)", "끝")


def test_complete_with_only_open_items(env: Env) -> None:
    env.act("confirm_many", at=1, finding_ids=list(env.findings))
    env.act("resolve_item", at=2, item_id="R-01", note="")
    env.act("complete_review", at=3, note="")
    assert env.history()[-1]["change"] == "검토 필요 → 검토 완료 (남은 항목: 미해결 검토사항 5건)"


def test_complete_with_only_open_findings(env: Env) -> None:
    for num in env.items:
        env.act("resolve_item", at=1, item_id=num, note="")
    env.act("complete_review", at=2, note="")
    assert env.history()[-1]["change"] == "검토 필요 → 검토 완료 (남은 항목: 미확인 탐지 29건)"


def test_complete_with_nothing_left(env: Env) -> None:
    for num in env.items:
        env.act("resolve_item", at=1, item_id=num, note="")
    env.act("confirm_many", at=2, finding_ids=list(env.findings))
    env.act("complete_review", at=3, note="")
    assert env.history()[-1]["change"] == "검토 필요 → 검토 완료"


def test_complete_of_a_result_without_items_is_unchanged() -> None:
    env = make_env(custom_result(SMALL))
    assert env.scope.items == ()
    env.act("complete_review", at=1, note="")
    assert env.history()[-1]["change"] == "검토 필요 → 검토 완료 (남은 항목: 미확인 탐지 4건)"


def test_reopened_items_count_as_open_again(env: Env) -> None:
    for num in env.items:
        env.act("resolve_item", at=1, item_id=num, note="")
    env.act("reopen_item", at=2, item_id="R-03")
    env.act("confirm_many", at=3, finding_ids=list(env.findings))
    env.act("complete_review", at=4, note="")
    assert env.history()[-1]["change"] == "검토 필요 → 검토 완료 (남은 항목: 미해결 검토사항 1건)"


def test_s2_counts_the_items(env: Env) -> None:
    block = env.read()
    assert block is not None
    assert block["history"][1]["change"] == "분석 완료 · 탐지 29건 · 위험등급 높음 · 검토사항 6건"
    failing = make_env(bundle_result([Spec("loan_application", (1, 1), validate=("red", [rule()]))], risk=None)).read()
    assert failing is not None and failing["history"][1]["change"] == "분석 완료 · 탐지 0건 · 위험등급 미평가 · 검토사항 1건"


# --- 조회 review.items ---------------------------------------------------------------------------------------------------


def test_review_items_are_normalized_and_only_current_objects(env: Env) -> None:
    env.store.put_review(
        env.id,
        items={
            storage_key("lowconf:0"): {"resolved": "true", "note": 5, "resolved_at": 7, "resolved_by": None},
            storage_key("lowconf:2"): {"resolved": 1},
            storage_key("lowconf:3"): "문자열",
            storage_key("lowconf:4"): None,
            storage_key("other:5"): {"resolved": True, "note": "n", "resolved_at": "t", "resolved_by": "b", "extra": 1},
            "lowconf:99": {"resolved": True},
        },
    )
    block = env.read()
    assert block is not None and list(block) == REVIEW_KEYS
    assert block["items"] == {
        "lowconf:0": UNRESOLVED,
        "lowconf:2": UNRESOLVED,
        "other:5": {"resolved": True, "note": "n", "resolved_at": "t", "resolved_by": "b"},
    }
    assert all(list(v) == ITEM_STATE_KEYS for v in block["items"].values())


@pytest.mark.parametrize("stored", [[], "x", 5, None])
def test_items_column_that_is_not_an_object_reads_as_empty(env: Env, stored: Any) -> None:
    env.store.put_review(env.id, items=stored)
    block = env.read()
    assert block is not None and block["items"] == {}


def test_items_column_missing_reads_as_empty(env: Env) -> None:
    env.store.put_review(env.id)
    env.store.reviews[env.id].pop("items")  # 열이 생기기 전 행처럼
    block = env.read()
    assert block is not None and block["items"] == {}
    env.act("resolve_item", at=1, item_id="R-01", note="")  # 그 위에 써도 된다
    assert set(env.row()["items"]) == {storage_key("lowconf:0")}


def test_review_read_failure_is_null(env: Env) -> None:
    env.store.fail.add("get_review")
    assert env.read() is None


def test_items_of_a_changed_result_are_ignored() -> None:
    # 다시 분석 등으로 결과가 바뀌어 저장된 id 가 지금 결과에 없으면 무시(값은 지우지 않음)
    env = make_env()
    env.act("resolve_item", at=1, item_id="R-02", note="")
    env.store.analyses[env.id]["result"] = custom_result(SMALL)
    block = env.read()
    assert block is not None and block["items"] == {}
    assert storage_key("nolocation:2:income_info") in env.row()["items"]


# --- 요청 본문 --------------------------------------------------------------------------------------------------------


def _body(kind: str = "resolve_item", **fields: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"type": kind, "actor": ACTOR, "item_id": "lowconf:0"}
    if kind == "resolve_item":
        base["note"] = "처리"
    return {**base, **fields}


def _bad(body: Any) -> str:
    with pytest.raises(ApiError) as info:
        validate_action(body)
    assert info.value.status_code == 400
    return info.value.detail


def test_good_bodies() -> None:
    action = validate_action(_body())
    assert (action.type, action.actor, action.item_id, action.text) == ("resolve_item", ACTOR, "lowconf:0", "처리")
    assert validate_action(_body(note="")).text == ""  # 빈 처리 내용도 받는다
    action = validate_action(_body("reopen_item"))
    assert (action.type, action.item_id, action.text) == ("reopen_item", "lowconf:0", "")


@pytest.mark.parametrize(
    "body",
    [
        {**_body(), "extra": 1},
        {**_body(), "finding_id": "0:a"},
        {k: v for k, v in _body().items() if k != "note"},
        {k: v for k, v in _body().items() if k != "item_id"},
        {k: v for k, v in _body("reopen_item").items() if k != "item_id"},
        _body("reopen_item", note=""),  # reopen_item 은 note 를 받지 않는다
        _body("reopen_item", reason=""),
    ],
    ids=["모르는필드", "다른동작필드", "note없음", "item_id없음", "reopen_item_id없음", "reopen에note", "reopen에reason"],
)
def test_exact_fields(body: dict[str, Any]) -> None:
    assert _bad(body) == MSG_FORMAT


@pytest.mark.parametrize("value", [5, None, [], ["lowconf:0"], {}, True], ids=["숫자", "null", "빈목록", "목록", "객체", "bool"])
def test_item_id_must_be_a_string(value: Any) -> None:
    assert _bad(_body(item_id=value)) == MSG_FORMAT
    assert _bad(_body("reopen_item", item_id=value)) == MSG_FORMAT


@pytest.mark.parametrize("value", [5, None, [], True], ids=["숫자", "null", "목록", "bool"])
def test_note_must_be_a_string(value: Any) -> None:
    assert _bad(_body(note=value)) == MSG_FORMAT


def test_note_length_counts_code_points() -> None:
    assert validate_action(_body(note="가" * 500)).text == "가" * 500
    assert validate_action(_body(note="\U0001f600" * 500)).text == "\U0001f600" * 500  # 비 BMP 도 코드 포인트 하나
    assert _bad(_body(note="가" * 501)) == MSG_TOO_LONG
    assert _bad(_body(note="\U0001f600" * 501)) == MSG_TOO_LONG


@pytest.mark.parametrize("note", ["a\x00b", "a\ud800b", "\udfff"], ids=["NUL", "상위서로게이트", "하위서로게이트"])
def test_note_with_unwritable_characters(note: str) -> None:
    assert _bad(_body(note=note)) == MSG_BAD_CHAR
    assert _bad(_body(note=note + "가" * 600)) == MSG_BAD_CHAR  # 쓸 수 없는 문자가 길이보다 먼저


@pytest.mark.parametrize("actor", ["", " 김", "김 ", "가" * 41, "김\x00", "김\ud800", "김\n이"])
def test_actor_rules(actor: str) -> None:
    assert _bad(_body(actor=actor)) == MSG_BAD_ACTOR
    assert _bad(_body("reopen_item", actor=actor)) == MSG_BAD_ACTOR
    assert _bad(_body(actor=actor, note="\x00")) == MSG_BAD_ACTOR  # 처리자가 글보다 먼저


def test_format_comes_before_actor() -> None:
    assert _bad(_body(actor="", item_id=5)) == MSG_FORMAT
    assert _bad({**_body(actor=""), "extra": 1}) == MSG_FORMAT
    assert _bad(_body(actor=5)) == MSG_FORMAT
    assert validate_action(_body(actor="가" * 40)).actor == "가" * 40


@pytest.mark.parametrize(
    "raw",
    [
        b'{"type":"resolve_item","actor":"a","item_id":"x","item_id":"y","note":""}',
        b'{"type":"resolve_item","actor":"a","item_id":"x","note":NaN}',
        b'{"type":"reopen_item","actor":"a","item_id":' + b"[" * 100_000 + b"]" * 100_000 + b"}",
        b'{"type":"resolve_item","actor":"a","item_id":"x","note":""',
        b"\xff\xfe",
        b'["resolve_item"]',
    ],
    ids=["같은키두번", "NaN", "깊은중첩", "닫히지않음", "UTF8아님", "객체아님"],
)
def test_existing_body_boundaries(raw: bytes) -> None:
    with pytest.raises(ApiError) as info:
        parse_action(raw)
    assert (info.value.status_code, info.value.detail) == (400, MSG_FORMAT)


def test_escaped_text_in_the_body() -> None:
    assert parse_action(b'{"type":"resolve_item","actor":"a","item_id":"x","note":"\\ud83d\\ude00"}').text == "\U0001f600"
    with pytest.raises(ApiError) as info:
        parse_action(b'{"type":"resolve_item","actor":"a","item_id":"x","note":"\\ud800"}')
    assert info.value.detail == MSG_BAD_CHAR
    # item_id 의 서로게이트는 그대로 받는다(지금 결과에 없으면 404)
    assert parse_action(b'{"type":"reopen_item","actor":"a","item_id":"x\\ud800"}').item_id == "x\ud800"


# --- API -------------------------------------------------------------------------------------------------------------------


def _post(ctx: Ctx, analysis_id: str, body: Any) -> Any:  # noqa: F811
    content = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=True).encode("ascii")
    return ctx.client.post(f"/api/py/analyses/{analysis_id}/review-actions", content=content, headers={"content-type": "application/json"})


def _done(ctx: Ctx, result: Any = None) -> str:  # noqa: F811
    return ctx.store.put(status="done", job_id="job_done", result=result if result is not None else stored_result())


def test_get_returns_result_items_and_empty_review_items(ctx: Ctx) -> None:  # noqa: F811
    analysis_id = _done(ctx)
    body = ctx.get(analysis_id).json()
    assert [i["id"] for i in body["result"]["items"]] == ITEM_IDS
    assert [i["number"] for i in body["result"]["items"]] == ["R-01", "R-02", "R-03", "R-04", "R-05", "R-06"]
    assert list(body["review"]) == REVIEW_KEYS and body["review"]["items"] == {}
    assert body["review"]["history"][1]["change"] == "분석 완료 · 탐지 29건 · 위험등급 높음 · 검토사항 6건"
    assert ctx.store.updates == [] and ctx.store.review_writes == []  # 조회는 쓰지 않는다
    ctx.no_upstage()


def test_stored_items_key_is_replaced_by_the_server_value(ctx: Ctx) -> None:  # noqa: F811
    result = stored_result()
    result["items"] = [{"id": "가짜", "number": "R-01", "type": "other"}]
    analysis_id = _done(ctx, result)
    assert [i["id"] for i in ctx.get(analysis_id).json()["result"]["items"]] == ITEM_IDS


def test_post_resolve_and_reopen_over_http(ctx: Ctx) -> None:  # noqa: F811
    analysis_id = _done(ctx)
    response = _post(ctx, analysis_id, {"type": "resolve_item", "actor": ACTOR, "item_id": "lowconf:2", "note": "확인함"})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"analysis", "changed"} and body["changed"] is True
    analysis = body["analysis"]
    assert set(analysis) == ANALYSIS_KEYS and list(analysis["review"]) == REVIEW_KEYS
    assert "stages" not in analysis["result"] and [i["id"] for i in analysis["result"]["items"]] == ITEM_IDS
    review = analysis["review"]
    value = review["items"]["lowconf:2"]
    assert (value["resolved"], value["note"], value["resolved_by"]) == (True, "확인함", ACTOR)
    last = review["history"][-1]
    assert (last["id"], last["kind"], last["target"], last["change"], last["reason"], last["actor"]) == (
        "H1",
        "resolve",
        "R-03 인식 확인 필요",
        "미해결 → 해결",
        "확인함",
        ACTOR,
    )
    assert value["resolved_at"] == last["at"]
    assert ctx.get(analysis_id).json() == analysis  # 다시 조회해도 같은 값
    response = _post(ctx, analysis_id, {"type": "reopen_item", "actor": ACTOR, "item_id": "lowconf:2"})
    assert response.status_code == 200 and response.json()["changed"] is True
    review = response.json()["analysis"]["review"]
    assert review["items"]["lowconf:2"] == {**value, "resolved": False}
    assert (review["history"][-1]["id"], review["history"][-1]["kind"], review["history"][-1]["change"], review["history"][-1]["reason"]) == (
        "H2",
        "reopenItem",
        "해결 → 미해결",
        "",
    )
    assert ctx.store.updates == []
    ctx.no_upstage()


def test_http_error_order(ctx: Ctx) -> None:  # noqa: F811
    analysis_id = _done(ctx)
    good = {"type": "resolve_item", "actor": ACTOR, "item_id": "lowconf:0", "note": ""}
    cases: list[tuple[Any, str, int, str]] = [
        (b'{"type":"resolve_item","actor":"' + b"a" * 70_000 + b'"}', analysis_id, 413, MSG_TOO_LARGE),
        ({**good, "item_id": 5, "actor": ""}, analysis_id, 400, MSG_FORMAT),
        ({**good, "actor": " 김", "note": "\x00"}, analysis_id, 400, MSG_BAD_ACTOR),
        ({**good, "note": "\x00"}, "7b944f1e-1234-4abc-8def-0123456789ab", 400, MSG_BAD_CHAR),
        ({**good, "note": "가" * 501}, analysis_id, 400, MSG_TOO_LONG),
        ({**good, "item_id": "없음"}, "7b944f1e-1234-4abc-8def-0123456789ab", 404, MSG_NOT_FOUND),
        ({**good, "item_id": "없음"}, analysis_id, 404, MSG_NO_ITEM),
        ({"type": "reopen_item", "actor": ACTOR, "item_id": "lowconf:0"}, analysis_id, 409, MSG_ITEM_STATE),
    ]
    for body, target, status, detail in cases:
        response = _post(ctx, target, body)
        assert (response.status_code, response.json()) == (status, {"detail": detail}), detail
    running = ctx.store.put(status="running", job_id="j", result=stored_result())
    response = _post(ctx, running, {**good, "item_id": "없음"})
    assert (response.status_code, response.json()) == (409, {"detail": MSG_NOT_REVIEWABLE})
    assert ctx.store.review_writes == []
    ctx.no_upstage()


def test_http_flow_complete_locks_both_then_reopen(ctx: Ctx) -> None:  # noqa: F811
    analysis_id = _done(ctx)
    assert _post(ctx, analysis_id, {"type": "resolve_item", "actor": ACTOR, "item_id": "other:5", "note": ""}).status_code == 200
    done = _post(ctx, analysis_id, {"type": "complete_review", "actor": ACTOR, "note": ""})
    assert done.json()["analysis"]["review"]["history"][-1]["change"] == "검토 필요 → 검토 완료 (남은 항목: 미확인 탐지 29건, 미해결 검토사항 5건)"
    for body in (
        {"type": "resolve_item", "actor": ACTOR, "item_id": "lowconf:0", "note": ""},
        {"type": "reopen_item", "actor": ACTOR, "item_id": "other:5"},
    ):
        response = _post(ctx, analysis_id, body)
        assert (response.status_code, response.json()) == (409, {"detail": MSG_LOCKED})
    assert _post(ctx, analysis_id, {"type": "reopen_review", "actor": ACTOR, "reason": ""}).status_code == 200
    assert _post(ctx, analysis_id, {"type": "reopen_item", "actor": ACTOR, "item_id": "other:5"}).status_code == 200
    response = _post(ctx, analysis_id, {"type": "resolve_item", "actor": ACTOR, "item_id": "other:5", "note": "다시"})
    assert response.status_code == 200
    kinds = [h["kind"] for h in response.json()["analysis"]["review"]["history"]]
    assert kinds == ["request", "ai", "resolve", "complete", "reopen", "reopenItem", "resolve"]
    assert ctx.store.updates == []


def test_http_history_full_and_store_error(ctx: Ctx) -> None:  # noqa: F811
    analysis_id = _done(ctx)
    ctx.store.put_review(analysis_id, history=[line(i, 0, "memo", "분석 건", "x") for i in range(1, 1001)], version=1000)
    response = _post(ctx, analysis_id, {"type": "resolve_item", "actor": ACTOR, "item_id": "lowconf:0", "note": ""})
    assert (response.status_code, response.json()) == (409, {"detail": MSG_HISTORY_FULL})
    other = _done(ctx)
    ctx.store.fail.add("insert_review")
    response = _post(ctx, other, {"type": "resolve_item", "actor": ACTOR, "item_id": "lowconf:0", "note": ""})
    assert (response.status_code, response.json()) == (502, {"detail": MSG_STORE})


def test_http_get_with_unreadable_review_still_has_items(ctx: Ctx) -> None:  # noqa: F811
    analysis_id = _done(ctx)
    ctx.store.fail.add("get_review")
    body = ctx.get(analysis_id).json()
    assert body["review"] is None and len(body["result"]["items"]) == 6


# --- 로그·StoreError 에 값 없음 -------------------------------------------------------------------------------------------

ANALYSIS_ID = "7b944f1e-1234-4abc-8def-0123456789ab"
RULE_SENTINEL = "규칙센티널R5"
ACTOR_SENTINEL = "처리자센티널Q7"
NOTE_SENTINEL = "처리내용센티널N2"
REASON_SENTINEL = "검증사유센티널S1"
OUTSIDE_SENTINEL = "OUTSIDE-ORIGINAL-ERROR-9f3k"
SENTINELS = (ANALYSIS_ID, RULE_SENTINEL, ACTOR_SENTINEL, NOTE_SENTINEL, REASON_SENTINEL, OUTSIDE_SENTINEL)


def _sentinel_result() -> dict[str, Any]:
    check = {**rule(name=RULE_SENTINEL), "reason": REASON_SENTINEL}
    return bundle_result([Spec("loan_application", (1, 1), {"applicant_name": ("값", None, "low")}, validate=("red", [check]))])


def _value_free(text: str) -> None:
    for value in SENTINELS:
        assert value not in text, "로그·오류 문구에 값이 섞였다"


def _put_fixed(store: FakeStore) -> None:
    made = store.put(status="done", job_id="job_done", result=_sentinel_result())
    row = store.analyses.pop(made)
    row["id"] = ANALYSIS_ID
    store.analyses[ANALYSIS_ID] = row
    for doc in store.documents.values():
        if doc["analysis_id"] == made:
            doc["analysis_id"] = ANALYSIS_ID


ITEM_ID = f"missing:0:{RULE_SENTINEL}"


LOG_OUTCOMES = {
    "ok": "ok",
    "unknown_item": (404, MSG_NO_ITEM),
    "state": (409, MSG_ITEM_STATE),
    "locked": (409, MSG_LOCKED),
    "insert_error": "store",
    "race_three": (409, MSG_CONFLICT),
    "deleted": (404, MSG_NOT_FOUND),
    "history_full": (409, MSG_HISTORY_FULL),
}


@pytest.mark.parametrize("scenario", list(LOG_OUTCOMES))
def test_item_actions_log_no_values(scenario: str) -> None:
    store = FakeStore()
    _put_fixed(store)
    body = {"type": "resolve_item", "actor": ACTOR_SENTINEL, "item_id": ITEM_ID, "note": NOTE_SENTINEL}
    if scenario == "unknown_item":
        body["item_id"] = f"missing:0:{RULE_SENTINEL}x"
    elif scenario == "state":
        body = {"type": "reopen_item", "actor": ACTOR_SENTINEL, "item_id": ITEM_ID}
    elif scenario == "locked":
        store.put_review(ANALYSIS_ID, status="done")
    elif scenario == "insert_error":
        store.fail.add("insert_review")
    elif scenario == "race_three":
        store.review_hooks = [_other("save_memo", m, text="x") for m in (1, 2, 3)]
    elif scenario == "deleted":
        store.review_hooks = [lambda s, aid: s.delete_analysis(aid)]
    elif scenario == "history_full":
        store.put_review(ANALYSIS_ID, history=[line(i, 0, "memo", "분석 건", "x") for i in range(1, 1001)], version=1000)
    action = validate_action(body)
    outcome: Any = "ok"
    with imask_log() as log:
        try:
            apply_review_action(store, ANALYSIS_ID, action, now=tick(5))
        except ApiError as exc:
            outcome = (exc.status_code, exc.detail)
            _value_free(exc.detail)
        except StoreError as exc:
            outcome = "store"
            _value_free(exc.message + repr(exc) + str(exc))
    assert outcome == LOG_OUTCOMES[scenario]
    if scenario == "ok":
        assert store.reviews[ANALYSIS_ID]["items"][storage_key(ITEM_ID)]["note"] == NOTE_SENTINEL  # 값은 저장에만
    _value_free("\n".join(log.lines))


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
        "items": {},
        "history": [],
        "version": version,
        "created_at": "2026-11-04T15:00:00+00:00",
        "updated_at": "2026-11-04T15:00:00+00:00",
    }


def _analysis_row() -> dict[str, Any]:
    return {
        "id": ANALYSIS_ID,
        "name": "합성 묶음",
        "status": "done",
        "agent_id": None,
        "upstage_job_id": "job_done",
        "result": _sentinel_result(),
        "error": None,
        "created_at": "2026-11-04T15:00:00+00:00",
        "updated_at": "2026-11-04T15:05:00+00:00",
        "started_at": "2026-11-04T15:00:00+00:00",
        "documents": [],
    }


@pytest.mark.parametrize(
    ("script", "status", "detail"),
    [
        (
            lambda: {
                ("analyses", "select"): [[_analysis_row()], UpstreamError()],
                ("analysis_reviews", "select"): [[]],
                ("analysis_reviews", "upsert"): [UpstreamError()],
            },
            502,
            MSG_STORE,
        ),
        (
            lambda: {
                ("analyses", "select"): [[_analysis_row()], UpstreamError()],
                ("analysis_reviews", "select"): [[_review_row(1)], [_review_row(2)], [_review_row(3)]],
                ("analysis_reviews", "update"): [[], [], []],
            },
            409,
            MSG_CONFLICT,
        ),
        (lambda: {("analyses", "select"): [UpstreamError()]}, 502, MSG_STORE),
    ],
    ids=["쓰기오류뒤다시읽기실패", "경쟁3번뒤다시읽기실패", "처음읽기실패"],
)
def test_item_action_store_errors_over_http_are_value_free(monkeypatch: pytest.MonkeyPatch, script: Any, status: int, detail: str) -> None:
    client = ScriptedClient(script())
    database = SupabaseStore(client)
    context = install(monkeypatch)
    app.dependency_overrides[get_store] = lambda: database
    body = {"type": "resolve_item", "actor": ACTOR_SENTINEL, "item_id": ITEM_ID, "note": NOTE_SENTINEL}
    try:
        with TestClient(app) as http, imask_log() as log:
            response = http.post(f"/api/py/analyses/{ANALYSIS_ID}/review-actions", json=body)
    finally:
        app.dependency_overrides.clear()
    assert (response.status_code, response.json()) == (status, {"detail": detail})
    assert all(not values for values in client.script.values()), "대본을 끝까지 썼다"
    text = "\n".join(log.lines)
    assert text  # 값 없는 문구는 잡혔다
    _value_free(text)
    _value_free(response.text)
    context.no_upstage()


# --- 삭제 경합을 실제 SupabaseStore(가짜 fluent 클라이언트)로 — reopen_item(T1-fix1) ------------------------------------------


def _resolved_review_row(version: int) -> dict[str, Any]:
    row = _review_row(version)
    row["items"] = {storage_key(ITEM_ID): {"resolved": True, "note": NOTE_SENTINEL, "resolved_at": "2026-11-04T15:01:00+00:00", "resolved_by": ACTOR_SENTINEL}}
    return row


REOPEN_RACES: dict[str, tuple[Any, int, str, bool]] = {
    # 이름 → (대본, 상태, 문구, 다시 읽기 저장소 오류 문구가 로그에 있어야 함)
    "UPDATE직전삭제": (
        lambda: {
            ("analyses", "select"): [[_analysis_row()], []],
            ("analysis_reviews", "select"): [[_resolved_review_row(1)], []],
            ("analysis_reviews", "update"): [[]],
        },
        404,
        MSG_NOT_FOUND,
        False,
    ),
    "첫검토행조회전삭제": (
        lambda: {("analyses", "select"): [[_analysis_row()], []], ("analysis_reviews", "select"): [[]]},
        404,
        MSG_NOT_FOUND,
        False,
    ),
    "검토행없음_분석있음": (
        lambda: {("analyses", "select"): [[_analysis_row()], [_analysis_row()]], ("analysis_reviews", "select"): [[]]},
        409,
        MSG_ITEM_STATE,
        False,
    ),
    "검토행있음_미해결": (
        lambda: {("analyses", "select"): [[_analysis_row()]], ("analysis_reviews", "select"): [[_review_row(1)]]},
        409,
        MSG_ITEM_STATE,
        False,
    ),
    "다시읽기오류": (
        lambda: {("analyses", "select"): [[_analysis_row()], UpstreamError()], ("analysis_reviews", "select"): [[]]},
        409,
        MSG_ITEM_STATE,
        True,
    ),
    "삭제뒤다시읽기오류": (
        lambda: {
            ("analyses", "select"): [[_analysis_row()], UpstreamError()],
            ("analysis_reviews", "select"): [[_resolved_review_row(1)], []],
            ("analysis_reviews", "update"): [[]],
        },
        409,
        MSG_ITEM_STATE,
        True,
    ),
}


@pytest.mark.parametrize("name", list(REOPEN_RACES))
def test_reopen_delete_races_with_supabase_store_over_http(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    script, status, detail, reread_error = REOPEN_RACES[name]
    client = ScriptedClient(script())
    database = SupabaseStore(client)
    context = install(monkeypatch)
    app.dependency_overrides[get_store] = lambda: database
    try:
        with TestClient(app) as http, imask_log() as log:
            response = http.post(
                f"/api/py/analyses/{ANALYSIS_ID}/review-actions", json={"type": "reopen_item", "actor": ACTOR_SENTINEL, "item_id": ITEM_ID}
            )
    finally:
        app.dependency_overrides.clear()
    assert (response.status_code, response.json()) == (status, {"detail": detail})
    assert all(not values for values in client.script.values()), "대본을 끝까지 썼다(다시 읽기까지 갔다)"
    text = "\n".join(log.lines)
    if reread_error:
        assert QUIET_READ in text  # 값 없는 다시 읽기 오류 문구는 잡혔다
    _value_free(text)
    _value_free(response.text)
    context.no_upstage()
