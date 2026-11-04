# ==========================================================================
#  검토사항(imask_backend.items) 테스트용 합성 자료 — 손으로 지은 값만 쓴다(실제 응답 파일의 값은 옮기지 않는다)
#  - bundle_result: 서류 묶음 하나의 저장 결과(analyses.result 꼴). 서류마다 분류·추출·검증(verdict + checks)·기타 안내를
#    원하는 모양으로 만든다. additional_values 는 ASCII JSON 이라 짝 없는 서로게이트·NUL 이 든 키·이름도 escape 로 저장되고
#    parse_stages 의 json.loads 로 되살아난다.
#  - merged_result: 2026-11-04 워크플로우 응답(위임장 합침) 모양 — 서류 5(추출 4·기타 1, 쪽 1·2·3–4·5·6), 탐지 26,
#    신뢰도 low 10(서류 0 에 4 · 2 에 3(3쪽 2·4쪽 1) · 3 에 3), 상자 없는 항목 0, 검증 content 4(서류마다 verdict green,
#    checks 1개 applicant_name_detected 통과). 예전 응답(위임장 따로 — 서류 6·탐지 29·위치 없는 항목 1)은
#    fake_findings.stored_result 가 본뜬다.
#  - vdoc·vfinding·rule: build_items 에 바로 넣는 화면용 서류·탐지 항목·검증 규칙(필요한 키만).
#  JWT·키 꼴 글자는 쓰지 않는다.
# ==========================================================================

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from fake_findings import rect

NO_VALUE = object()  # rule(value=NO_VALUE) — conditions.left 에 value 키를 넣지 않는다
NAME_RULE = "applicant_name_detected"


def rule(
    name: Any = NAME_RULE,
    passed: Any = False,
    *,
    field_name: Any = "applicant_name",
    value: Any = 0,
    conditions: Any = NO_VALUE,
    omit: tuple[str, ...] = (),
) -> dict[str, Any]:
    """검증 checks 의 규칙 하나(관찰한 모양 — severity·passed·reason·conditions{kind, passed, left, operator, right})."""
    left: dict[str, Any] = {"nodeType": "extract", "nodeName": "민감정보_추출", "field": field_name, "attr": "length"}
    if value is not NO_VALUE:
        left["value"] = value
    out: dict[str, Any] = {
        "name": name,
        "severity": "error",
        "passed": passed,
        "reason": "합성 사유 문장",
        "conditions": {"kind": "condition", "passed": passed, "left": left, "operator": "gte", "right": {"const": 1, "value": 1}}
        if conditions is NO_VALUE
        else conditions,
    }
    for key in omit:
        out.pop(key, None)
    return out


CHECKS_OK = [rule(passed=True, value=3)]


# --- 저장 결과(build_view 입력) --------------------------------------------------------------------


@dataclass
class Spec:
    """서류 하나. fields = 추출 키 → (값, 쪽(None 이면 위치 없음), 신뢰도). validate 가 None 이면 검증 content 없음."""

    code: str
    pages: tuple[int, int]
    fields: dict[str, tuple[str, int | None, str]] = field(default_factory=dict)
    validate: tuple[Any, Any] | None = ("green", CHECKS_OK)  # (verdict, checks) — checks 가 NO_VALUE 면 키 없음
    guide: str | None = None


def _entry(text: str, extra: dict[str, Any]) -> dict[str, Any]:
    return {"type": "output_text", "text": text, "annotations": [], "additional_values": json.dumps(extra, ensure_ascii=True)}


def _stage(model: str, step_type: str, *contents: dict[str, Any]) -> dict[str, Any]:
    return {"model": model, "step_type": step_type, "status": "completed", "content": list(contents)}


def _meta(page: int | None, confidence: str) -> dict[str, Any]:
    if page is None:
        return {"page": -1, "confidence": confidence, "coordinates": [], "word_coordinates": []}
    return {"page": page, "confidence": confidence, "coordinates": rect(0.1, 0.2), "word_coordinates": []}


def bundle_result(specs: list[Spec], *, risk: str | None = "상") -> dict[str, Any]:
    """서류 specs 의 저장 결과. 서류마다 분류 content 하나, 추출·검증·기타 안내는 서류마다 단계 하나(같은 쪽 범위)."""
    ranges = [[[s.pages[0], s.pages[1]]] for s in specs]
    output = [
        _stage(
            "step_2_classify",
            "document-classify",
            *(_entry(s.code, {"document_type": {"_value": s.code}, "page_ranges": r}) for s, r in zip(specs, ranges, strict=True)),
        )
    ]
    for spec, page_ranges in zip(specs, ranges, strict=True):
        if spec.fields:
            data = {key: value for key, (value, _page, _conf) in spec.fields.items()}
            meta = {key: _meta(page, conf) for key, (_value, page, conf) in spec.fields.items()}
            output.append(
                _stage(
                    "Information Extract - 민감정보_추출",
                    "information-extract",
                    _entry(json.dumps(data, ensure_ascii=True), {"page_ranges": page_ranges, **meta}),
                )
            )
    for spec, page_ranges in zip(specs, ranges, strict=True):
        if spec.guide is not None:
            output.append(_stage("Instruct - 기타_서류_안내", "instruct", _entry(spec.guide, {"citations": [], "page_ranges": page_ranges})))
    for spec, page_ranges in zip(specs, ranges, strict=True):
        if spec.validate is not None:
            verdict, checks = spec.validate
            extra: dict[str, Any] = {"page_ranges": page_ranges}
            if verdict is not NO_VALUE:
                extra["verdict"] = verdict
            if checks is not NO_VALUE:
                extra["checks"] = checks
            text = json.dumps(verdict if isinstance(verdict, str) else "", ensure_ascii=True)
            output.append(_stage("Validate - 필수항목_검증", "validate", _entry(text, extra)))
    if risk is not None:
        output.append(_stage("Instruct - 위험도_판정", "instruct", _entry("## 판정", {"enum": risk})))
    return {"format": "imask-upstage-v1", "job": {}, "summary": {"risk_level": risk} if risk else {}, "response": {"output": output}}


