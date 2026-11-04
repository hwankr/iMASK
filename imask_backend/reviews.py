# ==========================================================================
#  검토 동작 저장 — 실제 분석의 탐지 항목 검토·검토사항 해결을 analysis_reviews(분석 1건당 1행)에 저장한다 (FastAPI 와 무관)
#  계약: .orchestration/review-actions/BRIEF.md §5 · review-items BRIEF §5.4~5.6. 동작·이력 문구의 기준은 데모 코어
#  src/services/demo/core.ts.
#
#  - 검토할 수 있는 분석(review_scope): status done + result 객체 + 화면용 결과(build_view)의 유효한 서류 1개 이상
#    (index 는 bool 아닌 정수 ≥ 0, page_start·page_end 는 bool 아닌 정수 ≥ 1). 화면 isDetailReady·readDocSources 와 같다.
#    검토할 수 있는 탐지 항목 = 화면에 보이는 항목(document_index 가 유효한 서류에 속함 — toLiveFindings 와 같은 순서).
#    표시 번호 D{서류 순번}-{서류 안 순번 두 자리}, 표시 이름 label → field → '이름 없는 항목'(화면처럼 JavaScript trim 기준),
#    AI 값은 목록(fields.CATS·SUBJECTS·EXPOSURES) 밖이면 '기타 개인정보'·'기타'·'전체 노출'.
#    서류 순번·표시 이름은 검토사항(imask_backend.items — doc_numbers·finding_name)과 한 기준이다.
#    검토사항 대상(ItemTarget) = view["items"](items.build_items) 중 종류가 ITEM_TYPES(화면 RTYPE) 키이고 id·number 가 문자열이며
#    document_index 가 보이는 서류인 것(목록 순서). 같은 id·저장 키가 또 나오면 뒤의 것은 저장하지 않는다(동작 404, 미해결로 셈).
#  - 동작 12종: set_status·confirm_many·mark_false_positive·restore·reclassify·save_finding_memo·save_memo·
#    resolve_item·reopen_item(잠김 대상 9종), complete_review·reopen_review, log_export(내보내기 기록 — live-report BRIEF §5.6, 아래).
#  - resolve_item(item_id·note)·reopen_item(item_id) — 검토사항 해결·다시 열기(review-items BRIEF §5.6): item_id 는 문자열,
#    note 는 다른 글 필드와 같은 규칙(빈 글도 받음). 오류 순서: 413 → 400 형식 → 400 처리자 → 400 글 → 404 분석 →
#    409 검토할 수 없음 → 404 검토사항(지금 결과에 없음·저장할 수 없음) → 409 잠김 → 409 검토사항 상태(이미 해결에 resolve·
#    미해결에 reopen) → 409 이력 1000줄 → 409 경쟁 패배. 그 사이 분석이 지워졌으면 404(아래 '삭제 경합' — 12종 공통).
#    쓰기는 다른 동작과 같은 version 조건부 쓰기 하나(items 열 + 이력 한 줄 + version), 늘 changed true.
#    항목 값은 지금 값(없으면 미해결 기본값)에서 시작해
#    resolve 는 {resolved true, note, resolved_at 동작 시각, resolved_by 처리자}, reopen 은 resolved false 만(나머지 그대로).
#    이력: resolve → kind 'resolve'·target '{R-nn} {종류 라벨}'·change '미해결 → 해결'·reason note,
#    reopen → kind 'reopenItem'·같은 target·change '해결 → 미해결'·reason ''.
#    검토 완료 이력의 남은 항목 = '미확인 탐지 n건'·'미해결 검토사항 m건' 중 0 이 아닌 것(데모 completeReview 와 같다).
#  - 요청 본문(parse_action): UTF-8 JSON 객체 하나(같은 키 두 번·NaN·깊은 중첩 → 400), 종류(type)별로 정확히 정해진 필드만,
#    엄격한 타입, 목록 값. 400 문구 순서: 형식 → 처리자 이름 → 메모·사유(쓸 수 없는 문자 → 500자). 본문 크기(413)는 api 가 본다.
#  - 동작 하나 = 검토 행 하나를 조건부로 쓴다(apply_review_action): 분석 읽기 → 검토 행 읽기(없으면 기본값 version 0)
#    → 검사·계산 → 행이 없으면 insert … on conflict do nothing(version 1), 있으면 update … where version = 읽은 값.
#    바뀐 행이 없으면 경쟁에 진 것 — 검토 행을 다시 읽어 처음부터 다시 계산한다(모두 MAX_ATTEMPTS 번, 그래도 지면 409).
#    분석 행과 결과는 검토 동작으로 바뀌지 않으므로 다시 읽지 않는다. analyses 행은 절대 쓰지 않는다(updated_at 트리거).
#    Upstage 는 부르지 않는다. 오류 순서: 404 분석 → 409 검토할 수 없음 → 404 항목 → 409 잠김 → 409 상태 불일치
#    → (바뀐 것 없음 → 200 changed false) → 409 이력 1000줄 → 409 경쟁 패배. 저장소 오류는 StoreError(api 가 502).
#    version 조건부 쓰기(_write_review)는 다시 분석의 이력 한 줄(append_history_line — 다른 열은 그대로)도 같이 쓴다.
#    이 경로의 로그·StoreError 문구에는 값(메모·분석 id·항목 id·바깥 오류 원문)을 넣지 않는다 — 검토 행 저장소 오류는
#    SupabaseStore._review_error 가 동작 이름 + 예외 종류 + 영숫자 오류 코드만 남긴다(BRIEF §5.3). 분석 행 읽기(처음 읽기
#    _load_quiet·지워졌는지 다시 읽기 _analysis_gone)도 get_analysis(…, quiet=True) 로 같은 수준(live-report V-T1-1 M1 —
#    12종 모두. 응답·오류 순서는 그대로, 로그만 조용해짐). 검토사항 경로도 처리 내용·처리자·항목 id·규칙 이름을 남기지 않는다.
#  - 삭제 경합(그 사이 분석이 지워짐 → 404 '분석 건을 찾을 수 없습니다.', 12종 모두 같은 규칙 — shared-analyses BRIEF §5.6 ·
#    review-items BRIEF-F §5F F1). 분석이 지워지면 검토 행도 cascade 로 사라지므로 다음 셋에서 분석 행을 값 없이 다시
#    읽어(_analysis_gone — get_analysis quiet) 정말 없으면 404, 있거나 다시 읽기가 저장소 오류면 원래 결과를 낸다.
#    ① 검토 행 쓰기가 저장소 오류(insert 의 FK 위반 등) → 원래 502. ② MAX_ATTEMPTS 번 모두 경쟁에 짐 → 원래 409 경쟁.
#    ③ 쓰지 않고 끝나는 시도 — _compute 의 상태 409(StateConflict: 잠김·탐지 항목 상태·이미 완료·완료 전 다시 열기·
#    검토사항 상태) 또는 바뀐 것 없음(200 changed false) — 인데 그 시도에 읽은 검토 행이 None 일 때 → 원래 409·200.
#    ③ 은 처음 읽기(분석 읽기 뒤·첫 검토 행 읽기 전에 지워짐)와 경쟁 패배 뒤 다시 읽기(UPDATE 0행 → 다시 읽은 행 None)
#    둘 다에 걸린다. 검토 행이 있던 시도의 409·200 은 다시 읽지 않고 바로 낸다(추가 분석 읽기는 행이 None 인 시도에서만).
#    검토 행이 None 이면 상태는 기본값(needed·미확인·미해결)이라 그 시도에서 실제로 ③ 에 걸리는 것은 reopen_review(완료 전)·
#    set_status(open)·restore·reopen_item(상태 409)과 바뀐 것 없는 reclassify 다(나머지는 쓰기로 가서 ① 로 404).
#  - log_export(내보내기 기록): 본문은 정확히 type·actor·format('csv'|'json')·size(bool 아닌 정수 1~104,857,600)·
#    state('handed'|'saved')·file_name(꼴·확장자가 format 과 맞음 — 규칙은 imask_backend/exports.py). 모양이 틀리면
#    처리자 이름보다 먼저 400. 분석을 읽은 뒤 409 검토할 수 없음 다음에, file_name 이 이 분석의 기대 이름
#    (exports.expected_file_name — 만든 날짜(서울)·id 앞 4자, 만든 날짜를 읽지 못하면 없음)과 다르면 400 형식.
#    잠김과 무관(LOCKED_ACTIONS 밖 — 검토 완료 뒤에도 기록), 다른 열은 그대로 두고 이력 한 줄 + version 만 같은
#    version 조건부 쓰기로 쓴다(행이 없으면 기본값 행 + version 1). 이력 줄 kind 'export', target = file_name,
#    change '<CSV|JSON> · <크기(fmtSize 와 같은 글자)> · <다운로드 요청|저장 완료>', reason '민감한 값 마스킹'. 늘 changed true.
#    오류 순서: 413 → 400 모양 → 400 처리자 → 404 분석 → 409 검토할 수 없음 → 400 이 분석의 이름 아님 → 409 이력 1000줄
#    → 409 경쟁 패배(그 사이 지워졌으면 404).
#  - 저장 형식: findings·items jsonb 의 키 = 계약 id 의 storage_key(json.dumps(id, ensure_ascii=True)[1:-1] — ASCII 만).
#    항목 값은 처음 건드릴 때 AI 값으로 시작하고, 건드린 항목은 정규화한 값 + 바뀐 값으로 쓴다(그 항목의 모르는 키는 둔다).
#    items 값은 {resolved, note, resolved_at, resolved_by} — 조회 때 resolved 는 정확히 true 일 때만 true, note·resolved_by 는
#    문자열 아니면 '', resolved_at 은 문자열 아니면 null 로 정규화한다.
#    지금 결과에 없는 id·모르는 모양의 값·모양이 틀린 이력 줄은 지우지 않고 그대로 두되 응답에서는 무시한다.
#    이력 target 은 AI 값(이름)에서 오므로 짝 없는 서로게이트·NUL 을 U+FFFD 로 바꾸고 200자에서 자른다.
#    한 동작의 시각(항목 updated_at·memo_at·reviewed_at·이력 at)은 같은 값 = 지금(UTC), 단 마지막 이력보다 앞서지 않게.
#  - 조회용 review 블록(review_block·read_review): 검토할 수 있는 분석에만(그 밖은 null — 검토 행을 읽지도 않음).
#    검토 행을 읽지 못하면 값 없는 경고 후 null(상세 화면이 깨지지 않게). 행이 없으면 기본값(needed·빈 값·version 0).
#    S2 문구 '분석 완료 · 탐지 {보이는 탐지 수}건 · 위험등급 {등급} · 검토사항 {검토사항 대상 수 — 저장할 수 없는 것도}건'.
#    history = [S1(분석 요청)] + [저장된 줄 중 kind 'retry'(다시 분석 요청, 저장 순서)] + [S2(최초 AI 결과)] + [그 밖 저장된 줄].
#    S1·S2 는 조회할 때 만든다. 다시 분석은 failed 일 때만(= 완료 전), 검토 동작은 완료 뒤에만 생기므로 이 순서가 시간 순서다.
#    내보내기 기록(kind 'export')도 '그 밖 저장된 줄'에 저장 순서로 들어간다.
#  - 저장 키 충돌(서로 다른 id 가 같은 저장 키): json.loads 로 만든 문자열에서는 생기지 않는다(인접한 짝 없는 상위·하위
#    서로게이트가 나올 수 없음). 그래도 생기면 뒤의 항목은 저장하지 않고(동작 404) 기본값으로만 센다 — 값이 섞이지 않게.
# ==========================================================================

