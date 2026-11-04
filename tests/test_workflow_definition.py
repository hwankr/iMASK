# ==========================================================================
#  저장소 정의 workflows/final_imask_workflow.json 의 무결성 — 파일 모양(UTF-8·LF·2칸 들여쓰기),
#  그래프(없는 다음 step 없음·첫 step 하나), 분류 코드 = 분류 갈래 조건, Match 기준·대상이 병합-1 로
#  들어가는 Extract, 묶음_검증이 추출 노드를 가리킴, 추출 4개가 같은 17키 스키마,
#  위험도_판정 갈래 = 등급 4개이고 판정 프롬프트에 미션 2 정답지 키 5개가 있음.
#  네트워크·스크립트 없이 파일만 읽는다.
# ==========================================================================

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / "workflows" / "final_imask_workflow.json"

# Studio API 의 step 형식(키 순서까지)
STEP_KEYS = ("id", "name", "type", "data", "next_steps", "is_first", "node_id")
MAX_NEXT = 500  # step 하나의 next_steps 수


def workflow_body() -> dict:
    return json.loads(WORKFLOW.read_bytes().decode("utf-8"))


def steps_by_name() -> dict[str, dict]:
    return {s["name"]: s for s in workflow_body()["steps"]}


def dump_config(body: Any) -> bytes:
    """2칸 들여쓰기, UTF-8(BOM 없음), LF, 끝 줄바꿈 — workflows/*.json 의 모양."""
    return (json.dumps(body, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def check_config(body: dict) -> list[str]:
    """Studio 에 넣을 수 있는 꼴인지 — 문제 목록(없으면 빈 목록)."""
    problems: list[str] = []
    if not isinstance(body.get("name"), str) or not body["name"].strip():
        problems.append("설정 이름(name)이 없습니다")
    steps = body.get("steps")
    if not isinstance(steps, list) or not steps:
        return problems + ["steps 가 비었습니다"]
    names: dict[str, int] = {}
    for index, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            problems.append(f"{index}번째 step 이 객체가 아닙니다")
            continue
        name = step.get("name")
        if not isinstance(name, str) or not name:
            problems.append(f"{index}번째 step 에 이름이 없습니다")
        elif name in names:
            problems.append(f"{index}번째 step 의 이름이 {names[name]}번째 step 과 겹칩니다")
        else:
            names[name] = index
        if not isinstance(step.get("type"), str) or not step["type"]:
            problems.append(f"{index}번째 step 에 type 이 없습니다")
        if not isinstance(step.get("next_steps"), list):
            problems.append(f"{index}번째 step 의 next_steps 가 목록이 아닙니다")
        elif len(step["next_steps"]) > MAX_NEXT:
            problems.append(f"{index}번째 step 의 next_steps 가 너무 많습니다(>{MAX_NEXT})")
    firsts = [s for s in steps if isinstance(s, dict) and s.get("is_first") is True]
    if len(firsts) != 1:
        problems.append(f"첫 step(is_first)이 {len(firsts)}개입니다 — 하나여야 합니다")
    for index, step in enumerate(steps, 1):
        if not isinstance(step, dict) or not isinstance(step.get("next_steps"), list):
            continue
        for slot, nxt in enumerate(step["next_steps"][:MAX_NEXT], 1):
            if not isinstance(nxt, dict) or not isinstance(nxt.get("step_name"), str):
                problems.append(f"{index}번째 step 의 next_steps[{slot}] 모양이 다릅니다")
            elif nxt["step_name"] not in names:
                problems.append(f"{index}번째 step 의 next_steps[{slot}] 이 없는 step 을 가리킵니다")
    return problems


def test_workflow_file_shape():
    data = WORKFLOW.read_bytes()
    assert not data.startswith(b"\xef\xbb\xbf") and b"\r" not in data
    body = json.loads(data.decode("utf-8"))
    assert data == dump_config(body)  # 2칸 들여쓰기·LF·끝 줄바꿈
    assert set(body) == {"name", "steps"}
    for step in body["steps"]:
        assert list(step) == list(STEP_KEYS)
    assert check_config(body) == []


def test_workflow_graph():
    steps = steps_by_name()
    assert len(steps) == len(workflow_body()["steps"]) == 13
    for step in steps.values():
        for nxt in step["next_steps"]:
            assert nxt["step_name"] in steps
    firsts = [s for s in steps.values() if s["is_first"]]
    assert [s["name"] for s in firsts] == ["step_1_parse"]
    ids = [s["id"] for s in steps.values()] + [s["node_id"] for s in steps.values()]
    assert len(set(ids)) == len(ids)


def test_classify_codes_match_conditions():
    classify = steps_by_name()["step_2_classify"]
    codes = [o["const"] for o in classify["data"]["text"]["format"]["schema"]["oneOf"]]
    values = [n["condition"]["value"] for n in classify["next_steps"]]
    assert len(codes) == 14 and len(set(codes)) == 14
    assert sorted(values) == sorted(codes)  # 코드마다 정확히 한 갈래
    assert all(n["condition"]["field"] == "text" and n["condition"]["operator"] == "==" for n in classify["next_steps"])


def test_match_anchor_and_targets_feed_merge():
    steps = steps_by_name()
    merges = [s for s in steps.values() if s["type"] == "merge"]
    assert [m["name"] for m in merges] == ["병합-1"]
    match = steps["Match - 서류_대조"]
    assert [n["step_name"] for n in merges[0]["next_steps"]] == ["Match - 서류_대조"]
    data = match["data"]
    named = [data["anchor_step_name"]] + [t["step_name"] for t in data["targets"]]
    assert data["anchor_step_name"] == "Information Extract - 추출_신청서"
    for name in named:
        assert steps[name]["type"] == "information-extract"
        assert [n["step_name"] for n in steps[name]["next_steps"]] == ["병합-1"]
    methods = {t["output_key"]: t["document_match"]["method"]["type"] for t in data["targets"]}
    assert methods == {"추출_확인서": "exact", "추출_증빙": "fuzzy", "추출_위임장": "exact"}


def test_validate_checks_reference_extract_nodes():
    steps = steps_by_name()
    extract_names = {s["data"]["custom_name"] for s in steps.values() if s["type"] == "information-extract"}
    checks = steps["Validate - 묶음_검증"]["data"]["checks"]
    assert len(checks) == 5
    assert [c["severity"] for c in checks] == ["error"] + ["warning"] * 4
    for check in checks:
        assert check["condition"]["left"]["nodeName"] in extract_names


def test_extract_nodes_share_schema():
    steps = [s for s in steps_by_name().values() if s["type"] == "information-extract"]
    assert len(steps) == 4
    schemas = {json.dumps(s["data"]["text"], sort_keys=True, ensure_ascii=False) for s in steps}
    assert len(schemas) == 1
    keys = set(next(iter(steps))["data"]["text"]["format"]["schema"]["properties"])
    assert len(keys) == 17 and "applicant_name" in keys and "staff_contact" in keys


def test_risk_branches_cover_enum():
    risk = steps_by_name()["Instruct - 위험도_판정"]
    values = sorted(n["condition"]["value"] for n in risk["next_steps"])
    assert values == sorted(["상", "중", "하", "검토 필요"])
    prompt = risk["data"]["input"][0]["content"][0]["text"]
    for key in ("risk_level", "document_types", "sensitive_categories", "review_reasons", "reason"):
        assert f"{key}:" in prompt
