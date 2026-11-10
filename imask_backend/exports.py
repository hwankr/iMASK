# ==========================================================================
#  내보내기 기록(log_export)의 값 규칙 — 크기 표기·파일 이름 꼴·이 분석의 기대 파일 이름 (FastAPI 와 무관, 순수 함수)
#  계약: .orchestration/live-report/BRIEF.md §5.6. 이력 문구의 기준은 데모 코어 src/services/demo/core.ts 의 logExport.
#
#  - 크기 표기(fmt_size): 화면 src/lib/format.ts 의 fmtSize 와 같은 글자. 1,048,576 미만이면 max(1, Math.round(b/1024))
#    + 'KB', 아니면 (b/1048576).toFixed(1) + 'MB'. JS 의 Math.round·toFixed 는 동점에서 올리므로(2,560 B → 3KB,
#    1,310,720 B → 1.3MB) 파이썬 round()·format(.1f)(짝수 쪽) 대신 정수 계산으로 '절반은 올림' 한다.
#    두 구현이 같은 글자인지는 공유 표 tests/fmt_size_cases.json 으로 지킨다(파이썬 테스트 + 화면 vitest).
#  - 파일 이름 꼴(FILE_NAME_RE, re.fullmatch — '$' 는 끝 줄바꿈을 받으므로 쓰지 않는다. [0-9]·[0-9A-F] 는 ASCII 만):
#    iMASK_IM-<8자리>-<대문자 hex 4자리>_검토결과_탐지항목.csv | iMASK_IM-<8자리>-<대문자 hex 4자리>_검토결과.json,
#    확장자가 format 과 맞아야 한다(csv ↔ _검토결과_탐지항목.csv, json ↔ _검토결과.json). 새로 받는 기록은 IM- 만이다.
#    분석 번호 머리글자는 예전에 DG- 였다(web-polish C) — 그때 저장된 이력 줄(target 'iMASK_DG-…')은 저장된 그대로 읽힌다
#    (이력 읽기는 이름 꼴을 다시 검사하지 않는다 — reviews._stored_line). 옛 꼴은 LEGACY_FILE_NAME_RE 로만 적어 둔다.
#  - 이 분석의 기대 이름(expected_file_name): 'iMASK_' + 화면 analysisCode(src/services/api/mapping.ts)와 같은 분석 번호
#    'IM-<created_at 의 서울(UTC+9 고정) 날짜 YYYYMMDD>-<id 의 ASCII 영숫자 앞 4자 대문자>' + 형식별 꼬리.
#    created_at 은 화면 Date.parse 와 같은 값이 나오는 꼴만 읽는다: 'YYYY-MM-DD(T| )HH:MM(:SS(.소수)?)?(Z|±HH:MM)'
#    (ASCII 숫자, 시간대 필수 — 시간대 없는 값은 브라우저 지역 시각으로 읽혀 날짜가 달라질 수 있다. 시간대의 시는 00–23,
#    분은 00–59 — '+00:60'·'+01:99' 는 파이썬이 다른 시간대로 보정해 읽지만 화면은 NaN 이다). 같은 결과를 보장하는 범위는
#    PostgREST 의 시간대 있는 timestamptz 꼴이다(그 밖 꼴은 서버가 더 엄격할 수 있다 — 기대 이름 없음). 소수 초는 6자리에서
#    자른다(화면은 3자리 — 둘 다 내림이라 날짜는 같다). 읽지 못하거나(꼴·없는 날짜·범위 넘침) 해가 네 자리가 아니면
#    기대 이름이 없다(None) — 부르는 쪽이 400 으로 끝낸다. 해는 화면처럼 0 을 채우지 않는다.
#  - 이력 change: '<CSV|JSON> · <크기> · <다운로드 요청|저장 완료>', reason '민감한 값 마스킹', kind 'export'.
#  이 모듈은 로그를 남기지 않는다(파일 이름·처리자·분석 id 같은 값이 로그로 나가지 않게).
# ==========================================================================

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

BRAND = "iMASK"  # 화면 CONFIG.brandName — 실제 서비스는 이 꼴로만 이름을 만든다
MAX_EXPORT_BYTES = 104_857_600  # 100 MiB — size 의 상한(포함)
EXPORT_FORMATS = {"csv": "CSV", "json": "JSON"}  # format → 이력 change 의 표기
EXPORT_STATES = {"handed": "다운로드 요청", "saved": "저장 완료"}  # state → 이력 change 의 표기
FILE_SUFFIXES = {"csv": "_검토결과_탐지항목.csv", "json": "_검토결과.json"}  # format → 파일 이름 꼬리
EXPORT_KIND = "export"
EXPORT_REASON = "민감한 값 마스킹"

