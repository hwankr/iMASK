# ==========================================================================
#  검토사항 만들기 — 화면용 결과(documents·findings)와 검증 checks 원래 값 → result.items[] (review-items BRIEF §5.3)
#  FastAPI·저장소와 무관한 순수 함수다. findings.build_view 가 조회할 때 부른다(저장 형식은 그대로라 예전 분석에도 적용).
#  화면(src/services/api/contract.ts·mapping.ts)은 이 값을 매핑·덧씌우기만 하고 다시 계산하지 않는다.
#
#  - 보이는 서류(visible_documents): documents[] 중 index 가 bool 아닌 정수 ≥ 0, page_start·page_end 가 bool 아닌 정수 ≥ 1.
#    index 순, 같은 index 는 처음 것. 서류 순번(1부터) = 그 목록의 위치. 화면 쪽 범위 = [page_start, max(page_start, page_end)].
#    화면 readDocSources·reviews.review_scope 와 같은 기준(reviews 가 doc_numbers·finding_name 을 이 모듈에서 가져다 쓴다).
#  - 보이는 탐지 항목: findings[] 중 document_index 가 보이는 서류인 것(계약 순서). 표시 번호 D{서류 순번}-{서류 안 순번 두 자리},
#    표시 이름 = JS trim(label) → JS trim(field) → '이름 없는 항목'. 위치 있음 = page 가 bool 아닌 정수이고 화면 쪽 범위 안
#    그리고 boxes 가 비지 않은 목록. 파일 쪽 = 범위 안 page, 아니면 서류 page_start(상자와 무관). 서류 안 쪽 = 파일 쪽 − page_start + 1.
#    탐지 항목은 서류별로 **한 번만** 나눠 둔다(_contexts) — 재료가 탐지 항목 전체를 다시 훑지 않는다(선형 시간).
#
#  - 재료(material) = 서류 하나의 맥락(DocContext)을 받아 후보 만들기(Maker — 인자 없는 함수, 검토사항 하나)를 내는 함수.
#    재료 목록과 종류 순서는 MATERIALS 한 자리다. 순서: 서류 순서 → MATERIALS 순서 → 재료 안 순서.
#
#      순서 | 재료(MATERIALS)            | 종류        | 한 서류에                 | 계약 id
#      1    | checks: passed 가 정확히 False 인 서류 단위 규칙 | missing | 실패한 규칙(이름)마다 1개 | missing:<서류 index>:<규칙 이름(JS trim)>
#      1′   | checks: verdict 가 green 아님 + 1 의 항목 없음 + 묶음 모양 실패 없음 | missing | 1개 | verdict:<서류 index>
#      B1   | bundle_checks: 묶음_검증 fail(서류별 결과 있음) — ok False 인 보이는 서류 | missing | 규칙마다 1개 | missing:<서류 index>:<규칙 이름>
#      B1′  | bundle_checks: fail 인데 서류별 결과 없음 — 첫 보이는 서류 | missing | 규칙마다 1개 | bundle:<규칙 이름>
#      B2   | bundle_checks: error·absent(필수 서류 없음) — 첫 보이는 서류 | missing | 규칙마다 1개 | absent:<규칙 이름>
#      L1   | links: 서류_대조 unmatched — 대상 서류       | mismatch    | 쌍마다 1개               | mismatch:<기준 index>:<대상 index>
#      L2   | links: 서류_대조 insufficient — 대상 서류    | weaklink    | 쌍마다 1개               | weaklink:<기준 index>:<대상 index>
#      2    | nolocation: 위치 없는 보이는 탐지 항목 | nolocation | 항목마다 1개   | nolocation:<탐지 계약 id>
#      3    | lowconf: 신뢰도 low 인 보이는 탐지 항목 | lowconf   | 서류마다 1개(n건) | lowconf:<서류 index>
#      4    | other: kind 'other' 인 서류      | other       | 1개                       | other:<서류 index>
#
#    B·L 은 최종 흐름 워크플로우(final_imask_workflow)의 묶음 재료다. findings.build_view 가 final_flow.read_bundle_checks·
#    read_links 를 한 번 읽어 bundle_parts·link_pairs 로 서류별 후보 재료(DocBundle)로 나눠 build_items(bundle=…)에 넘긴다
#    (옛 워크플로우는 비어 있다). 묶음 재료는 위 표처럼 규칙·쌍 순서대로 그 서류의 checks 뒤·nolocation 앞에 온다.
#    - B: 규칙 이름은 규칙 1 과 같은 검사(_rule_name). fail 의 이름표 L = field 의 대응표 label(모르면 규칙 이름), absent 의
#      G = group(없으면 규칙 이름). warning·absent, pass, unknown 은 만들지 않는다.
#    - L: 기준·대상 서류가 둘 다 보이는 서류인 쌍만(link_pairs — 같은 대상 서류는 첫 쌍만). linked 는 만들지 않는다.
#      항목의 link_id = 그 쌍의 link:<기준>:<대상>(화면 links[] 의 id). 근거는 그 항목의 서류(대상 서류) 안만 가리킨다 —
#      mismatch 는 대상 서류의 대조 항목(field 가 같은 첫 탐지 항목)이 있으면 그 쪽 '값 보기', 없으면 첫 쪽.
#    - link_pairs·build_links 는 화면용 결과의 links[](문서 간 연결 — 쌍마다 하나)도 만든다(같은 쌍 목록 하나에서).
#
#    규칙 1 의 검사(바깥 데이터 — 모양이 틀린 것은 예외 없이 건너뛴다): checks 가 목록이 아니면 규칙 항목 없음(1′ 은 따진다),
#    목록이면 앞 MAX_CHECKS(200)개만. 객체가 아니거나 passed 가 bool 이 아니면 건너뜀. 묶음 모양(conditions.left.value 가
#    null·목록)의 실패는 항목을 만들지 않고 '묶음 모양 실패 있음'으로만 적는다(1′ 도 막는다). 이름은 문자열이고 JS trim 뒤
#    1~MAX_RULE_NAME(100) 코드 포인트, Cc·Cs 문자 없음. 같은 이름(trim 뒤)은 처음 실패만. 이름표 L = conditions.left.field 가
#    대응표 키면 그 label, 아니면 규칙 이름. 1′ 의 verdict 는 documents[].validation(findings._verdict)과 같은 값 —
#    문자열이고 앞뒤 공백을 지운 소문자가 비지 않고 'green' 이 아닐 때만. verdict 글자는 어디에도 내지 않는다.
#
#  - 글: 고정 문구 + 대응표 이름(또는 규칙 이름) + 표시 번호·이름 + 개수 + 쪽 번호만. 검증 reason·conditions 의 값·
#    verdict 글자·other_guide 는 넣지 않는다. L·N 은 40 코드 포인트를 넘으면 앞 39자 + '…', NUL·짝 없는 서로게이트 → U+FFFD.
#    주격 조사 P: L 의 마지막 글자가 한글 음절이면 받침 있음 '이'·없음 '가', 그 밖 '이(가)'. 접속 조사(와/과, with_particle):
#    받침 있음 '과'·없음 '와', 그 밖 '와(과)'. mismatch 제목의 서류 이름은 final_flow.FINAL_DOC_TYPES 이름(모르는 코드는 코드).
#    NUMS: 신뢰도 low 항목 표시 번호 앞 5개를 ', ' 로 + 넘으면 ' 외 {n−5}건'.
#  - 근거(evidence, 최대 MAX_EVIDENCE 20개): missing·verdict·bundle·absent·other·weaklink 는 서류 첫 쪽 하나, nolocation 은 그 항목
#    하나(누르면 그 항목), lowconf 는 위치 있는 low 항목을 파일 쪽별로 묶어 쪽 오름차순(앞 20쪽), mismatch 는 대조 항목 하나.
#  - 응답 모양: ITEM_KEYS 순서 그대로(맨 뒤 link_id — mismatch·weaklink 만 쌍 id, 그 밖 null). number = 전체 순서 R-{i:02d}(1부터).
#    같은 계약 id 가 또 나오면 처음 것만.
#  - 강건성: 예외를 밖으로 내지 않는다. 후보 하나가 실패하면 그 후보만, 재료 하나가 통째로 실패하면 그 서류의 그 재료만,
#    check 하나·탐지 항목 하나를 읽다 실패하면 그것만 버린다(값 없는 경고 — 재료 이름(고정 글자)과 예외 종류만). 탐지 항목의
#    표시 번호는 먼저 세므로 하나가 빠져도 다른 항목 번호는 reviews.review_scope 와 같다. 맥락 만들기(_contexts)가 실패하면
#    build_items 는 [] 이고, 부르는 쪽(findings.build_view)도 한 번 더 받아 items [] 로만 둔다(documents·findings·overall 은 그대로).
#  - 선형 시간: 서류·탐지 항목·check 를 각각 한 번씩 훑는다(check 는 서류마다 앞 200개, lowconf 근거 쪽은 heapq 로 앞 20개).
#
#  새 재료를 더하는 법
#  - 검증 규칙이 늘 때(필수항목_검증 의 checks 에 규칙이 더해짐): 고칠 것 없다 — 서류 단위 실패 규칙은 이름마다 missing 하나가 된다.
#    다른 종류로 보여야 하면 _from_checks 안에서 규칙 이름·conditions 모양으로 가르고, 종류는 ITEM_TYPES(= 화면 RTYPE)에 있어야 한다.
#  - 서류 하나에서 나오는 새 재료: DocContext 를 받아 Maker 목록을 내는 함수를 쓰고 MATERIALS 의 원하는 자리(종류 순서)에 넣는다.
#    그 재료에 필요한 바깥 값(새 단계의 content 등)은 findings.py 가 서류에 붙여 DocContext 의 새 필드로 넘긴다(응답 documents 에는
#    넣지 않는다). 계약 id 는 '<재료>:<서류 index>[:<구분>]' 꼴로 다른 재료와 겹치지 않게.
#  - 묶음 단위 단계(서류 묶음 전체에 하나 — 묶음_검증·서류_대조처럼): findings.py 가 그 단계를 한 번 읽고 bundle_parts 처럼
#    서류별 후보 재료(DocBundle 의 새 필드)로 나눠 넘긴다. 여기서는 DocContext.bundle 을 받는 재료를 MATERIALS 에 더한다.
#    서류를 가리킬 수 없는 실패는 첫 보이는 서류에 둔다(bundle:·absent: 처럼 서류 index 없는 계약 id). _from_checks 는 서류별
#    검증의 묶음 모양(value 가 null·목록)을 계속 '묶음 모양 실패'로만 적는다(묶음_검증은 서류별 검증 단계가 아니다).
# ==========================================================================

