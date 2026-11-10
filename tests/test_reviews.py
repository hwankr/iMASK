# ==========================================================================
#  imask_backend.reviews — 검토 동작 저장 업무 로직(FastAPI 없이 FakeStore 로)
#  - 동작 9종의 상태 전이·이력 문구가 데모 코어(src/services/demo/core.ts)와 같은지(정확한 문자열)
#  - 데모와 같은 세부(restore·reclassify·fmemo·save_memo·reopen·confirm_many), changed false, 409 문구 전부
#  - 경쟁(다시 읽어 그 위에 적용·첫 삽입끼리·3번 패배), 시각(같은 동작은 같은 값·마지막 이력보다 앞서지 않음)
#  - analyses 행(updated_at)을 쓰지 않음, 조회 블록(S1·S2·기본값·정규화·저장 값 보존), 요청 본문 검사
#  - 목록 동기화: FP_REASONS·FSTATUS 라벨·RSTATUS needed/done 라벨·HKIND 키가 src/display/rules.ts 와 같은지(읽기만)
# ==========================================================================

from __future__ import annotations

import copy
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from api_fakes import FakeStore
from fake_findings import stored_result
from fake_reviews import ACTOR, SMALL, custom_result

from imask_backend import reviews
from imask_backend.analyses import ApiError
from imask_backend.reviews import (
    FINDING_KEYS,
    FP_REASONS,
    FSTATUS,
    HISTORY_KEYS,
    HKIND,
    RSTATUS,
    ActionOutcome,
    apply_review_action,
    parse_action,
    read_review,
    review_scope,
    row_view,
    storage_key,
    validate_action,
)
from imask_backend.store import StoreError

ROOT = Path(__file__).resolve().parents[1]
RULES_TS = ROOT / "src" / "display" / "rules.ts"

CLOCK = datetime(2026, 11, 3, 1, 2, 3, tzinfo=UTC)


def tick(minutes: int) -> datetime:
    return CLOCK + timedelta(minutes=minutes)


def iso(minutes: int) -> str:
    return tick(minutes).isoformat()


class Env:
    """분석 하나 + 동작 도우미. 화면 번호(D1-01)를 계약 id 로 바꿔 보낸다."""

    def __init__(self, store: FakeStore, analysis_id: str) -> None:
        self.store = store
        self.id = analysis_id
        row = store.get_analysis(analysis_id)
        assert row is not None
        scope = review_scope(row, row_view(row))
        assert scope is not None
        self.scope = scope
        self.ids = {t.num: t.id for t in scope.targets}

    def fid(self, num: str) -> str:
        return self.ids[num]

    def body(self, kind: str, actor: str = ACTOR, **fields: Any) -> dict[str, Any]:
        out: dict[str, Any] = {"type": kind, "actor": actor}
        for name, value in fields.items():
            if name == "finding_id":
                value = self.ids.get(value, value)
            elif name == "finding_ids":
                value = [self.ids.get(v, v) for v in value]
            out[name] = value
        return out

    def act(self, kind: str, *, at: int = 0, actor: str = ACTOR, **fields: Any) -> ActionOutcome:
        action = validate_action(self.body(kind, actor, **fields))
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
        return self.row()["findings"][storage_key(self.fid(num))]


def make_env(result: dict[str, Any] | None = None, store: FakeStore | None = None) -> Env:
    store = store or FakeStore()
    analysis_id = store.put(status="done", job_id="job_done", result=result or custom_result(SMALL))
    return Env(store, analysis_id)


@pytest.fixture
def env() -> Env:
    return make_env()


def line(version: int, minutes: int, kind: str, target: str, change: str, reason: str = "", actor: str = ACTOR) -> dict[str, str]:
    return {"id": f"H{version}", "at": iso(minutes), "actor": actor, "kind": kind, "target": target, "change": change, "reason": reason}


def entry(env: Env, num: str, **values: Any) -> dict[str, Any]:
    """AI 값으로 시작한 항목 값 + 바뀐 값."""
    target = next(t for t in env.scope.targets if t.num == num)
    base = {
        "status": "open",
        "category": target.category,
        "subject": target.subject,
        "exposure": target.exposure,
        "fp_type": "",
        "fp_note": "",
        "reclass_note": "",
        "memo": "",
        "updated_at": None,
    }
    return {**base, **values}


# --- 검토할 수 있는 항목·번호·AI 값 --------------------------------------------------------------


def test_scope_numbers_labels_and_ai_values(env: Env) -> None:
    targets = env.scope.targets
    assert [t.num for t in targets] == ["D1-01", "D1-02", "D1-03", "D2-01"]
    assert [t.id for t in targets] == ["0:applicant_name", "0:applicant_rrn", "0:applicant_phone", "1:applicant_address"]
    assert [(t.label, t.category, t.subject, t.exposure) for t in targets] == [
        ("신청인 성명", "이름", "신청인", "전체 노출"),
        ("주민등록번호", "고유식별정보", "신청인", "전체 노출"),
        ("전화번호", "연락처·이메일", "신청인", "전체 노출"),
        ("주소", "주소", "신청인", "전체 노출"),
    ]
    assert all(t.key == storage_key(t.id) and t.writable for t in targets)


def test_scope_of_the_real_shaped_result_matches_the_screen_numbering() -> None:
    env = make_env(stored_result())
    nums = [t.num for t in env.scope.targets]
    assert len(nums) == 29  # 서류 5개(10/2/5/7/5) — 기타 서류(6쪽)는 항목 없음
    assert nums[:3] == ["D1-01", "D1-02", "D1-03"] and nums[9:12] == ["D1-10", "D2-01", "D2-02"] and nums[-1] == "D5-05"
    assert env.scope.risk_label == "높음"


def test_hundredth_finding_in_one_document_keeps_three_digits() -> None:
    data = {f"key_{i:03d}": f"값{i}" for i in range(101)}
    env = make_env(custom_result([data]))
    assert [t.num for t in env.scope.targets][98:] == ["D1-99", "D1-100", "D1-101"]


def test_label_falls_back_like_the_screen() -> None:
    # 표에 없는 키는 원래 키가 이름(공백만이면 '(이름 없는 항목)'). 화면은 JavaScript trim 기준으로 label → field → '이름 없는 항목'
    env = make_env(custom_result([{"  ": "값1", "﻿": "값2", "brand_new": "값3"}]))
    labels = [t.label for t in env.scope.targets]
    assert labels == ["(이름 없는 항목)", "이름 없는 항목", "brand_new"]


