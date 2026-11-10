# ==========================================================================
#  v6 응답(가림_확인·결합_확인이 있는 사슬) 읽기 — 검토사항 새 종류·가린 이름 연결·묶음 검증 사슬·지급보증 문장·목록 서류 수 (네트워크 없음)
#  자료: tests/fixtures/v6/case_<V·W·Y·Z·AA>.json — v6 최종 설정 실제 응답 5건의 모양을 가상 값으로 바꾼 것(같은 원문 → 같은 가상 값, 포함
#  관계·꼴·가림 기호 자리 유지 — 'X'·'x' 도 그대로. Parse 본문은 뺐고 통과 규칙은 노드마다 앞 2개만 조건 트리가 있다. 판정 JSON 의 reason·
#  recommended_action 은 고정 글자). 만든 도구: .orchestration/web-polish/tools/make_v6_fixtures.py(누출 검사 v6_leak.py).
#  케이스: V 서류 간 정보 결합(결합 두 규칙 모두 실패 — 사유 하나) · W 상(이름 하나 가림, 결합 통과) · Y·Z 가림 범위 확인 필요(체크카드 결제계좌) ·
#  AA 재식별 위험(warning 규칙만 실패). V·W·AA 는 체크카드(가리지 않은 이름) + IRP 신규(가린 이름) 두 서류다.
#  합성 변형은 그 자료를 고쳐 만든다. 실패 메시지에 나오는 값도 모두 가상 값이다.
# ==========================================================================

from __future__ import annotations

import copy
import functools
import json
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fake_findings import stored_result
from shared_ctx import Ctx, ctx, install  # noqa: F401
from view_contract import assert_bundle_check, assert_view