from __future__ import annotations

import heapq
import logging
import unicodedata
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from typing import Any

from .fields import field_info

logger = logging.getLogger("imask.items")

# --- src/display/rules.ts RTYPE 와 같은 값(키·라벨·순서 — tests/test_items.py 가 rules.ts 를 읽어 확인한다) -------------
ITEM_TYPES: dict[str, str] = {
    "unreadable": "판독 불가",
    "cutoff": "페이지 잘림",
    "mismatch": "값 불일치",
    "weaklink": "연결 근거 부족",
    "nolocation": "위치 확인 필요",
    "failed": "분석 실패",
    "missing": "필수 항목 없음",
    "lowconf": "인식 확인 필요",
    "other": "기타 서류",
}

# --- 한도 ------------------------------------------------------------------------------
MAX_CHECKS = 200  # 검증 checks 중 앞에서부터 보는 개수
MAX_RULE_NAME = 100  # 규칙 이름(JS trim 뒤 코드 포인트)
MAX_EVIDENCE = 20  # 검토사항 하나의 근거 수
MAX_NAME = 40  # 글에 넣는 이름표(L)·표시 이름(N)(코드 포인트) — 넘으면 앞 39자 + '…'
MAX_NUMS = 5  # lowconf 설명에 적는 표시 번호 수
MAX_LINK_FIELDS = 80  # links[].docs[].fields(코드 포인트) — 넘으면 앞 79자 + '…'

# --- 응답 모양(키 순서 그대로) ----------------------------------------------------------------
ITEM_KEYS = ("id", "number", "type", "document_index", "page", "finding_id", "title", "desc", "next", "evidence", "link_id")
EVIDENCE_KEYS = ("label", "page", "finding_ids", "finding_id")
# 화면용 결과 links[](문서 간 연결 — 서류_대조 쌍마다 하나)
LINK_KEYS = ("id", "number", "status", "state", "title", "field", "label", "docs", "basis", "missing", "check")
LINK_DOC_KEYS = ("document_index", "page", "fields", "finding_ids")

