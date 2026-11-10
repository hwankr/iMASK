# ==========================================================================
#  내보내기 기록(log_export) 테스트의 공용 준비 — 손으로 지은 값만(실제 분석 id·이름을 옮기지 않는다)
#  - 고정 id·만든 시각으로 완료 분석을 FakeStore 에 넣고(put_analysis), 그 분석의 파일 이름(CSV_NAME·JSON_NAME)을 쓴다.
#    만든 시각 2026-11-04T15:00:00+00:00 은 서울 2026-11-05 00:00 — 날짜가 UTC 와 다른 쪽(자정 경계)이다.
#  - 화면 analysisCode(src/services/api/mapping.ts)와 같은 규칙으로 손으로 계산한 code 를 적는다.
# ==========================================================================

from __future__ import annotations

from typing import Any

from api_fakes import FakeStore
from fake_reviews import ACTOR, SMALL, custom_result

ANALYSIS_ID = "7b944f1e-1234-4abc-8def-0123456789ab"
CREATED_AT = "2026-11-04T15:00:00+00:00"  # 서울 2026-11-05 00:00
CODE = "IM-20261105-7B94"
CSV_NAME = f"iMASK_{CODE}_검토결과_탐지항목.csv"
JSON_NAME = f"iMASK_{CODE}_검토결과.json"
OTHER_ID = "3c1d2e4f-aaaa-4bbb-8ccc-dddddddddddd"

MSG_FORMAT = "요청 형식이 올바르지 않습니다."
MSG_BAD_ACTOR = "처리자 이름이 올바르지 않습니다."
MSG_NOT_FOUND = "분석 건을 찾을 수 없습니다."
MSG_NOT_REVIEWABLE = "검토할 수 없는 분석입니다."
MSG_HISTORY_FULL = "검토 이력이 너무 많아 더 저장할 수 없습니다."
MSG_CONFLICT = "다른 요청과 겹쳐 저장하지 못했습니다. 잠시 후 다시 시도해 주세요."
MSG_TOO_LARGE = "요청 본문이 너무 큽니다."
MSG_STORE = "데이터 저장소에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요."

# 검토 행에서 log_export 가 바꾸지 않는 열
UNTOUCHED = ("status", "findings", "memo", "memo_at", "reviewer", "reviewed_at", "completion_note")


def put_analysis(
    store: FakeStore,
    *,
    analysis_id: str = ANALYSIS_ID,
    created_at: Any = CREATED_AT,
    status: str = "done",
    result: Any = None,
    with_result: bool = True,
) -> str:
    """분석 하나(기본: 완료 + 검토할 수 있는 결과)를 고정 id·만든 시각으로 넣는다."""
    if with_result and result is None and status == "done":
        result = custom_result(SMALL)
    made = store.put(status=status, job_id="job_done" if status != "queued" else None, result=result, created_at=created_at)
    row = store.analyses.pop(made)
    row["id"] = analysis_id
    store.analyses[analysis_id] = row
    for doc in store.documents.values():
        if doc["analysis_id"] == made:
            doc["analysis_id"] = analysis_id
    return analysis_id


def export_body(**overrides: Any) -> dict[str, Any]:
    """정상 log_export 본문(CSV · 6,127 B · 다운로드 요청) — 덮어쓸 필드만 준다."""
    return {
        "type": "log_export",
        "actor": ACTOR,
        "format": "csv",
        "size": 6127,
        "state": "handed",
        "file_name": CSV_NAME,
        **overrides,
    }