from imask_backend import final_flow, items as items_module
from imask_backend.final_flow import (
    MASK_MARKS,
    V2_SELF_NAMES,
    V6_LINKAGE_LABELS,
    V6_LINKAGE_RULE,
    V6_MASKED_NAMES,
    V6_REIDENT_RULE,
    has_mask,
    masked_name_fields,
    read_chain,
    read_linkage_passed,
    read_v2_links,
)
from imask_backend.findings import _attach_extracts, _documents, build_view
from imask_backend.items import (
    ITEM_TYPES,
    LINKAGE_RULE,
    LINKAGE_TEXTS,
    NODE_LINKAGE,
    NODE_MASK,
    REIDENT_RULE,
    REVIEW_REASONS,
    ChainRule,
    LinkPair,
    LinkSide,
    build_links,
    bundle_parts,
    v2_parts,
)
from imask_backend.manage import list_item
from imask_backend.results import (
    STAGE_V2_CONSISTENT,
    STAGE_V2_FORMAT,
    STAGE_V2_GRADE,
    STAGE_V2_IRP,
    STAGE_V2_LINKAGE,
    STAGE_V2_MASK,
    STAGE_V2_TAXPAYER,
    STAGE_VALIDATE,
    V2_CHAIN,
    is_v2,
    parse_stages,
    stage_key,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "v6"
V2_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "v2"
CASES = ("V", "W", "Y", "Z", "AA")
TIME_LIMIT = 2.0
MASKSCOPE_ID = "maskscope:0:체크카드_가입신청서_결제계좌_가림확인"
MASKED_MISSING = "이름이 가려져 있어 비교할 수 없습니다."
CARD, IRP_NEW, SELF, G, ATTORNEY = "체크카드_가입신청서", "IRP_신규신청서", "소비자피해보상금_지급신청서", "지급보증거래_신청서", "위임장_상속"
BRANCH_NODES = ("상_확인", "IRP해지_확인", "납세자번호_확인", "등급_결합", "등급_가림", "등급_재식별", "등급_결합_중")


@functools.cache
def _raw(case: str, folder: Path = FIXTURES) -> str:
    return (folder / f"case_{case}.json").read_bytes().decode("utf-8")


def load(case: str, folder: Path = FIXTURES) -> dict[str, Any]:
    return json.loads(_raw(case, folder))


def view_of(source: str | dict[str, Any]) -> dict[str, Any]:
    return build_view({"response": load(source) if isinstance(source, str) else source})


def step(response: dict[str, Any], node: str) -> dict[str, Any]:
    return next(item for item in response["output"] if item["model"].endswith(" - " + node))


def edit(response: dict[str, Any], node: str, change: Callable[[Any], Any], field: str = "additional_values") -> None:
    entry = step(response, node)["content"][0]
    value = json.loads(entry[field])
    returned = change(value)
    entry[field] = json.dumps(value if returned is None else returned, ensure_ascii=False)


def set_check(response: dict[str, Any], node: str, rule: str, passed: Any) -> None:
    def change(add: dict[str, Any]) -> None:
        for check in add["checks"]:
            if check["name"] == rule:
                check["passed"] = passed

    edit(response, node, change)


def set_value(response: dict[str, Any], form: str, key: str, value: Any) -> None:
    def change(data: dict[str, Any]) -> None:
        data[key] = value

    edit(response, form, change, "text")


def get_value(response: dict[str, Any], form: str, key: str) -> Any:
    return json.loads(step(response, form)["content"][0]["text"]).get(key)


def ids(view: dict[str, Any]) -> list[str]:
    return [item["id"] for item in view["items"]]


def link_item_ids(view: dict[str, Any]) -> list[str]:
    return [i for i in ids(view) if i.startswith(("mismatch:", "weaklink:"))]


def item_of(view: dict[str, Any], item_id: str) -> dict[str, Any]:
    return next(item for item in view["items"] if item["id"] == item_id)


def no_review_noise(view: dict[str, Any]) -> None:
    """v6 사유가 있는 분석에 verdict:* 와 가린 이름 쌍의 mismatch·weaklink 가 없다."""
    assert not [i for i in ids(view) if i.startswith(("verdict:", "mismatch:", "weaklink:"))], ids(view)


# --- 모양·단계 이름 -----------------------------------------------------------------------------------


@pytest.mark.parametrize("case", CASES)
def test_v6_fixture_is_v2_and_keeps_the_contract(case: str) -> None:
    response = load(case)
    assert is_v2(response)
    view = view_of(case)
    assert_view(view)
    assert all(doc["validation"] is None for doc in view["documents"])  # 서류별 검증(옛 필수항목_검증 경로)이 없다


def test_new_stages_get_their_own_keys() -> None:
    assert stage_key("Validate - 가림_확인", "validate") == STAGE_V2_MASK
    assert stage_key("Validate - 결합_확인", "validate") == STAGE_V2_LINKAGE
    assert stage_key("Validate - IRP해지_확인", "validate") == STAGE_V2_IRP
    assert stage_key("Validate - 납세자번호_확인", "validate") == STAGE_V2_TAXPAYER
    for node in ("등급_결합", "등급_가림_중", "등급_누락"):
        assert stage_key(f"Validate - {node}", "validate") == STAGE_V2_GRADE
    assert stage_key("Validate - 필수항목_검증", "validate") == STAGE_VALIDATE  # 옛 이름은 그대로
    assert stage_key("Validate - 모르는_단계", "validate") == STAGE_VALIDATE
    keys = {stage["name"]: stage["key"] for stage in parse_stages(load("V"))}
    assert keys["Validate - 가림_확인"] == STAGE_V2_MASK and keys["Validate - 결합_확인"] == STAGE_V2_LINKAGE
    assert keys["Validate - 등급_결합"] == STAGE_V2_GRADE
    assert STAGE_VALIDATE not in keys.values()


def test_chain_order_puts_mask_after_format_and_linkage_after_consistency() -> None:
    assert V2_CHAIN.index(STAGE_V2_MASK) == V2_CHAIN.index(STAGE_V2_FORMAT) + 1
    assert V2_CHAIN.index(STAGE_V2_LINKAGE) == V2_CHAIN.index(STAGE_V2_CONSISTENT) + 1
    assert V2_CHAIN[-1] == STAGE_V2_LINKAGE
    assert (items_module.NODE_MASK, items_module.NODE_LINKAGE) == (STAGE_V2_MASK, STAGE_V2_LINKAGE)
    assert (LINKAGE_RULE, REIDENT_RULE) == (V6_LINKAGE_RULE, V6_REIDENT_RULE)


def _old_key_stages(response: dict[str, Any]) -> list[dict[str, Any]]:
    """이 코드 전에 저장된 stages 모양 — 가림·결합·갈래 단계의 key 가 필수항목_검증."""
    stages = parse_stages(response)
    for stage in stages:
        if stage["step_type"] == "validate" and stage["key"] not in ("대상_확인", "단위_확인", "필수_확인", "형식_확인", "일치_확인", "상_확인"):
            stage["key"] = STAGE_VALIDATE
    return stages


@pytest.mark.parametrize("case", CASES)
def test_old_and_new_stage_keys_give_the_same_view(case: str) -> None:
    response = load(case)
    old = _old_key_stages(response)
    assert any(stage["key"] == STAGE_VALIDATE for stage in old)
    from_response = view_of(case)
    assert build_view({"stages": old}) == from_response
    assert build_view({"stages": parse_stages(response)}) == from_response


def test_old_key_stored_analysis_through_the_api(ctx: Ctx) -> None:  # noqa: F811
    result = stored_result(load("V"), keep_response=False)
    result["stages"] = _old_key_stages(load("V"))
    analysis_id = ctx.store.put(status="done", job_id="job_v6", result=result)
    body = ctx.get(analysis_id).json()["result"]
    assert "linkage:1" in [item["id"] for item in body["items"]]
    assert body["bundle_check"]["verdict"] == "red"
    assert body["links"][0]["missing"] == MASKED_MISSING


# --- 수락 기준(케이스별) ------------------------------------------------------------------------------


def test_v_linkage_item_and_masked_link() -> None:
    view = view_of("V")
    no_review_noise(view)
    assert [i["id"] for i in view["items"] if i["type"] in ("maskscope", "linkage", "reident")] == ["linkage:1"]
    item = item_of(view, "linkage:1")
    title, desc, next_step = LINKAGE_TEXTS["linkage"]
    assert (item["title"], item["desc"], item["next"], item["link_id"], item["finding_id"]) == (title, desc, next_step, None, None)
    assert item["document_index"] == 1
    assert item["evidence"] == [{"label": "1쪽 값 보기", "page": 3, "finding_ids": ["1:중_가입자명"], "finding_id": None}]
    (link,) = view["links"]
    assert (link["status"], link["state"], link["basis"], link["missing"]) == ("check", "insufficient", [], MASKED_MISSING)
    assert view["bundle_check"]["verdict"] == "red"
    checks = [(c["name"], c["severity"], c["status"], c["group"], c["field"], c["label"]) for c in view["bundle_check"]["checks"]]
    assert checks == [  # 결합 두 규칙: field null(조건 트리 첫 칸은 대상 칸이 아니다) + 사유 이름 label
        (V6_LINKAGE_RULE, "error", "fail", "결합_확인", None, "서류 간 정보 결합"),
        (V6_REIDENT_RULE, "warning", "fail", "결합_확인", None, "재식별 위험"),
    ]


@pytest.mark.parametrize("case", ["Y", "Z"])
def test_y_z_maskscope_item(case: str) -> None:
    view = view_of(case)
    no_review_noise(view)
    assert [i for i in ids(view) if i.startswith(("maskscope", "linkage", "reident", "review:"))] == [MASKSCOPE_ID]
    item = item_of(view, MASKSCOPE_ID)
    assert item["number"] == "R-01"  # 서류 안에서 형식 재료 뒤 · lowconf 앞
    assert item["title"] == "결제계좌 가림 범위 확인 필요"
    assert item["desc"] == "번호 일부가 가려져 있습니다. 남은 자리로 번호가 드러나지 않는지 확인이 필요합니다."
    assert item["next"] == "원본과 대조해 가림 범위를 확인해 주세요."
    assert item["evidence"] == [{"label": "1쪽 값 보기", "page": 1, "finding_ids": ["0:상_결제계좌"], "finding_id": None}]
    assert view["bundle_check"]["verdict"] == "red"
    assert [(c["name"], c["group"], c["label"]) for c in view["bundle_check"]["checks"]] == [
        ("체크카드_가입신청서_결제계좌_가림확인", "가림_확인", "결제계좌")
    ]


def test_aa_reident_item_only() -> None:
    view = view_of("AA")
    no_review_noise(view)
    assert [i["id"] for i in view["items"] if i["type"] in ("maskscope", "linkage", "reident")] == ["reident:1"]
    item = item_of(view, "reident:1")
    assert (item["title"], item["desc"], item["next"]) == LINKAGE_TEXTS["reident"]
    assert item["evidence"][0]["finding_ids"] == ["1:중_가입자명"]
    assert view["links"][0]["state"] == "insufficient" and view["links"][0]["missing"] == MASKED_MISSING
    assert view["bundle_check"]["verdict"] == "yellow"


def test_w_masked_name_without_review_reason_has_no_items() -> None:
    view = view_of("W")
    assert view["overall"]["level"] == "상" and view["decision"]["review_reasons"] == []
    assert not [i for i in ids(view) if i.startswith(("mismatch:", "weaklink:", "verdict:", "review:", "linkage", "reident", "maskscope"))]
    assert view["links"][0]["state"] == "insufficient" and view["links"][0]["missing"] == MASKED_MISSING
    assert view["bundle_check"] == {"verdict": "green", "checks": []}


# --- 갈래 단계 -------------------------------------------------------------------------------------


def test_branch_stages_never_count_as_failures() -> None:
    response = load("W")
    present = [node for node in BRANCH_NODES if any(item["model"].endswith(" - " + node) for item in response["output"])]
    assert present  # W 에는 상_확인·IRP해지_확인·납세자번호_확인 이 있다
    before = view_of(copy.deepcopy(response))
    for node in present:

        def fail_all(add: dict[str, Any]) -> None:
            add["verdict"] = "red"
            for check in add["checks"]:
                check["passed"] = False

        edit(response, node, fail_all)
        step(response, node)["content"][0]["text"] = "red"
    after = view_of(response)
    assert after["items"] == before["items"] and after["bundle_check"] == before["bundle_check"]
    assert {c["group"] for c in read_chain(response)["checks"]} <= set(V2_CHAIN) | {"내용_검토"}


def test_grade_stage_of_v_is_not_in_the_chain() -> None:
    response = load("V")
    set_check(response, "등급_결합", "상_항목_있음", False)
    assert [c["group"] for c in view_of(response)["bundle_check"]["checks"]] == ["결합_확인", "결합_확인"]


# --- 결합 재료 갈래 --------------------------------------------------------------------------------


def test_reident_appears_when_the_error_rule_passes() -> None:
    response = load("V")
    set_check(response, "결합_확인", V6_LINKAGE_RULE, True)
    view = view_of(response)
    # 규칙에서는 reident 하나. 판정 사유(서류 간 정보 결합)는 그대로라 그 종류 항목이 없어 사유 보충이 첫 보이는 서류에 붙는다
    assert [i["id"] for i in view["items"] if i["type"] in ("linkage", "reident")] == ["review:linkage", "reident:1"]


def test_unknown_or_non_bool_linkage_rule_makes_no_item() -> None:
    response = load("V")
    set_check(response, "결합_확인", V6_LINKAGE_RULE, "false")
    set_check(response, "결합_확인", V6_REIDENT_RULE, None)
    view = view_of(response)
    # 규칙 항목은 없다 — 판정 사유는 그대로라 사유 보충 review:linkage 하나(title = 사유 글자), verdict 없음
    assert [(i["id"], i["title"]) for i in view["items"] if i["type"] in ("linkage", "reident")] == [("review:linkage", "서류 간 정보 결합")]
    assert "verdict:0" not in ids(view)

    def rename(add: dict[str, Any]) -> None:
        for check in add["checks"]:
            check["name"] = "모르는_결합_규칙"
            check["passed"] = False

    response = load("V")
    edit(response, "결합_확인", rename)
    view = view_of(response)
    assert not [i for i in view["items"] if i["type"] == "reident"]
    linkage = [i for i in view["items"] if i["type"] == "linkage"]
    assert [(i["id"], i["title"]) for i in linkage] == [("review:linkage", "서류 간 정보 결합")]  # 사유 보충(title = 사유 글자)


def test_linkage_without_a_masked_name_document_goes_to_the_first_document() -> None:
    response = load("V")
    name = get_value(response, IRP_NEW, "중_가입자명")
    set_value(response, IRP_NEW, "중_가입자명", "".join(ch for ch in name if ch not in MASK_MARKS) + "가")
    view = view_of(response)
    item = item_of(view, "review:linkage")
    assert item["document_index"] == 0 and item["title"] == LINKAGE_TEXTS["linkage"][0]
    assert item["evidence"] == [{"label": "1쪽 열기", "page": 1, "finding_ids": [], "finding_id": None}]
    assert sum(1 for i in view["items"] if i["type"] == "linkage") == 1  # 사유 보충이 더하지 않는다


def test_masked_name_document_is_the_first_visible_one() -> None:
    response = load("V")
    name = get_value(response, CARD, "중_성명_한글")
    set_value(response, CARD, "중_성명_한글", "*" + name)
    view = view_of(response)
    assert "linkage:0" in ids(view) and "linkage:1" not in ids(view)
    assert item_of(view, "linkage:0")["evidence"][0]["finding_ids"] == ["0:중_성명_한글"]


def test_review_reasons_without_rule_items_fall_back_per_kind() -> None:
    response = load("Y")
    response["output"] = [item for item in response["output"] if not item["model"].endswith(" - 가림_확인")]
    view = view_of(response)
    item = item_of(view, "review:maskscope")
    assert (item["type"], item["title"], item["desc"], item["next"]) == (
        "maskscope",
        "가림 범위 확인 필요",
        "번호 일부가 가려져 있습니다. 남은 자리로 번호가 드러나지 않는지 확인이 필요합니다.",
        "원본과 대조해 가림 범위를 확인해 주세요.",
    )
    assert "verdict:0" not in ids(view)
    for reason, kind in (("가림 범위 확인 필요", "maskscope"), ("서류 간 정보 결합", "linkage"), ("재식별 위험", "reident")):
        assert REVIEW_REASONS[reason][0] == kind and REVIEW_REASONS[reason][3] == frozenset({kind})
        assert kind in ITEM_TYPES


def test_order_inside_a_document_follows_the_chain() -> None:
    # 한 서류에 형식 · 가림 · 일치 · 결합 실패를 모두 둔다 — 형식 → 가림 → 일치 → (연결) → 결합 → lowconf
    documents = [{"index": 0, "type": CARD, "page_start": 1, "page_end": 1, "kind": "extracted", "other_guide": None, "validation": None}]

    def rule(node: str, name: str) -> ChainRule:
        return ChainRule(node=node, name=name, severity="error", status="fail", field=None, label=None, code=CARD, cell=None, cell_label=None)

    rules = [
        rule(NODE_LINKAGE, LINKAGE_RULE),
        rule("일치_확인", "체크카드_규칙"),
        rule(NODE_MASK, "체크카드_가입신청서_결제계좌_가림확인"),
        rule("형식_확인", "체크카드_가입신청서_휴대폰"),
    ]
    rules.sort(key=lambda r: V2_CHAIN.index(r.node))
    bundle = v2_parts(documents, {}, rules, [], {}, {0: "중_성명_한글"})
    built = items_module.build_items(documents, [], [None], bundle)
    assert [i["type"] for i in built] == ["format", "maskscope", "mismatch", "linkage"]
    assert built[3]["id"] == "linkage:0"


# --- 가린 이름 연결(D2 · 코디네이터 Q2) ---------------------------------------------------------------


def _bundle(*forms: tuple[str, Any]) -> dict[str, Any]:
    """분류 순서대로 서식(코드, 본인 칸 값)을 가진 합성 v2 응답 — 값이 ... 면 추출 단계가 없다."""
    classify, steps = [], []
    for number, (code, value) in enumerate(forms, 1):
        ranges = [[number, number]]
        classify.append({"text": code, "additional_values": json.dumps({"document_type": {"_value": code}, "page_ranges": ranges}, ensure_ascii=False)})
        if value is ...:
            continue
        key = "중_신청인_성명" if code == G else V2_SELF_NAMES.get(code, "중_대리인_성명")
        meta = {key: {"_value": value, "confidence": "high", "page": number, "coordinates": [], "word_coordinates": []}, "page_ranges": ranges}
        steps.append(
            {
                "model": f"Information Extract - {code}",
                "status": "completed",
                "step_type": "information-extract",
                "content": [{"text": json.dumps({key: value}, ensure_ascii=False), "additional_values": json.dumps(meta, ensure_ascii=False)}],
            }
        )
    return {"output": [{"model": "step_2_classify", "status": "completed", "step_type": "document-classify", "content": classify}, *steps]}


def pairs_of(*forms: tuple[str, Any]) -> tuple[int | None, list[tuple[int, str, bool]]]:
    links = read_v2_links(_bundle(*forms))
    return links["anchor_index"], [(p["target_index"], p["status"], p["masked"]) for p in links["pairs"]]


@pytest.mark.parametrize(
    ("forms", "anchor", "pairs"),
    [
        # 대상 값이 가려졌으면 비교하지 않는다(가린 이름)
        (((SELF, "가나다"), (IRP_NEW, "가*다")), 0, [(1, "insufficient", True)]),
        (((SELF, "가나다"), (IRP_NEW, "가●다")), 0, [(1, "insufficient", True)]),
        # 기준 = 가림 기호가 없는 첫 서식(앞 서식이 가려졌으면 뒤 서식) — 쌍 id 의 기준 자리가 바뀐다
        (((SELF, "가*다"), (IRP_NEW, "가나다")), 1, [(0, "insufficient", True)]),
        (((SELF, "가*다"), (CARD, "가나다"), (IRP_NEW, "가나다")), 1, [(0, "insufficient", True), (2, "linked", False)]),
        # 가리지 않은 이름끼리는 그대로
        (((SELF, "가나다"), (IRP_NEW, "가나라")), 0, [(1, "unmatched", False)]),
        # 모두 가려졌으면 첫 서식이 기준이고 비교할 수 있었던 쌍은 모두 가린 이름
        (((SELF, "가*다"), (IRP_NEW, "가*다")), 0, [(1, "insufficient", True)]),
        (((SELF, "가*다"), (IRP_NEW, "나*라")), 0, [(1, "insufficient", True)]),
        # Q2: 기준이 가려져도 위임장·빈 대상·추출 없음·문자열 아님은 기존 판정(가린 이름 아님)
        (((SELF, "가*다"), (ATTORNEY, "가나다")), None, []),  # 서식 2종이지만 위임장은 본인 칸이 없다 — 기준은 SELF
        (((SELF, "가*다"), (IRP_NEW, "")), 0, [(1, "insufficient", False)]),
        (((SELF, "가*다"), (IRP_NEW, ...)), 0, [(1, "insufficient", False)]),
        # 문자열이 아닌 값은 가림 기호가 없는 값으로 본다(기준 고르기만 — 비교는 늘 근거 부족)
        (((SELF, "가*다"), (IRP_NEW, ["가*다"])), 1, [(0, "insufficient", False)]),
        (((SELF, 5), (IRP_NEW, "가나다")), 0, [(1, "insufficient", False)]),  # 가림이 없으면 기준은 예전과 같다
        # 지급보증 신청인 칸도 같다
        (((SELF, "가나다"), (G, "회사 대표 가*다")), 0, [(1, "insufficient", True)]),
        (((SELF, "가*다"), (G, "회사 대표 가*다")), 0, [(1, "insufficient", True)]),
        (((SELF, "가나다"), (G, "회사 대표 가나다")), 0, [(1, "linked", False)]),
    ],
)
def test_masked_name_pairs(forms: tuple[tuple[str, Any], ...], anchor: int | None, pairs: list[tuple[int, str, bool]]) -> None:
    got_anchor, got_pairs = pairs_of(*forms)
    if anchor is None:  # 위임장 경우: 기준은 SELF(0), 위임장 쌍은 가린 이름이 아니다
        assert got_anchor == 0 and got_pairs == [(1, "insufficient", False)]
    else:
        assert (got_anchor, got_pairs) == (anchor, pairs)


def test_masked_anchor_keeps_the_attorney_weaklink() -> None:
    view = view_of(_bundle((SELF, "가*다"), (ATTORNEY, "가나다"), (IRP_NEW, "가*다")))
    states = {link["id"]: (link["state"], link["missing"]) for link in view["links"]}
    assert states == {"link:0:1": ("insufficient", "비교할 본인 성명이 없습니다."), "link:0:2": ("insufficient", MASKED_MISSING)}
    assert link_item_ids(view) == ["weaklink:0:1"]


def test_masked_anchor_with_an_empty_target_keeps_the_weaklink() -> None:
    view = view_of(_bundle((SELF, "가*다"), (IRP_NEW, "")))
    (link,) = view["links"]
    assert (link["state"], link["missing"]) == ("insufficient", "비교할 본인 성명이 없습니다.")
    assert link_item_ids(view) == ["weaklink:0:1"]


def test_masked_pair_makes_no_weaklink_or_mismatch() -> None:
    view = view_of(_bundle((SELF, "가나다"), (IRP_NEW, "가*다"), (CARD, "다른이")))
    assert [link["state"] for link in view["links"]] == ["insufficient", "unmatched"]
    assert link_item_ids(view) == ["mismatch:0:2"]


def test_each_mask_mark_is_recognised() -> None:
    assert len(MASK_MARKS) == 10
    for mark in MASK_MARKS:
        assert pairs_of((SELF, "가나다"), (IRP_NEW, f"가{mark}다"))[1] == [(1, "insufficient", True)]
    assert not has_mask("가X다") and not has_mask(None) and not has_mask(["*"]) and not has_mask(5)


# --- 지급보증 문장(D9) ------------------------------------------------------------------------------


def test_guarantee_pair_texts_of_the_v2_fixtures() -> None:
    linked = next(link for link in view_of(load("B", V2_FIXTURES))["links"] if link["id"] == "link:0:1")
    assert linked["basis"] == ["신청인 성명에 본인 성명이 들어 있습니다."] and linked["missing"] == ""
    view = view_of(load("U", V2_FIXTURES))
    rows = {link["id"]: link for link in view["links"]}
    assert rows["link:1:0"]["missing"] == "신청인 성명에 본인 성명이 들어 있지 않습니다." and rows["link:1:0"]["basis"] == []
    assert rows["link:1:2"]["missing"] == "두 서류의 본인 성명이 다릅니다."  # 다른 서식 쌍은 그대로
    assert item_of(view, "mismatch:1:0")["title"] == "외국인 세대구성원 확인서와 본인 성명이 다릅니다"  # 검토사항 글은 그대로


def test_guarantee_insufficient_text_is_unchanged() -> None:
    view = view_of(_bundle((IRP_NEW, "가나다"), (G, "다른 회사")))  # 지급보증 비교 규칙이 없는 묶음 — 근거 부족
    (link,) = view["links"]
    assert (link["state"], link["missing"]) == ("insufficient", "비교할 본인 성명이 없습니다.")


def test_old_read_links_pairs_never_use_the_new_texts() -> None:
    side = LinkSide(index=1, page=1, fields="x", finding_ids=())
    pair = LinkPair(id="link:0:1", state="linked", field="f", label="본인 성명", shown="본인 성명", anchor_name="a", target_name="b", anchor=side, target=side)
    (row,) = build_links([pair])
    assert row["basis"] == ["두 서류의 본인 성명이 같습니다."]


# --- 목록 서류 수(D7) ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("count", "want"),
    [(0, 0), (3, 3), (None, None), (True, None), (False, None), (-1, None), (1.0, None), ("3", None), ([2], None), (10**400, 10**400)],
)
def test_list_row_document_count(count: Any, want: Any) -> None:
    row = {"id": "x", "status": "done", "document_count": count, "documents": [], "analysis_reviews": None}
    item = list_item(row)
    assert item["document_count"] == want and (want is not None or item["document_count"] is None)
    assert list(item)[-1] == "document_count"