# --- 최종 흐름 값(final_flow 와 같은 글자 — 순환 import 를 피해 여기 둔다. tests 가 같은지 확인한다) ----------------
LINK_LINKED = "linked"
LINK_UNMATCHED = "unmatched"
LINK_INSUFFICIENT = "insufficient"
LINK_STATES = (LINK_LINKED, LINK_UNMATCHED, LINK_INSUFFICIENT)
LINK_CONFIRMED = "confirmed"  # links[].status — linked
LINK_CHECK = "check"  # links[].status — 그 밖
CHECK_FAIL = "fail"
CHECK_ABSENT = "absent"
SEVERITY_ERROR = "error"

# --- 글(BRIEF §5.3 표 — {…} 만 바뀐다) -----------------------------------------------------------
MISSING_DESC = "필수 항목 검증을 통과하지 못했습니다."
MISSING_NEXT = "원본에서 직접 확인해 주세요."
VERDICT_TITLE = "필수 항목 검증을 통과하지 못했습니다"
VERDICT_DESC = "통과하지 못한 항목을 결과에서 찾지 못했습니다."
VERDICT_NEXT = "원본에서 필수 항목을 직접 확인해 주세요."
NOLOCATION_TITLE = "원문 위치가 없는 탐지 항목"
NOLOCATION_DESC = "{num} {name} — 원문 좌표가 없어 강조할 수 없습니다."
NOLOCATION_NEXT = "원본에서 직접 찾아 확인해 주세요."
LOWCONF_TITLE = "인식 신뢰도가 낮은 항목 {n}건"
LOWCONF_DESC = "{nums}의 값이 틀렸을 수 있습니다."
LOWCONF_NEXT = "원본과 값을 비교해 확인해 주세요."
OTHER_TITLE = "기타 서류로 분류된 문서"
OTHER_DESC = "워크플로우가 대출 서류 5종에 해당하지 않는 기타 서류로 분류했습니다."
OTHER_NEXT = "원본에 개인정보가 있는지 직접 확인해 주세요."
ABSENT_DESC = "필수 서류가 묶음에 없습니다."
ABSENT_NEXT = "빠진 서류가 있는지 원본에서 확인해 주세요."
MISMATCH_DESC = "서류 대조에서 같은 고객으로 확인되지 않았습니다."
LINK_NEXT = "같은 고객의 서류인지 원본에서 확인해 주세요."  # mismatch·weaklink 의 할 일 = links[] 의 check(linked 아님)
WEAKLINK_TITLE = "연결 근거가 부족합니다"
OPEN_LABEL = "{p}쪽 열기"
VALUES_LABEL = "{p}쪽 값 보기"
# links[] 글({L}·{P} 만 바뀐다)
LINK_SAME = "두 서류의 {label}{p} 같습니다."
LINK_DIFFERENT = "두 서류의 {label}{p} 다릅니다."
LINK_NOTHING = "비교할 {label}{p} 없습니다."  # weaklink 설명과 같다
LINK_CHECK_LINKED = "두 서류를 함께 보관·전달할 때 열람 권한을 확인해 주세요."
LINK_NO_VALUE = "{label} 값 없음"

# --- 표시 값 ---------------------------------------------------------------------------
UNNAMED_FINDING = "이름 없는 항목"  # 화면 contract.ts UNNAMED_FINDING(reviews 도 이 값을 쓴다)
REPLACEMENT = "�"
ELLIPSIS = "…"
GREEN = "green"
OTHER_KIND = "other"
LOW = "low"

# JavaScript String.prototype.trim 이 지우는 글자(WhiteSpace·LineTerminator) — 화면과 같은 기준으로 이름을 고른다
JS_SPACE = (
    "\t\n\v\f\r              "
    "    　﻿"
)
_HANGUL_FIRST = 0xAC00
_HANGUL_LAST = 0xD7A3


# 후보 하나 만들기(인자 없는 함수 — 검토사항 하나 또는 None). 예외는 그 후보만 버린다
Maker = Callable[[], dict[str, Any] | None]


# --- 작은 도우미 -------------------------------------------------------------------------


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def js_trim(text: str) -> str:
    """JavaScript trim 과 같은 앞뒤 공백 지우기(화면 toLiveFindings·riskFromLevel 과 같은 기준)."""
    return text.strip(JS_SPACE)


def _is_surrogate(char: str) -> bool:
    return "\ud800" <= char <= "\udfff"


def clip_text(text: str, limit: int) -> str:
    """limit 코드 포인트를 넘으면 앞 limit−1 자 + '…', NUL·짝 없는 서로게이트 → U+FFFD.

    바꾸기는 코드 포인트 하나를 하나로 바꾸므로 먼저 자른다(아주 긴 글도 limit 자만 훑는다).
    """
    short = text if len(text) <= limit else text[: limit - 1] + ELLIPSIS
    return "".join(REPLACEMENT if char == "\x00" or _is_surrogate(char) else char for char in short)


def clip_name(text: str) -> str:
    """글에 넣는 이름(L·N): MAX_NAME 코드 포인트를 넘으면 앞 39자 + '…', NUL·짝 없는 서로게이트 → U+FFFD."""
    return clip_text(text, MAX_NAME)


def _final_consonant(text: str) -> bool | None:
    """마지막 글자가 한글 음절이면 받침이 있는지, 그 밖(빈 글·영문·숫자·'…'·괄호·자모 등)은 None."""
    if text:
        code = ord(text[-1])
        if _HANGUL_FIRST <= code <= _HANGUL_LAST:
            return (code - _HANGUL_FIRST) % 28 != 0
    return None


def subject_particle(text: str) -> str:
    """주격 조사: 마지막 글자가 한글 음절이면 받침 있음 '이'·없음 '가', 그 밖(영문·숫자·'…'·괄호·자모 등)은 '이(가)'."""
    final = _final_consonant(text)
    return "이(가)" if final is None else ("이" if final else "가")


def with_particle(text: str) -> str:
    """접속 조사: 마지막 글자가 한글 음절이면 받침 있음 '과'·없음 '와', 그 밖은 '와(과)'."""
    final = _final_consonant(text)
    return "와(과)" if final is None else ("과" if final else "와")