def test_ai_values_outside_the_lists_fall_back() -> None:
    store = FakeStore()
    analysis_id = store.put(status="done", job_id="j", result=custom_result(SMALL))
    row = store.get_analysis(analysis_id)
    assert row is not None
    view = row_view(row)
    assert view is not None
    view["findings"][0].update({"category": "없는 분류", "subject": None, "exposure": ["x"], "label": 5, "field": " f "})
    scope = review_scope(row, view)
    assert scope is not None
    first = scope.targets[0]
    assert (first.category, first.subject, first.exposure, first.label) == ("기타 개인정보", "기타", "전체 노출", "f")


@pytest.mark.parametrize("status", ["queued", "running", "failed", "partial"])
def test_not_done_is_not_reviewable(status: str) -> None:
    store = FakeStore()
    analysis_id = store.put(status=status, result=custom_result(SMALL))
    row = store.get_analysis(analysis_id)
    assert row is not None
    assert review_scope(row, row_view(row)) is None


@pytest.mark.parametrize(
    "result",
    [None, "문자열", [], {"format": "imask-upstage-v1", "stages": []}, custom_result(SMALL, pageless_classify=True)],
    ids=["none", "string", "list", "old_no_documents", "pageless_documents_only"],
)
def test_done_without_valid_documents_is_not_reviewable(result: Any) -> None:
    store = FakeStore()
    analysis_id = store.put(status="done", result=result)
    row = store.get_analysis(analysis_id)
    assert row is not None
    assert review_scope(row, row_view(row)) is None
    action = validate_action({"type": "save_memo", "actor": ACTOR, "text": "메모"})
    with pytest.raises(ApiError) as info:
        apply_review_action(store, analysis_id, action)
    assert (info.value.status_code, info.value.detail) == (409, "검토할 수 없는 분석입니다.")
    assert store.review_writes == [] and "get_review" not in store.calls


def test_findings_of_a_pageless_document_are_not_targets() -> None:
    env = make_env(custom_result([{"applicant_name": "김가짜"}], unpaged={"applicant_rrn": "900101-1234567"}))
    row = env.store.get_analysis(env.id)
    assert row is not None
    view = row_view(row)
    assert view is not None
    assert [f["id"] for f in view["findings"]] == ["0:applicant_name", "1:applicant_rrn"]
    assert [t.id for t in env.scope.targets] == ["0:applicant_name"]
    err = env.error("set_status", finding_id="1:applicant_rrn", status="confirmed", reason="")
    assert (err.status_code, err.detail) == (404, "탐지 항목을 찾을 수 없습니다.")


# --- 동작별 전이·이력 문구(데모 코어와 같은 문자열) --------------------------------------------------


def test_full_flow_transitions_and_history_lines(env: Env) -> None:
    out = env.act("set_status", at=1, finding_id="D1-01", status="confirmed", reason="확인 사유")
    assert out.changed and out.review["version"] == 1
    assert env.saved("D1-01") == entry(env, "D1-01", status="confirmed", updated_at=iso(1))
    env.act("set_status", at=2, finding_id="D1-01", status="open", reason="")
    env.act("mark_false_positive", at=3, finding_id="D1-01", reason_type="기타", note="오탐 메모")
    assert env.saved("D1-01") == entry(env, "D1-01", status="false_positive", fp_type="기타", fp_note="오탐 메모", updated_at=iso(3))
    env.act("restore", at=4, finding_id="D1-01", note="되돌림")
    assert env.saved("D1-01") == entry(env, "D1-01", status="open", updated_at=iso(4))
    env.act("reclassify", at=5, finding_id="D1-01", category="주소", exposure="마스킹됨", reason="분류 사유")
    assert env.saved("D1-01") == entry(
        env, "D1-01", status="reclassified", category="주소", exposure="마스킹됨", reclass_note="분류 사유", updated_at=iso(5)
    )
    env.act("mark_false_positive", at=6, finding_id="D1-01", reason_type="이미 가려진 값", note="n2")
    env.act("restore", at=7, finding_id="D1-01", note="")
    env.act("save_finding_memo", at=8, finding_id="D1-01", text="항목 메모")
    env.act("save_finding_memo", at=9, finding_id="D1-01", text="")
    env.act("save_memo", at=10, text="검토 메모")
    env.act("save_memo", at=11, text="")
    env.act("set_status", at=12, finding_id="D1-02", status="confirmed", reason="")
    env.act("confirm_many", at=13, finding_ids=["D1-01", "D1-02", "D1-03"])
    env.act("complete_review", at=14, note="완료 메모")
    out = env.act("reopen_review", at=15, reason="다시 봄")

    expected = [
        line(1, 1, "confirm", "D1-01 이름", "미확인 → 확인함", "확인 사유"),
        line(2, 2, "unconfirm", "D1-01 이름", "확인함 → 미확인"),
        line(3, 3, "fp", "D1-01 신청인 성명", "이름 → 오탐 (기타)", "오탐 메모"),
        line(4, 4, "restore", "D1-01 신청인 성명", "오탐 → 미확인", "되돌림"),
        line(5, 5, "reclass", "D1-01 신청인 성명", "정보 종류: 이름 → 주소, 노출 상태: 전체 노출 → 마스킹됨", "분류 사유"),
        line(6, 6, "fp", "D1-01 신청인 성명", "주소 → 오탐 (이미 가려진 값)", "n2"),
        line(7, 7, "restore", "D1-01 신청인 성명", "오탐 → 분류 수정"),
        line(8, 8, "fmemo", "D1-01 주소", "항목 메모 저장", "항목 메모"),
        line(9, 9, "fmemo", "D1-01 주소", "항목 메모 삭제"),
        line(10, 10, "memo", "분석 건", "검토 메모 저장", "검토 메모"),
        line(11, 11, "memo", "분석 건", "검토 메모 삭제"),
        line(12, 12, "confirm", "D1-02 고유식별정보", "미확인 → 확인함"),
        line(13, 13, "confirm", "탐지 항목 1건", "미확인 → 확인함", "D1-03"),
        line(14, 14, "complete", "분석 건", "검토 필요 → 검토 완료 (남은 항목: 미확인 탐지 1건)", "완료 메모"),
        line(15, 15, "reopen", "분석 건", "검토 완료 → 검토 필요", "다시 봄"),
    ]
    assert env.history() == expected
    assert out.review["history"][2:] == expected  # 응답 = S1·S2 + 저장된 줄
    assert out.review["version"] == env.row()["version"] == 15
    # 마지막 항목 값: 분류 수정 유지, 오탐 사유는 지워짐, 항목 메모 삭제는 updated_at 을 바꾸지 않음
    assert env.saved("D1-01") == entry(
        env, "D1-01", status="reclassified", category="주소", exposure="마스킹됨", reclass_note="분류 사유", updated_at=iso(7)
    )
    assert out.review["status"] == "needed" and out.review["reviewer"] == ACTOR
    assert out.review["completion_note"] == "완료 메모" and out.review["reviewed_at"] is None