CODE_PREFIX = "IM-"  # 분석 번호 머리글자(화면 analysisCode 와 같다)
FILE_NAME_RE = re.compile(r"iMASK_IM-[0-9]{8}-[0-9A-F]{4}_검토결과(?:_탐지항목\.csv|\.json)")
# 머리글자가 DG- 이던 때의 이름 — 새 기록에는 받지 않는다(저장된 옛 이력 줄은 그대로 읽힌다)
LEGACY_FILE_NAME_RE = re.compile(r"iMASK_DG-[0-9]{8}-[0-9A-F]{4}_검토결과(?:_탐지항목\.csv|\.json)")
# created_at 으로 읽는 꼴(화면 parseIsoMs → Date.parse 와 같은 순간이 나오는 것만)
# 시간대는 Z 또는 ±HH:MM(시 00–23·분 00–59) — '+00:60' 처럼 파이썬이 다른 시간대로 보정해 읽는 값(화면은 NaN)을 받지 않는다
_CREATED_AT_RE = re.compile(
    r"([0-9]{4}-[0-9]{2}-[0-9]{2})[T ]([0-9]{2}:[0-9]{2}(?::[0-9]{2}(?:\.[0-9]+)?)?)"
    r"(Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])"
)
_FRACTION_RE = re.compile(r"\.([0-9]{6})[0-9]+")
_ASCII_ALNUM = frozenset("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
SEOUL = timezone(timedelta(hours=9))  # 화면 SEOUL_OFFSET_MS 와 같은 고정 +9

_KB = 1024
_MB = 1_048_576


def fmt_size(size: int) -> str:
    """바이트 → '412KB' · '1.2MB' (화면 fmtSize 와 같은 글자 — 동점은 올림, 정수 계산만)."""
    if size < _MB:
        return f"{max(1, (size + _KB // 2) // _KB)}KB"
    tenths = (size * 10 + _MB // 2) // _MB
    return f"{tenths // 10}.{tenths % 10}MB"


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def export_fields_ok(export_format: Any, size: Any, state: Any, file_name: Any) -> bool:
    """log_export 본문의 네 필드가 계약의 모양인지(타입·목록 값·범위·이름 꼴·확장자와 형식)."""
    if not (isinstance(export_format, str) and export_format in EXPORT_FORMATS):
        return False
    if not (_is_int(size) and 1 <= size <= MAX_EXPORT_BYTES):
        return False
    if not (isinstance(state, str) and state in EXPORT_STATES):
        return False
    if not (isinstance(file_name, str) and FILE_NAME_RE.fullmatch(file_name)):
        return False
    return file_name.endswith(FILE_SUFFIXES[export_format])


def export_change(export_format: str, size: int, state: str) -> str:
    """이력 change — 데모 logExport 와 같은 문구."""
    return f"{EXPORT_FORMATS[export_format]} · {fmt_size(size)} · {EXPORT_STATES[state]}"


def seoul_date(created_at: Any) -> str | None:
    """created_at → 서울 날짜 'YYYYMMDD'(해는 0 을 채우지 않음 — 화면과 같다). 읽지 못하면 None."""
    if not isinstance(created_at, str):
        return None
    match = _CREATED_AT_RE.fullmatch(created_at)
    if match is None:
        return None
    day, clock, zone = match.groups()
    clock = _FRACTION_RE.sub(r".\1", clock, count=1)  # 소수 초 6자리까지(내림)
    try:
        moment = datetime.fromisoformat(f"{day}T{clock}{'+00:00' if zone == 'Z' else zone}")
        if moment.tzinfo is None:  # 꼴이 시간대를 요구하므로 오지 않는다(지역 시각으로 읽지 않게)
            return None
        local = moment.astimezone(SEOUL)
    except (ValueError, OverflowError):  # 없는 날짜·시각·시간대, 범위 넘침
        return None
    return f"{local.year}{local.month:02d}{local.day:02d}"


def id_head(analysis_id: Any) -> str:
    """id 의 ASCII 영숫자 앞 4자 대문자(화면 analysisCode 와 같다). 문자열이 아니면 ''."""
    text = analysis_id if isinstance(analysis_id, str) else ""
    return "".join(char for char in text if char in _ASCII_ALNUM)[:4].upper()


def analysis_code(analysis_id: Any, created_at: Any) -> str | None:
    """분석 번호 'IM-YYYYMMDD-XXXX'. 만든 날짜를 읽지 못하면 None(화면은 'IM-XXXX' — 내보내기 이름 꼴이 아니다)."""
    date = seoul_date(created_at)
    if date is None:
        return None
    return f"{CODE_PREFIX}{date}-{id_head(analysis_id)}"


def expected_file_name(row: Mapping[str, Any], export_format: str) -> str | None:
    """이 분석(analyses 행)의 내보내기 파일 이름. 만든 날짜를 읽지 못하거나 이름 꼴이 아니면 None."""
    code = analysis_code(row.get("id"), row.get("created_at"))
    if code is None or export_format not in FILE_SUFFIXES:
        return None
    name = f"{BRAND}_{code}{FILE_SUFFIXES[export_format]}"
    return name if FILE_NAME_RE.fullmatch(name) else None