def finding_name(finding: Mapping[str, Any]) -> str:
    """탐지 항목 표시 이름 — JS trim(label) → JS trim(field) → '이름 없는 항목'(reviews.review_scope 의 Target 과 같다)."""
    return js_trim(_text(finding.get("label"))) or js_trim(_text(finding.get("field"))) or UNNAMED_FINDING


# --- 보이는 서류·탐지 항목 ----------------------------------------------------------------------


def visible_documents(documents: Any) -> list[tuple[int, Mapping[str, Any]]]:
    """보이는 서류 (documents 안 위치, 서류) — index 순, 같은 index 는 처음 것(화면 readDocSources 와 같다)."""
    if not isinstance(documents, list):
        return []
    seen: set[int] = set()
    out: list[tuple[int, Mapping[str, Any]]] = []
    for position, doc in enumerate(documents):
        if not isinstance(doc, Mapping):
            continue
        index, start, end = doc.get("index"), doc.get("page_start"), doc.get("page_end")
        if not (_is_int(index) and index >= 0 and _is_int(start) and start >= 1 and _is_int(end) and end >= 1):
            continue
        if index in seen:
            continue
        seen.add(index)
        out.append((position, doc))
    out.sort(key=lambda pair: pair[1]["index"])
    return out


def doc_numbers(documents: Any) -> dict[int, int]:
    """보이는 서류의 index → 서류 순번(1부터)."""
    return {doc["index"]: number for number, (_, doc) in enumerate(visible_documents(documents), 1)}


@dataclass(frozen=True)
class VisibleFinding:
    """보이는 탐지 항목 하나(검토사항 재료가 쓰는 값만)."""

    id: str | None  # 계약 id(문자열이 아니면 None — 근거·항목 id 로 쓰지 않는다)
    num: str  # 표시 번호 D1-01
    name: str  # 표시 이름
    page: int  # 파일 쪽(화면 쪽 범위 안 page, 아니면 서류 page_start)
    located: bool  # 위치 있음(범위 안 page + 비지 않은 boxes)
    low: bool  # 신뢰도 low


@dataclass(frozen=True)
class BundleCheck:
    """묶음_검증 규칙 하나가 서류 하나에 내는 후보 재료(bundle_parts 가 만든다)."""

    kind: str  # 'fail'(missing:<i>:<이름>) · 'bundle'(bundle:<이름>) · 'absent'(absent:<이름>)
    name: str  # 규칙 이름(_rule_name 을 통과한 JS trim 값)
    label: str  # 글에 넣을 이름(fail: L — 대응표 label 또는 규칙 이름, absent: G — group 또는 규칙 이름). 자르기 전


@dataclass(frozen=True)
class LinkSide:
    """서류_대조 쌍의 한쪽 서류 — links[].docs[] 하나."""

    index: int
    page: int  # 파일 쪽(대조 항목의 파일 쪽, 없으면 서류 page_start)
    fields: str  # '{L} {masked}' · '{L}' · '{L} 값 없음'(MAX_LINK_FIELDS 로 자른 값)
    finding_ids: tuple[str, ...]  # 대조 항목 id(없으면 비어 있음)


@dataclass(frozen=True)
class LinkPair:
    """보이는 서류_대조 쌍 하나(link_pairs 가 만든다) — links[] 한 줄과 mismatch·weaklink 재료가 같이 쓴다."""

    id: str  # link:<기준 index>:<대상 index>
    state: str  # linked · unmatched · insufficient
    field: str  # 대조 키(추출 원래 키)
    label: str  # 대응표 label(표에 없으면 field 그대로)
    shown: str  # L = clip_name(label)
    anchor_name: str  # 기준 서류 이름(clip_name)
    target_name: str  # 대상 서류 이름(clip_name)
    anchor: LinkSide
    target: LinkSide


@dataclass(frozen=True)
class DocBundle:
    """서류 하나에 붙는 묶음 재료(findings.build_view 가 bundle_parts 로 나눠 build_items(bundle=…)에 넘긴다)."""

    checks: tuple[BundleCheck, ...] = ()  # 묶음_검증 규칙 순서
    links: tuple[LinkPair, ...] = ()  # 이 서류가 대상인 쌍(쌍 순서)


EMPTY_BUNDLE = DocBundle()


@dataclass(frozen=True)
class DocContext:
    """보이는 서류 하나의 맥락 — 재료가 받는 값."""

    index: int
    number: int  # 서류 순번(1부터)
    start: int  # page_start
    end: int  # 화면 쪽 범위 끝 = max(page_start, page_end)
    kind: Any
    verdict: Any  # documents[].validation(findings._verdict)
    checks: Any  # 검증 additional_values.checks 원래 값(없으면 None)
    findings: tuple[VisibleFinding, ...]
    bundle: DocBundle = EMPTY_BUNDLE  # 묶음 재료(최종 흐름 — 묶음_검증·서류_대조)

    def inner(self, page: int) -> int:
        """파일 쪽 → 서류 안 쪽."""
        return page - self.start + 1


def _file_page(page: Any, start: int, end: int) -> int:
    """탐지 항목의 파일 쪽 — bool 아닌 정수이고 화면 쪽 범위 안이면 그 값, 아니면 서류 page_start(상자와 무관)."""
    return page if _is_int(page) and start <= page <= end else start


def _visible_finding(finding: Mapping[str, Any], num: str, start: int, end: int) -> VisibleFinding:
    raw_id, page, boxes, confidence = finding.get("id"), finding.get("page"), finding.get("boxes"), finding.get("confidence")
    in_range = _is_int(page) and start <= page <= end
    return VisibleFinding(
        id=raw_id if isinstance(raw_id, str) else None,
        num=num,
        name=finding_name(finding),
        page=_file_page(page, start, end),
        located=in_range and isinstance(boxes, list) and len(boxes) > 0,
        low=isinstance(confidence, str) and confidence == LOW,
    )


def _doc_bundle(bundle: Any, index: int) -> DocBundle:
    """build_items(bundle=…) 의 그 서류 몫 — 모양이 틀리면 없음."""
    parts = bundle.get(index) if isinstance(bundle, Mapping) else None
    return parts if isinstance(parts, DocBundle) else EMPTY_BUNDLE


