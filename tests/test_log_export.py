# ==========================================================================
#  검토 동작 log_export(내보내기 기록) — 업무 로직(FastAPI 없이 FakeStore 로, live-report BRIEF §5.6)
#  - 크기 표기 fmt_size 가 공유 표 tests/fmt_size_cases.json(화면 fmtSize 와 같은 글자 — T3 vitest 도 읽는다)과 같은지
#  - 분석 번호·기대 파일 이름이 화면 analysisCode(src/services/api/mapping.ts)와 같은 입력 → 같은 code(손 계산)인지,
#    자정 경계(UTC 15:00)·소수 초 6자리·'+00:00'·'Z', 읽지 못하는 created_at → 기대 이름 없음
#  - 본문 모양 400(키·format·size·state·file_name 꼴) → 처리자 400 순서, 원시 JSON(아주 큰 수·1e400·같은 키·깊은 중첩)
#  - 적용: 잠김과 무관(검토 완료 뒤에도), 다른 열 그대로 — 이력 한 줄 + version 만, 늘 changed true, 행이 없으면 기본값 행
#  - 오류 순서: 404 → 409 검토할 수 없음 → 400 이 분석의 이름 아님 → 409 이력 1000줄 → 409 경쟁 3번 / 지워짐 404
#  - analyses 행을 쓰지 않음, 로그에 값(파일 이름·처리자·분석 id)이 없음
# ==========================================================================

from __future__ import annotations

import copy
import json
import logging
import unicodedata
from datetime import UTC, datetime, timedelta
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from api_fakes import FakeStore
from fake_exports import (
    ANALYSIS_ID,
    CODE,
    CREATED_AT,
    CSV_NAME,
    JSON_NAME,
    MSG_BAD_ACTOR,
    MSG_CONFLICT,
    MSG_FORMAT,
    MSG_HISTORY_FULL,
    MSG_NOT_FOUND,
    MSG_NOT_REVIEWABLE,
    OTHER_ID,
    UNTOUCHED,
    export_body,
    put_analysis,
)
from fake_reviews import ACTOR, SMALL, custom_result

from imask_backend import exports, reviews
from imask_backend.analyses import ApiError
from imask_backend.exports import (
    FILE_NAME_RE,
    MAX_EXPORT_BYTES,
    analysis_code,
    expected_file_name,
    export_change,
    export_fields_ok,
    fmt_size,
    id_head,
    seoul_date,
)
from imask_backend.reviews import (
    ACTION_FIELDS,
    HKIND,
    LOCKED_ACTIONS,
    ActionOutcome,
    apply_review_action,
    parse_action,
    read_review,
    review_scope,
    row_view,
    validate_action,
)
from imask_backend.store import StoreError

CASES_PATH = Path(__file__).with_name("fmt_size_cases.json")
CLOCK = datetime(2026, 11, 5, 1, 2, 3, tzinfo=UTC)
MSG_LOCKED = "검토를 완료한 분석은 바꿀 수 없습니다."


def tick(minutes: int) -> datetime:
    return CLOCK + timedelta(minutes=minutes)


def export_line(version: int, minutes: int, *, name: str = CSV_NAME, change: str = "CSV · 6KB · 다운로드 요청") -> dict[str, str]:
    return {
        "id": f"H{version}",
        "at": tick(minutes).isoformat(),
        "actor": ACTOR,
        "kind": "export",
        "target": name,
        "change": change,
        "reason": "민감한 값 마스킹",
    }


def act(store: FakeStore, body: dict[str, Any], *, at: int = 0, analysis_id: str = ANALYSIS_ID) -> ActionOutcome:
    return apply_review_action(store, analysis_id, validate_action(body), now=tick(at))


def act_error(store: FakeStore, body: dict[str, Any], *, at: int = 0, analysis_id: str = ANALYSIS_ID) -> ApiError:
    with pytest.raises(ApiError) as info:
        act(store, body, at=at, analysis_id=analysis_id)
    return info.value


def ids(store: FakeStore, analysis_id: str = ANALYSIS_ID) -> dict[str, str]:
    row = store.get_analysis(analysis_id)
    assert row is not None
    scope = review_scope(row, row_view(row))
    assert scope is not None
    return {t.num: t.id for t in scope.targets}


def other(kind: str, **fields: Any) -> dict[str, Any]:
    return {"type": kind, "actor": ACTOR, **fields}


def filler(count: int) -> list[dict[str, str]]:
    return [
        {"id": f"H{i}", "at": tick(0).isoformat(), "actor": "가", "kind": "memo", "target": "분석 건", "change": "c", "reason": ""}
        for i in range(1, count + 1)
    ]


@pytest.fixture
def store() -> FakeStore:
    out = FakeStore()
    put_analysis(out)
    return out


# --- 크기 표기(공유 표) ---------------------------------------------------------------------------


def _cases() -> list[list[Any]]:
    return json.loads(CASES_PATH.read_bytes().decode("utf-8"))


def test_size_table_file_is_utf8_lf_and_has_every_boundary() -> None:
    raw = CASES_PATH.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw and raw.endswith(b"\n")
    cases = _cases()
    assert all(
        isinstance(c, list) and len(c) == 2 and type(c[0]) is int and isinstance(c[1], str) for c in cases
    ), "모양은 [[바이트, 글자], …]"
    sizes = [c[0] for c in cases]
    assert sizes == sorted(set(sizes))
    required = {
        0, 1, 511, 512, 513, 1023, 1024, 1535, 1536, 2559, 2560, 2561, 1048063, 1048064, 1048575, 1048576,
        1153433, 1153434, 1310719, 1310720, 1310721, 1835008, 2359296, 104857600,
    }  # fmt: skip
    assert required <= set(sizes)
    table = dict((b, s) for b, s in cases)
    must = {2560: "3KB", 1310720: "1.3MB", 2359296: "2.3MB", 1048064: "1024KB", 1048576: "1.0MB", 104857600: "100.0MB"}
    assert {b: table[b] for b in must} == must


@pytest.mark.parametrize(("size", "text"), _cases())
def test_fmt_size_matches_the_shared_table(size: int, text: str) -> None:
    assert fmt_size(size) == text


