# ==========================================================================
#  최종 흐름(final_imask_workflow, 설정 "1") 응답의 새 재료 읽기 — 순수 함수(아직 어디에도 연결하지 않는다)
#  입력은 results.parse_stages(response) 의 결과(stages, 응답 Mapping 을 줘도 parse_stages 로 바꾼다).
#  모양: final-flow/evidence/T0/final-shapes.md
#  - FINAL_DOC_TYPES: 분류 코드 → (한국어 이름, 묶음). 앞 14개(옛 설정, Other 까지)의 순서는 설정의 분류 oneOf 와 같다(테스트가
#    확인). 묶음은 추출 노드 이름 "추출_<묶음>" 의 <묶음>(신청서·확인서·증빙·위임장), Other 는 None. 뒤 10개는 설정 60(v2_full)의
#    서식 코드(묶음 None, 아래 '설정 60').
#  - read_decision(stages): 위험도_판정 본문의 "키: 값" 줄(미션 2 정답지 키 5개). 등급의 기준은 여전히
#    additional_values.enum(results.summarize) — 여기 risk_level 은 '본문에 적힌 값'이다.
#  - read_bundle_checks(stages): 묶음_검증의 verdict 와 규칙별 결과(pass·fail·absent·unknown, 서류별 ok).
#  - read_links(stages): 서류_대조의 기준 서류와 대상 서류 쌍(linked·unmatched·insufficient).
#  공통 규칙
#  - 단계는 status 가 completed(또는 없음)인 **첫** 항목만 본다. 단계가 없으면(옛 워크플로우) None.
#  - 바깥 모양이 틀려도 예외 없이 그 항목만 버리고, 못 읽은 값은 None — 확인된 빈 목록 [] 과 섞지 않는다.
#    그래도 예상 못 한 예외가 나면 값 없는 경고 로그를 남기고 None(나중에 build_view 전체가 비지 않게).
#  - 원문 값(추출 값·anchor_value·target_values·검증 reason·conditions 의 값)은 결과에 넣지 않는다 — 화면은
#    탐지 항목 id("<서류 index>:<추출 키>")로 값을 찾는다.
#  - 서류 번호 index 는 findings 의 서류 번호와 같다(findings._documents — 분류 contents 순서, 0부터).
#    어느 추출 노드로 간 서류인지는 병합-1 data.source_steps 의 step_name·branch_key("<index>:<코드>") 순서로 안다
#    (분류 서류가 아닌 index·같은 서류의 두 번째 항목은 버린다).
#  - 한도(아래 상수)를 넘는 값·목록은 자르지 않고 버린다. 짝 없는 서로게이트가 든 문자열도 버린다(textsafe) —
#    원문뿐 아니라 **푼 뒤의 값**도 본다(JSON escape "\ud800" 이 풀리면 서로게이트가 된다). 마지막 안전망으로 결과 어디에든
#    남아 있으면 결과 전체를 None(결과는 늘 UTF-8 로 인코딩된다).
#    모든 처리는 입력 길이에 선형이다(정규식은 고정 글자로 시작하거나 줄 처음에 고정). findings 의 추출 짝짓기를 쓰는
#    read_links 는 서류·추출 개수 한도 안에서만 짝짓는다(MAX_LINK_DOCUMENTS·MAX_LINK_EXTRACTS).
#
#  설정 60(v2_full) 응답 — 옛 응답은 아래 함수가 None 이고 옛 함수는 그대로다. 모양 구별은 results.is_v2(여기서도 is_v2 로 부른다):
#  - read_verdict(stages): 노드 이름이 판정_ 으로 시작하는 Instruct(지금 없는 판정_하 도), completed(또는 상태 없음)인 첫 항목. 본문이
#    객체일 때만 키 8개(V2_DECISION_KEYS 순서). risk_level 은 상·중·하·검토 필요만, 글은 인용 표시를 지우고 길이 2000 초과면 None,
#    목록은 문자열 목록만(문자열 아닌 항목·서로게이트가 있거나 V2_MAX_DECISION_ITEMS 개를 넘으면 그 키 None, 자르지 않는다). [] 은 [].
#    표시되는 항목의 원천은 Extract 다 — 목록 3키는 응답의 출력으로 그대로 보존한다(차이는 findings 가 개수만 경고).
#  - read_chain(stages): 검증 사슬 {verdict, checks[{id, name, severity, status, field, label, group}]}. 통과 규칙은 넣지 않는다(실패·
#    unknown 만, 사슬 순서 — 응답을 키우지 않게). group = 노드 이름, field = 조건 트리의 첫 칸 키(조건마다 왼쪽 → 오른쪽 순서, rowField 가
#    있으면 그 값), label = 그 칸의 이름(대응표에 없으면 None), 같은 이름은 _UniqueIds. 상_확인 은 넣지 않는다(red 는 실패가 아니라 상 칸이 없다는 뜻).
#    내용_검토 enum 이 내용 모순·조건부 누락이면 내용_검토 규칙 하나를 더하고 verdict 를 red 로 친다(본문은 읽지 않는다 — 원문 값).
#    verdict: 도는 노드(상_확인 제외) 중 red 또는 내용_검토 실패 → red, 아니고 yellow → yellow, 하나 이상 읽었고 모두 green → green,
#    못 읽으면 None. reason·conditions 의 value 는 넣지 않는다. 조건 트리는 반복문·깊이 한도로 훑고, 노드당 규칙은 MAX_CHECKS 까지.
#  - read_chain_rules(stages): 위와 같은 읽기의 재료 — 규칙마다 items.ChainRule(규칙이 가리키는 서식 코드·대응표 이름이 있는 첫 칸을
#    더해 검토사항이 쓴다). findings 는 이것을 한 번 읽어 chain_view 로 bundle_check 를 만든다.
#  - read_v2_links(stages): Extract 값으로 서류 연결을 계산한다(Match 가 없다) — read_links 와 같은 모양(field·anchor_index·pairs) + 기존
#    items.link_pairs 가 쓰는 doc_fields(서류 index → 그 서류의 비교 칸 키)·label(고정 '본인 성명').
#    서류 = 분류 순서의 10서식 서류(Other 제외). 서식이 1종 이하면 연결 없음. 기준 = 본인 칸(V2_SELF_NAMES) 값이 비지 않은 첫 서류
#    (가림 기호가 없는 값을 먼저 — 아래 v6).
#    비었는지는 일치_확인 의 [?@](JMESPath 참/거짓)와 같다 — 빈 문자열·null·빈 목록·빈 객체·false 만 빈 값, 공백만인 문자열은 값이고
#    공백을 정리하지 않는다. 문자열이 아닌 값은 비교할 수 없어 insufficient. 위임장_상속은 늘 insufficient, 지급보증거래_신청서는
#    신청인 성명에 기준 값이 들어 있으면 linked, 나머지는 값이 정확히 같으면 linked, 대상 칸이 비거나 추출이 없으면 insufficient.
#    지급보증 칸에 기준 값이 없을 때: 묶음에 소비자피해보상금_지급신청서·외국인_세대구성원_확인서가 둘 다 없으면(분류 코드 기준) 일치_확인 에 지급보증을
#    비교하는 규칙이 없어 판정과 어긋나지 않게 insufficient, 둘 중 하나라도 있으면 그 규칙이 도니 unmatched 다.
#
#  v6(가림_확인·결합_확인이 있는 응답 — 없는 응답은 아래 규칙이 걸릴 값이 없어 결과가 그대로다):
#  - 사슬(read_chain_rules·read_chain)은 results.V2_CHAIN 순서(대상 → 단위 → 필수 → 형식 → 가림 → 일치 → 결합). 단계는 이름(" - " 뒤 노드 이름)으로
#    찾으므로 저장된 key 가 필수항목_검증 이어도 같다. 갈래 단계(등급_*·IRP해지_확인·납세자번호_확인·상_확인)는 읽지 않는다.
#    결합_확인 두 규칙은 field null(조건 트리 첫 칸은 규칙의 대상 칸이 아니다)·label 은 사유 이름 V6_LINKAGE_LABELS(가린이름_연락처_결합_없음
#    '서류 간 정보 결합', 가린이름_식별정보_없음 '재식별 위험'). read_linkage_passed(stages): error 규칙이 명시적으로(passed 정확히 true) 통과했는지 —
#    사슬 읽기는 통과 규칙을 버리므로 이 사실만 따로 읽어 검토사항 reident 의 조건으로 넘긴다(findings → items.v2_parts).
#  - 가린 이름(MASK_MARKS 10개 — 서류간_본인성명_같음 이 비교에서 빼는 글자): read_v2_links 의 기준 = 본인 성명이 비지 않고 가림 기호가 없는 첫 서식,
#    없으면 본인 성명이 비지 않은 첫 서식. 비교까지 갔을 쌍(기준·대상 값이 모두 비지 않은 문자열)에서 어느 쪽이든 가림 기호가 있으면 insufficient 이고
#    pairs[].masked True(지급보증 칸도 같다). 위임장·추출 없음·빈 값·문자열 아님은 기존 판정이 먼저다(masked False — 코디네이터 Q2).
#    가림 여부는 서류마다 비교 칸 값에 한 번만 계산해 기준 고르기·쌍 계산이 같이 쓴다(쌍마다 기준 이름을 다시 훑지 않는다 — 이름 글자 합 + 서류 수에 선형).
#    pairs[].contains = 지급보증거래_신청서 쌍(포함으로 비교 — 화면 글이 '들어 있다/없다'). 옛 read_links 의 pairs 에는 두 키가 없다.
#  - masked_name_fields(docs): 결합_확인 두 규칙이 서식마다 보는 이름 칸 V6_MASKED_NAMES(v6_cfg.json 의 `matches [^*…]*` 피연산자 — 자동이체 중_예금주_성명,
#    휴면 중_원권리자_성명, FATCA 중_예금주_성명, 소비자피해 중_신청인_성명, 체크카드 중_성명_한글, IRP 해지·신규 중_가입자명. 외국인 세대구성원 확인서는
#    규칙이 보지 않는다) 값에 가림 기호가 든 서류 index → 그 칸 키 — 검토사항 linkage·reident 를 붙일 '가린 이름 서류'(items.v2_parts).
# ==========================================================================

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Any