def _contexts(documents: Any, findings: Any, checks: Any, bundle: Any = None) -> list[DocContext]:
    """보이는 서류마다 맥락 — 탐지 항목은 한 번만 훑어 서류별로 나눈다."""
    visible = visible_documents(documents)
    spans: dict[int, tuple[int, int, int]] = {}  # index → (서류 순번, start, end)
    for number, (_, doc) in enumerate(visible, 1):
        start = doc["page_start"]
        spans[doc["index"]] = (number, start, max(start, doc["page_end"]))
    grouped: dict[int, list[VisibleFinding]] = {index: [] for index in spans}
    seq: dict[int, int] = {}
    for finding in findings if isinstance(findings, list) else []:
        if not isinstance(finding, Mapping):
            continue
        try:
            index = finding.get("document_index")
            if not _is_int(index) or index not in spans:
                continue
            number, start, end = spans[index]
            seq[index] = seq.get(index, 0) + 1  # 번호는 먼저 센다(reviews.review_scope 와 같은 번호)
            grouped[index].append(_visible_finding(finding, f"D{number}-{seq[index]:02d}", start, end))
        except Exception as exc:  # 그 항목만 재료에서 뺀다 — 값 없이 예외 종류만
            logger.warning("검토사항 재료에서 탐지 항목 하나를 뺌: %s", type(exc).__name__)
    raw_checks = checks if isinstance(checks, (list, tuple)) else ()
    out: list[DocContext] = []
    for position, doc in visible:
        number, start, end = spans[doc["index"]]
        out.append(
            DocContext(
                index=doc["index"],
                number=number,
                start=start,
                end=end,
                kind=doc.get("kind"),
                verdict=doc.get("validation"),
                checks=raw_checks[position] if position < len(raw_checks) else None,
                findings=tuple(grouped[doc["index"]]),
                bundle=_doc_bundle(bundle, doc["index"]),
            )
        )
    return out


# --- 검토사항 한 개의 모양 ----------------------------------------------------------------------


def _evidence(label: str, page: int, finding_ids: Sequence[str], finding_id: str | None) -> dict[str, Any]:
    return {"label": label, "page": page, "finding_ids": list(finding_ids), "finding_id": finding_id}


def _first_page(ctx: DocContext) -> dict[str, Any]:
    """서류 첫 쪽 근거(missing·verdict·other)."""
    return _evidence(OPEN_LABEL.format(p=1), ctx.start, [], None)


def _item(
    ctx: DocContext,
    kind: str,
    item_id: str,
    *,
    page: int,
    finding_id: str | None,
    title: str,
    desc: str,
    next_step: str,
    evidence: list[dict[str, Any]],
    link_id: str | None = None,
) -> dict[str, Any]:
    # number 는 모든 후보를 모은 뒤 build_items 가 채운다(키 자리는 여기서 정한다)
    return {
        "id": item_id,
        "number": "",
        "type": kind,
        "document_index": ctx.index,
        "page": page,
        "finding_id": finding_id,
        "title": title,
        "desc": desc,
        "next": next_step,
        "evidence": evidence[:MAX_EVIDENCE],
        "link_id": link_id,
    }


# --- 재료 1·1′: 검증 checks · verdict ---------------------------------------------------------------


class _Bundle:
    """묶음 단위 모양의 실패(서류 하나의 '필수 항목 없음'이 아님)."""


BUNDLE = _Bundle()


def _rule_name(raw: Any) -> str | None:
    """규칙 이름: 문자열, JS trim 뒤 1~MAX_RULE_NAME 코드 포인트, Cc·Cs 문자 없음 — 아니면 None."""
    if not isinstance(raw, str):
        return None
    name = js_trim(raw)
    if not 1 <= len(name) <= MAX_RULE_NAME:
        return None
    if any(unicodedata.category(char) in ("Cc", "Cs") for char in name):
        return None
    return name


def mapped_label(field: Any) -> str | None:
    """conditions.left.field 가 대응표 키면 그 label, 아니면 None."""
    if not isinstance(field, str):
        return None
    info = field_info(field)
    return info.label if info.mapping_status != "unknown" else None


def failed_rule(check: Any) -> tuple[str, str] | _Bundle | None:
    """check 하나 → 서류 단위 실패 규칙 (이름, 이름표 L) · 묶음 모양 실패 BUNDLE · 그 밖(통과·모양 틀림) None."""
    if not isinstance(check, Mapping) or check.get("passed") is not False:
        return None  # 객체 아님·passed 가 bool 아님(문자열 'false'·0·null 포함)·통과
    conditions = check.get("conditions")
    left = conditions.get("left") if isinstance(conditions, Mapping) else None
    if isinstance(left, Mapping) and "value" in left and (left["value"] is None or isinstance(left["value"], list)):
        return BUNDLE
    name = _rule_name(check.get("name"))
    if name is None:
        return None
    label = mapped_label(left.get("field") if isinstance(left, Mapping) else None)
    return name, label if label is not None else name


def failed_rules(checks: Any) -> tuple[list[tuple[str, str]], bool]:
    """checks 원래 값 → (서류 단위 실패 규칙 [(이름, L)] — 같은 이름은 처음 것, 묶음 모양 실패 있음)."""
    if not isinstance(checks, list):
        return [], False
    rules: list[tuple[str, str]] = []
    names: set[str] = set()
    bundle = False
    for check in checks[:MAX_CHECKS]:
        try:
            rule = failed_rule(check)
        except Exception as exc:  # 그 check 만 건너뛴다
            logger.warning("검증 규칙 하나를 읽지 못해 건너뜀: %s", type(exc).__name__)
            continue
        if rule is None:
            continue
        if isinstance(rule, _Bundle):
            bundle = True
            continue
        if rule[0] in names:
            continue
        names.add(rule[0])
        rules.append(rule)
    return rules, bundle


def verdict_failed(verdict: Any) -> bool:
    """verdict 가 문자열이고 앞뒤 공백을 지운 소문자가 비지 않고 'green' 이 아니면 True."""
    if not isinstance(verdict, str):
        return False
    key = js_trim(verdict).strip().lower()
    return bool(key) and key != GREEN


def _missing_item(ctx: DocContext, name: str, label: str) -> dict[str, Any]:
    shown = clip_name(label)
    return _item(
        ctx,
        "missing",
        f"missing:{ctx.index}:{name}",
        page=ctx.start,
        finding_id=None,
        title=f"{shown}{subject_particle(shown)} 없습니다",
        desc=MISSING_DESC,
        next_step=MISSING_NEXT,
        evidence=[_first_page(ctx)],
    )