def test_confirm_many_example_from_the_brief(env: Env) -> None:
    env.act("set_status", at=1, finding_id="D1-02", status="confirmed", reason="")
    out = env.act("confirm_many", at=2, finding_ids=["D1-01", "D1-02", "D1-03"])
    assert out.changed
    assert env.history()[-1] == line(2, 2, "confirm", "탐지 항목 2건", "미확인 → 확인함", "D1-01, D1-03")
    assert env.saved("D1-01")["status"] == env.saved("D1-03")["status"] == "confirmed"
    assert env.saved("D1-02")["updated_at"] == iso(1)  # 건너뛴 항목은 그대로
    assert env.saved("D1-01")["updated_at"] == iso(2)


def test_confirm_many_uses_request_order_for_the_reason(env: Env) -> None:
    env.act("confirm_many", at=1, finding_ids=["D2-01", "D1-03", "D1-01"])
    assert env.history()[-1]["reason"] == "D2-01, D1-03, D1-01"
    assert env.history()[-1]["target"] == "탐지 항목 3건"


def test_complete_with_two_open_and_with_none(env: Env) -> None:
    env.act("confirm_many", at=1, finding_ids=["D1-01", "D1-02"])
    env.act("complete_review", at=2, note="")
    assert env.history()[-1] == line(2, 2, "complete", "분석 건", "검토 필요 → 검토 완료 (남은 항목: 미확인 탐지 2건)")
    assert env.row()["status"] == "done" and env.row()["reviewer"] == ACTOR and env.row()["reviewed_at"] == iso(2)
    env.act("reopen_review", at=3, reason="r")
    env.act("confirm_many", at=4, finding_ids=["D1-03", "D2-01"])
    env.act("complete_review", at=5, note="끝", actor="박검토")
    assert env.history()[-1] == line(5, 5, "complete", "분석 건", "검토 필요 → 검토 완료", "끝", actor="박검토")
    assert env.row()["reviewer"] == "박검토"


def test_false_positive_and_reclassified_do_not_count_as_open(env: Env) -> None:
    env.act("mark_false_positive", at=1, finding_id="D1-01", reason_type="기타", note="")
    env.act("reclassify", at=2, finding_id="D1-02", subject="보증인", reason="")
    env.act("complete_review", at=3, note="")
    assert env.history()[-1]["change"] == "검토 필요 → 검토 완료 (남은 항목: 미확인 탐지 2건)"


def test_reclassify_all_three_fields_in_demo_order(env: Env) -> None:
    env.act("reclassify", at=1, finding_id="D2-01", exposure="부분 마스킹", subject="기타 · 거래 상대방", category="기타 개인정보", reason="사유")
    assert env.history()[-1] == line(
        1,
        1,
        "reclass",
        "D2-01 주소",
        "정보 종류: 주소 → 기타 개인정보, 정보주체: 신청인 → 기타 · 거래 상대방, 노출 상태: 전체 노출 → 부분 마스킹",
        "사유",
    )


def test_reclassify_only_lists_fields_that_change(env: Env) -> None:
    env.act("reclassify", at=1, finding_id="D1-01", category="이름", subject="보증인", exposure=None, reason="")
    assert env.history()[-1]["change"] == "정보주체: 신청인 → 보증인"


def test_reclassify_keeps_fp_type_and_note_like_the_demo(env: Env) -> None:
    env.act("mark_false_positive", at=1, finding_id="D1-01", reason_type="이미 가려진 값", note="n")
    env.act("reclassify", at=2, finding_id="D1-01", category="주소", reason="r")
    saved = env.saved("D1-01")
    assert saved["status"] == "reclassified"
    assert (saved["fp_type"], saved["fp_note"]) == ("이미 가려진 값", "n")


def test_restore_after_reclassify_back_to_ai_values_is_open(env: Env) -> None:
    env.act("reclassify", at=1, finding_id="D1-01", category="주소", reason="")
    env.act("reclassify", at=2, finding_id="D1-01", category="이름", reason="")  # AI 값으로 되돌림(상태는 분류 수정)
    env.act("mark_false_positive", at=3, finding_id="D1-01", reason_type="기타", note="")
    env.act("restore", at=4, finding_id="D1-01", note="")
    assert env.saved("D1-01")["status"] == "open"
    assert env.history()[-1]["change"] == "오탐 → 미확인"


def test_finding_memo_does_not_touch_updated_at(env: Env) -> None:
    env.act("save_finding_memo", at=1, finding_id="D1-03", text="처음 메모")
    assert env.saved("D1-03") == entry(env, "D1-03", memo="처음 메모")  # updated_at None 그대로
    env.act("set_status", at=2, finding_id="D1-03", status="confirmed", reason="")
    env.act("save_finding_memo", at=3, finding_id="D1-03", text="둘째")
    assert env.saved("D1-03")["updated_at"] == iso(2)


def test_save_memo_delete_also_sets_memo_at(env: Env) -> None:
    env.act("save_memo", at=1, text="메모")
    assert (env.row()["memo"], env.row()["memo_at"]) == ("메모", iso(1))
    out = env.act("save_memo", at=2, text="")
    assert (env.row()["memo"], env.row()["memo_at"]) == ("", iso(2))
    assert (out.review["memo"], out.review["memo_at"]) == ("", iso(2))


def test_reopen_keeps_reviewer_and_completion_note(env: Env) -> None:
    env.act("complete_review", at=1, note="완료 메모")
    out = env.act("reopen_review", at=2, reason="다시", actor="박검토")
    row = env.row()
    assert (row["status"], row["reviewer"], row["completion_note"], row["reviewed_at"]) == ("needed", ACTOR, "완료 메모", None)
    assert out.review["reviewer"] == ACTOR
    assert env.history()[-1] == line(2, 2, "reopen", "분석 건", "검토 완료 → 검토 필요", "다시", actor="박검토")


def test_whitespace_only_text_counts_as_saved_like_javascript(env: Env) -> None:
    env.act("save_memo", at=1, text=" ")
    env.act("save_finding_memo", at=2, finding_id="D1-01", text="\n")
    assert [h["change"] for h in env.history()] == ["검토 메모 저장", "항목 메모 저장"]
    assert env.row()["memo"] == " "  # 받은 그대로(앞뒤 공백을 지우지 않음)


def test_one_action_uses_one_time_everywhere(env: Env) -> None:
    env.act("set_status", at=1, finding_id="D1-01", status="confirmed", reason="")
    assert env.saved("D1-01")["updated_at"] == env.history()[-1]["at"] == iso(1)
    env.act("complete_review", at=2, note="")
    assert env.row()["reviewed_at"] == env.history()[-1]["at"] == iso(2)


