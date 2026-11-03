# ==========================================================================
#  imask_backend.masking — 노출 상태 추정·가림 미리보기(표시용 가공, 판별 아님). 값은 모두 지어낸 가짜.
#  종류별 예시, ';' 조각·가림 문자·X 규칙, 불변식(길이 같음·글자는 원문이거나 '*'·원문 가림 문자 보존,
#  전체 노출이면 원문과 다름)을 여러 값으로 확인한다.
# ==========================================================================

from __future__ import annotations

import itertools

import pytest

from imask_backend.fields import KINDS
from imask_backend.masking import MASK_CHARS, exposure, mask_chars, masked


@pytest.mark.parametrize(
    ("value", "kind", "expected"),
    [
        ("홍길동", "name", "홍*동"),
        ("남궁민수", "name", "남**수"),
        ("김", "name", "*"),
        ("김가", "name", "김*"),
        ("홍●동", "name", "홍●동"),
        ("800101-1234567", "rrn", "800101-1******"),
        ("800101-1******", "rrn", "800101-1******"),
        ("800101-1XXXXXX", "rrn", "800101-1XXXXXX"),
        ("8001011234567", "id_number", "8001011******"),
        ("A1234567", "id_number", "A1****67"),
        ("AB12", "id_number", "AB**"),
        ("1980년 1월 1일", "birth_date", "1980년 *월 *일"),
        ("010-1234-5678", "phone", "010-****-5678"),
        ("0101", "phone", "01**"),
        ("010-1***", "phone", "010-1***"),
        ("123-45-678901", "account", "123-**-***901"),
        ("1234-5678-9012-3456", "card", "1234-****-****-3456"),
        ("1234-****-****-3456", "card", "1234-****-****-3456"),
        ("1234-xxxx-xxxx-3456", "card", "1234-xxxx-xxxx-3456"),
        ("hong@example.com", "email", "ho**@example.com"),
        ("abc@example.com", "email", "a**@example.com"),
        ("a@example.com", "email", "*@example.com"),
        ("me@a@b.com", "email", "me**@b.com"),
        ("메일 없음", "email", "메* 없*"),
        ("가상특별시 모의구 예시대로 77, 9층", "address", "가상특별시 모의구 **** **, **"),
        ("가상특별시 모의구", "address", "가상특별시 ***"),
        ("서울", "address", "**"),
        ("연봉: 12,340,000원", "text", "연봉: 1*,***,****"),
        ("회사명: (주)모의테스트", "text", "회사명: (주)*****"),
        ("02-123-4567", "text", "02-1**-4567"),
        ("+82 10 1234 5678", "text", "+82 1* **** 5678"),
        ("kim@bank.example", "text", "k**@bank.example"),
        ("연체 이력 있음 3회", "text", "연* 이* 있* 3*"),
        ("김", "text", "*"),
    ],
)
def test_examples(value: str, kind: str, expected: str) -> None:
    assert masked(value, kind) == expected


def test_semicolon_pieces_keep_separators_and_spaces() -> None:
    value = " 홍길동 ;김철수;  이영희  "
    assert masked(value, "name") == " 홍*동 ;김*수;  이*희  "
    staff = "박직원; 여신팀 A-1; 02-000-0000; staff@example.com"
    assert masked(staff, "text") == "박**; 여** A-*; 02-0**-0000; st***@example.com"


def test_empty_pieces_stay_as_is() -> None:
    assert masked(";; ;", "text") == ";; ;"
    assert masked("", "name") == ""