def _verdict_item(ctx: DocContext) -> dict[str, Any]:
    return _item(
        ctx,
        "missing",
        f"verdict:{ctx.index}",
        page=ctx.start,
        finding_id=None,
        title=VERDICT_TITLE,
        desc=VERDICT_DESC,
        next_step=VERDICT_NEXT,
        evidence=[_first_page(ctx)],
    )


def _from_checks(ctx: DocContext) -> list[Maker]:
    rules, bundle = failed_rules(ctx.checks)
    makers: list[Maker] = [partial(_missing_item, ctx, name, label) for name, label in rules]
    if not rules and not bundle and verdict_failed(ctx.verdict):
        makers.append(partial(_verdict_item, ctx))
    return makers


# --- 재료 B: 묶음_검증(최종 흐름) --------------------------------------------------------------------


def _bundle_item(ctx: DocContext, part: BundleCheck) -> dict[str, Any] | None:
    if part.kind == "fail":
        return _missing_item(ctx, part.name, part.label)
    if part.kind == "bundle":
        return _item(
            ctx,
            "missing",
            f"bundle:{part.name}",
            page=ctx.start,
            finding_id=None,
            title=VERDICT_TITLE,
            desc=VERDICT_DESC,
            next_step=VERDICT_NEXT,
            evidence=[_first_page(ctx)],
        )
    if part.kind == "absent":
        shown = clip_name(part.label)
        return _item(
            ctx,
            "missing",
            f"absent:{part.name}",
            page=ctx.start,
            finding_id=None,
            title=f"{shown}{subject_particle(shown)} 없습니다",
            desc=ABSENT_DESC,
            next_step=ABSENT_NEXT,
            evidence=[_first_page(ctx)],
        )
    return None


def _from_bundle_checks(ctx: DocContext) -> list[Maker]:
    return [partial(_bundle_item, ctx, part) for part in ctx.bundle.checks]


# --- 재료 L: 서류_대조(최종 흐름) --------------------------------------------------------------------


def _link_item(ctx: DocContext, pair: LinkPair) -> dict[str, Any] | None:
    if pair.target.index != ctx.index:
        return None  # 대상 서류의 재료만(근거가 그 서류 안을 가리키게)
    anchor, target = pair.anchor.index, pair.target.index
    shown = pair.shown
    if pair.state == LINK_UNMATCHED:
        side = pair.target
        if side.finding_ids and ctx.start <= side.page <= ctx.end:
            evidence = [_evidence(VALUES_LABEL.format(p=ctx.inner(side.page)), side.page, side.finding_ids, None)]
        else:
            evidence = [_first_page(ctx)]
        return _item(
            ctx,
            "mismatch",
            f"mismatch:{anchor}:{target}",
            page=evidence[0]["page"],
            finding_id=None,
            title=f"{pair.anchor_name}{with_particle(pair.anchor_name)} {shown}{subject_particle(shown)} 다릅니다",
            desc=MISMATCH_DESC,
            next_step=LINK_NEXT,
            evidence=evidence,
            link_id=pair.id,
        )
    if pair.state == LINK_INSUFFICIENT:
        return _item(
            ctx,
            "weaklink",
            f"weaklink:{anchor}:{target}",
            page=ctx.start,
            finding_id=None,
            title=WEAKLINK_TITLE,
            desc=LINK_NOTHING.format(label=shown, p=subject_particle(shown)),
            next_step=LINK_NEXT,
            evidence=[_first_page(ctx)],
            link_id=pair.id,
        )
    return None  # linked 는 검토사항이 아니다


def _from_links(ctx: DocContext) -> list[Maker]:
    return [partial(_link_item, ctx, pair) for pair in ctx.bundle.links]


# --- 묶음 재료 나누기(findings.build_view 가 부른다) ------------------------------------------------


def _bundle_check_parts(check: Any, visible: set[int], first: int) -> list[tuple[int, BundleCheck]]:
    """final_flow.read_bundle_checks 의 규칙 하나 → [(서류 index, 후보 재료)]. 만들지 않는 규칙은 []."""
    if not isinstance(check, Mapping):
        return []
    name = _rule_name(check.get("name"))
    if name is None:
        return []
    status = check.get("status")
    if status == CHECK_FAIL:
        documents = check.get("documents")
        if documents is None:
            return [(first, BundleCheck("bundle", name, name))]
        if not isinstance(documents, list):
            return []
        label = mapped_label(check.get("field"))
        part = BundleCheck("fail", name, label if label is not None else name)
        out: list[tuple[int, BundleCheck]] = []
        for document in documents:
            if not isinstance(document, Mapping) or document.get("ok") is not False:
                continue
            index = document.get("index")
            if _is_int(index) and index in visible:
                out.append((index, part))  # 같은 서류가 또 나오면 같은 계약 id — build_items 가 처음 것만 둔다
        return out
    if status == CHECK_ABSENT and check.get("severity") == SEVERITY_ERROR:
        group = check.get("group")
        return [(first, BundleCheck("absent", name, group if isinstance(group, str) and js_trim(group) else name))]
    return []  # warning·absent(그 종류 서류가 없을 뿐), pass, unknown


def bundle_parts(documents: Any, bundle_checks: Any, pairs: Iterable[LinkPair] = ()) -> dict[int, DocBundle]:
    """read_bundle_checks 결과와 link_pairs 쌍 → 보이는 서류 index → DocBundle(build_items(bundle=…) 의 값).

    규칙 하나·쌍 하나를 나누다 실패하면 그것만 버린다(값 없는 경고). 규칙은 앞 MAX_CHECKS 개만 본다.
    """
    visible = [doc["index"] for _, doc in visible_documents(documents)]
    if not visible:
        return {}
    shown, first = set(visible), visible[0]
    checks: dict[int, list[BundleCheck]] = {}
    raw = bundle_checks.get("checks") if isinstance(bundle_checks, Mapping) else None
    for check in raw[:MAX_CHECKS] if isinstance(raw, list) else []:
        try:
            for index, part in _bundle_check_parts(check, shown, first):
                checks.setdefault(index, []).append(part)
        except Exception as exc:  # 그 규칙만
            logger.warning("묶음 검증 규칙 하나를 나누지 못해 건너뜀: %s", type(exc).__name__)
    links: dict[int, list[LinkPair]] = {}
    for pair in pairs:
        if isinstance(pair, LinkPair) and pair.state != LINK_LINKED and pair.target.index in shown:
            links.setdefault(pair.target.index, []).append(pair)
    return {
        index: DocBundle(checks=tuple(checks.get(index, ())), links=tuple(links.get(index, ())))
        for index in visible
        if index in checks or index in links
    }


