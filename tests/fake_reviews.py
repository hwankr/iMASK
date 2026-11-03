# ==========================================================================
#  검토 동작 테스트용 가짜 결과 — 손으로 지은 값만 쓴다(실제 응답 파일의 값은 옮기지 않는다)
#  custom_result: 서류마다 1쪽씩 loan_application 분류 + 추출 data(키 순서 그대로). 텍스트·additional_values 는
#  ASCII JSON 이라 짝 없는 서로게이트·NUL 이 든 키도 escape 로 저장되고 parse_stages 의 json.loads 로 되살아난다.
#  JWT·키 꼴 글자는 쓰지 않는다.
# ==========================================================================

from __future__ import annotations

import json
from typing import Any

from fake_findings import rect

ACTOR = "김검토"


def _entry(text: str, extra: dict[str, Any]) -> dict[str, Any]:
    # additional_values 는 ASCII JSON — 짝 없는 서로게이트·NUL 키도 escape 로 저장되고 json.loads 로 되살아난다
    return {"type": "output_text", "text": text, "annotations": [], "additional_values": json.dumps(extra, ensure_ascii=True)}


def _stage(model: str, step_type: str, *contents: dict[str, Any]) -> dict[str, Any]:
    return {"model": model, "step_type": step_type, "status": "completed", "content": list(contents)}


def custom_result(
    docs: list[dict[str, Any]],
    *,
    unpaged: dict[str, Any] | None = None,
    risk: str | None = None,
    summary: dict[str, Any] | None = None,
    pageless_classify: bool = False,
) -> dict[str, Any]:
    """서류 i(0부터) = i+1 쪽 loan_application, 추출 data = docs[i](키 순서 그대로).

    unpaged 를 주면 page_ranges 없는 추출 하나를 더한다(짝 없는 서류 — 쪽이 없어 검토 대상이 아님).
    pageless_classify 면 분류에도 추출에도 쪽 범위를 넣지 않는다(옛 형식처럼 유효한 서류 0개).
    """
    ranges = (lambda page: []) if pageless_classify else (lambda page: [[page, page]])
    classify = _stage(
        "step_2_classify",
        "document-classify",
        *(
            _entry("loan_application", {"document_type": {"_value": "loan_application"}, "page_ranges": ranges(page)})
            for page in range(1, len(docs) + 1)
        ),
    )
    output = [classify]
    for page, data in enumerate(docs, 1):
        meta = {key: {"page": page, "confidence": "high", "coordinates": rect(0.1, 0.2), "word_coordinates": []} for key in data}
        output.append(
            _stage(
                "Information Extract - 민감정보_추출",
                "information-extract",
                _entry(json.dumps(data, ensure_ascii=True), {"page_ranges": ranges(page), **meta}),
            )
        )
    if unpaged is not None:
        output.append(
            _stage("Information Extract - 민감정보_추출", "information-extract", _entry(json.dumps(unpaged, ensure_ascii=True), {}))
        )
    if risk is not None:
        output.append(_stage("Instruct - 위험도_판정", "instruct", _entry("## 판정", {"enum": risk})))
    return {"format": "imask-upstage-v1", "job": {}, "summary": summary or {}, "response": {"output": output}}


SMALL = [
    {"applicant_name": "김가짜", "applicant_rrn": "900101-1234567", "applicant_phone": "010-0000-1234"},
    {"applicant_address": "가상시 예시로 1"},
]