@pytest.mark.parametrize(
    ("value", "kind", "expected"),
    [
        ("홍길동", "name", "전체 노출"),
        ("홍*동", "name", "부분 마스킹"),
        ("***", "name", "마스킹됨"),
        ("●●●-●●", "phone", "마스킹됨"),
        ("800101-1XXXXXX", "rrn", "부분 마스킹"),
        ("XXXXXX-XXXXXXX", "rrn", "마스킹됨"),
        ("xx×-××", "card", "마스킹됨"),
        ("example@example.com", "email", "전체 노출"),  # 이메일의 x 는 가림 문자가 아니다
        ("Xavier", "text", "전체 노출"),
        ("ex***@example.com", "email", "부분 마스킹"),
        ("홍길동; 김*수", "name", "부분 마스킹"),  # ';' 여러 값이어도 전체로 한 번
        ("＊＊; ■□", "name", "마스킹됨"),
        ("-", "text", "전체 노출"),
    ],
)
def test_exposure(value: str, kind: str, expected: str) -> None:
    assert exposure(value, kind) == expected


def test_x_counts_only_for_numeric_kinds() -> None:
    assert "X" in mask_chars("rrn") and "×" in mask_chars("card")
    for kind in ("name", "email", "address", "text", "모르는 종류"):
        assert not ({"X", "x", "×"} & mask_chars(kind))


SAMPLES = [
    "홍길동",
    "남궁민수",
    "김",
    "800101-1234567",
    "800101-1******",
    "900101-1XXXXXX",
    "010-1234-5678",
    "010 1234 5678",
    "1980년 1월 1일",
    "1234-5678-9012-3456",
    "1234-****-****-3456",
    "123-45-678901",
    "hong.gildong@example.com",
    "@example.com",
    "a@b",
    "가상특별시 모의구 예시대로 77, 9층",
    "회사명: (주)모의테스트; 소속: 시험2팀",
    "연봉: 12,340,000원",
    "희망 대출 금액 10,000,000원 12개월 상환",
    "박직원; 여신팀 A-1; 02-000-0000; staff@example.com",
    "  앞뒤 공백  ",
    "●●●●",
    "홍●동",
    "X-ray 촬영",
    "１２３４５６７８９０",  # 전각 숫자
    "Ünïcödé 名前",
    "a;b;;c",
    ":",
    "이름표:",
    "123",
    "(02) 123-4567",
]


@pytest.mark.parametrize(("value", "kind"), list(itertools.product(SAMPLES, (*KINDS, "모르는 종류"))))
def test_invariants(value: str, kind: str) -> None:
    out = masked(value, kind)
    assert len(out) == len(value)
    masks = mask_chars(kind)
    for original, shown in zip(value, out, strict=True):
        assert shown == original or shown == "*"
        if original in masks:
            assert shown == original  # 원문의 가림 문자는 그대로
    assert out.count(";") == value.count(";")
    if exposure(value, kind) == "전체 노출" and any(ch.isalnum() for ch in value):
        assert out != value  # 안전장치: 글자·숫자가 있는 전체 노출 값은 반드시 달라진다


def test_mask_chars_list() -> None:
    assert set("*＊●○■□◆◇★☆") == MASK_CHARS


# --- T1-fix2 m2: 번호처럼 보이는지의 숫자 정의를 숫자 세기(str.isdigit)와 같게 --------------------------


@pytest.mark.parametrize(
    "value",
    ["010-5555-0123", "０１０-５５５５-０１２３", "(０２) ５５５-０１２３", "+82 10 5555 0123", "０２.５５５.０１２３"],
    ids=["ascii", "fullwidth", "fullwidth_paren", "ascii_plus", "fullwidth_dots"],
)
def test_text_number_like_uses_phone_rule_for_any_digits(value: str) -> None:
    assert masked(value, "text") == masked(value, "phone")


def test_fullwidth_phone_in_text() -> None:
    assert masked("０１０-５５５５-０１２３", "text") == "０１０-****-０１２３"
    assert masked("０１０-５５５５-０１２３", "phone") == "０１０-****-０１２３"
    assert masked("０１０-５５５５-가나", "text") == "０**-****-**"  # 숫자·구분자만이 아니면 토큰 규칙(한 토큰 — 첫 글자만)