def test_list_api_carries_document_count(ctx: Ctx) -> None:  # noqa: F811
    done = ctx.store.put(status="done", job_id="job_1", result=stored_result(load("V")))
    failed = ctx.store.put(status="failed", error="실패")
    rows = {row["id"]: row for row in ctx.list().json()["analyses"]}
    assert rows[done]["document_count"] == 2 and rows[failed]["document_count"] is None


# --- 경계 강건성 -----------------------------------------------------------------------------------


def test_masked_name_fields_skips_bad_documents() -> None:
    stages = parse_stages(load("V"))
    docs, count = _documents(stages)
    _attach_extracts(stages, docs, count)
    assert masked_name_fields(docs) == {1: V6_MASKED_NAMES[IRP_NEW]}

    class Broken:
        type = CARD

        @property
        def extract(self) -> Any:
            raise RuntimeError("boom")

    assert masked_name_fields([Broken(), *docs]) == {1: V6_MASKED_NAMES[IRP_NEW]}
    assert masked_name_fields(None) == {} and masked_name_fields("문자열") == {}


def test_v2_parts_ignores_bad_rules_and_masked_maps() -> None:
    documents = [{"index": 0, "type": CARD, "page_start": 1, "page_end": 1}]
    rule = ChainRule(node=NODE_LINKAGE, name=LINKAGE_RULE, severity="error", status="fail", field=None, label=None, code=None, cell=None, cell_label=None)
    for masked in (None, "x", {0: 5}, {"0": "중_성명_한글"}, {7: "중_성명_한글"}):
        parts = v2_parts(documents, {}, [rule, "규칙 아님", None, 3], [], {}, masked)  # type: ignore[list-item]
        assert parts[0].linkage[0].fallback is True