from .fields import v2_field_info
from .findings import _attach_extracts, _documents, _ranges, jmes_empty
from .items import ChainRule, js_trim
from .results import (
    STAGE_BUNDLE_CHECK,
    STAGE_EXTRACT,
    STAGE_MATCH,
    STAGE_MERGE,
    STAGE_RISK,
    STAGE_V2_CONTENT,
    STAGE_V2_LINKAGE,
    STAGE_V2_VERDICT,
    V2_CHAIN,
    V2_FORM_CODES,
    as_stages,
    is_v2,
    usable_stages_for,
)
from .textsafe import has_unpaired_surrogates, text_is_safe

logger = logging.getLogger("imask.final_flow")

# --- 서류 종류와 묶음 -------------------------------------------------------------------

GROUP_APPLICATION = "신청서"
GROUP_CONFIRMATION = "확인서"
GROUP_PROOF = "증빙"
GROUP_ATTORNEY = "위임장"
GROUPS = (GROUP_APPLICATION, GROUP_CONFIRMATION, GROUP_PROOF, GROUP_ATTORNEY)
# 검증 규칙의 nodeName("추출_신청서")과 응답 단계 이름("Information Extract - 추출_신청서")의 앞부분
EXTRACT_NODE_PREFIX = "추출_"
EXTRACT_STEP_PREFIX = "Information Extract - "

# 분류 코드 → (짧은 한국어 이름, 묶음). 기존 5개 이름은 화면 src/display/rules.ts DOC_TYPE_NAMES 와 같다
FINAL_DOC_TYPES: dict[str, tuple[str, str | None]] = {
    "loan_application": ("대출신청서", GROUP_APPLICATION),
    "consent_form": ("동의서", GROUP_CONFIRMATION),
    "income_proof": ("소득 증빙", GROUP_PROOF),
    "power_of_attorney": ("위임장", GROUP_ATTORNEY),
    "debt_transaction": ("채무내역", GROUP_PROOF),
    "payment_guarantee_application": ("지급보증거래 신청서", GROUP_APPLICATION),
    "consumer_compensation_claim": ("소비자피해보상금 지급신청서", GROUP_APPLICATION),
    "foreign_household_confirmation": ("외국인 세대구성원 확인서", GROUP_CONFIRMATION),
    "debit_card_application": ("체크카드 가입신청서", GROUP_APPLICATION),
    "auto_transfer_application": ("자동이체 신청서", GROUP_APPLICATION),
    "dormant_deposit_claim": ("휴면예금 지급신청서", GROUP_APPLICATION),
    "fatca_crs_certification": ("FATCA/CRS 본인확인서", GROUP_CONFIRMATION),
    "retirement_pension_application": ("퇴직연금 신청서", GROUP_APPLICATION),
    "Other": ("기타", None),
    # 설정 60(v2_full)의 서식 코드(results.V2_FORM_CODES 와 같은 순서 — 추출 노드가 서식마다 하나라 묶음이 없다)
    "자동이체신청서": ("자동이체 신청서", None),
    "휴면예금지급신청서": ("휴면예금 지급신청서", None),
    "FATCA_CRS_본인확인서": ("FATCA/CRS 본인확인서", None),
    "위임장_상속": ("상속예금 위임장", None),
    "지급보증거래_신청서": ("지급보증거래 신청서", None),
    "소비자피해보상금_지급신청서": ("소비자피해보상금 지급신청서", None),
    "외국인_세대구성원_확인서": ("외국인 세대구성원 확인서", None),
    "체크카드_가입신청서": ("체크카드 가입신청서", None),
    "IRP_계약해지신청서": ("IRP 계약해지신청서", None),
    "IRP_신규신청서": ("IRP 신규신청서", None),
}

# --- 한도 -------------------------------------------------------------------------------