def _fields(keys: list[str], pages: list[int], low: set[str]) -> dict[str, tuple[str, int | None, str]]:
    return {key: (f"합성값{n}", page, "low" if key in low else "high") for n, (key, page) in enumerate(zip(keys, pages, strict=True))}


# 2026-11-04 워크플로우(위임장 합침) 모양 — 키 이름만 관찰과 같고 값은 지어낸 것
MERGED_KEYS: list[list[str]] = [
    [
        "applicant_name",
        "applicant_rrn",
        "applicant_phone",
        "applicant_email",
        "applicant_address",
        "employer_info",
        "account_number",
        "loan_info",
        "income_info",
        "staff_contact",
    ],
    ["applicant_name", "applicant_birth_date"],
    [
        "applicant_name",
        "applicant_rrn",
        "applicant_phone",
        "applicant_address",
        "employer_info",
        "income_info",
        "other_person_name",
        "other_person_rrn",
        "other_person_contact",
    ],
    ["applicant_name", "account_number", "card_number", "loan_info", "credit_negative_info"],
]
MERGED_LOW: list[set[str]] = [
    {"employer_info", "loan_info", "income_info", "staff_contact"},
    set(),
    {"employer_info", "income_info", "other_person_contact"},
    {"card_number", "loan_info", "credit_negative_info"},
]
# 서류 2(3–4쪽)의 쪽: low 항목 중 employer_info·income_info 는 3쪽, other_person_contact 는 4쪽
MERGED_PAGES: list[list[int]] = [[1] * 10, [2] * 2, [3, 3, 3, 3, 3, 3, 4, 4, 4], [5] * 5]


def merged_specs() -> list[Spec]:
    codes = ("loan_application", "consent_form", "income_proof", "debt_transaction")
    pages = ((1, 1), (2, 2), (3, 4), (5, 5))
    specs = [
        Spec(code, page, _fields(keys, item_pages, low))
        for code, page, keys, item_pages, low in zip(codes, pages, MERGED_KEYS, MERGED_PAGES, MERGED_LOW, strict=True)
    ]
    specs.append(Spec("Other", (6, 6), validate=None, guide="예상_서류_종류=합성 안내"))
    return specs


def merged_result() -> dict[str, Any]:
    return bundle_result(merged_specs())


def failing_result() -> dict[str, Any]:
    """검증 실패 합성 묶음: 서류 0(1쪽) 통과 · 서류 1(2–3쪽)은 신청인 성명 규칙 실패(verdict red) · 서류 2(4쪽) 통과."""
    keys = ["applicant_name", "applicant_phone"]
    return bundle_result(
        [
            Spec("loan_application", (1, 1), _fields(keys, [1, 1], set())),
            Spec("consent_form", (2, 3), {"applicant_phone": ("합성값", 3, "high")}, validate=("red", [rule()])),
            Spec("income_proof", (4, 4), _fields(keys, [4, 4], set())),
        ]
    )


# --- 화면용 값(build_items 에 바로 넣는 입력) -------------------------------------------------------------


def vdoc(index: Any, start: Any = None, end: Any = None, *, kind: Any = "extracted", validation: Any = None) -> dict[str, Any]:
    """화면용 서류 — 기본은 index+1 쪽 한 장."""
    first = index + 1 if start is None and isinstance(index, int) else start
    return {
        "index": index,
        "type": "loan_application",
        "page_start": first,
        "page_end": first if end is None else end,
        "kind": kind,
        "other_guide": None,
        "validation": validation,
    }


BOX = [[{"x": 0.1, "y": 0.2}, {"x": 0.2, "y": 0.2}, {"x": 0.2, "y": 0.3}, {"x": 0.1, "y": 0.3}]]


def vfinding(
    index: Any,
    field_name: str,
    *,
    page: Any = NO_VALUE,
    boxes: Any = NO_VALUE,
    confidence: Any = "high",
    label: Any = None,
    fid: Any = None,
) -> dict[str, Any]:
    """화면용 탐지 항목 — 기본(NO_VALUE)은 서류 index 의 index+1 쪽, 상자 하나, 신뢰도 high."""
    return {
        "id": f"{index}:{field_name}" if fid is None else fid,
        "document_index": index,
        "field": field_name,
        "category": "기타 개인정보",
        "label": field_name if label is None else label,
        "subject": "기타",
        "mapping_status": "unknown",
        "value": "합성값",
        "masked": "***",
        "exposure": "전체 노출",
        "risk": "unrated",
        "risk_source": None,
        "risk_reason": None,
        "page": (index + 1 if isinstance(index, int) else 1) if page is NO_VALUE else page,
        "boxes": BOX if boxes is NO_VALUE else boxes,
        "confidence": confidence,
    }