@pytest.mark.parametrize(
    "change",
    [
        lambda add: add.update(checks="목록 아님"),
        lambda add: add.update(checks=[None, 5, "x", {"name": None, "passed": False}, {"name": "가" * 10_000, "passed": False}]),
        lambda add: add.update(checks=[{"name": V6_LINKAGE_RULE, "passed": False, "conditions": {"conditions": [[{"left": 5}]] * 3}}]),
        lambda add: add.update(checks=[{"name": V6_LINKAGE_RULE + "\ud800", "passed": False}]),
        lambda add: add.update(verdict=10**400),
    ],
)
def test_odd_linkage_stage_shapes_never_raise(change: Callable[[dict[str, Any]], Any]) -> None:
    response = load("V")
    edit(response, "결합_확인", change)
    view = view_of(response)
    assert_view(view)
    assert view["overall"] == view_of("V")["overall"] and view["findings"] == view_of("V")["findings"]


def test_deep_condition_tree_on_a_mask_rule() -> None:
    response = load("Y")

    def deep(add: dict[str, Any]) -> None:
        node: dict[str, Any] = {"left": {"nodeName": CARD, "field": "상_결제계좌"}}
        for _ in range(300):
            node = {"logic": "or", "conditions": [node]}
        for check in add["checks"]:
            if check["passed"] is False:
                check["conditions"] = node

    edit(response, "가림_확인", deep)
    view = view_of(response)
    assert any(i["type"] == "maskscope" for i in view["items"])