# 이름·식별자(검증 규칙 이름, 필드 이름, 대조 키) 길이
MAX_NAME_LENGTH = 200
# 병합-1 source_steps 항목 수(넘으면 서류 경로를 모르는 것으로 본다)
MAX_SOURCE_STEPS = 1000
# branch_key 앞의 서류 번호 자릿수(아주 긴 숫자 문자열을 int 로 바꾸지 않게)
MAX_INDEX_DIGITS = 6
# 묶음_검증 checks 항목 수
MAX_CHECKS = 200
# 서류_대조 targets·matched 항목 수
MAX_LINK_TARGETS = 50
MAX_MATCHED = 1000
# 서류_대조 쌍을 만들 때 대상 서류의 추출 항목을 findings 와 같은 짝짓기(_attach_extracts)로 붙인다. 그 짝짓기는
# 추출마다 서류 목록 전체를 훑고 짝 없는 추출을 목록에 덧붙여 (추출 수 × (서류 수 + 추출 수)) 시간이 든다 —
# 분류 서류 수와 쓸 수 있는 추출 단계 수가 한도를 넘으면 짝짓기 전에 pairs 를 None 으로 둔다(일부만 잘라 잇지 않는다).
# 실제 묶음은 서류 수십 개 안쪽이고, 추출은 서류마다 하나다(MAX_SOURCE_STEPS 1000 과 같은 폭).
MAX_LINK_DOCUMENTS = 500
MAX_LINK_EXTRACTS = 1000
# 위험도_판정 본문: 읽는 줄 수, 값 길이(인용 표시를 지운 뒤), 목록 항목 수·항목 길이
MAX_DECISION_LINES = 200
MAX_DECISION_VALUE_LENGTH = 2000
MAX_DECISION_ITEMS = 50
MAX_DECISION_ITEM_LENGTH = 100
# 열거 값(verdict·severity)으로 볼 최대 길이
_MAX_ENUM_LENGTH = 32
# 설정 60 판정 목록 항목 수(넘으면 그 키 None — 실측 최대 38개, 옛 50 한도는 묶음에서 넘을 수 있다)
V2_MAX_DECISION_ITEMS = 500
# 조건 트리를 훑는 한도(규칙 하나) — 넘는 부분은 보지 않는다
MAX_TREE_DEPTH = 32
MAX_TREE_NODES = 1000
# 규칙 path 에서 서식 코드를 찾는 앞부분 길이
MAX_PATH_SCAN = 20_000

# --- 값 -------------------------------------------------------------------------------

VERDICTS = ("green", "yellow", "red")
SEVERITIES = ("error", "warning")
CHECK_PASS = "pass"
CHECK_FAIL = "fail"
CHECK_ABSENT = "absent"  # 그 종류 서류가 묶음에 없음('필수 항목 없음'이 아니다)
CHECK_UNKNOWN = "unknown"
LINK_LINKED = "linked"
LINK_UNMATCHED = "unmatched"
LINK_INSUFFICIENT = "insufficient"  # 근거 부족 — 기준 서류 없음·빈 값끼리의 '일치' 등
# 기준 서류를 못 찾았을 때 쌍 id 의 기준 자리
NO_ANCHOR = "-"

DECISION_KEYS = ("risk_level", "document_types", "sensitive_categories", "review_reasons", "reason")
DECISION_LIST_KEYS = frozenset({"document_types", "sensitive_categories", "review_reasons"})
DECISION_LEVELS = ("상", "중", "하", "검토 필요")
V2_DECISION_LIST_KEYS = frozenset(
    {"document_types", "high_risk_items", "medium_risk_items", "low_risk_items", "review_reasons"}
)
V2_DECISION_KEYS = (
    "risk_level",
    "document_types",
    "high_risk_items",
    "medium_risk_items",
    "low_risk_items",
    "review_reasons",
    "recommended_action",
    "reason",
)
# 내용_검토 enum 중 실패(판정으로 간다)
V2_CONTENT_FAILS = ("내용 모순", "조건부 누락")
# 서식 → 본인 칸(접두어 포함 키). 위임장_상속·지급보증거래_신청서는 없다(tools/forms.py self_name)
V2_SELF_NAMES = {
    "자동이체신청서": "중_예금주_성명",
    "휴면예금지급신청서": "중_원권리자_성명",
    "FATCA_CRS_본인확인서": "중_예금주_성명",
    "소비자피해보상금_지급신청서": "중_신청인_성명",
    "외국인_세대구성원_확인서": "중_본인_성명",
    "체크카드_가입신청서": "중_성명_한글",
    "IRP_계약해지신청서": "중_가입자명",
    "IRP_신규신청서": "중_가입자명",
}
V2_ATTORNEY = "위임장_상속"
V2_GUARANTEE = "지급보증거래_신청서"
V2_GUARANTEE_NAME = "중_신청인_성명"  # 상호 + 대표자가 섞일 수 있어 기준 값이 들어 있는지로 본다
# 일치_확인 에 지급보증_신청인에_<서식>_본인포함 규칙이 있는 서식(tools/build_full.py consistency_checks)
V2_GUARANTEE_RULE_FORMS = ("소비자피해보상금_지급신청서", "외국인_세대구성원_확인서")
V2_LINK_LABEL = "본인 성명"
# 가림 기호 — v6 일치_확인 서류간_본인성명_같음 의 contains 10개·결합_확인 정규식 [^*＊●○■□◆◇★☆] 와 같은 글자
MASK_MARKS = frozenset("*＊●○■□◆◇★☆")
# v6 결합_확인 두 규칙(가린이름_연락처_결합_없음·가린이름_식별정보_없음)이 서식마다 '이름이 가려졌는지' 보는 칸(v6_cfg.json 규칙 조건의
# `matches [^*…]*` 피연산자 — 두 규칙이 같은 7칸). V2_SELF_NAMES 에서 외국인_세대구성원_확인서(중_본인_성명)만 없다 — 규칙이 그 서식을 보지 않는다.
V6_MASKED_NAMES = {
    "자동이체신청서": "중_예금주_성명",
    "휴면예금지급신청서": "중_원권리자_성명",
    "FATCA_CRS_본인확인서": "중_예금주_성명",
    "소비자피해보상금_지급신청서": "중_신청인_성명",
    "체크카드_가입신청서": "중_성명_한글",
    "IRP_계약해지신청서": "중_가입자명",
    "IRP_신규신청서": "중_가입자명",
}
V6_LINKAGE_RULE = "가린이름_연락처_결합_없음"  # error → 판정 사유 '서류 간 정보 결합'
V6_REIDENT_RULE = "가린이름_식별정보_없음"  # warning → 판정 사유 '재식별 위험'
# 결합_확인 규칙 → bundle_check 의 label(칸 이름이 아니라 사유 이름 — 조건 트리의 첫 칸은 서식마다 다른 이름 칸이다)
V6_LINKAGE_LABELS = {V6_LINKAGE_RULE: "서류 간 정보 결합", V6_REIDENT_RULE: "재식별 위험"}

