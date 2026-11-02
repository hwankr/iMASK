# ==========================================================================
#  테스트용 가짜 Upstage 응답 — 실제 응답 구조(evidence/T1/stage-shapes.md)를 본떠 손으로 만든다.
#  값은 모두 지어낸 짧은 문자열이다. 실제 응답 파일은 테스트 자료로 쓰지 않는다.
# ==========================================================================

from __future__ import annotations

import json
from typing import Any

EXTRACT_KEYS = ("applicant_name", "applicant_rrn", "loan_info")


def item(model: str, step_type: str, *contents: dict[str, Any], status: str = "completed") -> dict[str, Any]:
    return {
        "id": f"msg_{model}",
        "type": "message",
        "role": "assistant",
        "status": status,
        "model": model,
        "step_type": step_type,
        "content": list(contents),
    }


def content(text: Any, additional: Any = None, *, raw_text: bool = False) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "type": "output_text",
        "text": text if raw_text else json.dumps(text, ensure_ascii=False),
        "annotations": [],
    }
    if additional is not None:
        entry["additional_values"] = json.dumps(additional, ensure_ascii=False)
    return entry


def classify_entry(code: str, page: int) -> dict[str, Any]:
    return content(
        code,
        {"document_type": {"_value": code, "confidence": "high"}, "page_ranges": [[page, page]]},
        raw_text=True,
    )


def extract_item(page: int) -> dict[str, Any]:
    data = {key: ("가짜값" if key == "applicant_name" else "") for key in EXTRACT_KEYS}
    additional = {"page_ranges": [[page, page]], "applicant_name": {"_value": "가짜값", "confidence": "high"}}
    return item("Information Extract - 민감정보_추출", "information-extract", content(data, additional))


def build_response(
    *,
    types: tuple[str, ...] = ("loan_application", "consent_form", "Other"),
    risk: str = "상",
    final: str = "권장_조치",
    status: str = "completed",
) -> dict[str, Any]:
    """서류 types 로 분류되고, Other 를 뺀 서류마다 추출·검증되는 응답."""
    doc_pages = [(code, page) for page, code in enumerate(types, 1)]
    output = [
        item("step_1_parse", "document-parse", content({"api": "2.0", "elements": []}, {"document_ids": ["f"]})),
        item("step_2_classify", "document-classify", *(classify_entry(c, p) for c, p in doc_pages)),
    ]
    output += [extract_item(p) for c, p in doc_pages if c != "Other"]
    output += [
        item("Instruct - 기타_서류_안내", "instruct", content("가짜 안내", {"citations": []}, raw_text=True))
        for c, _ in doc_pages
        if c == "Other"
    ]
    output += [
        item("Validate - 필수항목_검증", "validate", content("green", {"verdict": "green", "checks": []}))
        for c, _ in doc_pages
        if c != "Other"
    ]
    output.append(item("병합-1", "merge", content({"count": 2}, {"previous_step_name": "x"})))
    output.append(
        item("Instruct - 위험도_판정", "instruct", content("## 가짜 판정", {"enum": risk, "citations": []}, raw_text=True))
    )
    output.append(item(f"Instruct - {final}", "instruct", content("## 가짜 조치", {"citations": []}, raw_text=True)))
    return {"id": "resp_fake", "object": "response", "status": status, "output": output}