from __future__ import annotations

import json
import logging
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .analyses import DONE, MSG_NOT_FOUND, ApiError, _parse_time, _uuid_or_404, analysis_out
from .exports import EXPORT_KIND, EXPORT_REASON, expected_file_name, export_change, export_fields_ok
from .fields import CATS, EXPOSURES, SUBJECTS
from .findings import build_view
from .items import ITEM_TYPES, JS_SPACE, UNNAMED_FINDING, doc_numbers, finding_name
from .store import Store, StoreError

logger = logging.getLogger("imask.reviews")

# --- src/display/rules.ts 와 같은 값(순서까지 — tests/test_reviews.py 가 rules.ts 를 읽어 확인한다) ---------------
FP_REASONS = ("개인정보가 아닌 번호·문구", "다른 정보 종류를 잘못 인식", "이미 가려진 값", "기타")
# 탐지 항목 확인 상태(FSTATUS) 라벨
FSTATUS = {"open": "미확인", "confirmed": "확인함", "false_positive": "오탐", "reclassified": "분류 수정"}
# 검토 상태(RSTATUS 중 저장하는 두 값) 라벨
RSTATUS = {"needed": "검토 필요", "done": "검토 완료"}
# 이력 구분(HKIND) 키
HKIND = (
    "ai",
    "request",
    "retry",
    "confirm",
    "unconfirm",
    "fp",
    "restore",
    "reclass",
    "fmemo",
    "memo",
    "resolve",
    "reopenItem",
    "link",
    "complete",
    "reopen",
    "export",
)

# --- 한도 ------------------------------------------------------------------------------
MAX_TEXT = 500  # 메모·사유(코드 포인트) — 화면 NOTE_MAX(UTF-16 단위)보다 엄격하지 않다
MAX_ACTOR = 40
MAX_HISTORY = 1000  # 저장된 이력이 이만큼이면 더 쓰지 않는다
MAX_ATTEMPTS = 3  # 처음 + 다시 2번
MAX_BODY_BYTES = 65_536
MAX_TARGET = 200  # 이력 target(코드 포인트) — 넘으면 앞 199자 + '…'

# --- 사용자에게 보이는 문장 -----------------------------------------------------------------
MSG_BAD_REQUEST = "요청 형식이 올바르지 않습니다."
MSG_TEXT_TOO_LONG = "메모·사유는 500자 이하로 적어 주세요."
MSG_TEXT_BAD_CHAR = "메모·사유에 쓸 수 없는 문자가 있습니다."
MSG_BAD_ACTOR = "처리자 이름이 올바르지 않습니다."
MSG_BODY_TOO_LARGE = "요청 본문이 너무 큽니다."
MSG_FINDING_NOT_FOUND = "탐지 항목을 찾을 수 없습니다."
MSG_NOT_REVIEWABLE = "검토할 수 없는 분석입니다."
MSG_LOCKED = "검토를 완료한 분석은 바꿀 수 없습니다."
MSG_STATE_CHANGED = "탐지 항목 상태가 바뀌었습니다. 새로 고친 뒤 다시 시도해 주세요."
MSG_ALREADY_DONE = "이미 검토를 완료했습니다."
MSG_NOT_DONE = "검토를 완료한 분석만 다시 열 수 있습니다."
MSG_HISTORY_FULL = "검토 이력이 너무 많아 더 저장할 수 없습니다."
MSG_CONFLICT = "다른 요청과 겹쳐 저장하지 못했습니다. 잠시 후 다시 시도해 주세요."
MSG_ITEM_NOT_FOUND = "검토사항을 찾을 수 없습니다."
MSG_ITEM_STATE_CHANGED = "검토사항 상태가 바뀌었습니다. 새로 고친 뒤 다시 시도해 주세요."

