# ==========================================================================
#  공통 계약(BRIEF §5) 모양 검사 — documents·findings·overall·items 가 정확히 계약 키와 허용 값·타입인지
#  findings·API·e2e 테스트가 같이 쓴다. 실패하면 AssertionError(어느 항목·키인지 메시지에).
#  items(검토사항, review-items BRIEF §5.3): 키·순서, R-nn 이 1부터 이어짐, id 겹치지 않음, document_index 가 보이는 서류,
#  page·근거 page 가 그 서류의 화면 쪽 범위 안, finding_id·finding_ids 가 그 서류의 탐지 항목 id,
#  link_id 는 연결 항목만 'link:<기준>:<그 서류>'(links[] 에 있는 id), 그 밖 null(final-flow T3). 연결 항목 = weaklink 와 id 꼴이
#  mismatch:<정수>:<정수> 인 mismatch — 설정 60 의 mismatch:<서류>:<규칙>·review:mismatch 는 link_id null 이다.
#  links·decision·bundle_check(final-flow T3): 키·순서·허용 값, L-nn 이 1부터 이어짐, 쌍의 두 서류가 보이는 서류이고
#  쪽·탐지 항목 id 가 그 서류 안, decision 은 null 또는 키 5개(옛 응답)·8개(설정 60), bundle_check 는 null 또는 {verdict, checks[키 7개]}.
# ==========================================================================

from __future__ import annotations

import re
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
# 검토사항(review-items BRIEF §5.3) — 키는 이 순서 그대로(link_id 는 final-flow T3 에서 맨 뒤에)
ITEM_KEYS = ("id", "number", "type", "document_index", "page", "finding_id", "title", "desc", "next", "evidence", "link_id")
EVIDENCE_KEYS = ("label", "page", "finding_ids", "finding_id")
ITEM_TYPE_KEYS = {"unreadable", "cutoff", "mismatch", "weaklink", "nolocation", "failed", "format", "duplicate", "missing", "lowconf", "other"}
LINK_MISMATCH_ID = re.compile(r"mismatch:[0-9]+:[0-9]+")
NUMBER = re.compile(r"R-\d{2,}")
MAX_EVIDENCE = 20
# 화면용 결과의 최상위 키(build_view — API result 에는 format·job·summary 등이 더 있다)
VIEW_KEYS = ("documents", "findings", "overall", "items", "links", "decision", "bundle_check")
# 문서 간 연결(final-flow T3) — 키는 이 순서 그대로
LINK_KEYS = ("id", "number", "status", "state", "title", "field", "label", "docs", "basis", "missing", "check")
LINK_DOC_KEYS = ("document_index", "page", "fields", "finding_ids")
LINK_NUMBER = re.compile(r"L-\d{2,}")
LINK_STATUS = {"linked": "confirmed", "unmatched": "check", "insufficient": "check"}
MAX_LINK_FIELDS = 80
DECISION_KEYS = ("risk_level", "document_types", "sensitive_categories", "review_reasons", "reason")
DECISION_LIST_KEYS = {"document_types", "sensitive_categories", "review_reasons"}
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
V2_DECISION_LIST_KEYS = {"document_types", "high_risk_items", "medium_risk_items", "low_risk_items", "review_reasons"}
BUNDLE_CHECK_KEYS = ("id", "name", "severity", "status", "field", "label", "group")


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


def _screen_range(doc: Mapping[str, Any]) -> tuple[int, int] | None:
    """보이는 서류의 화면 쪽 범위(page_start, max(page_start, page_end)) — 보이지 않는 서류면 None."""
    start, end = doc.get("page_start"), doc.get("page_end")
    if _int(doc.get("index")) and doc["index"] >= 0 and _int(start) and start >= 1 and _int(end) and end >= 1:
        return start, max(start, end)
    return None


def assert_evidence(evidence: Any, where: str, span: tuple[int, int], finding_ids: set[str]) -> None:
    assert isinstance(evidence, Mapping) and list(evidence) == list(EVIDENCE_KEYS), where
    assert isinstance(evidence["label"], str) and evidence["label"], where
    assert _int(evidence["page"]) and span[0] <= evidence["page"] <= span[1], where
    ids = evidence["finding_ids"]
    assert isinstance(ids, list) and all(isinstance(i, str) and i in finding_ids for i in ids), where
    assert evidence["finding_id"] is None or evidence["finding_id"] in finding_ids, where