def test_action_time_never_goes_before_the_last_history_line(env: Env) -> None:
    env.act("save_memo", at=10, text="a")
    env.act("save_memo", at=5, text="b")  # 시계가 뒤로 가도
    assert [h["at"] for h in env.history()] == [iso(10), iso(10)]
    assert env.row()["memo_at"] == iso(10)


def test_new_rows_start_with_version_one_and_history_ids_follow_versions(env: Env) -> None:
    env.act("save_memo", at=1, text="a")
    (method, _, values, expect) = env.store.review_writes[0]
    assert method == "insert_review" and expect is None and values["version"] == 1
    assert set(values) == {"analysis_id", "status", "memo", "memo_at", "reviewer", "reviewed_at", "completion_note", "findings", "items", "history", "version"}
    env.act("save_memo", at=2, text="b")
    (method, _, values, expect) = env.store.review_writes[1]
    assert method == "update_review" and expect == 1 and values["version"] == 2
    assert set(values) == {"memo", "memo_at", "history", "version"}  # 바꾼 열만
    assert [h["id"] for h in env.history()] == ["H1", "H2"]


# --- 바뀐 것이 없는 동작(changed false) -----------------------------------------------------------


@pytest.mark.parametrize(
    "patch",
    [{}, {"category": None, "subject": None, "exposure": None}, {"category": "이름", "subject": "신청인", "exposure": "전체 노출"}],
    ids=["missing", "all_null", "same_as_now"],
)
def test_reclassify_without_change_writes_nothing(env: Env, patch: dict[str, Any]) -> None:
    out = env.act("reclassify", finding_id="D1-01", reason="사유", **patch)
    assert out.changed is False
    assert env.store.review_writes == [] and env.id not in env.store.reviews
    assert out.review["version"] == 0 and out.review["findings"] == {} and len(out.review["history"]) == 2
    env.act("save_memo", at=1, text="m")
    out = env.act("reclassify", at=2, finding_id="D1-01", reason="사유", **patch)
    assert out.changed is False and out.review["version"] == 1 and env.row()["version"] == 1
    assert len(env.store.review_writes) == 1 and len(env.history()) == 1


def test_confirm_many_with_nothing_open_writes_nothing(env: Env) -> None:
    env.act("confirm_many", at=1, finding_ids=["D1-01", "D1-02"])
    writes = len(env.store.review_writes)
    out = env.act("confirm_many", at=2, finding_ids=["D1-02", "D1-01"])
    assert out.changed is False and len(env.store.review_writes) == writes
    assert env.row()["version"] == 1 and len(env.history()) == 1


def test_changed_false_is_allowed_even_when_history_is_full(env: Env) -> None:
    env.store.put_review(env.id, history=[line(i, 0, "memo", "분석 건", "검토 메모 저장") for i in range(1, 1001)], version=1000)
    assert env.act("reclassify", finding_id="D1-01", reason="").changed is False


# --- 409 ----------------------------------------------------------------------------------------

MSG_LOCKED = "검토를 완료한 분석은 바꿀 수 없습니다."
MSG_STATE = "탐지 항목 상태가 바뀌었습니다. 새로 고친 뒤 다시 시도해 주세요."

LOCKED_CASES = [
    ("set_status", {"finding_id": "D1-01", "status": "confirmed", "reason": ""}),
    ("confirm_many", {"finding_ids": ["D1-01"]}),
    ("mark_false_positive", {"finding_id": "D1-01", "reason_type": "기타", "note": ""}),
    ("restore", {"finding_id": "D1-01", "note": ""}),
    ("reclassify", {"finding_id": "D1-01", "category": "주소", "reason": ""}),
    ("save_finding_memo", {"finding_id": "D1-01", "text": "m"}),
    ("save_memo", {"text": "m"}),
]


@pytest.mark.parametrize(("kind", "fields"), LOCKED_CASES, ids=[c[0] for c in LOCKED_CASES])
def test_done_review_is_locked_for_actions_one_to_seven(env: Env, kind: str, fields: dict[str, Any]) -> None:
    env.act("complete_review", note="")
    err = env.error(kind, **fields)
    assert (err.status_code, err.detail) == (409, MSG_LOCKED)
    assert env.row()["version"] == 1


def test_unknown_finding_is_404_before_the_lock(env: Env) -> None:
    env.act("complete_review", note="")
    err = env.error("set_status", finding_id="0:없는 키", status="confirmed", reason="")
    assert (err.status_code, err.detail) == (404, "탐지 항목을 찾을 수 없습니다.")


def test_lock_comes_before_changed_false(env: Env) -> None:
    env.act("complete_review", note="")
    assert env.error("reclassify", finding_id="D1-01", reason="").detail == MSG_LOCKED
    assert env.error("confirm_many", finding_ids=["D1-01"]).detail == MSG_LOCKED


def test_set_status_needs_the_right_previous_state(env: Env) -> None:
    assert env.error("set_status", finding_id="D1-01", status="open", reason="").detail == MSG_STATE  # open → open
    env.act("set_status", finding_id="D1-01", status="confirmed", reason="")
    assert env.error("set_status", finding_id="D1-01", status="confirmed", reason="").detail == MSG_STATE
    env.act("mark_false_positive", finding_id="D1-02", reason_type="기타", note="")
    assert env.error("set_status", finding_id="D1-02", status="confirmed", reason="").detail == MSG_STATE  # 오탐 → 확인 불가
    assert env.error("set_status", finding_id="D1-02", status="open", reason="").detail == MSG_STATE
    env.act("reclassify", finding_id="D1-03", category="주소", reason="")
    assert env.error("set_status", finding_id="D1-03", status="confirmed", reason="").detail == MSG_STATE
    assert env.error("set_status", finding_id="D1-03", status="open", reason="").detail == MSG_STATE
    assert env.error("set_status", finding_id="D1-03", status="confirmed", reason="").status_code == 409


def test_false_positive_twice_and_restore_of_non_fp_are_409(env: Env) -> None:
    assert env.error("restore", finding_id="D1-01", note="").detail == MSG_STATE
    env.act("mark_false_positive", finding_id="D1-01", reason_type="기타", note="")
    assert env.error("mark_false_positive", finding_id="D1-01", reason_type="기타", note="").detail == MSG_STATE
    env.act("restore", finding_id="D1-01", note="")
    assert env.error("restore", finding_id="D1-01", note="").detail == MSG_STATE


def test_complete_twice_and_reopen_while_needed_are_409(env: Env) -> None:
    err = env.error("reopen_review", reason="")  # 행이 없을 때도
    assert (err.status_code, err.detail) == (409, "검토를 완료한 분석만 다시 열 수 있습니다.")
    env.act("complete_review", note="")
    err = env.error("complete_review", note="")
    assert (err.status_code, err.detail) == (409, "이미 검토를 완료했습니다.")
    env.act("reopen_review", reason="")
    assert env.error("reopen_review", reason="").detail == "검토를 완료한 분석만 다시 열 수 있습니다."
    assert env.row()["version"] == 2


