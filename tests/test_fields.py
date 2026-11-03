# ==========================================================================
#  imask_backend.fields — 민감정보_추출 17키 대응표
#  - 화면 src/display/rules.ts 의 CATS·SUBJECTS·EXPOSURES 를 읽어(읽기만) Python 상수와 같은지
#  - 표의 category·subject 가 그 안에 있는지, needs_review 가 정확히 9개인지, 표에 없는 키는 unknown 인지
#  - 팀원용 문서 docs/field-mapping.md 의 표가 fields.py 와 같은지(키·category·label·subject·kind·mapping_status)
# ==========================================================================

from __future__ import annotations

import re
from pathlib import Path

import pytest

from imask_backend import masking
from imask_backend.fields import (
    CATS,
    EXPOSURES,
    FIELDS,
    KINDS,
    MAPPING_STATUSES,
    SUBJECTS,
    field_info,
)

ROOT = Path(__file__).resolve().parents[1]
RULES_TS = ROOT / "src" / "display" / "rules.ts"
DOC = ROOT / "docs" / "field-mapping.md"

EXTRACT_KEYS = (
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
NEEDS_REVIEW = {
    "applicant_id_number",
    "employer_info",
    "card_number",
    "loan_info",
    "income_info",
    "credit_negative_info",
    "other_person_name",
    "other_person_rrn",
    "other_person_contact",
}


def ts_const(name: str) -> tuple[str, ...]:
    """rules.ts 의 `export const NAME = [ '…', … ] as const;` 값을 순서대로."""
    text = RULES_TS.read_text(encoding="utf-8")
    match = re.search(rf"export const {name} = \[(.*?)\] as const", text, re.DOTALL)
    assert match, f"rules.ts 에 {name} 가 없다"
    return tuple(re.findall(r"'([^']*)'", match.group(1)))


@pytest.mark.parametrize(("name", "value"), [("CATS", CATS), ("SUBJECTS", SUBJECTS), ("EXPOSURES", EXPOSURES)])
def test_constants_match_screen_rules(name: str, value: tuple[str, ...]) -> None:
    assert ts_const(name) == value


def test_seventeen_keys_in_observed_order() -> None:
    assert tuple(FIELDS) == EXTRACT_KEYS


def test_categories_subjects_kinds_are_known() -> None:
    for key, info in FIELDS.items():
        assert info.category in ts_const("CATS"), key
        assert info.subject in ts_const("SUBJECTS"), key
        assert info.kind in KINDS, key
        assert info.mapping_status in MAPPING_STATUSES, key
        assert info.label, key


def test_needs_review_is_exactly_nine() -> None:
    assert {k for k, info in FIELDS.items() if info.mapping_status == "needs_review"} == NEEDS_REVIEW
    assert not [k for k, info in FIELDS.items() if info.mapping_status == "unknown"]


def test_fixed_values_from_spec() -> None:
    assert field_info("applicant_rrn").category == "고유식별정보"
    assert field_info("staff_contact").subject == "기타 · 은행 직원"
    assert field_info("other_person_contact").subject == "기타"
    assert field_info("card_number").category == "기타 개인정보"


def test_unknown_key_defaults() -> None:
    info = field_info("brand_new_key")
    assert (info.category, info.label, info.subject, info.kind, info.mapping_status) == (
        "기타 개인정보",
        "brand_new_key",
        "기타",
        "text",
        "unknown",
    )


def test_every_kind_has_a_masking_rule() -> None:
    assert set(KINDS) == set(masking._RULES)  # noqa: SLF001 — 종류 목록과 규칙 표가 어긋나지 않게


def _cell(text: str) -> str:
    """표 칸: 백틱 안 값이 있으면 그것, 없으면 칸 글자."""
    code = re.search(r"`([^`]+)`", text)
    return (code.group(1) if code else text).strip()


def doc_rows() -> dict[str, tuple[str, str, str, str, str]]:
    rows: dict[str, tuple[str, str, str, str, str]] = {}
    section = DOC.read_text(encoding="utf-8").split("## 1. 대응표", 1)[1].split("\n## ", 1)[0]
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 6 or not cells[0].startswith("`"):
            continue
        key = _cell(cells[0])
        assert key not in rows, f"문서 표에 {key} 가 두 번"
        rows[key] = (cells[1], cells[2], cells[3], _cell(cells[4]), _cell(cells[5]))
    return rows


def test_doc_table_matches_fields() -> None:
    rows = doc_rows()
    assert tuple(rows) == EXTRACT_KEYS
    for key, info in FIELDS.items():
        assert rows[key] == (info.category, info.label, info.subject, info.kind, info.mapping_status), key


def test_doc_asks_the_required_questions() -> None:
    text = DOC.read_text(encoding="utf-8")
    for needle in ("other_person_", "applicant_id_number", "card_number", "staff_contact", "`page`", "branch_key", "검토 필요"):
        assert needle in text