# --- 표시 값 ---------------------------------------------------------------------------
AI_CATEGORY_FALLBACK = "기타 개인정보"
AI_SUBJECT_FALLBACK = "기타"
AI_EXPOSURE_FALLBACK = "전체 노출"
SYSTEM_ACTOR = "시스템"
ANALYSIS_TARGET = "분석 건"
RISK_LABELS = {"상": "높음", "중": "보통", "하": "낮음", "검토 필요": "검토 필요"}  # 화면 riskFromLevel + ANALYSIS_RISK 라벨
UNRATED_LABEL = "미평가"
REPLACEMENT = "�"
ELLIPSIS = "…"

# JavaScript String.prototype.trim 이 지우는 글자(WhiteSpace·LineTerminator) — items.JS_SPACE 한 곳(화면과 같은 기준)
_JS_SPACE = JS_SPACE

# --- 요청 모양 -------------------------------------------------------------------------
# type → 종류별 필수 필드(공통 type·actor 는 따로). 글 필드(reason·note·text)는 동작마다 하나 이하
ACTION_FIELDS: dict[str, tuple[str, ...]] = {
    "set_status": ("finding_id", "status", "reason"),
    "confirm_many": ("finding_ids",),
    "mark_false_positive": ("finding_id", "reason_type", "note"),
    "restore": ("finding_id", "note"),
    "reclassify": ("finding_id", "reason"),
    "save_finding_memo": ("finding_id", "text"),
    "save_memo": ("text",),
    "complete_review": ("note",),
    "reopen_review": ("reason",),
    "log_export": ("format", "size", "state", "file_name"),  # 내보내기 기록(live-report BRIEF §5.6)
    "resolve_item": ("item_id", "note"),  # 검토사항 해결(review-items BRIEF §5.6)
    "reopen_item": ("item_id",),  # 검토사항 다시 열기
}
OPTIONAL_FIELDS: dict[str, tuple[str, ...]] = {"reclassify": ("category", "subject", "exposure")}
TEXT_FIELDS = ("reason", "note", "text")
# 검토사항 동작(item_id 로 result.items 의 검토사항을 가리킴)
ITEM_ACTIONS = ("resolve_item", "reopen_item")
SET_STATUSES = ("open", "confirmed")
# 잠김(검토 완료) 동안 거절하는 동작(BRIEF §5.5 의 1~7 + 검토사항 두 동작). log_export 는 넣지 않는다(검토 완료 뒤에도 내보내기를 기록)
LOCKED_ACTIONS = frozenset(
    {
        "set_status",
        "confirm_many",
        "mark_false_positive",
        "restore",
        "reclassify",
        "save_finding_memo",
        "save_memo",
        "resolve_item",
        "reopen_item",
    }
)

def review_defaults() -> dict[str, Any]:
    """새 검토 행의 값(version 제외) — 마이그레이션의 default 와 같다. 부를 때마다 새 dict·list."""
    return {
        "status": "needed",
        "memo": "",
        "memo_at": None,
        "reviewer": "",
        "reviewed_at": None,
        "completion_note": "",
        "findings": {},
        "items": {},
        "history": [],
    }


FINDING_KEYS = ("status", "category", "subject", "exposure", "fp_type", "fp_note", "reclass_note", "memo", "updated_at")
HISTORY_KEYS = ("id", "at", "actor", "kind", "target", "change", "reason")


@dataclass(frozen=True)
class ReviewAction:
    """검사를 통과한 요청 하나. text 는 그 동작의 글 필드(reason·note·text) 값(없는 동작은 '')."""

    type: str
    actor: str
    finding_id: str | None = None
    finding_ids: tuple[str, ...] = ()
    status: str | None = None
    reason_type: str | None = None
    category: str | None = None
    subject: str | None = None
    exposure: str | None = None
    text: str = ""
    # log_export 만(본문 format·size·state·file_name)
    export_format: str | None = None
    export_size: int | None = None
    export_state: str | None = None
    file_name: str | None = None
    # resolve_item·reopen_item 만(검토사항 계약 id)
    item_id: str | None = None


@dataclass(frozen=True)
class Target:
    """검토할 수 있는 탐지 항목 하나(화면에 보이는 항목)."""

    id: str  # 계약 id(원래 문자열)
    key: str  # 저장 키(storage_key)
    num: str  # 표시 번호 D1-01
    label: str  # 표시 이름
    category: str  # AI 값(목록 안으로 정규화)
    subject: str
    exposure: str
    writable: bool = True  # 저장 키가 앞 항목과 겹치면 False(저장하지 않음)


@dataclass(frozen=True)
class ItemTarget:
    """검토할 수 있는 검토사항 하나(result.items 중 종류·id·번호·서류가 맞는 것)."""

    id: str  # 계약 id(원래 문자열)
    key: str  # 저장 키(storage_key)
    num: str  # 표시 번호 R-01
    label: str  # 종류 라벨(ITEM_TYPES — 화면 RTYPE)
    writable: bool = True  # 같은 id 가 또 나왔거나 저장 키가 앞 항목과 겹치면 False(저장하지 않음 — 동작 404, 미해결로 셈)


@dataclass(frozen=True)
class ReviewScope:
    targets: tuple[Target, ...]
    by_id: Mapping[str, Target]  # 계약 id → 처음 나온 항목
    risk_label: str  # S2 의 위험등급(높음·보통·낮음·검토 필요·미평가)
    items: tuple[ItemTarget, ...] = ()  # 검토사항(저장할 수 없는 것도 — S2 개수·남은 항목 수에 센다)
    item_by_id: Mapping[str, ItemTarget] = field(default_factory=dict)  # 계약 id → 저장할 수 있는 검토사항


@dataclass(frozen=True)
class ActionOutcome:
    row: dict[str, Any]  # 분석 행(읽은 그대로)
    view: dict[str, Any]  # build_view 결과(한 번만 계산)
    review: dict[str, Any]  # 응답 review 블록(방금 쓴 값 또는 지금 값)
    changed: bool


# --- 작은 도우미 -------------------------------------------------------------------------


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _pick(values: Sequence[str] | Mapping[str, Any], value: Any, fallback: Any) -> Any:
    """목록 안의 문자열이면 그대로, 아니면 대체값(해시할 수 없는 값에도 예외 없음)."""
    return value if isinstance(value, str) and value in values else fallback


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _time_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def js_trim(text: str) -> str:
    """JavaScript trim 과 같은 앞뒤 공백 지우기(화면 toLiveFindings·riskFromLevel 과 같은 기준 — items.js_trim 과 같은 집합)."""
    return text.strip(_JS_SPACE)


def storage_key(finding_id: str) -> str:
    """계약 id → findings jsonb 의 키(ASCII 만 — NUL·서로게이트도 escape 로)."""
    return json.dumps(finding_id, ensure_ascii=True)[1:-1]


def _is_surrogate(char: str) -> bool:
    return "\ud800" <= char <= "\udfff"


