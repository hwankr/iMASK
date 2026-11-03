# ==========================================================================
#  공통 계약(BRIEF §5) 모양 검사 — documents·findings·overall 이 정확히 계약 키와 허용 값·타입인지
#  findings·API·e2e 테스트가 같이 쓴다. 실패하면 AssertionError(어느 항목·키인지 메시지에).
# ==========================================================================

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from imask_backend.fields import CATS, EXPOSURES, SUBJECTS

DOCUMENT_KEYS = {"index", "type", "page_start", "page_end", "kind", "other_guide", "validation"}
FINDING_KEYS = {
    "id",
    "document_index",
    "field",
    "category",
    "label",
    "subject",
    "mapping_status",
    "value",
    "masked",
    "exposure",
    "risk",
    "risk_source",
    "risk_reason",
    "page",
    "boxes",
    "confidence",
}
OVERALL_KEYS = {"level", "text", "next_stage", "next_text"}
RISKS = {"high", "medium", "low", "unrated"}


def _int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _str_or_none(value: Any) -> bool:
    return value is None or isinstance(value, str)


def assert_document(doc: Any) -> None:
    assert isinstance(doc, Mapping) and set(doc) == DOCUMENT_KEYS, doc
    assert _int(doc["index"]) and doc["index"] >= 0, doc
    assert _str_or_none(doc["type"]), doc
    start, end = doc["page_start"], doc["page_end"]
    assert (start is None and end is None) or (_int(start) and _int(end) and 1 <= start <= end), doc
    assert doc["kind"] in ("extracted", "other"), doc
    assert _str_or_none(doc["other_guide"]) and _str_or_none(doc["validation"]), doc


def assert_finding(finding: Any) -> None:
    assert isinstance(finding, Mapping) and set(finding) == FINDING_KEYS, finding
    f = finding
    # field 는 추출의 원래 키 그대로라 빈 문자열일 수도 있다(그때 label 은 "(이름 없는 항목)"). 짝 없는 서로게이트도
    # 원문 그대로 둘 수 있다 — 응답 경계(api/index.py)가 그런 응답을 ASCII escape JSON 으로 보낸다(T1-fix5)
    assert _int(f["document_index"]) and isinstance(f["field"], str), f["id"]
    assert f["id"] == f"{f['document_index']}:{f['field']}", f["id"]
    assert f["category"] in CATS and f["subject"] in SUBJECTS, f["id"]
    assert isinstance(f["label"], str) and f["label"], f["id"]
    assert f["mapping_status"] in ("ok", "needs_review", "unknown"), f["id"]
    assert isinstance(f["value"], str) and f["value"].strip(), f["id"]
    assert isinstance(f["masked"], str) and len(f["masked"]) == len(f["value"]), f["id"]
    assert f["exposure"] in EXPOSURES, f["id"]
    assert f["risk"] in RISKS, f["id"]
    if f["risk"] == "unrated":
        assert f["risk_source"] is None and f["risk_reason"] is None, f["id"]
    else:
        assert f["risk_source"] == "workflow" and _str_or_none(f["risk_reason"]), f["id"]
    assert f["page"] is None or (_int(f["page"]) and f["page"] >= 1), f["id"]
    assert isinstance(f["boxes"], list), f["id"]
    if f["page"] is None:
        assert f["boxes"] == [], f["id"]
    for box in f["boxes"]:
        assert isinstance(box, list) and len(box) == 4, f["id"]
        for point in box:
            assert isinstance(point, Mapping) and set(point) == {"x", "y"}, f["id"]
            for v in point.values():
                assert isinstance(v, float) and 0.0 <= v <= 1.0, f["id"]
    assert f["confidence"] in ("high", "low", None), f["id"]


def assert_overall(overall: Any) -> None:
    assert isinstance(overall, Mapping) and set(overall) == OVERALL_KEYS, overall
    assert overall["level"] in ("상", "중", "하", "검토 필요", None), overall
    assert isinstance(overall["text"], str) and isinstance(overall["next_text"], str), overall
    assert overall["next_stage"] in ("권장_조치", "검토_안내", None), overall


def assert_view(view: Any) -> None:
    """build_view 결과(또는 API result 의 세 키)가 계약 모양인지 — 개별 모양 + id 중복·서류 참조."""
    assert isinstance(view, Mapping)
    documents, findings = view["documents"], view["findings"]
    assert isinstance(documents, list) and isinstance(findings, list)
    for doc in documents:
        assert_document(doc)
    indexes = [d["index"] for d in documents]
    assert indexes == sorted(indexes) and len(set(indexes)) == len(indexes), indexes
    for finding in findings:
        assert_finding(finding)
    ids = [f["id"] for f in findings]
    assert len(set(ids)) == len(ids), "id 가 겹친다"
    assert {f["document_index"] for f in findings} <= set(indexes)
    assert_overall(view["overall"])
