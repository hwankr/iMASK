# ==========================================================================
#  Upstage 응답 파싱과 요약
#  - parse_stages(response): output[] 항목마다 단계 이름(model)·status·data(content[0].text 를
#    JSON 으로 푼 값)·additional_values(신뢰도·좌표, JSON 으로 푼 값)를 뽑는다. 순서는 output 순서.
#    한 항목에 content 가 여럿일 수 있어(서류-분류는 서류마다 하나) contents 에 모두 담는다.
#  - summarize(response 또는 stages): 단계는 순서가 아니라 **이름으로** 찾는다(BRIEF §4).
#  - 모양이 달라도 예외를 던지지 않는다. 못 찾은 값은 None.
#  - 개수는 **읽을 수 있는 항목만** 센다. 하나도 읽지 못했으면(content 없음·빈 배열·[null]·
#    JSON 아님·실패 단계) 0 이 아니라 None — '확인된 0'과 '알 수 없음'을 섞지 않는다.
#    개수·종류·위험도·마지막 단계는 status 가 completed(또는 없음)인 단계만 쓴다(stage_names·
#    stage_counts 는 전체 output 그대로). 일반 텍스트가 정상인 단계(분류 코드·기타 안내·
#    Markdown)는 텍스트 그대로 받아들인다.
#
#  실제 응답(2026-11-02, config_id 3)에서 확인한 단계 이름 — evidence/T1/stage-shapes.md:
#    step_1_parse · step_2_classify · "Information Extract - 민감정보_추출" ·
#    "Validate - 필수항목_검증" · 병합-1 · "Instruct - 위험도_판정" · "Instruct - 권장_조치" ·
#    "Instruct - 기타_서류_안내" (검토_안내 는 위험도 '검토 필요' 일 때만 나온다)
#  Studio 노드 이름 앞에 노드 종류("Instruct - " 등)가 붙어 오므로 " - <이름>" 꼴도 같은 단계로 본다.
#  서류-인식·서류-분류는 이름이 step_1_parse·step_2_classify 로 오므로 그 이름과 step_type 으로도 찾는다.
# ==========================================================================

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

# 워크플로우 단계(정규 이름 = Studio 노드 이름)
STAGE_PARSE = "서류-인식"
STAGE_CLASSIFY = "서류-분류"
STAGE_EXTRACT = "민감정보_추출"
STAGE_VALIDATE = "필수항목_검증"
STAGE_MERGE = "병합-1"
STAGE_RISK = "위험도_판정"
STAGE_ACTION = "권장_조치"
STAGE_REVIEW = "검토_안내"
STAGE_OTHER = "기타_서류_안내"

STAGE_KEYS = (
    STAGE_PARSE,
    STAGE_CLASSIFY,
    STAGE_EXTRACT,
    STAGE_VALIDATE,
    STAGE_MERGE,
    STAGE_RISK,
    STAGE_ACTION,
    STAGE_REVIEW,
    STAGE_OTHER,
)

# 정규 이름과 다르게 오는 실제 이름(output[].model)
_STAGE_ALIASES = {
    "step_1_parse": STAGE_PARSE,
    "step_2_classify": STAGE_CLASSIFY,
}

# 이름으로 못 찾을 때 쓰는 step_type(종류가 하나뿐인 단계만 — instruct 는 여럿이라 쓰지 않는다)
_STEP_TYPE_STAGES = {
    "document-parse": STAGE_PARSE,
    "document-classify": STAGE_CLASSIFY,
}

# 마지막 단계 후보(위험도 상·중·하 → 권장_조치, 검토 필요 → 검토_안내)
FINAL_STAGES = (STAGE_ACTION, STAGE_REVIEW)


def _loads(value: Any) -> Any:
    """문자열이면 JSON 으로 풀고, 실패하면 원래 문자열. 문자열이 아니면 그대로."""
    if isinstance(value, (str, bytes, bytearray)):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return value
    return value


