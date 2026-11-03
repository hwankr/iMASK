# ==========================================================================
#  민감정보_추출 필드 대응표 — 추출 키를 화면의 정보 종류·세부 이름·정보 주체로 옮긴다
#  - 백엔드는 판별하지 않는다. 키 이름만 보고 표에 적힌 값을 붙일 뿐이다(위험등급도 정하지 않음).
#  - category 는 src/display/rules.ts 의 CATS, subject 는 SUBJECTS 값 중 하나다(아래 상수는 그 복사본 —
#    tests/test_fields.py 가 rules.ts 를 읽어 같은지 확인한다).
#  - kind 는 가림 미리보기 규칙의 종류(imask_backend.masking). mapping_status 는 대응이 확정됐는지:
#    ok(확정) · needs_review(스키마 담당 팀원 확인 필요 — docs/field-mapping.md 의 질문) · unknown(표에 없는 키).
#  - 표에 없는 키도 버리지 않는다: 기타 개인정보 · 키 이름 그대로 · 기타 · text · unknown.
#  사람이 읽는 표와 질문은 docs/field-mapping.md(테스트가 이 파일과 같은지 확인한다).
# ==========================================================================

from __future__ import annotations

from dataclasses import dataclass

# --- src/display/rules.ts 와 같은 값(순서까지) ---------------------------------------
CATS = ("이름", "연락처·이메일", "주소", "생년월일", "고유식별정보", "계좌번호", "소득·거래정보", "기타 개인정보")
SUBJECTS = ("신청인", "보증인", "기타 · 거래 상대방", "기타 · 은행 직원", "기타")
EXPOSURES = ("전체 노출", "부분 마스킹", "마스킹됨")

MAPPING_STATUSES = ("ok", "needs_review", "unknown")

# 가림 규칙 종류(imask_backend.masking 이 종류마다 다르게 가린다)
KINDS = ("name", "rrn", "id_number", "birth_date", "phone", "email", "address", "account", "card", "text")


@dataclass(frozen=True)
class FieldInfo:
    category: str
    label: str
    subject: str
    kind: str
    mapping_status: str


def _f(category: str, label: str, subject: str, kind: str, status: str) -> FieldInfo:
    return FieldInfo(category=category, label=label, subject=subject, kind=kind, mapping_status=status)


# 민감정보_추출 17키(관찰 순서) — docs/field-mapping.md 의 표와 같다
FIELDS: dict[str, FieldInfo] = {
    "applicant_name": _f("이름", "신청인 성명", "신청인", "name", "ok"),
    "applicant_rrn": _f("고유식별정보", "주민등록번호", "신청인", "rrn", "ok"),
    "applicant_id_number": _f("고유식별정보", "신분증 번호", "신청인", "id_number", "needs_review"),
    "applicant_birth_date": _f("생년월일", "생년월일", "신청인", "birth_date", "ok"),
    "applicant_phone": _f("연락처·이메일", "전화번호", "신청인", "phone", "ok"),
    "applicant_email": _f("연락처·이메일", "이메일 주소", "신청인", "email", "ok"),
    "applicant_address": _f("주소", "주소", "신청인", "address", "ok"),
    "employer_info": _f("기타 개인정보", "직장 정보", "신청인", "text", "needs_review"),
    "account_number": _f("계좌번호", "계좌번호", "신청인", "account", "ok"),
    "card_number": _f("기타 개인정보", "카드번호", "신청인", "card", "needs_review"),
    "loan_info": _f("소득·거래정보", "대출 정보", "신청인", "text", "needs_review"),
    "income_info": _f("소득·거래정보", "소득 정보", "신청인", "text", "needs_review"),
    "credit_negative_info": _f("소득·거래정보", "신용 불이익 정보", "신청인", "text", "needs_review"),
    "other_person_name": _f("이름", "제3자 성명", "기타", "name", "needs_review"),
    "other_person_rrn": _f("고유식별정보", "제3자 주민등록번호", "기타", "rrn", "needs_review"),
    "other_person_contact": _f("연락처·이메일", "제3자 연락처", "기타", "text", "needs_review"),
    "staff_contact": _f("연락처·이메일", "은행 직원 연락처", "기타 · 은행 직원", "text", "ok"),
}

UNKNOWN_CATEGORY = "기타 개인정보"
UNKNOWN_SUBJECT = "기타"
UNKNOWN_KIND = "text"


def field_info(key: str) -> FieldInfo:
    """추출 키 → 대응. 표에 없는 키는 기타 개인정보·키 이름·기타·text·unknown."""
    info = FIELDS.get(key)
    if info is not None:
        return info
    return _f(UNKNOWN_CATEGORY, key, UNKNOWN_SUBJECT, UNKNOWN_KIND, "unknown")