def test_long_masked_name_is_linear() -> None:
    long_name = "가" * 2_000_000 + "*"
    start = time.perf_counter()
    assert has_mask(long_name)
    assert not has_mask("가" * 2_000_000)
    pairs_of((SELF, "가나다"), (IRP_NEW, long_name))
    assert time.perf_counter() - start < TIME_LIMIT


def test_linkage_labels_only_for_the_linkage_node() -> None:
    assert V6_LINKAGE_LABELS == {V6_LINKAGE_RULE: "서류 간 정보 결합", V6_REIDENT_RULE: "재식별 위험"}
    response = load("V")

    def move(add: dict[str, Any]) -> None:
        for check in add["checks"]:
            check["name"] = V6_LINKAGE_RULE
            check["passed"] = False

    edit(response, "일치_확인", move)  # 같은 이름이 다른 노드에 오면 칸 이름 그대로(결합 label 아님)
    rows = [c for c in read_chain(response)["checks"] if c["group"] == "일치_확인"]
    assert rows and all(c["label"] != "서류 간 정보 결합" for c in rows)


def test_new_code_logs_no_values(caplog: pytest.LogCaptureFixture) -> None:
    response = load("V")
    name = get_value(response, IRP_NEW, "중_가입자명")
    caplog.set_level(logging.WARNING)
    edit(response, "결합_확인", lambda add: add.update(checks=[{"name": V6_LINKAGE_RULE, "passed": False, "conditions": {"left": {"value": name}}}]))
    view_of(response)
    assert name not in caplog.text