def test_history_limit_is_409_and_writes_nothing(env: Env) -> None:
    lines = [line(i, 0, "memo", "분석 건", "검토 메모 저장") for i in range(1, 1000)]
    env.store.put_review(env.id, history=lines, version=999)
    env.act("save_memo", at=1, text="999 다음")  # 999 → 1000줄
    assert len(env.history()) == 1000 and env.history()[-1]["id"] == "H1000"
    err = env.error("save_memo", text="하나 더")
    assert (err.status_code, err.detail) == (409, "검토 이력이 너무 많아 더 저장할 수 없습니다.")
    assert env.row()["version"] == 1000 and env.row()["memo"] == "999 다음"


def test_history_limit_counts_malformed_stored_lines_too(env: Env) -> None:
    env.store.put_review(env.id, history=["모양이 틀린 줄"] * 1000, version=1)
    assert env.error("save_memo", text="x").detail == "검토 이력이 너무 많아 더 저장할 수 없습니다."


def test_state_conflict_comes_before_history_limit(env: Env) -> None:
    env.store.put_review(env.id, history=[line(i, 0, "memo", "분석 건", "x") for i in range(1, 1001)], version=1000, status="done")
    assert env.error("save_memo", text="x").detail == MSG_LOCKED
    assert env.error("complete_review", note="").detail == "이미 검토를 완료했습니다."


# --- 경쟁 --------------------------------------------------------------------------------------


def _other(kind: str, minutes: int, **fields: Any):  # noqa: ANN202 — 훅
    """다른 요청 하나(검토 행을 쓰기 직전에 끼어든다)."""

    def hook(store: FakeStore, analysis_id: str) -> None:
        env = Env(store, analysis_id)
        env.act(kind, at=minutes, actor="다른 사람", **fields)

    return hook


def test_first_inserts_race_and_the_loser_applies_on_top(env: Env) -> None:
    env.store.review_hooks.append(_other("set_status", 1, finding_id="D1-02", status="confirmed", reason=""))
    out = env.act("set_status", at=2, finding_id="D1-01", status="confirmed", reason="")
    assert out.changed and out.review["version"] == 2
    assert [(h["id"], h["actor"], h["target"]) for h in env.history()] == [
        ("H1", "다른 사람", "D1-02 고유식별정보"),
        ("H2", ACTOR, "D1-01 이름"),
    ]
    methods = [w[0] for w in env.store.review_writes]
    assert methods == ["insert_review", "insert_review", "update_review"]  # 다른 요청 → 내 삽입(충돌) → 다시 읽어 갱신
    assert env.saved("D1-01")["status"] == env.saved("D1-02")["status"] == "confirmed"


def test_update_race_rereads_and_keeps_both_actions(env: Env) -> None:
    env.act("save_memo", at=1, text="처음")
    env.store.review_hooks.append(_other("save_finding_memo", 2, finding_id="D1-01", text="다른 메모"))
    env.act("mark_false_positive", at=3, finding_id="D1-01", reason_type="기타", note="내 사유")
    assert [h["kind"] for h in env.history()] == ["memo", "fmemo", "fp"]
    assert [h["id"] for h in env.history()] == ["H1", "H2", "H3"]
    saved = env.saved("D1-01")
    assert (saved["memo"], saved["status"], saved["fp_note"]) == ("다른 메모", "false_positive", "내 사유")


def test_race_that_changes_the_state_turns_into_a_state_conflict(env: Env) -> None:
    env.store.review_hooks.append(_other("set_status", 1, finding_id="D1-01", status="confirmed", reason=""))
    err = env.error("set_status", at=2, finding_id="D1-01", status="confirmed", reason="")
    assert (err.status_code, err.detail) == (409, MSG_STATE)
    assert len(env.history()) == 1 and env.history()[0]["actor"] == "다른 사람"


def test_race_lost_three_times_is_409_and_nothing_of_mine_is_saved(env: Env) -> None:
    for minutes in (1, 2, 3):
        env.store.review_hooks.append(_other("save_memo", minutes, text=f"다른 {minutes}"))
    err = env.error("save_memo", at=4, text="내 메모")
    assert (err.status_code, err.detail) == (409, "다른 요청과 겹쳐 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.")
    assert [h["reason"] for h in env.history()] == ["다른 1", "다른 2", "다른 3"]
    assert env.row()["memo"] == "다른 3" and env.row()["version"] == 3
    mine = [w for w in env.store.review_writes if w[2]["history"][-1]["actor"] == ACTOR]
    assert [w[0] for w in mine] == ["insert_review", "update_review", "update_review"]  # 첫 삽입 충돌 포함 3번


def test_two_losses_then_win(env: Env) -> None:
    env.act("save_memo", at=1, text="a")
    for minutes in (2, 3):
        env.store.review_hooks.append(_other("save_memo", minutes, text=f"다른 {minutes}"))
    out = env.act("save_memo", at=4, text="내 메모")
    assert out.changed and env.row()["memo"] == "내 메모" and env.row()["version"] == 4


def test_store_error_is_raised_for_the_api_to_turn_into_502(env: Env) -> None:
    env.store.fail.add("get_review")
    with pytest.raises(StoreError):
        env.act("save_memo", text="m")
    env.store.fail = {"insert_review"}
    with pytest.raises(StoreError):
        env.act("save_memo", text="m")


def test_row_with_a_broken_version_is_not_written(env: Env) -> None:
    env.store.put_review(env.id, version="3")
    with pytest.raises(StoreError):
        env.act("save_memo", text="m")
    assert env.store.review_writes == []


# --- analyses 행은 그대로 ---------------------------------------------------------------------------


def test_review_actions_never_write_the_analysis_row(env: Env) -> None:
    before = copy.deepcopy(env.store.analyses[env.id])
    docs_before = copy.deepcopy(env.store.documents)
    env.act("set_status", at=1, finding_id="D1-01", status="confirmed", reason="")
    env.act("confirm_many", at=2, finding_ids=["D1-02"])
    env.act("mark_false_positive", at=3, finding_id="D1-03", reason_type="기타", note="")
    env.act("restore", at=4, finding_id="D1-03", note="")
    env.act("reclassify", at=5, finding_id="D2-01", category="이름", reason="")
    env.act("save_finding_memo", at=6, finding_id="D2-01", text="m")
    env.act("save_memo", at=7, text="m")
    env.act("complete_review", at=8, note="")
    env.act("reopen_review", at=9, reason="")
    assert env.store.analyses[env.id] == before  # updated_at 포함
    assert env.store.documents == docs_before
    assert env.store.updates == []
    assert not {"update_analysis", "claim_analysis", "update_document", "delete_analysis"} & set(env.store.calls)


