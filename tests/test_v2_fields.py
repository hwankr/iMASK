# ==========================================================================
#  imask_backend.fields — 설정 60(v2_full) 칸 대응표
#  - tests/fixtures/v2/config60_keys.json: 설정 60 의 추출 키 목록(값 없음)과 기준표의 형식 — 모든 접두어 키가 표에 있고 형식과 kind 가 맞는지
#  - 표 안팎에서 뜻이 다른 키, 표에 없는 접두어 키, 범주·주체·kind 규칙, 옛 field_info 는 그대로인지
#  - 팀원용 문서 docs/field-mapping.md '5. 설정 60 대응표' 가 fields.py 와 같은지
# ==========================================================================

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from imask_backend import masking
from imask_backend.fields import (
    CATS,
    KINDS,
    MAPPING_STATUSES,
    SUBJECTS,
    V2_FIELDS,
    V2_TABLE_FIELDS,
    field_info,
    v2_bare_key,
    v2_field_info,
    v2_grade,
)
from imask_backend.results import V2_FORM_CODES

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "field-mapping.md"
KEYS = json.loads((ROOT / "tests" / "fixtures" / "v2" / "config60_keys.json").read_bytes().decode("utf-8"))
GRADED = [row for row in KEYS if v2_grade(row["key"]) is not None]
# 기준표의 형식 → 가림 규칙 종류
FMT_KIND = {
    "date": "birth_date",
    "birth": "birth_date",
    "phone": "phone",
    "account": "account",
    "email": "email",
    "name": "name",
    "rrn": "rrn",
    "biz": "id_number",
    "tin": "id_number",
    "amount": "text",
}
ALL_INFOS = [*V2_FIELDS.items(), *V2_TABLE_FIELDS.items()]


def info_of(row: dict[str, str | None]):
    return v2_field_info(row["key"], row["table"])


def test_key_list_covers_the_ten_forms_and_has_no_values() -> None:
    assert {row["form"] for row in KEYS} == set(V2_FORM_CODES)
    assert all(set(row) == {"form", "table", "key", "fmt"} for row in KEYS)
    assert all(row["key"] != "incomplete_fields" for row in KEYS)


@pytest.mark.parametrize("row", GRADED, ids=lambda r: f"{r['form']}-{r['table']}-{r['key']}")
def test_every_graded_key_is_mapped_and_kind_follows_the_format(row: dict[str, str | None]) -> None:
    info = info_of(row)
    assert info.mapping_status == "ok", row["key"]
    if row["fmt"] is not None:
        assert info.kind == FMT_KIND[row["fmt"]], row["key"]


def test_table_has_no_keys_outside_the_config() -> None:
    assert set(V2_FIELDS) == {r["key"] for r in GRADED if r["table"] is None}
    assert set(V2_TABLE_FIELDS) == {(r["table"], r["key"]) for r in GRADED if r["table"] is not None}


@pytest.mark.parametrize(("key", "info"), ALL_INFOS, ids=lambda v: str(v)[:40])
def test_values_are_known(key, info) -> None:
    assert info.category in CATS and info.subject in SUBJECTS and info.kind in KINDS
    assert info.mapping_status in MAPPING_STATUSES and info.mapping_status == "ok"
    name = key if isinstance(key, str) else key[1]
    assert v2_grade(name) is not None
    assert info.label and "_" not in info.label and info.label == info.label.strip()
    assert v2_grade(info.label) is None  # label 에 접두어가 없다


@pytest.mark.parametrize(
    ("key", "table", "kind"),
    [
        ("중_신청인_성명", None, "name"),  # 지급보증은 기준표 형식이 없어도 성명
        ("중_담보제공자_성명", None, "name"),
        ("중_성명_영문", None, "name"),
        ("중_예금주_영문성", None, "name"),
        ("중_성명", "세대구성원", "name"),
        ("중_가족성명_한글", "가족카드신청인정보", "name"),
        ("상_신청인_주민등록번호", None, "rrn"),
        ("상_외국인등록번호", "세대구성원", "rrn"),
        ("상_해외조세_납세자번호", "해외조세목적상국가", "id_number"),
        ("중_보증처_사업자번호", None, "id_number"),
        ("중_사업자번호", None, "id_number"),
        ("중_예금주_생년월일_또는_사업자번호", None, "birth_date"),
        ("중_보증처_연락처_이메일", None, "text"),
        ("중_예금주_연락처", None, "phone"),
        ("중_가족휴대폰", "가족카드신청인정보", "phone"),
        ("상_출금계좌번호", None, "account"),
        ("상_결제계좌", None, "account"),
        ("상_개인형IRP계좌번호", None, "account"),
        ("상_은행이체_입금계좌", "은행계좌", "account"),
        ("상_상속재산_계좌번호", "상속재산", "account"),
        ("상_휴면계좌_번호", "휴면예금", "account"),
        ("중_원권리자_이메일", None, "email"),
        ("하_작성일자", None, "birth_date"),
        ("하_은행이체_개시일", "은행계좌", "birth_date"),
        ("중_대리인_주소", None, "address"),
        ("중_해외조세_상세주소", "해외조세목적상국가", "address"),
        ("중_아파트_동", "아파트관리비", "address"),
        ("상_보증금액_숫자", None, "text"),
    ],
)
def test_kinds_from_the_spec(key: str, table: str | None, kind: str) -> None:
    assert v2_field_info(key, table).kind == kind


