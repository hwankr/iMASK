# ==========================================================================
#  탐지 항목 변환(imask_backend.findings) 테스트용 가짜 Upstage 응답 — 손으로 지은 값만 쓴다
#  관찰한 모양(evidence/T1/stage-shapes.md)을 본뜬다: 분류 6개(마지막이 Other), 추출 5개(output 순서를
#  섞음: 3·1·5·2·4쪽), 기타 안내 1, 검증 5, 병합, 위험도, 권장 조치. 값이 있는 키 수는 서류마다 10/2/5/7/5
#  = 29 이고, 그중 하나(3쪽 income_info)는 page -1·좌표 없음이라 좌표 있는 항목은 28 이다.
#  실제 응답 파일의 값은 옮기지 않는다(모두 지어낸 가짜). JWT·키 꼴 글자는 쓰지 않는다.
# ==========================================================================

from __future__ import annotations

import copy
import json
from typing import Any

from fake_responses import content, item

DOC_TYPES = ("loan_application", "consent_form", "income_proof", "power_of_attorney", "debt_transaction", "Other")
EXTRACT_ORDER = (3, 1, 5, 2, 4)  # output 순서(쪽 번호) — 분류 순서와 다르게 섞는다

ALL_KEYS = (
    "applicant_name",
    "applicant_rrn",
    "applicant_id_number",
    "applicant_birth_date",
    "applicant_phone",
    "applicant_email",
    "applicant_address",
    "employer_info",
    "account_number",
    "card_number",
    "loan_info",
    "income_info",
    "credit_negative_info",
    "other_person_name",
    "other_person_rrn",
    "other_person_contact",
    "staff_contact",
)

# 쪽 → 값이 있는 키(지어낸 값)
VALUES: dict[int, dict[str, str]] = {
    1: {
        "applicant_name": "김가짜",
        "applicant_rrn": "900101-1234567",
        "applicant_phone": "010-0000-1234",
        "applicant_email": "fake.user@example.com",
        "applicant_address": "가상시 연습구 예시로 12, 3층",
        "employer_info": "회사명: (주)모의상회; 소속: 시험2팀; 직급: 견습생; 재직: 7년 5개월",
        "account_number": "000-00-123456",
        "loan_info": "희망 대출 금액 10,000,000원 12개월 상환",
        "income_info": "연소득: 30,000,000원",
        "staff_contact": "박직원; 여신팀 A-1; 02-000-0000; staff@example.com",
    },
    2: {"applicant_name": "김가짜", "applicant_birth_date": "2001년 2월 3일"},
    3: {
        "applicant_name": "김가짜",
        "applicant_rrn": "900101-1******",
        "applicant_address": "가상시 연습구 예시로 12, 3층",
        "employer_info": "회사명: (주)모의상회",
        "income_info": "총급여: 30,000,000원; 결정세액: 1,000,000원",
    },
    4: {
        "applicant_name": "김가짜",
        "applicant_rrn": "900101-1234567",
        "applicant_phone": "010-0000-1234",
        "applicant_address": "가상시 연습구 예시로 12, 3층",
        "other_person_name": "이대리",
        "other_person_rrn": "850505-2345678",
        "other_person_contact": "010-0000-5678; 가상시 연습구 견본로 34, 5층",
    },
    5: {
        "applicant_name": "김가짜",
        "account_number": "000-00-654321",
        "card_number": "1234-****-****-5678",
        "loan_info": "가짜은행 신용대출 5,000,000원 금리 5.5% 연체; 가짜카드 카드론 1,000,000원 금리 9.9% 상환 2회",
        "credit_negative_info": "연체 이력 있음 3회",
    },
}
LOW_CONFIDENCE = {"employer_info", "loan_info", "income_info", "staff_contact", "other_person_contact", "card_number"}
NO_LOCATION = {(3, "income_info")}  # page -1, 좌표 없음
WORD_BOXES = {"applicant_address": 3, "other_person_contact": 2}  # 단어별 사각형 수(나머지는 1)
COORDS_ONLY = {(5, "credit_negative_info")}  # 단어 좌표 없이 값 영역만

EXPECTED_DOCUMENTS = 6
EXPECTED_FINDINGS = sum(len(v) for v in VALUES.values())  # 29
EXPECTED_BOXED = EXPECTED_FINDINGS - len(NO_LOCATION)  # 28
RISK_TEXT = "## 위험도 판정\n상【†1】\n\n## 근거\n- 가짜 근거【†2】"
ACTION_TEXT = "## 권장 조치\n- **주민등록번호** | 대상 서류: 가짜 | 처리 방법: 가림 | 이유: 가짜【†1】\n※ 담당자 최종 확인 필요"
REVIEW_TEXT = "## 검토 안내\n- 가짜 검토 안내【†1】"
OTHER_TEXT = "예상_서류_종류=가짜 서류, 검토_사유=가짜 사유【†1】, 담당자_조치=가짜 조치"