def assert_item(item: Any, spans: Mapping[int, tuple[int, int]], finding_ids: Mapping[int, set[str]]) -> None:
    """검토사항 하나(review-items BRIEF §5.3 — 키·순서·종류·서류·쪽·근거). spans·finding_ids 는 보이는 서류 index 기준."""
    assert isinstance(item, Mapping) and list(item) == list(ITEM_KEYS), item
    where = str(item["id"])[:60]
    assert isinstance(item["id"], str) and item["id"], where
    assert isinstance(item["number"], str) and NUMBER.fullmatch(item["number"]), where
    assert item["type"] in ITEM_TYPE_KEYS, where
    index = item["document_index"]
    assert _int(index) and index in spans, where  # 보이는 서류의 검토사항만
    span, own = spans[index], finding_ids[index]
    assert _int(item["page"]) and span[0] <= item["page"] <= span[1], where
    assert item["finding_id"] is None or item["finding_id"] in own, where
    if item["type"] == "nolocation":
        assert isinstance(item["finding_id"], str), where
    else:
        assert item["finding_id"] is None, where
    for name in ("title", "desc", "next"):
        assert isinstance(item[name], str) and item[name], where
    assert isinstance(item["evidence"], list) and len(item["evidence"]) <= MAX_EVIDENCE, where
    for evidence in item["evidence"]:
        assert_evidence(evidence, where, span, own)
    if is_link_item(item):
        link_id = item["link_id"]
        assert isinstance(link_id, str) and re.fullmatch(r"link:\d+:\d+", link_id), where
        assert link_id.rsplit(":", 1)[1] == str(index), where  # 대상 서류(이 항목의 서류)의 쌍
    else:
        assert item["link_id"] is None, where


def is_link_item(item: Mapping[str, Any]) -> bool:
    """연결 항목(link_id 가 있어야 한다) — weaklink 와 id 꼴이 mismatch:<정수>:<정수> 인 mismatch."""
    return item["type"] == "weaklink" or (item["type"] == "mismatch" and LINK_MISMATCH_ID.fullmatch(item["id"]) is not None)


def _spans_and_ids(documents: list[Any], findings: list[Any]) -> tuple[dict[int, tuple[int, int]], dict[int, set[str]]]:
    """보이는 서류 index → 화면 쪽 범위, 그 서류의 탐지 항목 id."""
    spans: dict[int, tuple[int, int]] = {}
    for doc in documents:
        span = _screen_range(doc) if isinstance(doc, Mapping) else None
        if span is not None and doc["index"] not in spans:
            spans[doc["index"]] = span
    finding_ids: dict[int, set[str]] = {index: set() for index in spans}
    for finding in findings:
        if isinstance(finding, Mapping) and finding.get("document_index") in finding_ids and isinstance(finding.get("id"), str):
            finding_ids[finding["document_index"]].add(finding["id"])
    return spans, finding_ids


def assert_items(items: Any, documents: list[Any], findings: list[Any], links: list[Any] | None = None) -> None:
    """result.items 전체 — 각 항목 모양 + R-nn 연속 + id 겹치지 않음 + 서류·쪽·탐지 항목 참조.

    links 를 주면 mismatch·weaklink 의 link_id 가 그 안의 id 인지도 본다.
    """
    assert isinstance(items, list), items
    spans, finding_ids = _spans_and_ids(documents, findings)
    for item in items:
        assert_item(item, spans, finding_ids)
    assert [i["number"] for i in items] == [f"R-{n:02d}" for n in range(1, len(items) + 1)], "R-nn 이 1부터 이어지지 않는다"
    ids = [i["id"] for i in items]
    assert len(set(ids)) == len(ids), "검토사항 id 가 겹친다"
    if links is not None:
        link_ids = {link["id"] for link in links}
        for item in items:
            if is_link_item(item):
                assert item["link_id"] in link_ids, item["id"]