def safe_line_text(text: str, limit: int) -> str:
    """이력 글(바깥에서 온 값): 서로게이트·NUL → U+FFFD, limit 코드 포인트를 넘으면 앞 limit-1 자 + '…'."""
    cleaned = "".join(REPLACEMENT if char == "\x00" or _is_surrogate(char) else char for char in text)
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1] + ELLIPSIS


def safe_target(text: str) -> str:
    """이력 target: 서로게이트·NUL → U+FFFD, MAX_TARGET 코드 포인트를 넘으면 앞 199자 + '…'."""
    return safe_line_text(text, MAX_TARGET)


# --- 요청 본문 -----------------------------------------------------------------------------


class _DuplicateKey(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise _DuplicateKey(key)
        out[key] = value
    return out


def _no_constant(name: str) -> Any:
    raise ValueError(name)  # NaN·Infinity 는 JSON 이 아니다


def _bad(detail: str = MSG_BAD_REQUEST) -> ApiError:
    return ApiError(400, detail)


def parse_json(raw: bytes) -> Any:
    """본문 바이트 → 값. UTF-8 아님·JSON 아님·같은 키 두 번·NaN·깊은 중첩(RecursionError)·큰 정수 → 400."""
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object, parse_constant=_no_constant)
    except (ValueError, RecursionError):  # UnicodeDecodeError·JSONDecodeError·_DuplicateKey 는 ValueError
        raise _bad() from None


def _actor_ok(actor: str) -> bool:
    return (
        1 <= len(actor) <= MAX_ACTOR
        and actor == actor.strip()
        and not any(unicodedata.category(char) in ("Cc", "Cs") for char in actor)
    )


def _text_problem(text: str) -> str | None:
    if any(char == "\x00" or _is_surrogate(char) for char in text):
        return MSG_TEXT_BAD_CHAR
    if len(text) > MAX_TEXT:
        return MSG_TEXT_TOO_LONG
    return None


def _optional_choice(body: Mapping[str, Any], name: str, values: Sequence[str]) -> str | None:
    """reclassify 의 선택 필드: 빠졌거나 null 이면 None, 있으면 목록 값(아니면 400)."""
    value = body.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or value not in values:
        raise _bad()
    return value


def validate_action(body: Any) -> ReviewAction:
    """파싱한 본문 → ReviewAction. 틀리면 ApiError(400, 정해진 문구)."""
    if not isinstance(body, dict):
        raise _bad()
    kind = body.get("type")
    if not isinstance(kind, str) or kind not in ACTION_FIELDS:
        raise _bad()
    required = {"type", "actor", *ACTION_FIELDS[kind]}
    allowed = required | set(OPTIONAL_FIELDS.get(kind, ()))
    keys = set(body)
    if not required <= keys or not keys <= allowed:
        raise _bad()

    actor = body["actor"]
    if not isinstance(actor, str):
        raise _bad()
    values: dict[str, Any] = {"type": kind, "actor": actor}
    if "finding_id" in required:
        if not isinstance(body["finding_id"], str):
            raise _bad()
        values["finding_id"] = body["finding_id"]
    if "item_id" in required:
        if not isinstance(body["item_id"], str):
            raise _bad()
        values["item_id"] = body["item_id"]
    if "finding_ids" in required:
        ids = body["finding_ids"]
        if not isinstance(ids, list) or not ids or not all(isinstance(i, str) for i in ids) or len(set(ids)) != len(ids):
            raise _bad()
        values["finding_ids"] = tuple(ids)
    if "status" in required:
        if not isinstance(body["status"], str) or body["status"] not in SET_STATUSES:
            raise _bad()
        values["status"] = body["status"]
    if "reason_type" in required:
        if not isinstance(body["reason_type"], str) or body["reason_type"] not in FP_REASONS:
            raise _bad()
        values["reason_type"] = body["reason_type"]
    if kind == "reclassify":
        values["category"] = _optional_choice(body, "category", CATS)
        values["subject"] = _optional_choice(body, "subject", SUBJECTS)
        values["exposure"] = _optional_choice(body, "exposure", EXPOSURES)
    if kind == "log_export":
        if not export_fields_ok(body["format"], body["size"], body["state"], body["file_name"]):
            raise _bad()
        values.update(
            export_format=body["format"], export_size=body["size"], export_state=body["state"], file_name=body["file_name"]
        )
    text_field = next((name for name in TEXT_FIELDS if name in required), None)
    if text_field is not None:
        if not isinstance(body[text_field], str):
            raise _bad()
        values["text"] = body[text_field]

    if not _actor_ok(actor):
        raise _bad(MSG_BAD_ACTOR)
    if text_field is not None:
        problem = _text_problem(values["text"])
        if problem is not None:
            raise _bad(problem)
    return ReviewAction(**values)


def parse_action(raw: bytes) -> ReviewAction:
    """본문 바이트(이미 MAX_BODY_BYTES 이하) → ReviewAction. 틀리면 ApiError(400)."""
    return validate_action(parse_json(raw))


# --- 검토할 수 있는 분석·항목 --------------------------------------------------------------------


def row_view(row: Mapping[str, Any]) -> dict[str, Any] | None:
    """분석 행의 화면용 결과(build_view). result 가 객체가 아니면 None."""
    result = row.get("result")
    return build_view(result) if isinstance(result, Mapping) else None


def _risk_label(row: Mapping[str, Any], view: Mapping[str, Any]) -> str:
    """S2 의 위험등급 — overall.level(비면 summary.risk_level), 화면 riskFromLevel 과 같다."""
    overall = view.get("overall")
    level = overall.get("level") if isinstance(overall, Mapping) else None
    if not (isinstance(level, str) and js_trim(level)):
        result = row.get("result")
        summary = result.get("summary") if isinstance(result, Mapping) else None
        level = summary.get("risk_level") if isinstance(summary, Mapping) else None
    level = js_trim(level) if isinstance(level, str) else ""
    return RISK_LABELS.get(level, UNRATED_LABEL)


def _doc_numbers(documents: Any) -> dict[int, int]:
    """유효한 서류의 index → 서류 순번(1부터, index 순, 같은 index 는 처음 것만) — items.doc_numbers(검토사항과 한 기준)."""
    return doc_numbers(documents)


def _item_targets(items: Any, numbers: Mapping[int, int]) -> tuple[tuple[ItemTarget, ...], dict[str, ItemTarget]]:
    """view["items"] → 검토사항 대상(목록 순서)과 계약 id → 저장할 수 있는 대상.

    종류가 ITEM_TYPES 밖이거나 id·number 가 문자열이 아니거나 document_index 가 보이는 서류가 아니면 대상이 아니다.
    같은 id 가 또 나오거나 저장 키가 앞 대상과 겹치면 뒤의 것은 저장하지 않는다(writable False — 미해결로 센다).
    """
    if not isinstance(items, list):
        return (), {}
    targets: list[ItemTarget] = []
    by_id: dict[str, ItemTarget] = {}
    keys: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping):
            continue
        kind, item_id, number, index = item.get("type"), item.get("id"), item.get("number"), item.get("document_index")
        if not (isinstance(kind, str) and kind in ITEM_TYPES and isinstance(item_id, str) and isinstance(number, str)):
            continue
        if not _is_int(index) or index not in numbers:
            continue
        key = storage_key(item_id)
        target = ItemTarget(
            id=item_id, key=key, num=number, label=ITEM_TYPES[kind], writable=item_id not in by_id and key not in keys
        )
        if target.writable:
            by_id[item_id] = target
            keys.add(key)
        elif item_id not in by_id:
            logger.warning("저장 키가 겹치는 검토사항이 있어 뒤의 항목은 저장하지 않습니다")
        targets.append(target)
    return tuple(targets), by_id