def test_python_rounding_would_differ_at_the_ties() -> None:
    # 그래서 정수 계산을 쓴다 — 파이썬 round()·format(.1f) 는 짝수 쪽(JS 는 올림)
    assert f"{round(2560 / 1024)}KB" == "2KB" and fmt_size(2560) == "3KB"
    assert format(1310720 / 1048576, ".1f") + "MB" == "1.2MB" and fmt_size(1310720) == "1.3MB"
    assert format(2359296 / 1048576, ".1f") + "MB" == "2.2MB" and fmt_size(2359296) == "2.3MB"


def _js_fmt_size(size: int) -> str:
    """JS 규칙을 정확한 유리수로 따로 계산(Math.round = floor(x + 1/2), toFixed(1) = 동점이면 큰 쪽)."""
    if size < 1048576:
        return f"{max(1, int((Fraction(size, 1024) + Fraction(1, 2)) // 1))}KB"
    tenths = int((Fraction(size * 10, 1048576) + Fraction(1, 2)) // 1)
    return f"{tenths // 10}.{tenths % 10}MB"


def test_fmt_size_matches_exact_rational_rounding_over_a_sweep() -> None:
    sizes = list(range(0, 4096)) + list(range(1_040_000, 1_060_000, 7)) + [m * 262144 + d for m in range(4, 401) for d in (-1, 0, 1)]
    sizes += list(range(MAX_EXPORT_BYTES - 3000, MAX_EXPORT_BYTES + 1, 13))
    assert [fmt_size(s) for s in sizes] == [_js_fmt_size(s) for s in sizes]


# --- 분석 번호·기대 파일 이름(화면 analysisCode 와 같은 입력 → 같은 code) ----------------------------------

# (id, created_at, 화면 analysisCode 가 내는 code) — 손으로 계산(서울 = UTC+9, id 의 ASCII 영숫자 앞 4자 대문자)
SCREEN_CODES = [
    (ANALYSIS_ID, "2026-11-04T14:59:59.999999+00:00", "IM-20261104-7B94"),  # 서울 23:59:59.999 — 그날
    (ANALYSIS_ID, "2026-11-04T15:00:00+00:00", "IM-20261105-7B94"),  # 서울 00:00 — 다음 날
    (ANALYSIS_ID, "2026-11-04T14:59:59.999999Z", "IM-20261104-7B94"),
    (ANALYSIS_ID, "2026-11-04T15:00:00Z", "IM-20261105-7B94"),
    (ANALYSIS_ID, "2026-11-04T15:00:00.000000+00:00", "IM-20261105-7B94"),
    (ANALYSIS_ID, "2026-11-04T15:00:00.000001+00:00", "IM-20261105-7B94"),
    (ANALYSIS_ID, "2026-11-04T14:59:59.9999999+00:00", "IM-20261104-7B94"),  # 7자리(화면은 3자리로 자름 — 둘 다 내림)
    (ANALYSIS_ID, "2026-11-04 15:00:00+00:00", "IM-20261105-7B94"),  # Postgres 꼴 공백
    (ANALYSIS_ID, "2026-11-04T14:59+00:00", "IM-20261104-7B94"),  # 초 없음
    (ANALYSIS_ID, "2026-11-04T00:00:00-00:00", "IM-20261104-7B94"),
    (ANALYSIS_ID, "2026-11-04T23:59:59+09:00", "IM-20261104-7B94"),
    (ANALYSIS_ID, "2026-11-05T00:00:00+09:00", "IM-20261105-7B94"),
    (ANALYSIS_ID, "2026-11-03T23:30:00-05:00", "IM-20261104-7B94"),  # UTC 11-04 04:30 → 서울 13:30
    (ANALYSIS_ID, "2026-12-31T15:00:00+00:00", "IM-20270101-7B94"),  # 해 넘김
    (ANALYSIS_ID, "2028-02-28T15:00:00+00:00", "IM-20280229-7B94"),  # 윤일
    # 시간대 범위 끝(시 23·분 59)과 분 단위 시간대 — 화면도 같은 날짜(V-T1-1 m1 뒤에도 그대로)
    (ANALYSIS_ID, "2026-11-04T00:00:00+23:59", "IM-20261103-7B94"),  # UTC 11-03 00:01 → 서울 09:01
    (ANALYSIS_ID, "2026-11-04T00:00:00-23:59", "IM-20261105-7B94"),  # UTC 11-04 23:59 → 서울 11-05 08:59
    (ANALYSIS_ID, "2026-11-04T20:44:59+05:45", "IM-20261104-7B94"),  # UTC 14:59:59 → 서울 23:59:59
    (ANALYSIS_ID, "2026-11-04T20:45:00+05:45", "IM-20261105-7B94"),  # UTC 15:00 → 서울 00:00
    (ANALYSIS_ID, "2026-11-04T05:59:59.999999-09:00", "IM-20261104-7B94"),
    (ANALYSIS_ID, "2026-11-04T06:00:00-09:00", "IM-20261105-7B94"),
    ("ab-c-d9f0-0000-4000-8000-000000000000", "2026-11-04T00:00:00Z", "IM-20261104-ABCD"),  # 영숫자만 셈
    ("00000000-0000-4000-8000-000000000000", "2026-11-04T00:00:00Z", "IM-20261104-0000"),
    ("FFFFFFFF-0000-4000-8000-000000000000", "2026-11-04T00:00:00Z", "IM-20261104-FFFF"),
]


@pytest.mark.parametrize(("analysis_id", "created_at", "code"), SCREEN_CODES)
def test_code_matches_the_screen_analysis_code(analysis_id: str, created_at: str, code: str) -> None:
    assert analysis_code(analysis_id, created_at) == code
    row = {"id": analysis_id, "created_at": created_at}
    assert expected_file_name(row, "csv") == f"iMASK_{code}_검토결과_탐지항목.csv"
    assert expected_file_name(row, "json") == f"iMASK_{code}_검토결과.json"


@pytest.mark.parametrize(
    "created_at",
    [
        None,
        "",
        12345,
        1793804400.0,
        ["2026-11-04T15:00:00Z"],
        "not a date",
        "2026-11-04T15:00:00+00",  # 분 없는 시간대 — 화면 Date.parse 는 NaN
        "20261104T150000Z",  # 기본 꼴 — 화면은 NaN
        "2026-11-04T15:00:00",  # 시간대 없음 — 화면은 브라우저 지역 시각으로 읽는다(날짜가 달라질 수 있음)
        "2026-11-04",  # 날짜만
        "2026-11-04T15:00:00.+00:00",
        "2026-02-30T00:00:00Z",  # 없는 날(화면 V8 은 3월로 넘김 — 서버는 읽지 않는다)
        "2026-11-04T24:00:00Z",
        "2026-11-04T15:00:00+24:00",
        # 시간대 시 24 이상·분 60 이상 — 파이썬 fromisoformat 은 다른 시간대로 보정해 읽지만 화면은 NaN(V-T1-1 m1)
        "2026-11-04T15:00:00+00:60",
        "2026-11-04T15:00:00-00:60",
        "2026-11-04T15:00:00+01:99",
        "2026-11-04T15:00:00+23:60",
        "2026-11-04T15:00:00-24:00",
        "2026-11-04T15:00:00+99:00",
        "2026-11-04T15:00:00+0:00",
        "2026-11-04T15:00:00+000:00",
        "2026-11-04t15:00:00Z",
        "2026-11-04T15:00:00z",
        " 2026-11-04T15:00:00Z",
        "2026-11-04T15:00:00Z ",
        "2026-11-04T15:00:00Z\n",
        "２０２６-11-04T15:00:00Z",  # 전각 숫자
        "\u0662\u0660\u0662\u0666-11-04T15:00:00Z",  # 아라비아-인도 숫자
        "9999-12-31T20:00:00+00:00",  # 서울로 바꾸면 해가 10000 — 범위 넘침
        "0000-01-01T00:00:00Z",
    ],
)
def test_unreadable_created_at_has_no_expected_name(created_at: Any) -> None:
    assert seoul_date(created_at) is None
    assert analysis_code(ANALYSIS_ID, created_at) is None
    assert expected_file_name({"id": ANALYSIS_ID, "created_at": created_at}, "csv") is None


def test_years_without_four_digits_have_no_expected_name() -> None:
    # 화면처럼 해를 0 으로 채우지 않는다 → 'IM-9991104-…' 는 이름 꼴(8자리)이 아니다
    assert seoul_date("0999-11-04T00:00:00Z") == "9991104"
    assert expected_file_name({"id": ANALYSIS_ID, "created_at": "0999-11-04T00:00:00Z"}, "csv") is None


@pytest.mark.parametrize(
    ("analysis_id", "head"),
    [
        (ANALYSIS_ID, "7B94"),
        ("7B944F1E-1234", "7B94"),
        ("-_7.b{9}4", "7B94"),
        ("ab", "AB"),
        ("", ""),
        (None, ""),
        (1234, ""),
        ("ａｂｃｄ1234", "1234"),  # 전각 글자는 영숫자가 아니다(화면 정규식 [^0-9a-zA-Z])
        ("\u0130bcd1", "BCD1"),  # 비 ASCII 대문자는 빠진다
    ],
)
def test_id_head_is_ascii_alnum_first_four_upper(analysis_id: Any, head: str) -> None:
    assert id_head(analysis_id) == head


def test_short_or_non_hex_heads_have_no_expected_name() -> None:
    assert expected_file_name({"id": "ab", "created_at": CREATED_AT}, "csv") is None
    assert expected_file_name({"id": "zzzz-0000", "created_at": CREATED_AT}, "csv") is None  # [0-9A-F] 꼴이 아님
    assert expected_file_name({"id": ANALYSIS_ID, "created_at": CREATED_AT}, "xlsx") is None


def test_fixture_name_is_the_seoul_date_not_the_utc_date() -> None:
    assert CODE == "IM-20261105-7B94" and CREATED_AT.startswith("2026-11-04T15")
    assert expected_file_name({"id": ANALYSIS_ID, "created_at": CREATED_AT}, "csv") == CSV_NAME


# --- 요청 본문 ---------------------------------------------------------------------------------


def test_log_export_is_the_tenth_action_and_not_locked() -> None:
    assert ACTION_FIELDS["log_export"] == ("format", "size", "state", "file_name")
    assert len(ACTION_FIELDS) == 12  # review-items §5.6 — resolve_item·reopen_item 을 더해 12종
    assert "log_export" not in LOCKED_ACTIONS and len(LOCKED_ACTIONS) == 9  # 검토사항 두 동작도 잠김 대상
    assert "export" in HKIND


def test_good_bodies_parse() -> None:
    action = validate_action(export_body())
    assert (action.type, action.actor, action.export_format, action.export_size, action.export_state, action.file_name) == (
        "log_export",
        ACTOR,
        "csv",
        6127,
        "handed",
        CSV_NAME,
    )
    assert (action.finding_id, action.finding_ids, action.text) == (None, (), "")
    action = validate_action(export_body(format="json", size=22021, state="saved", file_name=JSON_NAME))
    assert (action.export_format, action.export_size, action.export_state, action.file_name) == ("json", 22021, "saved", JSON_NAME)
    # 이름 꼴만 본다 — 다른 분석의 이름도 본문 단계에서는 통과(분석을 읽은 뒤 400)
    assert validate_action(export_body(file_name="iMASK_IM-19991231-0000_검토결과_탐지항목.csv")).file_name.endswith(".csv")


@pytest.mark.parametrize("size", [1, 2, 6127, MAX_EXPORT_BYTES - 1, MAX_EXPORT_BYTES])
def test_size_boundaries_pass(size: int) -> None:
    assert validate_action(export_body(size=size)).export_size == size


def _bad(body: Any) -> str:
    with pytest.raises(ApiError) as info:
        validate_action(body)
    assert info.value.status_code == 400
    return info.value.detail


@pytest.mark.parametrize("missing", ["type", "actor", "format", "size", "state", "file_name"])
def test_missing_key_is_400(missing: str) -> None:
    body = export_body()
    del body[missing]
    assert _bad(body) == MSG_FORMAT


@pytest.mark.parametrize(
    "extra",
    [{"x": 1}, {"finding_id": "0:a"}, {"text": ""}, {"reason": ""}, {"note": ""}, {"category": None}, {"name": "a"}, {"Format": "csv"}],
)
def test_unknown_key_is_400(extra: dict[str, Any]) -> None:
    assert _bad({**export_body(), **extra}) == MSG_FORMAT


@pytest.mark.parametrize("value", ["CSV", "Csv", "JSON", "xlsx", "pdf", "", " csv", "csv ", "csv\n", 1, 0, None, True, [], ["csv"], {"csv": 1}])
def test_bad_format_is_400(value: Any) -> None:
    assert _bad(export_body(format=value)) == MSG_FORMAT


@pytest.mark.parametrize(
    "value",
    [0, -1, -6127, MAX_EXPORT_BYTES + 1, 10**400, -(10**400), 1.0, 6127.0, 1.5, float("inf"), float("nan"), "1", "6127", True, False, None, [], [6127], {}],
)
def test_bad_size_is_400(value: Any) -> None:
    assert _bad(export_body(size=value)) == MSG_FORMAT


@pytest.mark.parametrize("value", ["HANDED", "Saved", "done", "downloaded", "", "handed ", " saved", None, 1, True, [], {}])
def test_bad_state_is_400(value: Any) -> None:
    assert _bad(export_body(state=value)) == MSG_FORMAT


@pytest.mark.parametrize("value", [None, 1, 1.0, True, [], [CSV_NAME], {}, {"name": CSV_NAME}])
def test_file_name_must_be_a_string(value: Any) -> None:
    assert _bad(export_body(file_name=value)) == MSG_FORMAT


STEM = "iMASK_IM-20261105-7B94"
BAD_NAMES: dict[str, tuple[str, str]] = {
    "brand_upper": ("csv", "IMASK_IM-20261105-7B94_검토결과_탐지항목.csv"),
    "brand_other": ("csv", "DocGuard_IM-20261105-7B94_검토결과_탐지항목.csv"),
    "no_brand": ("csv", "IM-20261105-7B94_검토결과_탐지항목.csv"),
    "no_underscore": ("csv", "iMASKIM-20261105-7B94_검토결과_탐지항목.csv"),
    "lower_dg": ("csv", "iMASK_dg-20261105-7B94_검토결과_탐지항목.csv"),
    "lower_hex": ("csv", "iMASK_IM-20261105-7b94_검토결과_탐지항목.csv"),
    "non_hex": ("csv", "iMASK_IM-20261105-7G94_검토결과_탐지항목.csv"),
    "date_7": ("csv", "iMASK_IM-2026115-7B94_검토결과_탐지항목.csv"),
    "date_9": ("csv", "iMASK_IM-202611050-7B94_검토결과_탐지항목.csv"),
    "date_dashes": ("csv", "iMASK_IM-2026-11-05-7B94_검토결과_탐지항목.csv"),
    "hex_3": ("csv", "iMASK_IM-20261105-7B9_검토결과_탐지항목.csv"),
    "hex_5": ("csv", "iMASK_IM-20261105-7B94A_검토결과_탐지항목.csv"),
    "no_date": ("csv", "iMASK_IM-7B94_검토결과_탐지항목.csv"),
    "fullwidth_date": ("csv", "iMASK_IM-２０２６1105-7B94_검토결과_탐지항목.csv"),
    "fullwidth_hex": ("csv", "iMASK_IM-20261105-７B94_검토결과_탐지항목.csv"),
    "arabic_indic_date": ("csv", "iMASK_IM-\u0662\u0660\u0662\u06661105-7B94_검토결과_탐지항목.csv"),
    "superscript_digit": ("csv", "iMASK_IM-2026110\u00b2-7B94_검토결과_탐지항목.csv"),
    "trailing_lf": ("csv", CSV_NAME + "\n"),
    "trailing_crlf": ("csv", CSV_NAME + "\r\n"),
    "leading_lf": ("csv", "\n" + CSV_NAME),
    "leading_space": ("csv", " " + CSV_NAME),
    "trailing_space": ("csv", CSV_NAME + " "),
    "trailing_tab": ("csv", CSV_NAME + "\t"),
    "trailing_nbsp": ("csv", CSV_NAME + "\u00a0"),
    "trailing_ideographic_space": ("csv", CSV_NAME + "\u3000"),
    "nul_end": ("csv", CSV_NAME + "\x00"),
    "nul_inside": ("csv", STEM + "\x00_검토결과_탐지항목.csv"),
    "lone_high_surrogate": ("csv", CSV_NAME + "\ud800"),
    "lone_low_surrogate_inside": ("csv", STEM + "_검\udc00토결과_탐지항목.csv"),
    "zero_width_space": ("csv", STEM + "_검\u200b토결과_탐지항목.csv"),
    "nfd_hangul": ("csv", unicodedata.normalize("NFD", CSV_NAME)),
    "slash_prefix": ("csv", "/" + CSV_NAME),
    "dotdot_prefix": ("csv", "../" + CSV_NAME),
    "backslash_prefix": ("csv", "C:\\tmp\\" + CSV_NAME),
    "slash_inside": ("csv", STEM + "/검토결과_탐지항목.csv"),
    "backslash_inside": ("csv", STEM + "\\검토결과_탐지항목.csv"),
    "json_name_for_csv": ("csv", JSON_NAME),
    "csv_name_for_json": ("json", CSV_NAME),
    "csv_then_json": ("json", CSV_NAME + ".json"),
    "json_then_csv": ("csv", JSON_NAME + ".csv"),
    "csv_txt": ("csv", CSV_NAME + ".txt"),
    "upper_csv_ext": ("csv", STEM + "_검토결과_탐지항목.CSV"),
    "upper_json_ext": ("json", STEM + "_검토결과.JSON"),
    "csv_stem_json_ext": ("json", STEM + "_검토결과_탐지항목.json"),
    "json_stem_csv_ext": ("csv", STEM + "_검토결과.csv"),
    "no_extension": ("csv", STEM + "_검토결과_탐지항목"),
    "doubled_suffix": ("csv", STEM + "_검토결과_탐지항목_검토결과_탐지항목.csv"),
    "doubled_stem": ("csv", STEM + "_" + CSV_NAME),
    "empty": ("csv", ""),
    "only_suffix": ("json", "_검토결과.json"),
}


@pytest.mark.parametrize(("export_format", "name"), list(BAD_NAMES.values()), ids=list(BAD_NAMES))
def test_bad_file_names_are_400(export_format: str, name: str) -> None:
    assert FILE_NAME_RE.fullmatch(name) is None or not name.endswith(exports.FILE_SUFFIXES[export_format])
    assert not export_fields_ok(export_format, 6127, "handed", name)
    assert _bad(export_body(format=export_format, file_name=name)) == MSG_FORMAT


@pytest.mark.parametrize("actor", ["", " ", "a" * 41, " 김검토", "김검토 ", "김\t검토", "김\x00", "김\x7f", "김\u0085", "김\ud800", "\n"])
def test_bad_actor_comes_after_the_shape(actor: str) -> None:
    assert _bad(export_body(actor=actor)) == MSG_BAD_ACTOR
    # 모양이 틀리면 처리자보다 먼저 형식 400
    assert _bad(export_body(actor=actor, size=0)) == MSG_FORMAT
    assert _bad(export_body(actor=actor, file_name=CSV_NAME + "\n")) == MSG_FORMAT
    assert _bad({**export_body(actor=actor), "x": 1}) == MSG_FORMAT


@pytest.mark.parametrize("actor", [1, None, True, [], {}])
def test_actor_of_the_wrong_type_is_the_format_message(actor: Any) -> None:
    assert _bad(export_body(actor=actor)) == MSG_FORMAT


@pytest.mark.parametrize("actor", ["김검토", "a", "a" * 40, "Kim Reviewer", "검토 담당 😀"])
def test_good_actor(actor: str) -> None:
    assert validate_action(export_body(actor=actor)).actor == actor


def _raw(size: str = "6127", name: str = CSV_NAME, *, extra: str = "") -> bytes:
    text = '{"type":"log_export","actor":"김검토","format":"csv","size":' + size + ',"state":"handed","file_name":"' + name + '"' + extra + "}"
    return text.encode("utf-8")


@pytest.mark.parametrize(
    "raw",
    [
        _raw("1" + "0" * 400),  # 10**400 정수 리터럴
        _raw("-" + "1" + "0" * 400),
        _raw("1" * 5000),  # 파이썬 정수 자릿수 한도 → 400
        _raw("1e400"),
        _raw("-1e400"),
        _raw("1E3"),
        _raw("1.0"),
        _raw("6127.0"),
        _raw("-0"),
        _raw("0"),
        _raw("104857601"),
        _raw('"6127"'),
        _raw("true"),
        _raw("null"),
        _raw("NaN"),
        _raw("Infinity"),
        _raw("-Infinity"),
        _raw("06127"),
        _raw("+6127"),
        _raw("0x17EF"),
        _raw(extra=',"size":6127'),  # 같은 키 두 번
        _raw(extra=',"file_name":"' + CSV_NAME + '"'),
        _raw(extra=',"type":"log_export"'),
        _raw(name=CSV_NAME + "\\n"),  # 이스케이프한 끝 줄바꿈
        _raw(name=CSV_NAME + "\\u0000"),
        _raw(name=CSV_NAME + "\\ud800"),
        _raw(name="iMASK_IM-20261105-7B94_\\uac80\\ud1a0\\uacb0\\uacfc_\\ud0d0\\uc9c0\\ud56d\\ubaa9.csv\\n"),
        b'{"type":"log_export","actor":"\xea\xb9\x80","format":"csv","size":6127,"state":"handed","file_name":' + b"[" * 100_000 + b"]" * 100_000 + b"}",
        b'{"type":"log_export","actor":"\xea\xb9\x80","format":"csv","size":' + b"[" * 30_000 + b"]" * 30_000 + b',"state":"handed","file_name":"x"}',
        _raw()[:-1],  # 잘린 본문
        _raw().decode("utf-8").encode("utf-16"),
        b"\xef\xbb\xbf" + _raw(),
    ],
)
def test_raw_bodies_are_400(raw: bytes) -> None:
    with pytest.raises(ApiError) as info:
        parse_action(raw)
    assert (info.value.status_code, info.value.detail) == (400, MSG_FORMAT)


def test_raw_body_with_escaped_hangul_is_the_same_name() -> None:
    escaped = json.dumps(export_body(), ensure_ascii=True).encode("ascii")
    assert b"\\uac80" in escaped and parse_action(escaped).file_name == CSV_NAME
    assert parse_action(_raw("104857600")).export_size == MAX_EXPORT_BYTES
    assert parse_action(_raw("1")).export_size == 1


# --- 적용: 잠김과 무관·이력 한 줄 + version 만 ------------------------------------------------------------


def test_first_export_creates_the_default_row_with_one_line(store: FakeStore) -> None:
    out = act(store, export_body(), at=1)
    assert out.changed is True
    row = store.reviews[ANALYSIS_ID]
    assert {k: row[k] for k in UNTOUCHED} == {
        "status": "needed",
        "findings": {},
        "memo": "",
        "memo_at": None,
        "reviewer": "",
        "reviewed_at": None,
        "completion_note": "",
    }
    assert row["version"] == 1 and row["history"] == [export_line(1, 1)]
    method, analysis_id, values, expect = store.review_writes[-1]
    assert (method, analysis_id, expect) == ("insert_review", ANALYSIS_ID, None)
    assert values["history"] == [export_line(1, 1)] and values["version"] == 1
    assert out.review["version"] == 1 and out.review["history"][-1] == export_line(1, 1)
    assert [h["id"] for h in out.review["history"]] == ["S1", "S2", "H1"]


def test_export_on_a_completed_review_changes_only_history_and_version(store: FakeStore) -> None:
    fid = ids(store)
    act(store, other("mark_false_positive", finding_id=fid["D1-02"], reason_type="기타", note="사유"), at=1)
    act(store, other("reclassify", finding_id=fid["D2-01"], exposure="마스킹됨", reason="r"), at=2)
    act(store, other("save_finding_memo", finding_id=fid["D1-01"], text="항목 메모"), at=3)
    act(store, other("save_memo", text="검토 메모"), at=4)
    act(store, other("complete_review", note="완료 메모"), at=5)
    before = copy.deepcopy(store.reviews[ANALYSIS_ID])
    assert before["status"] == "done" and before["version"] == 5

    out = act(store, export_body(), at=6)
    after = store.reviews[ANALYSIS_ID]
    assert {k: after[k] for k in UNTOUCHED} == {k: before[k] for k in UNTOUCHED}
    assert after["version"] == 6
    assert after["history"][:-1] == before["history"]
    assert after["history"][-1] == export_line(6, 6)
    method, _, values, expect = store.review_writes[-1]
    assert method == "update_review" and expect == 5 and set(values) == {"history", "version"}  # 다른 열은 보내지도 않는다
    assert out.changed is True and out.review["status"] == "done" and out.review["version"] == 6
    assert out.review["reviewer"] == ACTOR and out.review["completion_note"] == "완료 메모"
    assert out.review["history"][-1] == export_line(6, 6)

    # JSON · 저장 완료도 같은 방식으로 한 줄 더(같은 내용을 다시 보내도 늘 changed true)
    out = act(store, export_body(format="json", size=22021, state="saved", file_name=JSON_NAME), at=7)
    assert out.changed is True
    assert store.reviews[ANALYSIS_ID]["history"][-1] == export_line(7, 7, name=JSON_NAME, change="JSON · 22KB · 저장 완료")
    out = act(store, export_body(format="json", size=22021, state="saved", file_name=JSON_NAME), at=7)
    assert out.changed is True and store.reviews[ANALYSIS_ID]["version"] == 8
    # 잠김은 그대로 — 다른 동작은 여전히 409
    assert act_error(store, other("save_memo", text="x"), at=8).detail == MSG_LOCKED
    assert {k: store.reviews[ANALYSIS_ID][k] for k in UNTOUCHED} == {k: before[k] for k in UNTOUCHED}


@pytest.mark.parametrize(
    ("body", "change"),
    [
        (export_body(size=1), "CSV · 1KB · 다운로드 요청"),
        (export_body(size=2560), "CSV · 3KB · 다운로드 요청"),
        (export_body(size=1310720, state="saved"), "CSV · 1.3MB · 저장 완료"),
        (export_body(size=MAX_EXPORT_BYTES), "CSV · 100.0MB · 다운로드 요청"),
        (export_body(format="json", size=5172, file_name=JSON_NAME), "JSON · 5KB · 다운로드 요청"),
        (export_body(format="json", size=2359296, state="saved", file_name=JSON_NAME), "JSON · 2.3MB · 저장 완료"),
    ],
)
def test_change_text_matches_the_demo_log_export(store: FakeStore, body: dict[str, Any], change: str) -> None:
    out = act(store, body, at=1)
    line = store.reviews[ANALYSIS_ID]["history"][-1]
    assert line["change"] == change and line["target"] == body["file_name"] and line["reason"] == "민감한 값 마스킹"
    assert line["kind"] == "export" and line["actor"] == ACTOR and out.review["history"][-1] == line
    assert export_change(body["format"], body["size"], body["state"]) == change


def test_export_time_never_goes_before_the_last_history_line(store: FakeStore) -> None:
    later = "2099-01-01T00:00:00+00:00"
    store.put_review(ANALYSIS_ID, history=[{**filler(1)[0], "at": later}], version=1)
    act(store, export_body(), at=1)
    assert store.reviews[ANALYSIS_ID]["history"][-1]["at"] == later
    act(store, export_body(), at=2)  # 다음 줄도 앞서지 않는다
    assert store.reviews[ANALYSIS_ID]["history"][-1]["at"] == later


def test_export_lines_follow_the_read_order(store: FakeStore) -> None:
    retry = {"id": "H1", "at": "2026-11-04T10:00:00+00:00", "actor": ACTOR, "kind": "retry", "target": "묶음.pdf", "change": "c", "reason": ""}
    store.put_review(ANALYSIS_ID, history=[retry], version=1)
    act(store, other("save_memo", text="m"), at=1)
    act(store, export_body(), at=2)
    row = store.get_analysis(ANALYSIS_ID)
    assert row is not None
    block = read_review(store, row, row_view(row))
    assert block is not None
    assert [(h["id"], h["kind"]) for h in block["history"]] == [("S1", "request"), ("H1", "retry"), ("S2", "ai"), ("H2", "memo"), ("H3", "export")]


def test_malformed_stored_lines_are_kept_and_counted(store: FakeStore) -> None:
    store.put_review(ANALYSIS_ID, history=["모양이 틀린 줄", {"kind": "export"}], version=2)
    out = act(store, export_body(), at=1)
    history = store.reviews[ANALYSIS_ID]["history"]
    assert history[:2] == ["모양이 틀린 줄", {"kind": "export"}] and history[2] == export_line(3, 1)
    assert [h["id"] for h in out.review["history"]] == ["S1", "S2", "H3"]


def test_export_never_writes_the_analysis_row(store: FakeStore) -> None:
    before = copy.deepcopy(store.analyses[ANALYSIS_ID])
    docs_before = copy.deepcopy(store.documents)
    act(store, export_body(), at=1)
    act(store, other("complete_review", note=""), at=2)
    act(store, export_body(format="json", size=22021, state="saved", file_name=JSON_NAME), at=3)
    assert store.analyses[ANALYSIS_ID] == before and store.documents == docs_before
    assert store.updates == []
    assert not {"update_analysis", "claim_analysis", "update_document", "delete_analysis", "remove_objects"} & set(store.calls)


# --- 오류 순서 -------------------------------------------------------------------------------------


@pytest.mark.parametrize("analysis_id", ["not-a-uuid", "", "00000000-0000-4000-8000-000000000000"])
def test_unknown_analysis_is_404_even_with_a_wrong_name(store: FakeStore, analysis_id: str) -> None:
    for body in (export_body(), export_body(file_name="iMASK_IM-20000101-0000_검토결과_탐지항목.csv")):
        err = act_error(store, body, analysis_id=analysis_id)
        assert (err.status_code, err.detail) == (404, MSG_NOT_FOUND)


def test_uppercase_path_id_is_the_same_analysis(store: FakeStore) -> None:
    out = act(store, export_body(), at=1, analysis_id=ANALYSIS_ID.upper())
    assert out.changed and store.reviews[ANALYSIS_ID]["version"] == 1


@pytest.mark.parametrize(
    ("status", "result"),
    [
        ("queued", None),
        ("running", None),
        ("failed", None),
        ("done", None),
        ("done", {"format": "imask-upstage-v1", "stages": []}),
        ("done", custom_result(SMALL, pageless_classify=True)),
        ("done", "not an object"),
    ],
    ids=["queued", "running", "failed", "done_without_result", "done_old_format", "done_zero_documents", "done_result_not_object"],
)
def test_unreviewable_is_409_before_the_name_check(status: str, result: Any) -> None:
    store = FakeStore()
    put_analysis(store, status=status, result=result, with_result=False)
    for body in (export_body(), export_body(file_name="iMASK_IM-20000101-0000_검토결과_탐지항목.csv")):
        err = act_error(store, body)
        assert (err.status_code, err.detail) == (409, MSG_NOT_REVIEWABLE)
    assert "get_review" not in store.calls and store.review_writes == []


WRONG_NAMES = {
    "other_analysis": "iMASK_IM-20261105-3C1D_검토결과_탐지항목.csv",
    "utc_date": "iMASK_IM-20261104-7B94_검토결과_탐지항목.csv",  # UTC 날짜(서울 날짜가 아님)
    "next_day": "iMASK_IM-20261106-7B94_검토결과_탐지항목.csv",
    "id_one_off": "iMASK_IM-20261105-7B95_검토결과_탐지항목.csv",
    "id_tail": "iMASK_IM-20261105-89AB_검토결과_탐지항목.csv",  # id 의 뒤 4자
    "zero_id": "iMASK_IM-20261105-0000_검토결과_탐지항목.csv",
}


@pytest.mark.parametrize("name", list(WRONG_NAMES.values()), ids=list(WRONG_NAMES))
def test_name_of_another_analysis_is_400_without_touching_the_review_row(store: FakeStore, name: str) -> None:
    err = act_error(store, export_body(file_name=name))
    assert (err.status_code, err.detail) == (400, MSG_FORMAT)
    json_name = name.replace("_검토결과_탐지항목.csv", "_검토결과.json")
    err = act_error(store, export_body(format="json", file_name=json_name))
    assert (err.status_code, err.detail) == (400, MSG_FORMAT)
    assert "get_review" not in store.calls and store.review_writes == [] and store.reviews == {}


def test_names_of_two_analyses_only_fit_their_own(store: FakeStore) -> None:
    put_analysis(store, analysis_id=OTHER_ID, created_at="2026-11-05T00:00:00Z")
    other_name = "iMASK_IM-20261105-3C1D_검토결과_탐지항목.csv"
    assert act_error(store, export_body(file_name=other_name)).status_code == 400
    assert act_error(store, export_body(), analysis_id=OTHER_ID).status_code == 400
    assert act(store, export_body(file_name=other_name), analysis_id=OTHER_ID, at=1).changed
    assert act(store, export_body(), at=1).changed
    assert store.reviews[OTHER_ID]["history"][-1]["target"] == other_name
    assert store.reviews[ANALYSIS_ID]["history"][-1]["target"] == CSV_NAME


@pytest.mark.parametrize(
    "created_at",
    [None, "", "garbage", "2026-11-04T15:00:00", "2026-11-04", "2026-11-04T15:00:00+00", 1793804400, "9999-12-31T20:00:00+00:00"],
)
def test_row_with_unreadable_created_at_is_400(created_at: Any) -> None:
    store = FakeStore()
    put_analysis(store, created_at=created_at)
    for name in (CSV_NAME, "iMASK_IM-20261104-7B94_검토결과_탐지항목.csv"):
        err = act_error(store, export_body(file_name=name))
        assert (err.status_code, err.detail) == (400, MSG_FORMAT)
    assert store.review_writes == []


@pytest.mark.parametrize(
    ("created_at", "name"),
    [
        ("2026-11-04T14:59:59.999999+00:00", "iMASK_IM-20261104-7B94_검토결과_탐지항목.csv"),
        ("2026-11-04T14:59:59.999999Z", "iMASK_IM-20261104-7B94_검토결과_탐지항목.csv"),
        ("2026-11-04T15:00:00+00:00", "iMASK_IM-20261105-7B94_검토결과_탐지항목.csv"),
        ("2026-11-04T15:00:00Z", "iMASK_IM-20261105-7B94_검토결과_탐지항목.csv"),
        ("2026-11-04T15:00:00.000000+00:00", "iMASK_IM-20261105-7B94_검토결과_탐지항목.csv"),
    ],
)
def test_midnight_boundary_rows(created_at: str, name: str) -> None:
    store = FakeStore()
    put_analysis(store, created_at=created_at)
    assert act(store, export_body(file_name=name), at=1).changed
    # 자정 반대쪽 날짜의 이름은 400
    other_day = name.replace("20261104", "20261105") if "20261104" in name else name.replace("20261105", "20261104")
    assert act_error(store, export_body(file_name=other_day)).status_code == 400


def test_action_without_export_fields_never_writes() -> None:
    # 검사를 지나지 않은 동작 값(직접 만든 ReviewAction)도 이름이 없으면 400 — 기대 이름이 없을 때 None == None 으로 통과하지 않게
    for created_at in (CREATED_AT, None):
        store = FakeStore()
        put_analysis(store, created_at=created_at)
        for action in (
            reviews.ReviewAction(type="log_export", actor=ACTOR),
            reviews.ReviewAction(type="log_export", actor=ACTOR, export_format="csv"),
            reviews.ReviewAction(type="log_export", actor=ACTOR, file_name=CSV_NAME),
        ):
            with pytest.raises(ApiError) as info:
                apply_review_action(store, ANALYSIS_ID, action, now=tick(1))
            assert (info.value.status_code, info.value.detail) == (400, MSG_FORMAT)
        assert store.review_writes == []


def test_wrong_name_is_400_before_the_history_limit(store: FakeStore) -> None:
    store.put_review(ANALYSIS_ID, history=filler(1000), version=1000)
    err = act_error(store, export_body(file_name=WRONG_NAMES["utc_date"]))
    assert (err.status_code, err.detail) == (400, MSG_FORMAT)
    err = act_error(store, export_body())
    assert (err.status_code, err.detail) == (409, MSG_HISTORY_FULL)


def test_history_limit_is_409_even_when_completed_and_writes_nothing(store: FakeStore) -> None:
    store.put_review(ANALYSIS_ID, history=filler(999), version=999, status="done", reviewer="가", completion_note="n")
    act(store, export_body(), at=1)  # 999 → 1000줄
    row = store.reviews[ANALYSIS_ID]
    assert len(row["history"]) == 1000 and row["history"][-1] == export_line(1000, 1) and row["status"] == "done"
    writes = len(store.review_writes)
    err = act_error(store, export_body(), at=2)
    assert (err.status_code, err.detail) == (409, MSG_HISTORY_FULL)
    assert len(store.review_writes) == writes and store.reviews[ANALYSIS_ID]["version"] == 1000


def test_history_limit_counts_malformed_lines(store: FakeStore) -> None:
    store.put_review(ANALYSIS_ID, history=["틀린 줄"] * 1000, version=1)
    assert act_error(store, export_body()).detail == MSG_HISTORY_FULL


# --- 경쟁·지워짐·저장소 오류 ------------------------------------------------------------------------


def _bump(store: FakeStore, analysis_id: str) -> None:
    store.reviews[analysis_id]["version"] += 1  # 다른 요청이 먼저 썼다


def test_race_lost_three_times_is_409_and_nothing_of_mine_is_saved(store: FakeStore, caplog: pytest.LogCaptureFixture) -> None:
    store.put_review(ANALYSIS_ID)
    store.review_hooks = [_bump, _bump, _bump]
    with caplog.at_level(logging.DEBUG, logger="imask"):
        err = act_error(store, export_body(), at=1)
    assert (err.status_code, err.detail) == (409, MSG_CONFLICT)
    assert store.reviews[ANALYSIS_ID]["history"] == [] and store.reviews[ANALYSIS_ID]["version"] == 4
    assert [w[3] for w in store.review_writes] == [1, 2, 3]  # 매번 다시 읽은 version 으로
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "겹쳐" in logged
    for value in (CSV_NAME, ACTOR, ANALYSIS_ID, "7B94", "검토결과"):
        assert value not in logged


def test_race_with_real_actions_keeps_both(store: FakeStore) -> None:
    fid = ids(store)

    def other_request(s: FakeStore, analysis_id: str) -> None:
        act(s, other("set_status", finding_id=fid["D1-01"], status="confirmed", reason=""), at=1, analysis_id=analysis_id)

    store.review_hooks = [other_request]
    out = act(store, export_body(), at=2)
    history = store.reviews[ANALYSIS_ID]["history"]
    assert [(h["id"], h["kind"]) for h in history] == [("H1", "confirm"), ("H2", "export")]
    assert history[1] == export_line(2, 2)
    assert [w[0] for w in store.review_writes] == ["insert_review", "insert_review", "update_review"]
    assert out.review["findings"][fid["D1-01"]]["status"] == "confirmed"  # 남의 값 위에 얹었다


def test_two_losses_then_win(store: FakeStore) -> None:
    store.put_review(ANALYSIS_ID)
    store.review_hooks = [_bump, _bump]
    out = act(store, export_body(), at=1)
    assert out.changed and store.reviews[ANALYSIS_ID]["version"] == 4
    assert store.reviews[ANALYSIS_ID]["history"] == [export_line(4, 1)]


def test_deleted_before_the_insert_is_404(store: FakeStore) -> None:
    store.review_hooks = [lambda s, aid: s.delete_analysis(aid)]
    err = act_error(store, export_body())
    assert (err.status_code, err.detail) == (404, MSG_NOT_FOUND)
    assert ANALYSIS_ID not in store.reviews


def test_deleted_before_the_update_is_404(store: FakeStore) -> None:
    store.put_review(ANALYSIS_ID)
    store.review_hooks = [lambda s, aid: s.delete_analysis(aid)]
    err = act_error(store, export_body())
    assert (err.status_code, err.detail) == (404, MSG_NOT_FOUND)


def test_three_losses_then_deleted_is_404(store: FakeStore) -> None:
    store.put_review(ANALYSIS_ID)

    def bump_and_delete(s: FakeStore, aid: str) -> None:
        _bump(s, aid)
        s.analyses.pop(aid)

    store.review_hooks = [_bump, _bump, bump_and_delete]
    err = act_error(store, export_body())
    assert (err.status_code, err.detail) == (404, MSG_NOT_FOUND)


@pytest.mark.parametrize("method", ["get_analysis", "get_review", "insert_review"])
def test_store_errors_are_raised_for_502(store: FakeStore, method: str) -> None:
    store.fail.add(method)
    with pytest.raises(StoreError):
        act(store, export_body())


def test_update_store_error_is_raised_for_502(store: FakeStore) -> None:
    act(store, export_body(), at=1)
    store.fail.add("update_review")
    with pytest.raises(StoreError):
        act(store, export_body(), at=2)


def test_row_with_a_broken_version_is_not_written(store: FakeStore) -> None:
    store.put_review(ANALYSIS_ID, version="3")
    with pytest.raises(StoreError):
        act(store, export_body())
    assert store.review_writes == []


def test_reviews_module_reexports_nothing_new_by_accident() -> None:
    # 기존 9종의 필드 표는 그대로(log_export 와 검토사항 두 동작 resolve_item·reopen_item 만 더함)
    assert {k: v for k, v in ACTION_FIELDS.items() if k not in ("log_export", "resolve_item", "reopen_item")} == {
        "set_status": ("finding_id", "status", "reason"),
        "confirm_many": ("finding_ids",),
        "mark_false_positive": ("finding_id", "reason_type", "note"),
        "restore": ("finding_id", "note"),
        "reclassify": ("finding_id", "reason"),
        "save_finding_memo": ("finding_id", "text"),
        "save_memo": ("text",),
        "complete_review": ("note",),
        "reopen_review": ("reason",),
    }
    assert reviews.OPTIONAL_FIELDS == {"reclassify": ("category", "subject", "exposure")}