# --- 조회 블록 ---------------------------------------------------------------------------------


def _read(env: Env) -> dict[str, Any] | None:
    row = env.store.get_analysis(env.id)
    assert row is not None
    return read_review(env.store, row, row_view(row))


def test_block_without_a_row_is_the_default_with_two_system_lines(env: Env) -> None:
    analysis = env.store.analyses[env.id]
    block = _read(env)
    assert block == {
        "status": "needed",
        "memo": "",
        "memo_at": None,
        "reviewer": "",
        "reviewed_at": None,
        "completion_note": "",
        "findings": {},
        "items": {},
        "history": [
            {"id": "S1", "at": analysis["created_at"], "actor": "시스템", "kind": "request", "target": "분석 건", "change": "파일 1개 분석 요청", "reason": ""},
            {
                "id": "S2",
                "at": analysis["updated_at"],
                "actor": "시스템",
                "kind": "ai",
                "target": "분석 건",
                "change": "분석 완료 · 탐지 4건 · 위험등급 미평가 · 검토사항 0건",
                "reason": "",
            },
        ],
        "version": 0,
    }


@pytest.mark.parametrize(
    ("risk", "summary", "label"),
    [
        ("상", None, "높음"),
        ("중", None, "보통"),
        ("하", None, "낮음"),
        ("검토 필요", None, "검토 필요"),
        (None, {"risk_level": " 중 "}, "보통"),
        (None, {"risk_level": " 검토 필요 "}, "검토 필요"),
        (None, {"risk_level": "검토필요"}, "미평가"),
        (None, {"risk_level": "x"}, "미평가"),
    ],
)
def test_system_line_risk_label(risk: str | None, summary: dict[str, Any] | None, label: str) -> None:
    env = make_env(custom_result(SMALL, risk=risk, summary=summary))
    block = _read(env)
    assert block is not None
    assert block["history"][1]["change"] == f"분석 완료 · 탐지 4건 · 위험등급 {label} · 검토사항 0건"


def test_system_line_counts_uploaded_document_rows() -> None:
    store = FakeStore()
    env = make_env(store=store)
    store.documents["extra"] = {**next(iter(store.docs_of(env.id))), "id": "extra", "created_at": "9999"}
    block = _read(env)
    assert block is not None and block["history"][0]["change"] == "파일 2개 분석 요청"


def test_block_for_unreviewable_is_none_without_reading_the_row() -> None:
    store = FakeStore()
    analysis_id = store.put(status="running", job_id="j")
    row = store.get_analysis(analysis_id)
    assert row is not None
    assert read_review(store, row, row_view(row)) is None
    assert "get_review" not in store.calls


def test_block_read_failure_is_none_with_a_value_free_warning(env: Env, caplog: pytest.LogCaptureFixture) -> None:
    env.store.fail.add("get_review")
    env.store.fail_message = f"secret-ish {env.id}"
    with caplog.at_level("WARNING", logger="imask"):
        assert _read(env) is None
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "review 를 null 로" in logged and env.id not in logged


def test_block_overlays_only_current_reviewable_ids_with_original_keys(env: Env) -> None:
    env.act("set_status", at=1, finding_id="D1-02", status="confirmed", reason="")
    block = _read(env)
    assert block is not None
    assert list(block["findings"]) == ["0:applicant_rrn"]
    assert set(block["findings"]["0:applicant_rrn"]) == set(FINDING_KEYS)
    assert all(set(h) == set(HISTORY_KEYS) for h in block["history"])


def test_normalization_ignores_bad_values_and_keeps_them_stored(env: Env) -> None:
    key1, key2, key3 = (storage_key(env.fid(n)) for n in ("D1-01", "D1-02", "D1-03"))
    good = line(1, 1, "memo", "분석 건", "검토 메모 저장", "m")
    weird_findings = {
        key1: {
            "status": "bogus",
            "category": "없는 분류",
            "subject": 5,
            "exposure": None,
            "fp_type": "모르는 사유",
            "fp_note": 3,
            "reclass_note": ["x"],
            "memo": {"a": 1},
            "updated_at": 7,
            "extra": "남김",
        },
        key2: "객체가 아님",
        key3: {"status": ["unhashable"], "category": {"x": 1}},
        "9:지금 없는 id": {"status": "confirmed"},
    }
    weird_history = [
        good,
        {**good, "kind": "nope"},
        "문자열",
        {**good, "at": 5},
        {**good, "id": "H2", "extra": "x"},
    ]
    env.store.put_review(env.id, status="weird", memo=5, memo_at=6, findings=weird_findings, history=weird_history, version=2)
    block = _read(env)
    assert block is not None
    assert (block["status"], block["memo"], block["memo_at"]) == ("needed", "", None)
    assert block["findings"] == {"0:applicant_name": entry(env, "D1-01"), "0:applicant_phone": entry(env, "D1-03")}
    assert [h["id"] for h in block["history"]] == ["S1", "S2", "H1", "H2"]
    assert "extra" not in block["history"][-1]

    # 다음 쓰기(검토 메모) 뒤에도 저장 값은 그대로 남는다(맨 위 열은 DB check·not null 이 막으므로 정상 값으로 둔다)
    env.store.reviews[env.id].update(status="needed", memo="", memo_at=None)
    env.act("save_memo", at=2, text="새 메모")
    row = env.row()
    assert row["findings"] == weird_findings
    assert row["history"][:5] == weird_history and len(row["history"]) == 6
    # 건드린 항목은 정규화한 값 + 바뀐 값으로 쓰되 모르는 키는 둔다
    env.act("save_finding_memo", at=3, finding_id="D1-01", text="항목")
    assert env.row()["findings"][key1] == {**entry(env, "D1-01", memo="항목"), "extra": "남김"}
    assert env.row()["findings"][key2] == "객체가 아님" and env.row()["findings"]["9:지금 없는 id"] == {"status": "confirmed"}
    # 정규화한 항목에서 다시 동작(목록 밖 status → open 으로 보고 확인 가능)
    env.act("set_status", at=4, finding_id="D1-03", status="confirmed", reason="")
    assert env.history()[-1]["change"] == "미확인 → 확인함"


# --- 저장 키·이력 target ------------------------------------------------------------------------


def test_storage_key_is_ascii_and_distinct() -> None:
    ids = ["0:a", "0:\ud800", "0:\udfff", "0:\x00", '0:"', "0:\\", "0:한", "0:😀", "0:\\ud800", "0:\\u0000", "0:�"]
    keys = [storage_key(i) for i in ids]
    assert all(k.isascii() for k in keys)
    assert len(set(keys)) == len(ids)
    assert [json.loads(f'"{k}"') for k in keys] == ids  # 되돌리면 원래 id