@pytest.mark.parametrize(
    ("key", "table", "category"),
    [
        ("상_은행이체_금액", "은행계좌", "소득·거래정보"),
        ("상_상속재산_잔액", "상속재산", "소득·거래정보"),
        ("상_삼개월이상요양_의료비및간병인비용", None, "소득·거래정보"),
        ("상_연말정산소득공제금액", None, "소득·거래정보"),
        ("상_회사부담금_상품명", "회사부담금매수상품", "소득·거래정보"),
        ("상_가입자부담금_운용비율", "가입자부담금매수상품", "소득·거래정보"),
        ("상_신청인_주민등록번호", None, "고유식별정보"),
        ("상_외국인등록번호", "세대구성원", "고유식별정보"),
        ("상_해외조세_납세자번호", "해외조세목적상국가", "고유식별정보"),
        ("상_출금_계좌번호", None, "계좌번호"),
        ("상_휴면계좌_번호", "휴면예금", "계좌번호"),
        ("중_본인_성명", None, "이름"),
        ("중_보증처_주소", None, "주소"),
        ("중_보증처_연락처_이메일", None, "연락처·이메일"),
        ("중_위임인_생년월일", "위임인", "생년월일"),
    ],
)
def test_categories_from_the_spec(key: str, table: str | None, category: str) -> None:
    assert v2_field_info(key, table).category == category


@pytest.mark.parametrize(
    ("key", "table", "subject"),
    [
        ("중_예금주_성명", None, "신청인"),
        ("중_원권리자_성명", None, "신청인"),
        ("중_위임인_성명", "위임인", "신청인"),
        ("중_담보제공자_성명", None, "보증인"),
        ("중_담보제공자_주소", None, "보증인"),
        ("중_보증처_상호", None, "기타 · 거래 상대방"),
        ("중_보증처_사업자번호", None, "기타 · 거래 상대방"),
        ("중_접수_담당자명", None, "기타 · 은행 직원"),
        ("중_접수_담당자전화", None, "기타 · 은행 직원"),
        ("중_대리인_성명", None, "기타"),
        ("중_대리인신청_대리인성명", None, "기타"),
        ("중_법정대리인_성명", "법적대리인", "기타"),
        ("중_성명", "세대구성원", "기타"),
        ("상_외국인등록번호", "세대구성원", "기타"),
        ("중_가족성명_한글", "가족카드신청인정보", "기타"),
        ("중_피상속인_성명", None, "기타"),
    ],
)
def test_subjects_from_the_spec(key: str, table: str | None, subject: str) -> None:
    assert v2_field_info(key, table).subject == subject


def test_same_key_inside_and_outside_a_table() -> None:
    # 중_생년월일 — IRP·체크카드는 가입자 본인, 세대구성원 표는 다른 사람
    assert v2_field_info("중_생년월일").subject == "신청인"
    assert v2_field_info("중_생년월일", "세대구성원").subject == "기타"
    assert v2_field_info("중_성별").subject == "신청인"
    assert v2_field_info("중_성별", "세대구성원").subject == "기타"


def test_key_only_lookup_finds_table_cells() -> None:
    # 규칙의 rowField 이름용
    assert v2_field_info("상_외국인등록번호").label == "외국인등록번호"
    assert v2_field_info("중_성명").label == "성명"
    assert v2_field_info("상_해외조세_납세자번호").kind == "id_number"


@pytest.mark.parametrize(
    ("key", "table"), [("중_새로운_칸", None), ("상_새칸", "세대구성원"), ("중_성명", "없는표")], ids=["밖", "표", "모르는표"]
)
def test_unknown_prefixed_key(key: str, table: str | None) -> None:
    info = v2_field_info(key, table)
    assert (info.category, info.subject, info.kind, info.mapping_status) == ("기타 개인정보", "기타", "text", "unknown")
    assert info.label == v2_bare_key(key)


def test_old_field_info_does_not_know_the_new_keys() -> None:
    assert field_info("중_예금주_성명").mapping_status == "unknown"
    assert field_info("applicant_name").label == "신청인 성명"


@pytest.mark.parametrize(
    ("key", "table", "value", "kept"),
    [
        ("상_신청인_주민등록번호", None, "800101-1234567", "800101-1"),
        ("상_외국인등록번호", "세대구성원", "800101-5234567", "800101-5"),
        ("상_출금계좌번호", None, "123-45-678901", "123-"),
        ("중_예금주_연락처", None, "010-1234-5678", "010-"),
    ],
)
def test_masking_keeps_only_the_kind_head(key: str, table: str | None, value: str, kept: str) -> None:
    shown = masking.masked(value, v2_field_info(key, table).kind)
    assert shown.startswith(kept) and shown != value and len(shown) == len(value) and "*" in shown


def _doc_rows() -> dict[tuple[str | None, str], tuple[str, str, str, str, str]]:
    section = DOC.read_bytes().decode("utf-8").split("## 5. 설정 60 대응표", 1)[1].split("\n## ", 1)[0]
    rows: dict[tuple[str | None, str], tuple[str, str, str, str, str]] = {}
    for line in section.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 7 or not cells[1].startswith("`"):
            continue
        code = re.compile(r"`([^`]+)`")
        table_match = code.search(cells[0])
        key = code.search(cells[1]).group(1)
        table = table_match.group(1) if table_match else None
        assert (table, key) not in rows, f"문서 표에 {key} 가 두 번"
        rows[(table, key)] = (cells[2], cells[3], cells[4], code.search(cells[5]).group(1), code.search(cells[6]).group(1))
    return rows


def test_doc_table_matches_fields() -> None:
    rows = _doc_rows()
    want = {(None, key): info for key, info in V2_FIELDS.items()} | dict(V2_TABLE_FIELDS.items())
    assert list(rows) == list(want)
    for pair, info in want.items():
        assert rows[pair] == (info.category, info.label, info.subject, info.kind, info.mapping_status), pair