def stage_key(name: Any, step_type: Any = None) -> str | None:
    """output[].model(과 step_type)을 정규 단계 이름으로. 모르는 단계는 None."""
    if isinstance(name, str):
        if name in STAGE_KEYS:
            return name
        if name in _STAGE_ALIASES:
            return _STAGE_ALIASES[name]
        for key in STAGE_KEYS:
            if name.endswith(" - " + key):
                return key
    if isinstance(step_type, str):
        return _STEP_TYPE_STAGES.get(step_type)
    return None


def _content_entry(entry: Any) -> dict[str, Any]:
    if not isinstance(entry, Mapping):
        return {"data": None, "additional_values": None}
    additional = entry.get("additional_values")
    return {
        "data": _loads(entry.get("text")),
        "additional_values": None if additional is None else _loads(additional),
    }


def parse_stages(response: Any) -> list[dict[str, Any]]:
    """응답의 output[] 를 단계 목록으로 바꾼다. 모양이 달라도 예외 없이 빈 목록·None 으로.

    항목마다: name(output[].model 원문), key(정규 단계 이름 또는 None), status, step_type,
    data·additional_values(content[0] 을 푼 값), contents(content[] 전부를 같은 방식으로 푼 목록).
    """
    if not isinstance(response, Mapping):
        return []
    output = response.get("output")
    if not isinstance(output, list):
        return []
    stages: list[dict[str, Any]] = []
    for item in output:
        if not isinstance(item, Mapping):
            continue
        content = item.get("content")
        contents = [_content_entry(c) for c in content] if isinstance(content, list) else []
        first = contents[0] if contents else {"data": None, "additional_values": None}
        name = item.get("model")
        step_type = item.get("step_type")
        stages.append(
            {
                "name": name,
                "key": stage_key(name, step_type),
                "status": item.get("status"),
                "step_type": step_type,
                "data": first["data"],
                "additional_values": first["additional_values"],
                "contents": contents,
            }
        )
    return stages


def _as_stages(response_or_stages: Any) -> list[Mapping[str, Any]]:
    if isinstance(response_or_stages, Mapping):
        return parse_stages(response_or_stages)
    if isinstance(response_or_stages, Sequence) and not isinstance(response_or_stages, (str, bytes)):
        return [s for s in response_or_stages if isinstance(s, Mapping)]
    return []


def _key_of(stage: Mapping[str, Any]) -> str | None:
    key = stage.get("key")
    if key in STAGE_KEYS:
        return key
    return stage_key(stage.get("name"), stage.get("step_type"))


def stages_for(stages: Sequence[Mapping[str, Any]], key: str) -> list[Mapping[str, Any]]:
    """정규 이름이 key 인 단계를 모두(output 순서대로)."""
    return [s for s in stages if _key_of(s) == key]


def _usable(stage: Mapping[str, Any]) -> bool:
    """요약에 쓸 단계: status 가 completed 이거나 없음(손으로 만든 stages). 실패·진행 중은 뺀다."""
    return stage.get("status") in (None, "completed")


def _usable_for(stages: Sequence[Mapping[str, Any]], key: str) -> list[Mapping[str, Any]]:
    return [s for s in stages_for(stages, key) if _usable(s)]


def _count_or_none(count: int) -> int | None:
    """하나도 읽지 못했으면 None(개수를 정할 수 없음)."""
    return count if count > 0 else None


def _has_text_or_object(data: Any) -> bool:
    return (isinstance(data, str) and bool(data.strip())) or isinstance(data, Mapping)