def rect(x: float, y: float, w: float = 0.1, h: float = 0.02) -> list[dict[str, float]]:
    return [{"x": x, "y": y}, {"x": x + w, "y": y}, {"x": x + w, "y": y + h}, {"x": x, "y": y + h}]


def _meta(page: int, key: str, value: str) -> dict[str, Any]:
    if not value or (page, key) in NO_LOCATION:
        return {"_value": value, "confidence": "low", "confidence_score": 0.1, "page": -1, "coordinates": [], "word_coordinates": []}
    words = [] if (page, key) in COORDS_ONLY else [rect(0.1 + 0.12 * i, 0.3) for i in range(WORD_BOXES.get(key, 1))]
    return {
        "_value": value,
        "confidence": "low" if key in LOW_CONFIDENCE else "high",
        "confidence_score": 0.5 if key in LOW_CONFIDENCE else 0.95,
        "page": page,
        "coordinates": rect(0.1, 0.3, 0.5, 0.02),
        "word_coordinates": words,
    }


def extract_data(page: int) -> dict[str, str]:
    values = VALUES[page]
    return {key: values.get(key, "") for key in ALL_KEYS}


def extract_additional(page: int, data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = extract_data(page) if data is None else data
    additional: dict[str, Any] = {"previous_step_name": "step_2_classify", "page_ranges": [[page, page]]}
    for key, value in data.items():
        additional[key] = _meta(page, key, value if isinstance(value, str) else "")
    return additional


def extract_item(page: int, *, status: str = "completed", data: dict[str, Any] | None = None, ranges: Any = None) -> dict[str, Any]:
    data = extract_data(page) if data is None else data
    additional = extract_additional(page, data)
    if ranges is not None:
        additional["page_ranges"] = ranges
    return item("Information Extract - 민감정보_추출", "information-extract", content(data, additional), status=status)


def classify_item(types: tuple[str, ...] = DOC_TYPES) -> dict[str, Any]:
    entries = [
        content(
            code,
            {"document_type": {"_value": code, "confidence_score": 0.9, "confidence": "high"}, "page_ranges": [[page, page]]},
            raw_text=True,
        )
        for page, code in enumerate(types, 1)
    ]
    return item("step_2_classify", "document-classify", *entries)


def risk_item(*, enum: Any = "상", text: Any = RISK_TEXT, raw_text: bool = True, additional: dict[str, Any] | None = None, status: str = "completed") -> dict[str, Any]:
    extra = {"enum": enum, "citations": [{"index": 1, "source_type": "extract", "source_ref": "applicant_rrn", "page": 1}], "page_ranges": [[p, p] for p in range(1, 6)]}
    if additional:
        extra.update(additional)
    return item("Instruct - 위험도_판정", "instruct", content(text, extra, raw_text=raw_text), status=status)


def build_findings_response(
    *,
    risk: Any = "상",
    final: str | None = "권장_조치",
    risk_stage: dict[str, Any] | None = None,
    with_risk: bool = True,
) -> dict[str, Any]:
    """관찰 모양을 본뜬 완료 응답(include[]=all). risk_stage 를 주면 위험도_판정 항목을 그것으로 바꾼다."""
    pages = [page for page, code in enumerate(DOC_TYPES, 1) if code != "Other"]
    output: list[dict[str, Any]] = [
        item("step_1_parse", "document-parse", content({"api": "2.0", "elements": []}, {"document_ids": ["f"]})),
        classify_item(),
    ]
    output += [extract_item(page) for page in EXTRACT_ORDER]
    output.append(
        item("Instruct - 기타_서류_안내", "instruct", content(OTHER_TEXT, {"citations": [], "page_ranges": [[6, 6]]}, raw_text=True))
    )
    output += [
        item("Validate - 필수항목_검증", "validate", content("green", {"verdict": "green", "checks": [], "page_ranges": [[p, p]]}))
        for p in pages
    ]
    merge = {"count": 5, "branch_keys": [f"{i}:{code}" for i, code in enumerate(DOC_TYPES) if code != "Other"]}
    output.append(item("병합-1", "merge", content(merge, {"previous_step_name": "Validate - 필수항목_검증"})))
    if with_risk:
        output.append(risk_stage if risk_stage is not None else risk_item(enum=risk))
    if final is not None:
        text = ACTION_TEXT if final == "권장_조치" else REVIEW_TEXT
        output.append(item(f"Instruct - {final}", "instruct", content(text, {"citations": []}, raw_text=True)))
    return {"id": "resp_fake_findings", "object": "response", "status": "completed", "output": output}


def stored_result(response: dict[str, Any] | None = None, *, keep_response: bool = True) -> dict[str, Any]:
    """analyses.result 꼴(imask-upstage-v1). keep_response=False 면 예전처럼 stages 만 있는 결과."""
    from imask_backend.analyses import build_result

    result = build_result(copy.deepcopy(response or build_findings_response()), "7")
    if not keep_response:
        result.pop("response")
    return result


def risk_json(items: list[dict[str, Any]]) -> str:
    return json.dumps(items, ensure_ascii=False)