def test_colliding_storage_keys_never_mix_values() -> None:
    # json.loads 결과에서는 생기지 않지만(인접한 짝 없는 상위·하위 서로게이트), 생겨도 뒤 항목은 저장하지 않는다
    high, low = "\ud83d", "\ude00"
    store = FakeStore()
    analysis_id = store.put(status="done", job_id="j", result=custom_result(SMALL))
    row = store.get_analysis(analysis_id)
    assert row is not None
    view = row_view(row)
    assert view is not None
    view["findings"][0]["id"] = "0:" + chr(0x1F600)
    view["findings"][1]["id"] = "0:" + high + low
    scope = review_scope(row, view)
    assert scope is not None
    first, second = scope.targets[:2]
    assert first.key == second.key and first.writable and not second.writable
    assert second.id not in scope.by_id and len(scope.targets) == 4


def test_safe_target_replaces_and_truncates() -> None:
    assert reviews.safe_target("a\x00b\ud800c") == "a�b�c"
    assert reviews.safe_target("가" * 200) == "가" * 200
    assert reviews.safe_target("가" * 201) == "가" * 199 + "…"


def test_surrogate_and_nul_names_are_replaced_in_history_targets() -> None:
    data = {"name\ud800": "값1", "nul\x00key": "값2", "x" * 300: "값3"}
    env = make_env(custom_result([data]))
    env.act("mark_false_positive", at=1, finding_id="D1-01", reason_type="기타", note="")
    env.act("mark_false_positive", at=2, finding_id="D1-02", reason_type="기타", note="")
    env.act("mark_false_positive", at=3, finding_id="D1-03", reason_type="기타", note="")
    targets = [h["target"] for h in env.history()]
    assert targets[0] == "D1-01 name�" and targets[1] == "D1-02 nul�key"
    assert len(targets[2]) == 200 and targets[2].endswith("…") and targets[2].startswith("D1-03 xxx")
    stored = env.row()["findings"]
    assert all(k.isascii() for k in stored) and len(stored) == 3


# --- 요청 본문 검사 -------------------------------------------------------------------------------


def _bad(body: Any) -> str:
    with pytest.raises(ApiError) as info:
        validate_action(body)
    assert info.value.status_code == 400
    return info.value.detail


def test_every_action_parses_with_exactly_its_fields() -> None:
    bodies = [
        {"type": "set_status", "actor": ACTOR, "finding_id": "0:a", "status": "open", "reason": ""},
        {"type": "confirm_many", "actor": ACTOR, "finding_ids": ["0:a", "0:b"]},
        {"type": "mark_false_positive", "actor": ACTOR, "finding_id": "0:a", "reason_type": FP_REASONS[0], "note": "n"},
        {"type": "restore", "actor": ACTOR, "finding_id": "0:a", "note": ""},
        {"type": "reclassify", "actor": ACTOR, "finding_id": "0:a", "reason": "r"},
        {"type": "reclassify", "actor": ACTOR, "finding_id": "0:a", "reason": "r", "category": "주소", "subject": None, "exposure": "마스킹됨"},
        {"type": "save_finding_memo", "actor": ACTOR, "finding_id": "0:a", "text": ""},
        {"type": "save_memo", "actor": ACTOR, "text": "t"},
        {"type": "complete_review", "actor": ACTOR, "note": ""},
        {"type": "reopen_review", "actor": ACTOR, "reason": ""},
    ]
    for body in bodies:
        action = validate_action(body)
        assert action.type == body["type"] and action.actor == ACTOR
    assert validate_action(bodies[1]).finding_ids == ("0:a", "0:b")
    assert validate_action(bodies[5]).category == "주소" and validate_action(bodies[5]).subject is None


BASE = {"type": "set_status", "actor": ACTOR, "finding_id": "0:a", "status": "confirmed", "reason": ""}
MSG_FORMAT = "요청 형식이 올바르지 않습니다."


@pytest.mark.parametrize(
    "body",
    [
        [],
        "save_memo",
        5,
        None,
        {},
        {**BASE, "type": "unknown"},
        {**BASE, "type": 5},
        {**BASE, "extra": 1},
        {k: v for k, v in BASE.items() if k != "reason"},
        {k: v for k, v in BASE.items() if k != "actor"},
        {**BASE, "status": "false_positive"},
        {**BASE, "status": "reclassified"},
        {"type": "mark_false_positive", "actor": ACTOR, "finding_id": "0:a", "reason_type": "모르는 사유", "note": ""},
        {"type": "reclassify", "actor": ACTOR, "finding_id": "0:a", "reason": "", "category": "모르는 분류"},
        {"type": "reclassify", "actor": ACTOR, "finding_id": "0:a", "reason": "", "subject": "모르는 주체"},
        {"type": "reclassify", "actor": ACTOR, "finding_id": "0:a", "reason": "", "exposure": "모르는 노출"},
        {"type": "reclassify", "actor": ACTOR, "finding_id": "0:a", "reason": "", "category": ""},
        {"type": "reclassify", "actor": ACTOR, "finding_id": "0:a", "reason": "", "category": 1},
        {"type": "set_status", "actor": ACTOR, "finding_id": "0:a", "status": "confirmed", "reason": "", "category": "주소"},
        {"type": "confirm_many", "actor": ACTOR, "finding_ids": []},
        {"type": "confirm_many", "actor": ACTOR, "finding_ids": ["0:a", "0:a"]},
        {"type": "confirm_many", "actor": ACTOR, "finding_ids": ["0:a", 1]},
        {"type": "confirm_many", "actor": ACTOR, "finding_ids": "0:a"},
        {"type": "confirm_many", "actor": ACTOR, "finding_ids": ["0:a"], "finding_id": "0:a"},
        {"type": "save_memo", "actor": ACTOR, "text": "t", "finding_id": "0:a"},
        {"type": "save_memo", "actor": ACTOR, "note": "t"},
    ],
)
def test_shape_errors_are_the_format_message(body: Any) -> None:
    assert _bad(body) == MSG_FORMAT


@pytest.mark.parametrize("field", ["actor", "finding_id", "status", "reason"])
@pytest.mark.parametrize("value", [1, 1.5, True, None, [], ["x"], {}, {"a": "b"}])
def test_wrong_types_are_the_format_message(field: str, value: Any) -> None:
    assert _bad({**BASE, field: value}) == MSG_FORMAT


@pytest.mark.parametrize("value", [1, True, None, [], {}])
def test_wrong_text_types_for_every_text_field(value: Any) -> None:
    assert _bad({"type": "save_memo", "actor": ACTOR, "text": value}) == MSG_FORMAT
    assert _bad({"type": "complete_review", "actor": ACTOR, "note": value}) == MSG_FORMAT
    assert _bad({"type": "mark_false_positive", "actor": ACTOR, "finding_id": "0:a", "reason_type": value, "note": ""}) == MSG_FORMAT