def review_scope(row: Mapping[str, Any], view: Mapping[str, Any] | None) -> ReviewScope | None:
    """검토할 수 있는 분석이면 그 항목들(화면 순서·번호), 아니면 None."""
    if row.get("status") != DONE or view is None:
        return None
    numbers = _doc_numbers(view.get("documents"))
    findings = view.get("findings")
    if not numbers or not isinstance(findings, list):
        return None
    seq: dict[int, int] = {}
    targets: list[Target] = []
    by_id: dict[str, Target] = {}
    keys: set[str] = set()
    for finding in findings:
        if not isinstance(finding, Mapping):
            continue
        index = finding.get("document_index")
        if not _is_int(index) or index not in numbers:
            continue
        number = numbers[index]
        seq[number] = seq.get(number, 0) + 1
        finding_id = _text(finding.get("id"))
        key = storage_key(finding_id)
        target = Target(
            id=finding_id,
            key=key,
            num=f"D{number}-{seq[number]:02d}",
            label=finding_name(finding),
            category=_pick(CATS, finding.get("category"), AI_CATEGORY_FALLBACK),
            subject=_pick(SUBJECTS, finding.get("subject"), AI_SUBJECT_FALLBACK),
            exposure=_pick(EXPOSURES, finding.get("exposure"), AI_EXPOSURE_FALLBACK),
            writable=finding_id not in by_id and key not in keys,
        )
        if target.writable:
            by_id[finding_id] = target
            keys.add(key)
        elif finding_id not in by_id:
            logger.warning("저장 키가 겹치는 탐지 항목이 있어 뒤의 항목은 저장하지 않습니다")
        targets.append(target)
    items, item_by_id = _item_targets(view.get("items"), numbers)
    return ReviewScope(
        targets=tuple(targets), by_id=by_id, risk_label=_risk_label(row, view), items=items, item_by_id=item_by_id
    )


# --- 검토 행 정규화 ----------------------------------------------------------------------------


@dataclass(frozen=True)
class _State:
    exists: bool
    status: str
    findings: Mapping[str, Any]  # 저장된 그대로
    history: Sequence[Any]  # 저장된 그대로
    version: int
    items: Mapping[str, Any] = field(default_factory=dict)  # 저장된 그대로(검토사항 해결 기록)


def _state(raw: Mapping[str, Any] | None, *, for_write: bool) -> _State:
    """검토 행 → 상태. 행이 없으면 기본값(version 0). for_write 면 version 이 틀린 행은 StoreError(쓸 수 없음)."""
    if raw is None:
        return _State(exists=False, status="needed", findings={}, history=[], version=0, items={})
    version = raw.get("version")
    if not (_is_int(version) and version >= 1):
        if for_write:
            raise StoreError("검토 행 읽기: version 이 올바르지 않습니다")
        version = 0
    findings = raw.get("findings")
    history = raw.get("history")
    items = raw.get("items")
    return _State(
        exists=True,
        status=_pick(RSTATUS, raw.get("status"), "needed"),
        findings=findings if isinstance(findings, Mapping) else {},
        history=history if isinstance(history, list) else [],
        version=version,
        items=items if isinstance(items, Mapping) else {},
    )