def test_final_flow_module_keeps_mask_marks_in_one_place() -> None:
    assert final_flow.MASK_MARKS == frozenset("*＊●○■□◆◇★☆")
    assert set(V6_MASKED_NAMES) == set(V2_SELF_NAMES) - {"외국인_세대구성원_확인서"}
    assert all(V6_MASKED_NAMES[code] == V2_SELF_NAMES[code] for code in V6_MASKED_NAMES)


# --- 운영 e2e 스크립트(scripts/api_e2e.py)가 v6 결과를 받아들이는지(실행하지 않고 계약 검사 함수만) ---------------------


@functools.cache
def _e2e_script() -> Any:
    import importlib.util

    spec = importlib.util.spec_from_file_location("api_e2e_v6", Path(__file__).resolve().parents[1] / "scripts" / "api_e2e.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("case", CASES)
def test_e2e_script_contract_checks_accept_v6_results(case: str) -> None:
    from imask_backend.analyses import build_result, result_out

    script = _e2e_script()
    view = result_out(build_result(load(case), "9"))
    assert script.ITEM_TYPES == ITEM_TYPES
    assert script._is_v2(view)
    assert script._final_problems(view) == []
    assert script._view_problems(view) == []
    assert script._items_shape_problems(view["items"], view) == []
    want, reason = script._expected_items(view)
    assert want is not None and reason == ""
    own = [i for i in view["items"] if i["id"].startswith(script.V2_OWN_ITEMS)]
    assert script._items_compare(own, want, skip=("number",)) == []


def test_e2e_script_rejects_a_wrong_guarantee_text() -> None:
    from imask_backend.analyses import build_result, result_out

    script = _e2e_script()
    view = result_out(build_result(load("B", V2_FIXTURES), "60"))
    assert script._final_problems(view) == []
    row = next(link for link in view["links"] if link["id"] == "link:0:1")
    row["basis"] = ["두 서류의 본인 성명이 같습니다."]  # 지급보증 쌍에 옛 글 — 받지 않는다
    assert script._final_problems(view) != []


# --- 수정 1회차: M1 가림 검사 횟수 · M2 재식별 조건 · m2 결합 규칙 field ---------------------------------------------


def _counting_has_mask(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """final_flow.has_mask 를 감싸 부른 횟수와 검사한 문자 수를 센다(연결 계산·가린 이름 서류 찾기가 같은 함수를 부른다)."""
    seen = {"calls": 0, "chars": 0}
    real = final_flow.has_mask

    def counted(value: Any) -> bool:
        seen["calls"] += 1
        seen["chars"] += len(value) if isinstance(value, str) else 0
        return real(value)

    monkeypatch.setattr(final_flow, "has_mask", counted)
    return seen


@pytest.mark.parametrize("anchor_mask", [False, True])
def test_mask_checks_are_linear_in_names_and_documents(monkeypatch: pytest.MonkeyPatch, anchor_mask: bool) -> None:
    # 긴 기준 이름 하나 + 짧은 대상 이름 n개를 함께 2배씩 늘린다(서류 수는 연결 한도 500 안) — 검사량은 입력 크기에 선형이어야 한다
    rows = []
    for scale in (1, 2, 4, 8):
        length, targets = 5_000 * scale, 50 * scale
        anchor = "가" * length + ("*" if anchor_mask else "")
        forms = [(SELF, anchor), *[(IRP_NEW, "가나다") for _ in range(targets)]]
        names = len(anchor) + 3 * targets
        seen = _counting_has_mask(monkeypatch)
        links = read_v2_links(_bundle(*forms))
        assert len(links["pairs"]) == targets
        assert seen["calls"] <= len(forms) and seen["chars"] <= names  # 값마다 한 번
        rows.append((names + len(forms), seen["chars"] + seen["calls"]))
        monkeypatch.undo()
    for (size_a, work_a), (size_b, work_b) in zip(rows, rows[1:]):
        assert work_b <= work_a * (size_b / size_a) * 1.01  # 입력이 2배면 검사량도 2배 안쪽


def test_whole_view_checks_each_name_a_bounded_number_of_times(monkeypatch: pytest.MonkeyPatch) -> None:
    anchor = "가" * 50_000
    forms = [(SELF, anchor), *[(IRP_NEW, "가*다") for _ in range(100)]]
    seen = _counting_has_mask(monkeypatch)
    view_of(_bundle(*forms))
    names = len(anchor) + 3 * 100
    # 연결 계산 한 번 + 결합 재료의 가린 이름 서류 찾기 한 번 — 이름마다 많아야 두 번
    assert seen["calls"] <= 2 * len(forms) and seen["chars"] <= 2 * names


def _set_reasons(response: dict[str, Any], reasons: list[str]) -> None:
    item = next(i for i in response["output"] if i["step_type"] == "instruct" and "판정_" in i["model"])
    body = json.loads(item["content"][0]["text"])
    body["review_reasons"] = reasons
    item["content"][0]["text"] = json.dumps(body, ensure_ascii=False)


def _drop_rule(response: dict[str, Any], rule: str) -> None:
    edit(response, "결합_확인", lambda add: add.update(checks=[c for c in add["checks"] if c["name"] != rule]))


ERROR_RULE_STATES: list[Callable[[dict[str, Any]], None]] = [
    lambda r: set_check(r, "결합_확인", V6_LINKAGE_RULE, None),
    lambda r: set_check(r, "결합_확인", V6_LINKAGE_RULE, "true"),
    lambda r: set_check(r, "결합_확인", V6_LINKAGE_RULE, 1),
    lambda r: _drop_rule(r, V6_LINKAGE_RULE),
]


@pytest.mark.parametrize("state", range(len(ERROR_RULE_STATES)), ids=["null", "문자열", "정수", "규칙 없음"])
@pytest.mark.parametrize(("reason", "want"), [("서류 간 정보 결합", "review:linkage"), ("재식별 위험", "review:reident")])
def test_unreadable_error_rule_never_makes_a_reident_item(state: int, reason: str, want: str) -> None:
    response = load("V")
    ERROR_RULE_STATES[state](response)
    _set_reasons(response, [reason])
    assert read_linkage_passed(response) is False
    view = view_of(response)
    got = [i["id"] for i in view["items"] if i["type"] in ("linkage", "reident")]
    assert got == [want]  # 재식별 재료를 추론하지 않고 판정 사유 보충 하나만
    assert not ({"linkage", "reident"} <= {i["type"] for i in view["items"]})
    assert "verdict:0" not in ids(view)
    warning = [c for c in view["bundle_check"]["checks"] if c["name"] == V6_REIDENT_RULE]
    assert [(c["status"], c["field"], c["label"]) for c in warning] == [("fail", None, "재식별 위험")]  # 검증 표시는 그대로


def test_explicitly_passed_error_rule_is_required_for_reident() -> None:
    assert read_linkage_passed(load("AA")) is True
    assert read_linkage_passed(load("V")) is False  # error 규칙 실패
    assert read_linkage_passed(load("W")) is True
    assert read_linkage_passed(load("Y")) is False  # 결합_확인 단계 없음
    assert read_linkage_passed(None) is False and read_linkage_passed("x") is False
    response = load("AA")
    edit(response, "결합_확인", lambda add: add.update(checks="목록 아님"))
    assert read_linkage_passed(response) is False
    response = load("AA")
    edit(response, "결합_확인", lambda add: add["checks"].append({"name": " " + V6_LINKAGE_RULE, "passed": None}))
    assert read_linkage_passed(response) is False  # 같은 이름 규칙 하나라도 통과가 아니면
    assert ids(view_of("AA")).count("reident:1") == 1 and ids(view_of("V")).count("linkage:1") == 1


def test_contract_helper_allows_only_the_exact_linkage_labels() -> None:
    def bundle(name: str, label: Any, field: Any = None, group: str = "결합_확인") -> dict[str, Any]:
        return {"verdict": "red", "checks": [{"id": name, "name": name, "severity": "error", "status": "fail", "field": field, "label": label, "group": group}]}

    assert_bundle_check(bundle(V6_LINKAGE_RULE, "서류 간 정보 결합"))
    assert_bundle_check(bundle(V6_REIDENT_RULE, "재식별 위험"))
    assert_bundle_check(bundle("모르는_규칙", None))
    for wrong in (
        bundle("모르는_결합_규칙", "아무 라벨"),
        bundle(V6_LINKAGE_RULE, "재식별 위험"),
        bundle(V6_REIDENT_RULE, None),
        bundle(V6_LINKAGE_RULE, "서류 간 정보 결합", field="중_예금주_성명"),
        bundle(V6_LINKAGE_RULE, "서류 간 정보 결합", group="일치_확인"),
    ):
        with pytest.raises(AssertionError):
            assert_bundle_check(wrong)