# --- 서류_대조 쌍과 화면용 links[] ------------------------------------------------------------------------


@dataclass(frozen=True)
class _Hit:
    """서류 하나에서 대조 키(field)가 같은 첫 보이는 탐지 항목."""

    id: str
    masked: Any
    page: int  # 파일 쪽


def _field_hits(visible: Mapping[int, Mapping[str, Any]], findings: Any, field: str) -> dict[int, _Hit]:
    """보이는 서류마다 field 가 같은 첫 탐지 항목(계약 순서, id 가 문자열인 것) — 탐지 항목을 한 번만 훑는다."""
    hits: dict[int, _Hit] = {}
    for finding in findings if isinstance(findings, list) else []:
        if not isinstance(finding, Mapping):
            continue
        try:
            index = finding.get("document_index")
            if not _is_int(index) or index not in visible or index in hits:
                continue
            raw_id = finding.get("id")
            if not isinstance(raw_id, str) or finding.get("field") != field:
                continue
            doc = visible[index]
            start = doc["page_start"]
            hits[index] = _Hit(id=raw_id, masked=finding.get("masked"), page=_file_page(finding.get("page"), start, max(start, doc["page_end"])))
        except Exception as exc:  # 그 항목만
            logger.warning("서류 대조 항목 하나를 읽지 못해 건너뜀: %s", type(exc).__name__)
    return hits


def _doc_name(doc: Mapping[str, Any], names: Mapping[str, str]) -> str:
    """서류 이름 — 분류 코드의 짧은 이름(모르는 코드는 코드 그대로), clip_name."""
    code = doc.get("type")
    if not isinstance(code, str):
        return ""
    name = names.get(code)
    return clip_name(name if isinstance(name, str) else code)


def _side(doc: Mapping[str, Any], hit: _Hit | None, shown: str) -> LinkSide:
    if hit is None:
        return LinkSide(index=doc["index"], page=doc["page_start"], fields=clip_text(LINK_NO_VALUE.format(label=shown), MAX_LINK_FIELDS), finding_ids=())
    # 원문 value 는 쓰지 않는다(masked 만). 아주 긴 masked 도 MAX_LINK_FIELDS 자만 붙여 자른다(앞 79자는 같다)
    text = f"{shown} {hit.masked[:MAX_LINK_FIELDS]}" if isinstance(hit.masked, str) else shown
    return LinkSide(index=doc["index"], page=hit.page, fields=clip_text(text, MAX_LINK_FIELDS), finding_ids=(hit.id,))


def link_pairs(documents: Any, findings: Any, links: Any, names: Mapping[str, str]) -> list[LinkPair]:
    """final_flow.read_links 결과 → 보이는 쌍(쌍 순서). names = 분류 코드 → 짧은 이름(final_flow.FINAL_DOC_TYPES).

    기준 서류가 없거나(anchor_index None)·pairs 가 None·field 가 없으면 []. 기준·대상 서류가 둘 다 보이는 서류이고
    상태가 알려진 값인 쌍만, 같은 대상 서류는 첫 쌍만. 쌍 하나를 만들다 실패하면 그 쌍만 버린다(값 없는 경고).
    """
    if not isinstance(links, Mapping):
        return []
    anchor_index, pairs, field = links.get("anchor_index"), links.get("pairs"), links.get("field")
    if not _is_int(anchor_index) or not isinstance(pairs, list) or not isinstance(field, str) or not field:
        return []
    visible = {doc["index"]: doc for _, doc in visible_documents(documents)}
    anchor_doc = visible.get(anchor_index)
    if anchor_doc is None:
        return []
    label = field_info(field).label
    shown = clip_name(label)
    hits = _field_hits(visible, findings, field)
    anchor_side = _side(anchor_doc, hits.get(anchor_index), shown)
    anchor_name = _doc_name(anchor_doc, names)
    out: list[LinkPair] = []
    seen: set[int] = set()
    for pair in pairs:
        try:
            if not isinstance(pair, Mapping):
                continue
            target, state = pair.get("target_index"), pair.get("status")
            if not _is_int(target) or target == anchor_index or target in seen or target not in visible:
                continue
            if not isinstance(state, str) or state not in LINK_STATES:
                continue
            seen.add(target)
            doc = visible[target]
            out.append(
                LinkPair(
                    id=f"link:{anchor_index}:{target}",
                    state=state,
                    field=field,
                    label=label,
                    shown=shown,
                    anchor_name=anchor_name,
                    target_name=_doc_name(doc, names),
                    anchor=anchor_side,
                    target=_side(doc, hits.get(target), shown),
                )
            )
        except Exception as exc:  # 그 쌍만
            logger.warning("서류 대조 쌍 하나를 읽지 못해 건너뜀: %s", type(exc).__name__)
    return out


def _link_doc(side: LinkSide) -> dict[str, Any]:
    return {"document_index": side.index, "page": side.page, "fields": side.fields, "finding_ids": list(side.finding_ids)}


def link_view(pair: LinkPair, number: int) -> dict[str, Any]:
    """쌍 하나 → links[] 한 줄(LINK_KEYS 순서). number = 결과 안 순서(1부터)."""
    p = subject_particle(pair.shown)
    if pair.state == LINK_LINKED:
        basis, missing, check = [LINK_SAME.format(label=pair.shown, p=p)], "", LINK_CHECK_LINKED
    elif pair.state == LINK_UNMATCHED:
        basis, missing, check = [], LINK_DIFFERENT.format(label=pair.shown, p=p), LINK_NEXT
    else:
        basis, missing, check = [], LINK_NOTHING.format(label=pair.shown, p=p), LINK_NEXT
    return {
        "id": pair.id,
        "number": f"L-{number:02d}",
        "status": LINK_CONFIRMED if pair.state == LINK_LINKED else LINK_CHECK,
        "state": pair.state,
        "title": f"{pair.anchor_name} · {pair.target_name}",
        "field": pair.field,
        "label": pair.label,
        "docs": [_link_doc(pair.anchor), _link_doc(pair.target)],
        "basis": basis,
        "missing": missing,
        "check": check,
    }