def _contents_of(stage: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    contents = stage.get("contents")
    if isinstance(contents, list):
        return [c for c in contents if isinstance(c, Mapping)]
    # contents 가 없는 목록(손으로 만든 stages 등)은 data·additional_values 하나로 본다
    return [{"data": stage.get("data"), "additional_values": stage.get("additional_values")}]


def _document_type(content: Mapping[str, Any]) -> str | None:
    """서류-분류 content 하나의 서류 종류: additional_values.document_type._value, 없으면 text.

    비지 않은 문자열만 인정한다(읽지 못한 항목은 None → 서류로 세지 않음).
    """
    additional = content.get("additional_values")
    if isinstance(additional, Mapping):
        doc_type = additional.get("document_type")
        if isinstance(doc_type, Mapping):
            doc_type = doc_type.get("_value")
        if isinstance(doc_type, str) and doc_type.strip():
            return doc_type.strip()
    data = content.get("data")
    if isinstance(data, str) and data.strip():
        return data.strip()
    return None


def _risk_level(stage: Mapping[str, Any]) -> str | None:
    """위험도_판정 의 additional_values.enum(상·중·하·검토 필요)."""
    additional = stage.get("additional_values")
    if isinstance(additional, Mapping):
        value = additional.get("enum")
        if isinstance(value, str) and value:
            return value
    return None


def summarize(response_or_stages: Any) -> dict[str, Any]:
    """응답(또는 parse_stages 결과)에서 요약값을 뽑는다. 못 찾은 값은 None, 예외 없음.

    읽는 위치(evidence/T1/stage-shapes.md). 아래 여섯 값은 status 가 completed(또는 없음)인 단계만 쓴다
    (stage_names·stage_counts 는 상태와 상관없이 전체 output 을 그대로 센다):
      document_count           서류-분류 content[] 중 분류 코드를 읽을 수 있는 항목 수(서류마다 하나)
      document_types           그 항목들의 additional_values.document_type._value (없으면 text)
      extracted_document_count 민감정보_추출 output 항목 중 data 가 JSON 객체인 수(서류마다 하나)
      risk_level               위험도_판정 additional_values.enum
      final_stage              권장_조치·검토_안내 중 나온 단계의 정규 이름
      other_document_count     기타_서류_안내 output 항목 중 본문(text)이 있는 수
    세 개수와 document_types 는 하나도 읽지 못했으면(단계 없음 포함) None.
    """
    stages = _as_stages(response_or_stages)
    names = [s.get("name") for s in stages if isinstance(s.get("name"), str)]

    document_types = [
        t
        for s in _usable_for(stages, STAGE_CLASSIFY)
        for t in (_document_type(c) for c in _contents_of(s))
        if t is not None
    ]

    extracted = sum(1 for s in _usable_for(stages, STAGE_EXTRACT) if isinstance(s.get("data"), Mapping))

    risk_level = next((r for r in (_risk_level(s) for s in _usable_for(stages, STAGE_RISK)) if r), None)

    final_stage = next((k for k in (_key_of(s) for s in stages if _usable(s)) if k in FINAL_STAGES), None)

    others = sum(1 for s in _usable_for(stages, STAGE_OTHER) if _has_text_or_object(s.get("data")))

    return {
        "stage_names": list(dict.fromkeys(names)),
        "stage_counts": dict(Counter(names)),
        "document_count": _count_or_none(len(document_types)),
        "document_types": document_types or None,
        "extracted_document_count": _count_or_none(extracted),
        "risk_level": risk_level,
        "final_stage": final_stage,
        "other_document_count": _count_or_none(others),
    }


# --- 다른 모듈(findings 등)이 쓰는 공개 도우미 — 위 요약과 같은 규칙을 그대로 쓴다 -----------------


def as_stages(response_or_stages: Any) -> list[Mapping[str, Any]]:
    """응답(Mapping)이면 parse_stages, 단계 목록이면 Mapping 인 것만. 그 밖은 빈 목록."""
    return _as_stages(response_or_stages)


def usable_stages_for(stages: Sequence[Mapping[str, Any]], key: str) -> list[Mapping[str, Any]]:
    """정규 이름이 key 이고 쓸 수 있는(completed 또는 상태 없음) 단계를 output 순서대로."""
    return _usable_for(stages, key)


def stage_contents(stage: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """단계의 content 목록(Mapping 인 것만). contents 가 없으면 data·additional_values 하나로 본다."""
    return _contents_of(stage)


def document_type(content: Mapping[str, Any]) -> str | None:
    """서류-분류 content 하나의 분류 코드(document_type._value, 없으면 text). 못 읽으면 None."""
    return _document_type(content)