# 인용 표시 【†n】 — 고정 글자로 시작해 선형
_CITATION = re.compile(r"【†\d{1,9}】")
# 규칙 path 의 서식 코드 — 고정 글자로 시작하고 코드 길이를 잘라 선형
_PATH_EXTRACT = re.compile(r'extract\."([^"]{1,64})"')
# 키 줄: 줄 처음(글머리·굵게를 뗀 뒤)의 영문 키 + ':' — match 로 한 번만 시도한다
_KEY_LINE = re.compile(r"([A-Za-z_]{1,40})[ \t]*:")
# 지운 인용 표시 앞뒤를 띄어 쓰지 않는 글자(문장 부호)
_NO_SPACE_BEFORE = frozenset(",.;:!?)]}…。、")
_QUOTE_PAIRS = (('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’"), ("`", "`"))

Stages = list[Mapping[str, Any]]


# --- 공통 도우미 ------------------------------------------------------------------------


def _guarded(reader: Callable[[Stages], Any], stages: Any) -> Any:
    """reader(as_stages(stages)). 예상 못 한 예외는 값 없는 경고 후 None.

    마지막 안전망: 결과 어딘가에 짝 없는 서로게이트가 남아 있으면(각 값의 검사가 빠진 버그) 결과 전체를 None —
    결과는 늘 json.dumps(…, ensure_ascii=False).encode("utf-8") 로 인코딩된다.
    """
    try:
        result = reader(as_stages(stages))
        if has_unpaired_surrogates(result):
            logger.warning("최종 흐름 재료에 인코딩할 수 없는 글자가 남아 버림(%s)", reader.__name__)
            return None
        return result
    except Exception as exc:  # 바깥 모양 때문에 화면 전체가 비지 않게 — 값 없이 예외 종류만
        logger.warning("최종 흐름 재료를 읽지 못함(%s): %s", reader.__name__, type(exc).__name__)
        return None


def _first(stages: Stages, key: str) -> Mapping[str, Any] | None:
    found = usable_stages_for(stages, key)
    return found[0] if found else None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _name(value: Any) -> str | None:
    """이름·식별자: 비지 않은(공백만도 아닌) 문자열, MAX_NAME_LENGTH 이하, 짝 없는 서로게이트 없음 → 원래 문자열 그대로."""
    if isinstance(value, str) and len(value) <= MAX_NAME_LENGTH and value.strip() and text_is_safe(value):
        return value
    return None


def _enum(value: Any, allowed: Sequence[str]) -> str | None:
    """앞뒤 공백을 지우고 소문자로 바꾼 값이 allowed 중 하나면 그 값."""
    if isinstance(value, str) and len(value) <= _MAX_ENUM_LENGTH:
        cleaned = value.strip().lower()
        if cleaned in allowed:
            return cleaned
    return None


def _group_of_node(node_name: Any) -> str | None:
    """'추출_<묶음>' → <묶음>(알려진 묶음만). 그 밖은 None."""
    if isinstance(node_name, str) and node_name.startswith(EXTRACT_NODE_PREFIX):
        group = node_name[len(EXTRACT_NODE_PREFIX) :]
        return group if group in GROUPS else None
    return None


def _group_of_step(step_name: Any) -> str | None:
    """'Information Extract - 추출_<묶음>' → <묶음>."""
    if isinstance(step_name, str) and step_name.startswith(EXTRACT_STEP_PREFIX):
        return _group_of_node(step_name[len(EXTRACT_STEP_PREFIX) :])
    return None


def _branch_index(branch_key: Any) -> int | None:
    """'<index>:<코드>' 의 index(ASCII 숫자 MAX_INDEX_DIGITS 자리 이하). 아니면 None."""
    if not isinstance(branch_key, str):
        return None
    head, sep, _ = branch_key.partition(":")
    if not sep or not head or len(head) > MAX_INDEX_DIGITS or not (head.isascii() and head.isdigit()):
        return None
    return int(head)


def _routes(stages: Stages, known: set[int]) -> dict[str, list[int]] | None:
    """추출 단계 이름 → 그 단계로 간 서류 index(source_steps 순서). 병합-1 을 못 읽으면 None(경로를 모름).

    index 가 분류 서류(known)가 아니거나 앞에서 이미 나온 서류면 그 항목을 버린다.
    """
    merge = _first(stages, STAGE_MERGE)
    if merge is None:
        return None
    steps = _mapping(merge.get("data")).get("source_steps")
    if not isinstance(steps, list) or len(steps) > MAX_SOURCE_STEPS:
        return None
    routes: dict[str, list[int]] = {}
    seen: set[int] = set()
    for step in steps:
        if not isinstance(step, Mapping):
            continue
        name = step.get("step_name")
        index = _branch_index(step.get("branch_key"))
        if not isinstance(name, str) or index is None or index not in known or index in seen:
            continue
        seen.add(index)
        routes.setdefault(name, []).append(index)
    return routes


def _blank(value: Any) -> bool:
    """빈 값인지 — findings 가 탐지 항목을 만들지 않는 값과 같다(공백만인 문자열·None·bool·빈 목록/객체·그 밖의 꼴)."""
    if isinstance(value, str):
        return not value.strip()
    if value is None or isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return False
    if isinstance(value, (list, Mapping)):
        return not value
    return True


class _UniqueIds:
    """같은 이름이 또 나오면 '이름#2'·'이름#3'(이미 쓴 id 와도 겹치지 않게)."""

    def __init__(self) -> None:
        self._used: set[str] = set()
        self._counts: dict[str, int] = {}

    def next(self, name: str) -> str:
        count = self._counts.get(name, 0)
        while True:
            count += 1
            candidate = name if count == 1 else f"{name}#{count}"
            if candidate not in self._used:
                break
        self._counts[name] = count
        self._used.add(candidate)
        return candidate


# --- 위험도_판정 본문 ---------------------------------------------------------------------


def read_decision(stages: Any) -> dict[str, Any] | None:
    """위험도_판정 첫 completed 항목 본문의 "키: 값" 줄 → {risk_level, document_types, sensitive_categories,
    review_reasons, reason}. 못 읽은 키는 None. 단계가 없거나 본문이 문자열이 아니거나 키 줄이 하나도 없으면 None.

    - 앞 MAX_DECISION_LINES 줄만 읽는다. 모르는 키는 버리고, 같은 키는 첫 줄이 정한다(그 값을 못 읽어도 다음 줄을 보지 않음).
    - 줄의 앞뒤 공백·글머리("- "·"* ")·굵게("**")를 떼고, 값의 인용 표시 【†n】(여러 개·사이 공백)를 지운다.
    - 값에 짝 없는 서로게이트가 있거나(원문, 그리고 JSON 목록을 푼 뒤·다듬은 뒤의 값 — 목록은 한 항목이라도 그렇면 전체)
      인용 표시를 지운 값이 MAX_DECISION_VALUE_LENGTH 를 넘으면 그 값은 None.
    - risk_level 은 상·중·하·검토 필요 중 하나만. reason 은 빈 값이면 None.
    - 목록 키: "[a, b]"·"[]"·"a, b"(JSON 문자열 목록도) → 목록. 따옴표를 떼고 빈 항목은 버린다.
      항목이 MAX_DECISION_ITEMS 개를 넘으면 그 값은 None, MAX_DECISION_ITEM_LENGTH 를 넘는 항목은 버린다(모두 버려지면 None).
      값이 비었거나 '['로 시작해 ']'로 끝나지 않으면 None('확인된 빈 목록'은 빈 항목만 있는 "[]" 꼴뿐).
    """
    return _guarded(_read_decision, stages)


def _read_decision(stages: Stages) -> dict[str, Any] | None:
    stage = _first(stages, STAGE_RISK)
    if stage is None:
        return None
    text = stage.get("data")
    if not isinstance(text, str):
        return None
    found: dict[str, Any] = {}
    for line in text.split("\n", MAX_DECISION_LINES)[:MAX_DECISION_LINES]:
        parsed = _key_line(line)
        if parsed is None:
            continue
        key, raw = parsed
        if key not in found:
            found[key] = _decision_value(key, raw)
    if not found:
        return None
    return {key: found.get(key) for key in DECISION_KEYS}


def _key_line(line: str) -> tuple[str, str] | None:
    """(키, 값 원문) — 키가 DECISION_KEYS 중 하나인 줄만."""
    body = line.strip()
    if body[:2] in ("- ", "* "):
        body = body[2:].lstrip()
    body = body.replace("**", "")
    match = _KEY_LINE.match(body)
    if match is None:
        return None
    key = match.group(1).lower()
    if key not in DECISION_KEYS:
        return None
    return key, body[match.end() :]


def _strip_citations(text: str) -> str:
    """인용 표시 【†n】 와 그 앞 공백을 지운다. 지운 자리 양쪽이 글자면 한 칸 띄운다(문장 부호 앞은 붙인다)."""
    if "【" not in text:
        return text
    parts = _CITATION.split(text)
    last = len(parts) - 1
    out: list[str] = []
    gap = False  # 지운 표시 앞에 공백이 있었는지
    for i, part in enumerate(parts):
        body = part.rstrip() if i < last else part
        if body:
            if gap and out and not body[0].isspace() and body[0] not in _NO_SPACE_BEFORE:
                out.append(" ")
            out.append(body)
            gap = False
        if len(body) < len(part):
            gap = True
    return "".join(out)


def _decision_value(key: str, raw: str) -> Any:
    if not text_is_safe(raw):
        return None
    value = _strip_citations(raw).strip()
    if len(value) > MAX_DECISION_VALUE_LENGTH:
        return None
    if key in DECISION_LIST_KEYS:
        result: Any = _decision_list(value)
    elif key == "risk_level":
        result = value if value in DECISION_LEVELS else None
    else:
        result = value or None
    # 다듬고 푼 **뒤의** 값도 같은 기준으로 본다(JSON escape 가 짝 없는 서로게이트로 풀릴 수 있다)
    return result if _safe_value(result) else None


def _safe_value(value: Any) -> bool:
    """None·문자열·문자열 목록이 모두 UTF-8 로 인코딩되는지(짝 없는 서로게이트 없음)."""
    if isinstance(value, str):
        return text_is_safe(value)
    if isinstance(value, list):
        return all(isinstance(item, str) and text_is_safe(item) for item in value)
    return value is None


def _json_strings(value: str) -> list[str] | None:
    """JSON 문자열 목록이면 그 목록(따옴표 안의 쉼표를 지키려고). 아니면 None."""
    try:
        parsed = json.loads(value)
    except (ValueError, RecursionError):
        return None
    if isinstance(parsed, list) and all(isinstance(item, str) for item in parsed):
        return parsed
    return None


def _unquote(item: str) -> str:
    for opening, closing in _QUOTE_PAIRS:
        if len(item) >= 2 and item.startswith(opening) and item.endswith(closing):
            return item[1:-1].strip()
    return item


def _decision_list(value: str) -> list[str] | None:
    if not value:
        return None
    if value.startswith("["):
        if not value.endswith("]"):
            return None
        items = _json_strings(value)
        if items is None:
            items = value[1:-1].split(",")
        elif not all(text_is_safe(item) for item in items):
            # 원문은 ASCII 여도 "\ud800" 같은 escape 가 짝 없는 서로게이트로 풀린다 — 그 키의 값 전체를 버린다
            return None
    else:
        items = value.split(",")
    cleaned = [item for item in (_unquote(i.strip()) for i in items) if item]
    if len(cleaned) > MAX_DECISION_ITEMS:
        return None
    kept = [item for item in cleaned if len(item) <= MAX_DECISION_ITEM_LENGTH]
    # 항목이 있었는데 모두 길어서 버렸으면 '확인된 빈 목록'이 아니다
    return kept if kept or not cleaned else None


# --- 묶음_검증 --------------------------------------------------------------------------


def read_bundle_checks(stages: Any) -> dict[str, Any] | None:
    """묶음_검증 첫 completed 항목 → {"verdict", "checks"}. 단계가 없으면 None.

    - verdict: additional_values.verdict(비지 않은 문자열이 아니면 본문)가 green·yellow·red 면 그 값, 아니면 None.
    - checks: additional_values.checks 가 목록이 아니거나 MAX_CHECKS 개를 넘으면 None. 항목마다
      {id, name, severity, passed, field, group, status, documents} — 이름이 없는(문자열 아님·빈 값·너무 김·
      서로게이트) 규칙은 버린다. reason·conditions 의 값은 넣지 않는다.
      status: passed True → pass / passed False 이고 left.value 가 null → absent(그 종류 서류 없음 — 다만 병합-1 이
      그 노드로 간 서류를 보여 주면 모순이라 unknown) / passed False 이고 값이 목록 → fail / 그 밖 unknown.
      documents: left.value 가 0 이상 정수 목록이고 길이가 그 추출 노드로 간 서류 수와 같으면
      [{index, ok: 길이 > 0}](서류 순서 = 병합-1 source_steps), 아니면 None.
    """
    return _guarded(_read_bundle_checks, stages)


def _read_bundle_checks(stages: Stages) -> dict[str, Any] | None:
    stage = _first(stages, STAGE_BUNDLE_CHECK)
    if stage is None:
        return None
    additional = _mapping(stage.get("additional_values"))
    raw = additional.get("verdict")
    verdict = _enum(raw if isinstance(raw, str) and raw.strip() else stage.get("data"), VERDICTS)
    return {"verdict": verdict, "checks": _checks(stages, additional.get("checks"))}


def _checks(stages: Stages, raw: Any) -> list[dict[str, Any]] | None:
    if not isinstance(raw, list) or len(raw) > MAX_CHECKS:
        return None
    docs, _ = _documents(stages)
    routes = _routes(stages, {d.index for d in docs})
    ids = _UniqueIds()
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        name = _name(item.get("name"))
        if name is None:
            continue
        left = _mapping(_mapping(item.get("conditions")).get("left"))
        node = _name(left.get("nodeName"))
        node_docs = routes.get(EXTRACT_STEP_PREFIX + node, []) if routes is not None and node is not None else None
        passed = item.get("passed")
        passed = passed if isinstance(passed, bool) else None
        out.append(
            {
                "id": ids.next(name),
                "name": name,
                "severity": _enum(item.get("severity"), SEVERITIES),
                "passed": passed,
                "field": _name(left.get("field")),
                "group": _group_of_node(node),
                "status": _check_status(passed, left, node_docs),
                "documents": _check_documents(left.get("value"), node_docs),
            }
        )
    return out


def _check_status(passed: bool | None, left: Mapping[str, Any], node_docs: list[int] | None) -> str:
    if passed is True:
        return CHECK_PASS
    if passed is False:
        if "value" in left and left["value"] is None:
            # 그 종류 서류가 묶음에 없음. 병합-1 이 그 노드로 간 서류를 보여 주면 모순 — 단정하지 않는다
            return CHECK_ABSENT if not node_docs else CHECK_UNKNOWN
        if isinstance(left.get("value"), list):
            return CHECK_FAIL
    return CHECK_UNKNOWN


def _check_documents(value: Any, node_docs: list[int] | None) -> list[dict[str, Any]] | None:
    if node_docs is None or not isinstance(value, list) or len(value) != len(node_docs):
        return None
    if not all(_is_int(length) and length >= 0 for length in value):
        return None
    return [{"index": index, "ok": length > 0} for index, length in zip(node_docs, value)]


# --- 서류_대조 --------------------------------------------------------------------------


def read_links(stages: Any) -> dict[str, Any] | None:
    """서류_대조 첫 completed 항목 → {"field", "anchor_index", "pairs"}. 단계가 없으면 None.

    - anchor_index: 분류 서류 중 쪽 범위가 additional_values.page_ranges 와 같은 첫 서류(빈 범위는 짝 없음).
    - field: 첫 대상(targets 의 첫 객체)의 document_match.anchor_key.
    - pairs: targets 가 목록이 아니거나 MAX_LINK_TARGETS 개를 넘거나 병합-1 을 못 읽거나, 분류 서류가 MAX_LINK_DOCUMENTS 개·
      쓸 수 있는 추출 단계가 MAX_LINK_EXTRACTS 개를 넘으면(짝짓기 시간 한도) None. 대상(targets[].step_name)
      마다 그 추출 노드로 간 서류마다 {id: "link:<anchor_index>:<target_index>", target_index, group, status}
      (기준 서류를 못 찾으면 id 의 기준 자리는 "-"). 같은 대상 서류는 첫 쌍만, 기준 서류 자신은 넣지 않는다.
      status — insufficient: 기준 서류 없음, anchor_value 가 빔, matched 를 못 읽음(목록 아님·한도 넘음),
      대조 키를 모름, 대상 서류의 추출 항목이 없거나 그 키 값이 빔 / linked: 대상 서류 쪽 범위가 matched[].page_ranges
      중 하나와 같음 / unmatched: 그 밖.
    값(anchor_value·target_values)은 넣지 않는다.
    """
    return _guarded(_read_links, stages)


def _matched_ranges(raw: Any) -> set[tuple[tuple[int, int], ...]] | None:
    if not isinstance(raw, list) or len(raw) > MAX_MATCHED:
        return None
    return {ranges for ranges in (_ranges(entry) for entry in raw if isinstance(entry, Mapping)) if ranges}


def _read_links(stages: Stages) -> dict[str, Any] | None:
    stage = _first(stages, STAGE_MATCH)
    if stage is None:
        return None
    additional = _mapping(stage.get("additional_values"))
    docs, classify_count = _documents(stages)
    by_index = {doc.index: doc for doc in docs}  # 분류 서류만(아래에서 덧붙는 짝 없는 추출 서류는 넣지 않는다)
    anchor_ranges = _ranges(additional)
    anchor = next((doc for doc in docs if anchor_ranges and doc.ranges == anchor_ranges), None)
    anchor_index = anchor.index if anchor is not None else None

    targets = additional.get("targets")
    if not isinstance(targets, list) or len(targets) > MAX_LINK_TARGETS:
        return {"field": None, "anchor_index": anchor_index, "pairs": None}
    first = next((t for t in targets if isinstance(t, Mapping)), None)
    field = _name(_mapping(first.get("document_match")).get("anchor_key")) if first is not None else None

    routes = _routes(stages, set(by_index))
    if routes is None:
        return {"field": field, "anchor_index": anchor_index, "pairs": None}
    if len(docs) > MAX_LINK_DOCUMENTS or len(usable_stages_for(stages, STAGE_EXTRACT)) > MAX_LINK_EXTRACTS:
        return {"field": field, "anchor_index": anchor_index, "pairs": None}  # 짝짓기가 제곱 시간이 되기 전에 멈춘다
    _attach_extracts(stages, docs, classify_count)  # 대상 서류의 추출 항목 — findings 와 같은 짝짓기
    anchor_part = str(anchor_index) if anchor_index is not None else NO_ANCHOR
    seen: set[int] = set()
    pairs: list[dict[str, Any]] = []
    for target in targets:
        if not isinstance(target, Mapping):
            continue
        step_name = target.get("step_name")
        if not isinstance(step_name, str):
            continue
        match = _mapping(target.get("document_match"))
        key = _name(match.get("target_key")) or _name(match.get("anchor_key"))
        matched = _matched_ranges(match.get("matched"))
        weak = anchor_index is None or _blank(match.get("anchor_value")) or matched is None or key is None
        group = _group_of_step(step_name)
        for index in routes.get(step_name, []):
            if index in seen or index == anchor_index:
                continue
            seen.add(index)
            doc = by_index[index]
            data = doc.extract[0] if doc.extract is not None else None
            if weak or data is None or _blank(data.get(key)):
                status = LINK_INSUFFICIENT
            elif doc.ranges and matched is not None and doc.ranges in matched:
                status = LINK_LINKED
            else:
                status = LINK_UNMATCHED
            pairs.append({"id": f"link:{anchor_part}:{index}", "target_index": index, "group": group, "status": status})
    return {"field": field, "anchor_index": anchor_index, "pairs": pairs}


# --- 설정 60: 판정 8키 --------------------------------------------------------------------


def read_verdict(stages: Any) -> dict[str, Any] | None:
    """판정 단계(판정_* Instruct, completed 또는 상태 없음인 첫 항목)의 본문 → 키 8개. 단계가 없거나 본문이 객체가 아니면 None."""
    return _guarded(_read_verdict, stages)


def _read_verdict(stages: Stages) -> dict[str, Any] | None:
    stage = next((s for s in usable_stages_for(stages, STAGE_V2_VERDICT) if s.get("step_type") in (None, "instruct")), None)
    if stage is None:
        return None
    body = stage.get("data")
    if not isinstance(body, Mapping):
        return None
    return {key: _verdict_value(key, body.get(key)) for key in V2_DECISION_KEYS}


def _verdict_text(raw: Any) -> str | None:
    """글 하나: 문자열·서로게이트 없음 → 인용 표시를 지우고 앞뒤 공백을 뗀 값. 길이 2000 초과·빈 값이면 None."""
    if not isinstance(raw, str) or not text_is_safe(raw):
        return None
    value = _strip_citations(raw).strip()
    return value if value and len(value) <= MAX_DECISION_VALUE_LENGTH else None


def _verdict_list(raw: Any) -> list[str] | None:
    """목록: 문자열 목록만, 항목 한도·항목 길이를 넘거나 문자열 아닌 항목·서로게이트가 있으면 None(자르지 않는다). [] 은 []."""
    if not isinstance(raw, list) or len(raw) > V2_MAX_DECISION_ITEMS:
        return None
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not text_is_safe(item):
            return None
        value = _strip_citations(item).strip()
        if len(value) > MAX_DECISION_VALUE_LENGTH:
            return None
        out.append(value)
    return out


def _verdict_value(key: str, raw: Any) -> Any:
    if key in V2_DECISION_LIST_KEYS:
        return _verdict_list(raw)
    value = _verdict_text(raw)
    if key == "risk_level":
        return value if value in DECISION_LEVELS else None
    return value


# --- 설정 60: 검증 사슬 -------------------------------------------------------------------


def _tree_operands(tree: Any) -> Iterator[Mapping[str, Any]]:
    """조건 트리의 피연산자를 순서대로(조건마다 왼쪽 → 오른쪽) — 반복문, 깊이·개수 한도 안에서(아주 깊거나 큰 트리에서 예외가 나지 않게)."""
    stack: list[tuple[Any, int]] = [(tree, 0)]
    seen = 0
    while stack and seen < MAX_TREE_NODES:
        node, depth = stack.pop()
        seen += 1
        if not isinstance(node, Mapping):
            continue
        children = node.get("conditions")
        if isinstance(children, list):
            if depth < MAX_TREE_DEPTH:
                stack.extend((child, depth + 1) for child in reversed(children[:MAX_TREE_NODES]))
            continue
        for side in ("left", "right"):
            operand = node.get(side)
            if isinstance(operand, Mapping):
                yield operand


def _path_code(path: Any) -> str | None:
    """path 의 extract."<코드>" 중 첫 10서식 코드."""
    if not isinstance(path, str):
        return None
    for match in _PATH_EXTRACT.finditer(path[:MAX_PATH_SCAN]):
        if match.group(1) in V2_FORM_CODES:
            return match.group(1)
    return None


def _name_code(name: str) -> str | None:
    """규칙 이름 앞부분 '<코드>_' 의 10서식 코드."""
    return next((code for code in V2_FORM_CODES if name.startswith(code + "_")), None)


def _chain_rule(node: str, name: str, item: Mapping[str, Any]) -> ChainRule:
    """실패·unknown 규칙 하나 → ChainRule(값 없음 — 칸 키·이름·서식 코드만, 양쪽 피연산자의 value 는 읽지 않는다)."""
    field: str | None = None
    label: str | None = None
    cell: tuple[str | None, str] | None = None
    cell_label: str | None = None
    node_code: str | None = None
    path_code: str | None = None
    for operand in _tree_operands(item.get("conditions")):
        if node_code is None and operand.get("nodeName") in V2_FORM_CODES:
            node_code = operand["nodeName"]
        if path_code is None:
            path_code = _path_code(operand.get("path"))
        row, outer = _name(operand.get("rowField")), _name(operand.get("field"))
        key, table = (row, outer) if row is not None else (outer, None)
        if key is None:
            continue
        info = v2_field_info(key, table)
        known = info.mapping_status != "unknown"
        if field is None:
            field, label = key, (info.label if known else None)
        if cell is None and known:
            cell, cell_label = (table, key), info.label
    if node == STAGE_V2_LINKAGE and name in V6_LINKAGE_LABELS:
        # 결합 두 규칙: 조건 트리의 첫 칸(자동이체신청서 이름 칸)은 규칙의 대상 칸이 아니다 — field 는 null, label 은 사유 이름
        field, label = None, V6_LINKAGE_LABELS[name]
    return ChainRule(
        node=node,
        name=name,
        severity=_enum(item.get("severity"), SEVERITIES),
        status=CHECK_FAIL if item.get("passed") is False else CHECK_UNKNOWN,
        field=field,
        label=label,
        code=node_code or path_code or _name_code(name),
        cell=cell,
        cell_label=cell_label,
    )


def _node_rules(node: str, raw: Any) -> list[ChainRule]:
    """노드의 checks → 실패·unknown 규칙(이름이 없는 규칙은 버린다). 목록이 아니거나 MAX_CHECKS 개를 넘으면 없음."""
    if not isinstance(raw, list) or len(raw) > MAX_CHECKS:
        return []
    out: list[ChainRule] = []
    for item in raw:
        try:
            if not isinstance(item, Mapping) or item.get("passed") is True:
                continue
            name = _name(item.get("name"))
            if name is not None:
                out.append(_chain_rule(node, name, item))
        except Exception as exc:  # 그 규칙만 — 값 없이 예외 종류만
            logger.warning("검증 규칙 하나를 읽지 못해 건너뜀: %s", type(exc).__name__)
    return out


def _content_failed(stages: Stages) -> bool:
    """내용_검토 enum 이 실패 값인지(본문은 읽지 않는다)."""
    stage = _first(stages, STAGE_V2_CONTENT)
    enum = _mapping(stage.get("additional_values")).get("enum") if stage is not None else None
    return isinstance(enum, str) and enum.strip() in V2_CONTENT_FAILS


def read_chain_rules(stages: Any) -> tuple[list[ChainRule], str | None] | None:
    """검증 사슬의 (실패·unknown 규칙, verdict) — 사슬 순서. 옛 응답은 None."""
    return _guarded(_read_chain_rules, stages)


def _read_chain_rules(stages: Stages) -> tuple[list[ChainRule], str | None] | None:
    if not is_v2(stages):
        return None
    rules: list[ChainRule] = []
    verdicts: list[str] = []
    for node in V2_CHAIN:
        stage = _first(stages, node)
        if stage is None:
            continue
        additional = _mapping(stage.get("additional_values"))
        raw = additional.get("verdict")
        verdict = _enum(raw if isinstance(raw, str) and raw.strip() else stage.get("data"), VERDICTS)
        if verdict is not None:
            verdicts.append(verdict)
        rules.extend(_node_rules(node, additional.get("checks")))
    if _content_failed(stages):
        verdicts.append("red")
        rules.append(
            ChainRule(
                node=STAGE_V2_CONTENT,
                name=STAGE_V2_CONTENT,
                severity="error",
                status=CHECK_FAIL,
                field=None,
                label=None,
                code=None,
                cell=None,
                cell_label=None,
            )
        )
    if "red" in verdicts:
        return rules, "red"
    if "yellow" in verdicts:
        return rules, "yellow"
    return rules, "green" if verdicts else None


def read_linkage_passed(stages: Any) -> bool:
    """결합_확인 의 error 규칙(가린이름_연락처_결합_없음)이 **명시적으로 통과**했는지 — 그 이름(JS trim)의 규칙이 하나 이상 있고 모두 passed 가
    정확히 True 일 때만 True. 단계·규칙이 없거나 passed 가 bool 이 아니거나 checks 모양이 틀리면 False(재식별 재료를 추론하지 않는다 — 머리 주석).
    read_chain_rules 는 통과 규칙을 버리므로(bundle_check 계약) 이 사실만 따로 읽는다."""
    return _guarded(_read_linkage_passed, stages) is True


def _read_linkage_passed(stages: Stages) -> bool:
    if not is_v2(stages):
        return False
    stage = _first(stages, STAGE_V2_LINKAGE)
    raw = _mapping(stage.get("additional_values")).get("checks") if stage is not None else None
    if not isinstance(raw, list) or len(raw) > MAX_CHECKS:
        return False
    seen = False
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        name = _name(item.get("name"))
        if name is None or js_trim(name) != V6_LINKAGE_RULE:
            continue
        if item.get("passed") is not True:
            return False
        seen = True
    return seen


def chain_view(chain: Any) -> dict[str, Any] | None:
    """read_chain_rules 결과 → {verdict, checks[키 7개]}. 같은 이름은 '이름#2'."""
    if chain is None:
        return None
    rules, verdict = chain
    ids = _UniqueIds()
    checks = [
        {
            "id": ids.next(rule.name),
            "name": rule.name,
            "severity": rule.severity,
            "status": rule.status,
            "field": rule.field,
            "label": rule.label,
            "group": rule.node,
        }
        for rule in rules
    ]
    return {"verdict": verdict, "checks": checks}


def read_chain(stages: Any) -> dict[str, Any] | None:
    """검증 사슬 {verdict, checks[{id, name, severity, status, field, label, group}]}. 옛 응답은 None."""
    return _guarded(_read_chain, stages)


def _read_chain(stages: Stages) -> dict[str, Any] | None:
    return chain_view(_read_chain_rules(stages))


# --- 설정 60: 서류 연결 -------------------------------------------------------------------


def has_mask(value: Any) -> bool:
    """문자열에 가림 기호(MASK_MARKS)가 하나라도 있는지 — 값 길이에 선형. 문자열이 아니면 False."""
    return isinstance(value, str) and not MASK_MARKS.isdisjoint(value)


def masked_name_fields(docs: Any) -> dict[int, str]:
    """결합_확인 이 보는 이름 칸(V6_MASKED_NAMES)의 Extract 값에 가림 기호가 든 서류 index → 그 칸 키(findings._Doc 목록).
    모양이 틀린 서류는 건너뛴다(값 없는 경고)."""
    out: dict[int, str] = {}
    for doc in docs if isinstance(docs, Sequence) else ():
        try:
            field = V6_MASKED_NAMES.get(doc.type) if isinstance(doc.type, str) else None
            if field is not None and doc.extract is not None and _is_int(doc.index) and has_mask(doc.extract[0].get(field)):
                out.setdefault(doc.index, field)
        except Exception as exc:  # 그 서류만 — 값 없이 예외 종류만
            logger.warning("가린 이름 서류 하나를 읽지 못해 건너뜀: %s", type(exc).__name__)
    return out


def _v2_link_status(
    doc: Any, field: str | None, anchor_value: Any, guarantee_rule: bool, anchor_masked: bool, masks: Mapping[int, bool]
) -> tuple[str, bool]:
    """쌍 하나의 (상태, 가린 이름인지) — 머리 주석. 값은 정리하지 않고 그대로 비교한다. guarantee_rule = 일치_확인 에 지급보증을 비교하는
    규칙이 있는 묶음인지. 가린 이름은 비교까지 갔을 쌍(기준·대상 값이 모두 비지 않은 문자열)에만 — 다른 까닭의 근거 부족이 먼저다.
    가림 여부는 값마다 한 번 계산해 둔 것을 쓴다(anchor_masked = 기준 값, masks = 서류 index → 그 서류 비교 칸 값) — 쌍마다 기준 이름을 다시 훑지 않는다."""
    if doc.type == V2_ATTORNEY or doc.extract is None or field is None or not isinstance(anchor_value, str):
        return LINK_INSUFFICIENT, False
    value = doc.extract[0].get(field)
    if jmes_empty(value) or not isinstance(value, str):
        return LINK_INSUFFICIENT, False
    if anchor_masked or masks.get(doc.index, False):
        return LINK_INSUFFICIENT, True  # 일치_확인 의 서류간_본인성명_같음 이 비교에서 빼는 값
    if doc.type == V2_GUARANTEE:
        if anchor_value in value:
            return LINK_LINKED, False
        return (LINK_UNMATCHED if guarantee_rule else LINK_INSUFFICIENT), False
    return (LINK_LINKED if value == anchor_value else LINK_UNMATCHED), False


def read_v2_links(stages: Any) -> dict[str, Any] | None:
    """Extract 값으로 계산한 서류 연결 {field, anchor_index, pairs, doc_fields, label}. 옛 응답은 None. 값은 넣지 않는다."""
    return _guarded(_read_v2_links, stages)


def _read_v2_links(stages: Stages) -> dict[str, Any] | None:
    if not is_v2(stages):
        return None
    docs, classify_count = _documents(stages)
    forms = [doc for doc in docs if doc.type in V2_FORM_CODES]
    # 서류 index → 그 서류의 비교 칸(위임장_상속은 없다)
    doc_fields = {
        doc.index: V2_GUARANTEE_NAME if doc.type == V2_GUARANTEE else V2_SELF_NAMES[doc.type]
        for doc in forms
        if doc.type == V2_GUARANTEE or doc.type in V2_SELF_NAMES
    }
    out: dict[str, Any] = {"field": None, "anchor_index": None, "pairs": [], "doc_fields": doc_fields, "label": V2_LINK_LABEL}
    if len({doc.type for doc in forms}) <= 1:
        out["doc_fields"] = {}
        return out  # 서식이 1종 이하 — 연결 없음(같은 서식 두 건도)
    if len(docs) > MAX_LINK_DOCUMENTS or len(usable_stages_for(stages, STAGE_EXTRACT)) > MAX_LINK_EXTRACTS:
        out["pairs"] = None  # 짝짓기가 제곱 시간이 되기 전에 멈춘다(일부만 잘라 잇지 않는다)
        return out
    _attach_extracts(stages, docs, classify_count)
    # 서류마다 비교 칸 값의 가림 여부를 **한 번만** 계산한다(연결 계산 전체가 이름 글자 합 + 서류 수에 선형이게)
    masks = {
        doc.index: has_mask(doc.extract[0].get(doc_fields[doc.index]))
        for doc in forms
        if doc.extract is not None and doc.index in doc_fields
    }
    named = [
        doc
        for doc in forms
        if doc.type in V2_SELF_NAMES and doc.extract is not None and not jmes_empty(doc.extract[0].get(V2_SELF_NAMES[doc.type]))
    ]
    # 기준 = 가림 기호가 없는 본인 성명의 첫 서식, 없으면 본인 성명이 비지 않은 첫 서식(그때 비교할 수 있었던 쌍은 모두 가린 이름)
    anchor = next((doc for doc in named if not masks.get(doc.index, False)), named[0] if named else None)
    if anchor is None:
        return out
    field = V2_SELF_NAMES[anchor.type]
    anchor_value = anchor.extract[0].get(field)
    anchor_masked = masks.get(anchor.index, False)
    guarantee_rule = any(doc.type in V2_GUARANTEE_RULE_FORMS for doc in forms)
    pairs = []
    for doc in forms:
        if doc.index == anchor.index:
            continue
        status, masked = _v2_link_status(doc, doc_fields.get(doc.index), anchor_value, guarantee_rule, anchor_masked, masks)
        pairs.append(
            {
                "id": f"link:{anchor.index}:{doc.index}",
                "target_index": doc.index,
                "group": None,
                "status": status,
                "masked": masked,
                "contains": doc.type == V2_GUARANTEE,
            }
        )
    out.update(field=field, anchor_index=anchor.index, pairs=pairs)
    return out