def build_links(pairs: Iterable[LinkPair]) -> list[dict[str, Any]]:
    """link_pairs 쌍 → 화면용 links[]. 한 줄을 만들다 실패하면 그 줄만 버리고 번호는 남은 줄로 이어 매긴다."""
    rows: list[dict[str, Any]] = []
    for pair in pairs:
        try:
            rows.append(link_view(pair, len(rows) + 1))
        except Exception as exc:  # 그 줄만
            logger.warning("문서 간 연결 한 줄을 만들지 못해 건너뜀: %s", type(exc).__name__)
    return rows


# --- 재료 2: 위치 없는 탐지 항목 ------------------------------------------------------------------


def _nolocation_item(ctx: DocContext, finding: VisibleFinding) -> dict[str, Any] | None:
    if finding.id is None:
        return None
    return _item(
        ctx,
        "nolocation",
        f"nolocation:{finding.id}",
        page=finding.page,
        finding_id=finding.id,
        title=NOLOCATION_TITLE,
        desc=NOLOCATION_DESC.format(num=finding.num, name=clip_name(finding.name)),
        next_step=NOLOCATION_NEXT,
        evidence=[_evidence(OPEN_LABEL.format(p=ctx.inner(finding.page)), finding.page, [finding.id], finding.id)],
    )


def _from_unlocated(ctx: DocContext) -> list[Maker]:
    return [partial(_nolocation_item, ctx, finding) for finding in ctx.findings if not finding.located]


# --- 재료 3: 인식 신뢰도 low -------------------------------------------------------------------------


def _lowconf_item(ctx: DocContext, low: Sequence[VisibleFinding]) -> dict[str, Any]:
    count = len(low)
    nums = ", ".join(f.num for f in low[:MAX_NUMS]) + (f" 외 {count - MAX_NUMS}건" if count > MAX_NUMS else "")
    pages: dict[int, list[str]] = {}
    for finding in low:
        if finding.located and finding.id is not None:
            pages.setdefault(finding.page, []).append(finding.id)
    first = heapq.nsmallest(MAX_EVIDENCE, pages)  # 쪽 오름차순 앞 20쪽(전체 정렬 없이)
    evidence = [_evidence(VALUES_LABEL.format(p=ctx.inner(page)), page, pages[page], None) for page in first]
    return _item(
        ctx,
        "lowconf",
        f"lowconf:{ctx.index}",
        page=evidence[0]["page"] if evidence else ctx.start,
        finding_id=None,
        title=LOWCONF_TITLE.format(n=count),
        desc=LOWCONF_DESC.format(nums=nums),
        next_step=LOWCONF_NEXT,
        evidence=evidence,
    )


def _from_low_confidence(ctx: DocContext) -> list[Maker]:
    low = [finding for finding in ctx.findings if finding.low]
    return [partial(_lowconf_item, ctx, low)] if low else []


# --- 재료 4: 기타 서류 -------------------------------------------------------------------------------


def _other_item(ctx: DocContext) -> dict[str, Any]:
    return _item(
        ctx,
        "other",
        f"other:{ctx.index}",
        page=ctx.start,
        finding_id=None,
        title=OTHER_TITLE,
        desc=OTHER_DESC,
        next_step=OTHER_NEXT,
        evidence=[_first_page(ctx)],
    )


def _from_other_kind(ctx: DocContext) -> list[Maker]:
    return [partial(_other_item, ctx)] if isinstance(ctx.kind, str) and ctx.kind == OTHER_KIND else []


# --- 재료 목록(한 자리) -------------------------------------------------------------------------------

@dataclass(frozen=True)
class Material:
    name: str  # 로그용 고정 이름(값 아님)
    type: str  # 만드는 종류(ITEM_TYPES 키 — links 는 mismatch 와 weaklink 둘을 만든다)
    make: Callable[[DocContext], Iterable[Maker]]


# 종류 순서 = 이 목록의 순서(서류마다 차례로 돈다). 새 재료는 머리 주석 '새 재료를 더하는 법'을 따른다.
MATERIALS: tuple[Material, ...] = (
    Material("checks", "missing", _from_checks),  # 1 · 1′
    Material("bundle_checks", "missing", _from_bundle_checks),  # B1 · B1′ · B2
    Material("links", "mismatch", _from_links),  # L1 · L2(weaklink)
    Material("nolocation", "nolocation", _from_unlocated),  # 2
    Material("lowconf", "lowconf", _from_low_confidence),  # 3
    Material("other", "other", _from_other_kind),  # 4
)


def build_items(documents: Any, findings: Any, checks: Any = None, bundle: Any = None) -> list[dict[str, Any]]:
    """화면용 documents·findings + 서류별 checks 원래 값(documents 와 같은 위치, 없으면 None) + 묶음 재료
    (bundle — bundle_parts 의 서류 index → DocBundle, 없으면 None) → result.items[].

    후보 하나·재료 하나의 예외는 그것만 버린다(값 없는 경고). 맥락 만들기가 실패하면 [](값 없는 경고) — 부르는 쪽
    (findings.build_view)도 한 번 더 받는다.
    """
    try:
        contexts = _contexts(documents, findings, checks, bundle)
    except Exception as exc:
        logger.warning("검토사항 맥락을 만들지 못해 비웁니다: %s", type(exc).__name__)
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ctx in contexts:
        for material in MATERIALS:
            try:
                makers = list(material.make(ctx))
            except Exception as exc:  # 그 서류의 그 재료만 버린다
                logger.warning("검토사항 재료 하나를 읽지 못해 건너뜀: %s (%s)", material.name, type(exc).__name__)
                continue
            for make in makers:
                try:
                    item = make()
                except Exception as exc:  # 그 후보만 버린다
                    logger.warning("검토사항 하나를 만들지 못해 건너뜀: %s (%s)", material.name, type(exc).__name__)
                    continue
                if item is None or item["id"] in seen:
                    continue
                seen.add(item["id"])
                out.append(item)
    for number, item in enumerate(out, 1):
        item["number"] = f"R-{number:02d}"
    return out