def _memo(text: str, actor: str = ACTOR) -> dict[str, Any]:
    return {"type": "save_memo", "actor": actor, "text": text}


def test_text_length_is_counted_in_code_points() -> None:
    assert validate_action(_memo("가" * 500)).text == "가" * 500
    assert validate_action(_memo("😀" * 500)).text == "😀" * 500  # UTF-16 로는 1000
    assert _bad(_memo("가" * 501)) == "메모·사유는 500자 이하로 적어 주세요."
    assert validate_action(_memo("줄\n바꿈\t탭\r")).text == "줄\n바꿈\t탭\r"
    assert validate_action(_memo("  앞뒤 공백  ")).text == "  앞뒤 공백  "


@pytest.mark.parametrize("text", ["\x00", "a\x00b", "\ud800", "x\udfff", "\udc00\ud800"])
def test_nul_and_surrogates_in_text_are_rejected(text: str) -> None:
    assert _bad(_memo(text)) == "메모·사유에 쓸 수 없는 문자가 있습니다."
    assert _bad({"type": "reopen_review", "actor": ACTOR, "reason": text}) == "메모·사유에 쓸 수 없는 문자가 있습니다."


@pytest.mark.parametrize("actor", ["", " ", "a" * 41, " 김검토", "김검토 ", "김\t검토", "김\x00", "김\x7f", "김\u0085", "김\ud800", "\n"])
def test_bad_actor(actor: str) -> None:
    assert _bad(_memo("m", actor)) == "처리자 이름이 올바르지 않습니다."


@pytest.mark.parametrize("actor", ["김검토", "a", "a" * 40, "Kim Reviewer", "검토 담당 😀"])
def test_good_actor(actor: str) -> None:
    assert validate_action(_memo("m", actor)).actor == actor


def test_400_message_order_format_then_actor_then_text() -> None:
    assert _bad({"type": "save_memo", "actor": "", "text": "가" * 501, "x": 1}) == MSG_FORMAT
    assert _bad(_memo("가" * 501, actor="")) == "처리자 이름이 올바르지 않습니다."
    assert _bad(_memo("\x00" + "가" * 501)) == "메모·사유에 쓸 수 없는 문자가 있습니다."


def test_finding_id_accepts_any_string() -> None:
    for fid in ["", "\ud800", "\x00", "가" * 5000, '"\\']:
        assert validate_action({**BASE, "finding_id": fid}).finding_id == fid


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"not json",
        b'{"type": "save_memo"',
        b"\xff\xfe{}",
        '{"type":"save_memo","actor":"김","text":"메모"}'.encode("utf-16"),
        b'\xef\xbb\xbf{"type":"save_memo","actor":"a","text":"m"}',
        b'{"type":"save_memo","type":"save_memo","actor":"a","text":"m"}',
        b'{"type":"save_memo","actor":"a","text":"m","text":"m"}',
        b'{"type":"save_memo","actor":"a","text":NaN}',
        b'{"type":"save_memo","actor":"a","text":Infinity}',
        b"[" * 30000 + b"]" * 30000,
        b'{"a":' * 10000 + b"1" + b"}" * 10000,
        b"[" * 65536,
        b'{"type":"save_memo","actor":"a","text":"m","n":' + b"1" * 5000 + b"}",
        b'"\\ud800"',
    ],
    ids=["empty", "not_json", "truncated", "not_utf8", "utf16", "bom", "dup_type", "dup_text", "nan", "inf", "deep_list", "deep_object", "unclosed_deep", "huge_int", "top_string"],
)
def test_raw_body_errors_are_400(raw: bytes) -> None:
    with pytest.raises(ApiError) as info:
        parse_action(raw)
    assert (info.value.status_code, info.value.detail) == (400, MSG_FORMAT)


def test_raw_body_with_escaped_pairs_and_surrogates() -> None:
    action = parse_action(b'{"type":"save_memo","actor":"a","text":"\\ud83d\\ude00"}')
    assert action.text == "😀"
    action = parse_action(b'{"type":"save_finding_memo","actor":"a","finding_id":"0:\\ud800\\u0000","text":""}')
    assert action.finding_id == "0:\ud800\x00"
    with pytest.raises(ApiError) as info:
        parse_action(b'{"type":"save_memo","actor":"a","text":"\\ud800"}')
    assert info.value.detail == "메모·사유에 쓸 수 없는 문자가 있습니다."


# --- 목록 동기화(src/display/rules.ts 를 읽기만) ------------------------------------------------------


def _ts_block(name: str) -> str:
    text = RULES_TS.read_text(encoding="utf-8")
    match = re.search(rf"export const {name} = (\[.*?\]|\{{.*?\n\}}) (?:as const|satisfies)", text, re.DOTALL)
    assert match, f"rules.ts 에 {name} 가 없다"
    return match.group(1)


def _ts_labels(name: str) -> dict[str, str]:
    return dict(re.findall(r"^\s*(\w+): \{ label: '([^']*)'", _ts_block(name), re.MULTILINE))


def test_fp_reasons_match_screen_rules() -> None:
    assert tuple(re.findall(r"'([^']*)'", _ts_block("FP_REASONS"))) == FP_REASONS


def test_finding_status_labels_match_screen_rules() -> None:
    assert _ts_labels("FSTATUS") == FSTATUS


def test_review_status_labels_match_screen_rules() -> None:
    labels = _ts_labels("RSTATUS")
    assert {key: labels[key] for key in RSTATUS} == RSTATUS


def test_history_kinds_match_screen_rules() -> None:
    keys = tuple(re.findall(r"^\s*(\w+): '", _ts_block("HKIND"), re.MULTILINE))
    assert keys == HKIND
    used = {"request", "ai", "confirm", "unconfirm", "fp", "restore", "reclass", "fmemo", "memo", "complete", "reopen"}
    assert used <= set(HKIND)


def test_written_kinds_are_all_known(env: Env) -> None:
    env.act("set_status", at=1, finding_id="D1-01", status="confirmed", reason="")
    env.act("set_status", at=2, finding_id="D1-01", status="open", reason="")
    env.act("mark_false_positive", at=3, finding_id="D1-01", reason_type="기타", note="")
    env.act("restore", at=4, finding_id="D1-01", note="")
    env.act("reclassify", at=5, finding_id="D1-01", category="주소", reason="")
    env.act("save_finding_memo", at=6, finding_id="D1-01", text="")
    env.act("save_memo", at=7, text="")
    env.act("complete_review", at=8, note="")
    env.act("reopen_review", at=9, reason="")
    assert all(h["kind"] in HKIND for h in env.history())
    block = _read(env)
    assert block is not None and len(block["history"]) == 11  # 모두 모양이 맞아 응답에 보인다