def assert_link(link: Any, spans: Mapping[int, tuple[int, int]], finding_ids: Mapping[int, set[str]]) -> None:
    """문서 간 연결 한 줄 — 키·순서·상태·두 서류(보이는 서류, 쪽·탐지 항목 id 가 그 서류 안)·글."""
    assert isinstance(link, Mapping) and list(link) == list(LINK_KEYS), link
    where = str(link["id"])[:60]
    assert isinstance(link["number"], str) and LINK_NUMBER.fullmatch(link["number"]), where
    assert link["state"] in LINK_STATUS and link["status"] == LINK_STATUS[link["state"]], where
    for name in ("title", "field", "label", "missing", "check"):
        assert isinstance(link[name], str), where
    assert link["title"] and link["field"] and link["label"] and link["check"], where
    assert isinstance(link["basis"], list) and all(isinstance(b, str) and b for b in link["basis"]), where
    if link["state"] == "linked":
        assert len(link["basis"]) == 1 and link["missing"] == "", where
    else:
        assert link["basis"] == [] and link["missing"], where
    docs = link["docs"]
    assert isinstance(docs, list) and len(docs) == 2, where
    indexes = []
    for doc in docs:
        assert isinstance(doc, Mapping) and list(doc) == list(LINK_DOC_KEYS), where
        index = doc["document_index"]
        assert _int(index) and index in spans, where
        span = spans[index]
        assert _int(doc["page"]) and span[0] <= doc["page"] <= span[1], where
        assert isinstance(doc["fields"], str) and 0 < len(doc["fields"]) <= MAX_LINK_FIELDS, where
        ids = doc["finding_ids"]
        assert isinstance(ids, list) and len(ids) <= 1 and all(isinstance(i, str) and i in finding_ids[index] for i in ids), where
        indexes.append(index)
    assert indexes[0] != indexes[1], where
    assert link["id"] == f"link:{indexes[0]}:{indexes[1]}", where


def assert_links(links: Any, documents: list[Any], findings: list[Any]) -> None:
    """links 전체 — 각 줄 모양 + L-nn 연속 + id 겹치지 않음 + 기준 서류가 모두 같음."""
    assert isinstance(links, list), links
    spans, finding_ids = _spans_and_ids(documents, findings)
    for link in links:
        assert_link(link, spans, finding_ids)
    assert [link["number"] for link in links] == [f"L-{n:02d}" for n in range(1, len(links) + 1)], "L-nn 이 1부터 이어지지 않는다"
    ids = [link["id"] for link in links]
    assert len(set(ids)) == len(ids), "연결 id 가 겹친다"
    assert len({link["docs"][0]["document_index"] for link in links}) <= 1, "기준 서류가 둘 이상이다"


def assert_decision(decision: Any) -> None:
    """null 또는 위험도_판정 키 5개(read_decision 그대로) 또는 설정 60 판정 키 8개(read_verdict 그대로)."""
    if decision is None:
        return
    assert isinstance(decision, Mapping), decision
    v2 = "high_risk_items" in decision
    assert list(decision) == list(V2_DECISION_KEYS if v2 else DECISION_KEYS), decision
    assert decision["risk_level"] in ("상", "중", "하", "검토 필요", None), decision
    assert _str_or_none(decision["reason"]), decision
    if v2:
        assert _str_or_none(decision["recommended_action"]), decision
    for key in V2_DECISION_LIST_KEYS if v2 else DECISION_LIST_KEYS:
        value = decision[key]
        assert value is None or (isinstance(value, list) and all(isinstance(v, str) for v in value)), key


def assert_bundle_check(bundle: Any) -> None:
    """null 또는 {verdict, checks[{id, name, severity, status, field, label, group}]} — 규칙의 서류별 결과는 없다."""
    if bundle is None:
        return
    assert isinstance(bundle, Mapping) and list(bundle) == ["verdict", "checks"], bundle
    assert bundle["verdict"] in ("green", "yellow", "red", None), bundle
    assert isinstance(bundle["checks"], list), bundle
    for check in bundle["checks"]:
        assert isinstance(check, Mapping) and list(check) == list(BUNDLE_CHECK_KEYS), check
        assert isinstance(check["id"], str) and isinstance(check["name"], str), check
        assert check["severity"] in ("error", "warning", None), check
        assert check["status"] in ("pass", "fail", "absent", "unknown"), check
        for key in ("field", "label", "group"):
            assert _str_or_none(check[key]), check
        if check["field"] is None:
            assert check["label"] is None, check


def assert_view(view: Any) -> None:
    """build_view 결과(또는 API result 의 화면용 키)가 계약 모양인지 — 개별 모양 + id 중복·서류 참조 + 검토사항 +
    문서 간 연결·판정 키·묶음 검증."""
    assert isinstance(view, Mapping)
    assert set(VIEW_KEYS) <= set(view), sorted(set(VIEW_KEYS) - set(view))
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
    assert_links(view["links"], documents, findings)
    assert_items(view["items"], documents, findings, view["links"])
    assert_decision(view["decision"])
    assert_bundle_check(view["bundle_check"])