def finding_state(target: Target, findings: Mapping[str, Any]) -> dict[str, Any]:
    """항목 하나의 지금 검토 값(저장 값을 정규화, 없으면 AI 값으로 시작)."""
    out: dict[str, Any] = {
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
    saved = findings.get(target.key) if target.writable else None
    if isinstance(saved, Mapping):
        out["status"] = _pick(FSTATUS, saved.get("status"), "open")
        out["category"] = _pick(CATS, saved.get("category"), target.category)
        out["subject"] = _pick(SUBJECTS, saved.get("subject"), target.subject)
        out["exposure"] = _pick(EXPOSURES, saved.get("exposure"), target.exposure)
        out["fp_type"] = _pick(FP_REASONS, saved.get("fp_type"), "")
        for name in ("fp_note", "reclass_note", "memo"):
            out[name] = _text(saved.get(name))
        out["updated_at"] = _time_or_none(saved.get("updated_at"))
    return out


def item_state(target: ItemTarget, items: Mapping[str, Any]) -> dict[str, Any]:
    """검토사항 하나의 지금 해결 값(저장 값을 정규화, 없으면 미해결 기본값).

    resolved 는 저장 값이 정확히 true 일 때만 true, note·resolved_by 는 문자열 아니면 '', resolved_at 은 문자열 아니면 null.
    """
    saved = items.get(target.key) if target.writable else None
    if not isinstance(saved, Mapping):
        return {"resolved": False, "note": "", "resolved_at": None, "resolved_by": ""}
    return {
        "resolved": saved.get("resolved") is True,
        "note": _text(saved.get("note")),
        "resolved_at": _time_or_none(saved.get("resolved_at")),
        "resolved_by": _text(saved.get("resolved_by")),
    }


def history_line(line: Any) -> dict[str, str] | None:
    """모양이 맞는 저장 이력 한 줄(kind 가 HKIND 키, 나머지가 문자열) → 응답 줄, 아니면 None."""
    if not isinstance(line, Mapping) or not isinstance(line.get("kind"), str) or line.get("kind") not in HKIND:
        return None
    if not all(isinstance(line.get(name), str) for name in HISTORY_KEYS):
        return None
    return {name: line[name] for name in HISTORY_KEYS}


def _system_lines(row: Mapping[str, Any], scope: ReviewScope) -> list[dict[str, str]]:
    documents = row.get("documents")
    files = len([d for d in documents if isinstance(d, Mapping)]) if isinstance(documents, list) else 0
    found = len(scope.targets)
    return [
        {
            "id": "S1",
            "at": _text(row.get("created_at")),
            "actor": SYSTEM_ACTOR,
            "kind": "request",
            "target": ANALYSIS_TARGET,
            "change": f"문서 {files}개 분석 요청",
            "reason": "",
        },
        {
            "id": "S2",
            "at": _text(row.get("updated_at")),
            "actor": SYSTEM_ACTOR,
            "kind": "ai",
            "target": ANALYSIS_TARGET,
            "change": f"분석 완료 · 탐지 {found}건 · 위험등급 {scope.risk_label} · 검토사항 {len(scope.items)}건",
            "reason": "",
        },
    ]


def review_block(row: Mapping[str, Any], scope: ReviewScope, raw: Mapping[str, Any] | None) -> dict[str, Any]:
    """응답 review 블록(BRIEF §5.6 · review-items §5.5) — 검토 행(없으면 기본값)을 정규화한다. 저장 키는 원래 계약 id 로 돌려준다.

    findings·items 는 지금 결과의 저장할 수 있는 대상 중 저장 값이 객체인 것만(다시 분석 등으로 사라진 id 는 무시).
    """
    state = _state(raw, for_write=False)
    source: Mapping[str, Any] = raw if raw is not None else review_defaults()
    findings: dict[str, Any] = {}
    for target in scope.targets:
        if target.writable and isinstance(state.findings.get(target.key), Mapping):
            findings[target.id] = finding_state(target, state.findings)
    items: dict[str, Any] = {}
    for item in scope.items:
        if item.writable and isinstance(state.items.get(item.key), Mapping):
            items[item.id] = item_state(item, state.items)
    stored_lines = [line for line in (history_line(item) for item in state.history) if line is not None]
    first, ai = _system_lines(row, scope)
    retries = [line for line in stored_lines if line["kind"] == "retry"]
    others = [line for line in stored_lines if line["kind"] != "retry"]
    return {
        "status": state.status,
        "memo": _text(source.get("memo")),
        "memo_at": _time_or_none(source.get("memo_at")),
        "reviewer": _text(source.get("reviewer")),
        "reviewed_at": _time_or_none(source.get("reviewed_at")),
        "completion_note": _text(source.get("completion_note")),
        "findings": findings,
        "items": items,
        "history": [first, *retries, ai, *others],
        "version": state.version,
    }


# --- 동작 계산 -------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Change:
    columns: dict[str, Any]  # 바꿀 열(findings 포함, history·version 제외)
    kind: str
    target: str
    change: str
    reason: str


def _action_time(history: Sequence[Any], now: datetime) -> str:
    """동작 시각 = now(UTC). 저장된 마지막(모양이 맞는) 이력의 at 보다 앞서면 그 시각."""
    moment = now.astimezone(UTC)
    for item in reversed(history):
        line = history_line(item)
        if line is None:
            continue
        last = _parse_time(line["at"])
        if last is None:
            continue
        try:
            moment = max(moment, last.astimezone(UTC))
        except (OverflowError, ValueError):
            pass
        break
    return moment.isoformat()


def _targets_for(scope: ReviewScope, action: ReviewAction) -> tuple[Target, ...]:
    """동작이 가리키는 항목(요청 순서). 하나라도 지금 검토 가능 항목이 아니면 404."""
    if action.finding_id is not None:
        ids: tuple[str, ...] = (action.finding_id,)
    else:
        ids = action.finding_ids
    targets = tuple(scope.by_id.get(i) for i in ids)
    if any(t is None for t in targets):
        raise ApiError(404, MSG_FINDING_NOT_FOUND)
    return targets  # type: ignore[return-value]


def _item_for(scope: ReviewScope, action: ReviewAction) -> ItemTarget | None:
    """검토사항 동작이 가리키는 검토사항. 지금 결과에 없거나 저장할 수 없으면 404. 그 밖 동작은 None."""
    if action.type not in ITEM_ACTIONS:
        return None
    item = scope.item_by_id.get(action.item_id) if action.item_id is not None else None
    if item is None:
        raise ApiError(404, MSG_ITEM_NOT_FOUND)
    return item


def _with_entry(findings: Mapping[str, Any], target: Target, value: Mapping[str, Any]) -> dict[str, Any]:
    """저장된 findings 사본에 항목 하나를 쓴다(그 항목의 모르는 키는 둔다, 다른 키는 그대로)."""
    out = dict(findings)
    saved = findings.get(target.key)
    out[target.key] = {**(dict(saved) if isinstance(saved, Mapping) else {}), **value}
    return out


def _with_item(items: Mapping[str, Any], target: ItemTarget, value: Mapping[str, Any]) -> dict[str, Any]:
    """저장된 items 사본에 검토사항 하나를 쓴다(그 항목의 모르는 키·다른 키·지금 결과에 없는 id 는 그대로)."""
    out = dict(items)
    saved = items.get(target.key)
    out[target.key] = {**(dict(saved) if isinstance(saved, Mapping) else {}), **value}
    return out


class StateConflict(ApiError):
    """검토 행 상태 때문에 쓰지 않는 409 — _compute 가 내는 409 는 모두 이것(12종 공통, review-items BRIEF-F §5F F1).

    잠김(MSG_LOCKED)·탐지 항목 상태(MSG_STATE_CHANGED)·이미 완료(MSG_ALREADY_DONE)·완료 전 다시 열기(MSG_NOT_DONE)·
    검토사항 상태(MSG_ITEM_STATE_CHANGED). apply_review_action 이 '바뀐 것 없음'과 같은 한 곳에서, 이 시도에 검토 행이
    없었을 때만(그 사이 분석이 지워져 검토 행도 cascade 로 사라졌을 수 있음) 분석을 다시 읽어 404 로 바꾼다.
    응답은 ApiError 와 같다(409 + 문구 — api 의 ApiError 처리기가 하위 클래스도 받는다).
    """

    def __init__(self, detail: str) -> None:
        super().__init__(409, detail)


def _resolve_item(action: ReviewAction, target: ItemTarget, state: _State, at: str) -> _Change:
    current = item_state(target, state.items)
    if current["resolved"]:
        raise StateConflict(MSG_ITEM_STATE_CHANGED)
    entry = {**current, "resolved": True, "note": action.text, "resolved_at": at, "resolved_by": action.actor}
    return _Change(
        columns={"items": _with_item(state.items, target, entry)},
        kind="resolve",
        target=f"{target.num} {target.label}",
        change="미해결 → 해결",
        reason=action.text,
    )


def _reopen_item(target: ItemTarget, state: _State) -> _Change:
    current = item_state(target, state.items)
    if not current["resolved"]:
        raise StateConflict(MSG_ITEM_STATE_CHANGED)
    entry = {**current, "resolved": False}  # note·resolved_at·resolved_by 는 그대로(데모 reopenItem 과 같다)
    return _Change(
        columns={"items": _with_item(state.items, target, entry)},
        kind="reopenItem",
        target=f"{target.num} {target.label}",
        change="해결 → 미해결",
        reason="",
    )


def _set_status(action: ReviewAction, target: Target, state: _State, at: str) -> _Change:
    current = finding_state(target, state.findings)
    before = current["status"]
    wanted = action.status or "open"
    if (wanted == "confirmed" and before != "open") or (wanted == "open" and before != "confirmed"):
        raise StateConflict(MSG_STATE_CHANGED)
    entry = {**current, "status": wanted, "updated_at": at}
    return _Change(
        columns={"findings": _with_entry(state.findings, target, entry)},
        kind="confirm" if wanted == "confirmed" else "unconfirm",
        target=f"{target.num} {current['category']}",
        change=f"{FSTATUS[before]} → {FSTATUS[wanted]}",
        reason=action.text,
    )


def _confirm_many(targets: Sequence[Target], state: _State, at: str) -> _Change | None:
    findings: Mapping[str, Any] = state.findings
    done: list[Target] = []
    for target in targets:
        current = finding_state(target, findings)
        if current["status"] != "open":
            continue
        findings = _with_entry(findings, target, {**current, "status": "confirmed", "updated_at": at})
        done.append(target)
    if not done:
        return None
    return _Change(
        columns={"findings": dict(findings)},
        kind="confirm",
        target=f"탐지 항목 {len(done)}건",
        change=f"{FSTATUS['open']} → {FSTATUS['confirmed']}",
        reason=", ".join(t.num for t in done),
    )


def _mark_false_positive(action: ReviewAction, target: Target, state: _State, at: str) -> _Change:
    current = finding_state(target, state.findings)
    if current["status"] == "false_positive":
        raise StateConflict(MSG_STATE_CHANGED)
    reason_type = action.reason_type or ""
    entry = {**current, "status": "false_positive", "fp_type": reason_type, "fp_note": action.text, "updated_at": at}
    return _Change(
        columns={"findings": _with_entry(state.findings, target, entry)},
        kind="fp",
        target=f"{target.num} {target.label}",
        change=f"{current['category']} → {FSTATUS['false_positive']} ({reason_type})",
        reason=action.text,
    )


def _restore(action: ReviewAction, target: Target, state: _State, at: str) -> _Change:
    current = finding_state(target, state.findings)
    if current["status"] != "false_positive":
        raise StateConflict(MSG_STATE_CHANGED)
    ai = (target.category, target.subject, target.exposure)
    now_values = (current["category"], current["subject"], current["exposure"])
    status = "reclassified" if now_values != ai else "open"
    entry = {**current, "status": status, "fp_type": "", "fp_note": "", "updated_at": at}
    return _Change(
        columns={"findings": _with_entry(state.findings, target, entry)},
        kind="restore",
        target=f"{target.num} {target.label}",
        change=f"{FSTATUS['false_positive']} → {FSTATUS[status]}",
        reason=action.text,
    )


# reclassify 가 비교하는 순서(데모 코어와 같다): 요청 필드, 저장 필드, 이력 이름
_RECLASS_FIELDS = (("category", "category", "정보 종류"), ("subject", "subject", "정보주체"), ("exposure", "exposure", "노출 상태"))


def _reclassify(action: ReviewAction, target: Target, state: _State, at: str) -> _Change | None:
    current = finding_state(target, state.findings)
    entry = dict(current)
    changes: list[str] = []
    for request_name, column, title in _RECLASS_FIELDS:
        wanted = getattr(action, request_name)
        if wanted is not None and wanted != entry[column]:
            changes.append(f"{title}: {entry[column]} → {wanted}")
            entry[column] = wanted
    if not changes:
        return None
    entry.update({"status": "reclassified", "reclass_note": action.text, "updated_at": at})  # fp_type·fp_note 는 그대로
    return _Change(
        columns={"findings": _with_entry(state.findings, target, entry)},
        kind="reclass",
        target=f"{target.num} {target.label}",
        change=", ".join(changes),
        reason=action.text,
    )


def _save_finding_memo(action: ReviewAction, target: Target, state: _State) -> _Change:
    current = finding_state(target, state.findings)
    entry = {**current, "memo": action.text}  # updated_at 은 바꾸지 않는다(데모와 같다)
    return _Change(
        columns={"findings": _with_entry(state.findings, target, entry)},
        kind="fmemo",
        target=f"{target.num} {current['category']}",
        change="항목 메모 저장" if action.text else "항목 메모 삭제",
        reason=action.text,
    )


def _open_count(scope: ReviewScope, state: _State) -> int:
    return sum(1 for t in scope.targets if finding_state(t, state.findings)["status"] == "open")


def _open_item_count(scope: ReviewScope, state: _State) -> int:
    """미해결 검토사항 수 — 저장할 수 없는 검토사항은 미해결로 센다."""
    return sum(1 for t in scope.items if not item_state(t, state.items)["resolved"])


def _compute(
    action: ReviewAction,
    scope: ReviewScope,
    targets: Sequence[Target],
    state: _State,
    at: str,
    item: ItemTarget | None = None,
) -> _Change | None:
    """검사(잠김·상태)와 새 값 계산. 바뀐 것이 없으면 None. 409 는 모두 StateConflict(검토 행 상태 — 쓰지 않음)."""
    if action.type in LOCKED_ACTIONS and state.status == "done":
        raise StateConflict(MSG_LOCKED)  # 검토 행이 없으면 status needed 라 여기 오지 않는다(같은 묶음으로 다룰 뿐)
    kind = action.type
    if kind in ITEM_ACTIONS:
        if item is None:
            raise ApiError(404, MSG_ITEM_NOT_FOUND)  # apply_review_action 이 먼저 찾는다 — 여기에는 오지 않는다
        return _resolve_item(action, item, state, at) if kind == "resolve_item" else _reopen_item(item, state)
    if kind == "set_status":
        return _set_status(action, targets[0], state, at)
    if kind == "confirm_many":
        return _confirm_many(targets, state, at)
    if kind == "mark_false_positive":
        return _mark_false_positive(action, targets[0], state, at)
    if kind == "restore":
        return _restore(action, targets[0], state, at)
    if kind == "reclassify":
        return _reclassify(action, targets[0], state, at)
    if kind == "save_finding_memo":
        return _save_finding_memo(action, targets[0], state)
    if kind == "save_memo":
        return _Change(
            columns={"memo": action.text, "memo_at": at},
            kind="memo",
            target=ANALYSIS_TARGET,
            change="검토 메모 저장" if action.text else "검토 메모 삭제",
            reason=action.text,
        )
    if kind == "complete_review":
        if state.status != "needed":
            raise StateConflict(MSG_ALREADY_DONE)  # 검토 행이 없으면 needed 라 여기 오지 않는다
        left, open_items = _open_count(scope, state), _open_item_count(scope, state)
        parts = [f"미확인 탐지 {left}건"] if left else []
        if open_items:
            parts.append(f"미해결 검토사항 {open_items}건")
        rest = f" (남은 항목: {', '.join(parts)})" if parts else ""
        return _Change(
            columns={"status": "done", "reviewed_at": at, "reviewer": action.actor, "completion_note": action.text},
            kind="complete",
            target=ANALYSIS_TARGET,
            change=f"{RSTATUS['needed']} → {RSTATUS['done']}{rest}",
            reason=action.text,
        )
    if kind == "reopen_review":
        if state.status != "done":
            raise StateConflict(MSG_NOT_DONE)
        return _Change(
            columns={"status": "needed", "reviewed_at": None},  # reviewer·completion_note 는 그대로(데모와 같다)
            kind="reopen",
            target=ANALYSIS_TARGET,
            change=f"{RSTATUS['done']} → {RSTATUS['needed']}",
            reason=action.text,
        )
    if kind == "log_export":
        # 잠김과 무관(LOCKED_ACTIONS 밖), 다른 열은 그대로 — 이력 한 줄 + version 만. 늘 changed true
        if action.export_format is None or action.export_size is None or action.export_state is None:
            raise ApiError(400, MSG_BAD_REQUEST)  # validate_action 을 지난 값에는 오지 않는다
        return _Change(
            columns={},
            kind=EXPORT_KIND,
            target=action.file_name or "",
            change=export_change(action.export_format, action.export_size, action.export_state),
            reason=EXPORT_REASON,
        )
    raise ApiError(400, MSG_BAD_REQUEST)  # validate_action 을 지난 값에는 오지 않는다


# --- 동작 적용 -------------------------------------------------------------------------------


def _write_review(
    store: Store, analysis_id: str, state: _State, columns: Mapping[str, Any], line: Mapping[str, str]
) -> dict[str, Any] | None:
    """검토 행 하나를 version 조건부로 쓴다 — columns + 이력 한 줄(id = H{새 version}) → 쓴 행, 경쟁에 지면 None.

    행이 없으면 insert … on conflict do nothing(기본값 + version 1), 있으면 update … where version = 읽은 값.
    저장소 오류는 StoreError(값 없는 문구 — SupabaseStore._review_error).
    """
    version = state.version + 1
    entry = {"id": f"H{version}", **{name: line[name] for name in HISTORY_KEYS if name != "id"}}
    values = {**columns, "history": [*state.history, entry], "version": version}
    if state.exists:
        return store.update_review(analysis_id, values, expect_version=state.version)
    return store.insert_review({"analysis_id": analysis_id, **review_defaults(), **values})


def _load_quiet(store: Store, analysis_id: str) -> dict[str, Any]:
    """검토 동작 경로의 분석 읽기 — 없으면 404. 저장소 오류는 값 없는 StoreError(get_analysis quiet — api 가 502)."""
    row = store.get_analysis(analysis_id, quiet=True)
    if row is None:
        raise ApiError(404, MSG_NOT_FOUND)
    return row


def _analysis_gone(store: Store, analysis_id: str) -> bool:
    """분석 행이 정말 없는지(값 없는 다시 읽기로 None). 다시 읽기 저장소 오류면 False — 원래 오류(502·409)를 그대로 낸다."""
    try:
        return store.get_analysis(analysis_id, quiet=True) is None
    except StoreError:
        return False


def apply_review_action(
    store: Store, analysis_id: str, action: ReviewAction, *, now: datetime | Callable[[], datetime] | None = None
) -> ActionOutcome:
    """동작 하나를 검토 행에 조건부로 쓴다 → ActionOutcome. analyses 행은 읽기만 한다. Upstage 는 부르지 않는다."""
    analysis_id = _uuid_or_404(analysis_id)
    row = _load_quiet(store, analysis_id)  # 값 없는 StoreError → 502, 없으면 404
    view = row_view(row)
    scope = review_scope(row, view)
    if scope is None or view is None:
        raise ApiError(409, MSG_NOT_REVIEWABLE)
    # log_export: 이 분석의 파일 이름(만든 날짜·id 로 정해짐)이어야 한다 — 만든 날짜를 읽지 못하면 기대 이름이 없어 400
    if action.type == "log_export":
        expected = expected_file_name(row, action.export_format) if action.export_format is not None else None
        if expected is None or action.file_name != expected:
            raise ApiError(400, MSG_BAD_REQUEST)
    targets = _targets_for(scope, action) if action.finding_id is not None or action.finding_ids else ()
    item = _item_for(scope, action)  # 검토사항 두 동작만 — 지금 결과에 없거나 저장할 수 없으면 404
    moment = now() if callable(now) else (now or datetime.now(UTC))

    for _attempt in range(MAX_ATTEMPTS):
        raw = store.get_review(analysis_id)  # StoreError → 502
        state = _state(raw, for_write=True)
        at = _action_time(state.history, moment)
        conflict: StateConflict | None = None
        try:
            planned = _compute(action, scope, targets, state, at, item)
        except StateConflict as exc:
            conflict, planned = exc, None
        if planned is None:
            # 쓰지 않고 끝나는 시도(상태 409 · 바뀐 것 없음 200) — 12종 공통 한 곳(BRIEF-F §5F F1). 이 시도에 검토 행이
            # 없었다면(처음 읽기든 경쟁 패배 뒤 다시 읽기든) 그 사이 분석이 지워져 검토 행도 cascade 로 사라졌을 수 있다:
            # 값 없는 다시 읽기로 정말 없으면 404, 있거나 다시 읽기가 저장소 오류면 원래 결과. 검토 행이 있던 시도는
            # 다시 읽지 않는다(추가 분석 읽기는 검토 행이 None 인 시도에서만).
            if raw is None and _analysis_gone(store, analysis_id):
                raise ApiError(404, MSG_NOT_FOUND)
            if conflict is not None:
                raise conflict
            # 바뀐 것 없음 — 쓰지 않는다(이력·version 그대로)
            return ActionOutcome(row=row, view=view, review=review_block(row, scope, raw), changed=False)
        if len(state.history) >= MAX_HISTORY:
            raise ApiError(409, MSG_HISTORY_FULL)
        line = {
            "at": at,
            "actor": action.actor,
            "kind": planned.kind,
            "target": safe_target(planned.target),
            "change": planned.change,
            "reason": planned.reason,
        }
        try:
            written = _write_review(store, analysis_id, state, planned.columns, line)
        except StoreError:
            # 그 사이 분석이 지워졌으면(FK 위반 등) 404 — 아니면 지금처럼 502
            if _analysis_gone(store, analysis_id):
                raise ApiError(404, MSG_NOT_FOUND) from None
            raise
        if written is not None:
            return ActionOutcome(row=row, view=view, review=review_block(row, scope, written), changed=True)
        logger.info("검토 행 쓰기가 다른 요청과 겹쳐 다시 읽습니다")
    if _analysis_gone(store, analysis_id):
        raise ApiError(404, MSG_NOT_FOUND)
    raise ApiError(409, MSG_CONFLICT)


class HistoryFull(Exception):
    """저장된 이력이 MAX_HISTORY 줄이라 더 쓰지 않았다(append_history_line)."""


def append_history_line(
    store: Store,
    analysis_id: str,
    *,
    actor: str,
    kind: str,
    target: str,
    change: str,
    reason: str,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """검토 행에 이력 한 줄만 더한다(다른 열은 그대로) — 검토 동작과 같은 version 조건부 쓰기, MAX_ATTEMPTS 번.

    줄의 at 은 지금(UTC), 저장된 마지막(모양이 맞는) 이력보다 앞서지 않게. target·reason 은 부르는 쪽이 안전화한다.
    → 쓴 행. 모두 경쟁에 지면 None. 이력이 MAX_HISTORY 줄이면 HistoryFull. 저장소 오류·틀린 version 은 StoreError.
    """
    moment = now or datetime.now(UTC)
    for _attempt in range(MAX_ATTEMPTS):
        state = _state(store.get_review(analysis_id), for_write=True)
        if len(state.history) >= MAX_HISTORY:
            raise HistoryFull()
        line = {
            "at": _action_time(state.history, moment),
            "actor": actor,
            "kind": kind,
            "target": target,
            "change": change,
            "reason": reason,
        }
        written = _write_review(store, analysis_id, state, {}, line)
        if written is not None:
            return written
        logger.info("검토 행 쓰기가 다른 요청과 겹쳐 다시 읽습니다")
    return None


def review_action_out(
    store: Store, analysis_id: str, action: ReviewAction, *, now: datetime | Callable[[], datetime] | None = None
) -> dict[str, Any]:
    """POST review-actions 응답 본문: {"analysis": AnalysisOut(조회와 같은 모양, stages 없음), "changed": bool}."""
    outcome = apply_review_action(store, analysis_id, action, now=now)
    return {"analysis": analysis_out(outcome.row, review=outcome.review, view=outcome.view), "changed": outcome.changed}


# --- 조회 -------------------------------------------------------------------------------------


def read_review(store: Store, row: Mapping[str, Any], view: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """조회용 review 블록. 검토할 수 없으면 None(검토 행을 읽지 않음). 읽지 못하면 값 없는 경고 후 None."""
    scope = review_scope(row, view)
    if scope is None:
        return None
    try:
        raw = store.get_review(str(row.get("id")))
        return review_block(row, scope, raw)
    except StoreError:
        logger.warning("검토 기록을 읽지 못해 review 를 null 로 보냅니다")
    except Exception as exc:  # 조회가 500 이 되지 않게 — 값 없이 예외 종류만
        logger.warning("검토 기록을 만들지 못해 review 를 null 로 보냅니다: %s", type(exc).__name__)
    return None


def analysis_read_out(
    store: Store,
    row: Mapping[str, Any],
    *,
    include_stages: bool = False,
    upstage_status: str | None = None,
    poll_error: str | None = None,
) -> dict[str, Any]:
    """GET 조회 응답 — build_view 를 한 번만 계산해 result 와 review 블록에 함께 쓴다."""
    view = row_view(row)
    return analysis_out(
        row,
        include_stages=include_stages,
        upstage_status=upstage_status,
        poll_error=poll_error,
        review=read_review(store, row, view),
        view=view,
    )
