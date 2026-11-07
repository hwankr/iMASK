# ==========================================================================
#  v3 서명 칸 — 설정 60 에 없는 여섯 칸이 응답에 오면 제 이름·등급·상자로 항목이 되고, 설정 60 응답에서는 달라지는 것이 없는지 (네트워크 없음)
#  자료: tests/fixtures/v2/case_C(체크카드·IRP 신규)·case_M(외국인)의 사본을 메모리에서 고쳐 v3 응답 모양을 만든다.
#  값은 그 자료의 가상 값을 빌려 쓰고, 좌표는 이 시험이 정한 수다.
#  값 경계: 실패 출력에 값이 나오면 안 된다. pytest 는 assert 식의 인자, --tb=long 이면 프레임 인자, --showlocals 면 지역 변수까지 찍는다.
#  그래서 시험 함수의 지역 변수·인자·assert 식에는 값 없는 사실(칸 이름·개수·불리언)만 둔다. 응답을 만지는 일은 @_value_free 도우미 안에서만 하고,
#  도우미 안의 예외는 종류·자리만 남긴 예외로 바꾼다. 공용 검사기 assert_view 도 도우미 안에서 부르고 자리만 남긴다(_contract_problem).
#  test_failure_output_has_no_raw_values 가 일부러 실패시킨 하위 pytest 의 출력으로 이 경계를 지킨다.
# ==========================================================================

from __future__ import annotations

import functools
import json
import logging
import os
import re
import subprocess
import sys
import traceback
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any, NamedTuple, TypeVar

import pytest
from view_contract import assert_view

from imask_backend import masking
from imask_backend.findings import build_view
from imask_backend.results import V2_FORM_CODES

THIS_FILE = Path(__file__).resolve()
ROOT = THIS_FILE.parents[1]
FIXTURES = THIS_FILE.parent / "fixtures" / "v2"
CASES = tuple("ABCDEFGHIJKLMNOPQRSTU")
CHECK_CARD = "체크카드_가입신청서"
IRP_NEW = "IRP_신규신청서"
FOREIGNER = "외국인_세대구성원_확인서"
FORMS_OF = {"C": (CHECK_CARD, IRP_NEW), "M": (FOREIGNER,)}
CASE_OF = {form: case for case, forms in FORMS_OF.items() for form in forms}
EXTRACT_MODEL = "Information Extract - "
GAP_WARNING = "판정 목록과 추출 칸이 다릅니다"

# 계약: (서식, 키) → (category, label, subject)
V3_ROWS: dict[tuple[str, str], tuple[str, str, str]] = {
    (CHECK_CARD, "중_서명란_본인성명"): ("이름", "서명란 본인 성명", "신청인"),
    (CHECK_CARD, "중_마이너스통장_본인성명"): ("이름", "마이너스통장 확인 본인 성명", "신청인"),
    (IRP_NEW, "중_설명확인_가입자명"): ("이름", "설명 확인 가입자명", "신청인"),
    (IRP_NEW, "중_서명란_가입자명"): ("이름", "서명란 가입자명", "신청인"),
    (FOREIGNER, "중_하단_본인_서명"): ("이름", "하단 본인 서명", "신청인"),
    (FOREIGNER, "중_하단_담보제공자_서명"): ("이름", "하단 담보제공자 서명", "보증인"),
}
ROW_IDS = [f"{form}-{key}" for form, key in V3_ROWS]
# 외국인 서식의 옛 이름(접두어 없음) → v3 이름
RENAMED = {"하단_본인_서명": "중_하단_본인_서명", "하단_담보제공자_서명": "중_하단_담보제공자_서명"}
# 추가 칸 → (값을 빌려 올 같은 서식의 칸, 쪽, 상자 왼쪽, 상자 위쪽)
ADDED: dict[str, dict[str, tuple[str, int, float, float]]] = {
    CHECK_CARD: {
        "중_서명란_본인성명": ("중_성명_한글", 1, 0.62, 0.91),
        "중_마이너스통장_본인성명": ("중_성명_한글", 1, 0.58, 0.74),
    },
    IRP_NEW: {
        "중_설명확인_가입자명": ("중_가입자명", 3, 0.55, 0.81),
        "중_서명란_가입자명": ("중_가입자명", 6, 0.6, 0.88),
    },
}


# --- 값 경계 --------------------------------------------------------------------------------

_Fact = TypeVar("_Fact")


class ValueFreeFailure(Exception):
    """도우미 안에서 난 예외의 값 없는 대신 — 메시지는 예외 종류와 자리뿐이다."""


def _where(exc: BaseException) -> str:
    last = traceback.extract_tb(exc.__traceback__)[-1]
    return f"{type(exc).__name__} @ {Path(last.filename).name}:{last.lineno}"


def _value_free(helper: Callable[..., _Fact]) -> Callable[..., _Fact]:
    """응답을 만지는 도우미 표시 — 값 없는 인자만 받고 값 없는 사실만 돌려준다.

    원래 예외는 from None 으로 끊는다. 그 traceback 의 프레임 인자·지역 변수(json.loads 의 원문, 응답 객체)가 실패 출력에 나오지 않는다.
    """

    @functools.wraps(helper)
    def wrapper(*args: Any, **kwargs: Any) -> _Fact:
        try:
            return helper(*args, **kwargs)
        except Exception as exc:
            raise ValueFreeFailure(_where(exc)) from None

    return wrapper


def _contract_problem(view: dict[str, Any]) -> str | None:
    """공용 계약 검사 — 어기면 자리만 돌려준다. 메시지와 프레임에 항목 객체가 있어 그대로 올려 보내지 않는다."""
    try:
        assert_view(view)
    except AssertionError as exc:
        return _where(exc)
    return None


# --- 자료 만들기(값을 만지므로 @_value_free 도우미 안에서만 부른다) -----------------------------------------


def load(case: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"case_{case}.json").read_bytes().decode("utf-8"))


def view_of(response: dict[str, Any]) -> dict[str, Any]:
    return build_view({"response": response})


def _extract(response: dict[str, Any], form: str) -> dict[str, Any]:
    return next(s for s in response["output"] if s["model"] == f"{EXTRACT_MODEL}{form}")["content"][0]


def _read(response: dict[str, Any], form: str) -> tuple[dict[str, Any], dict[str, Any]]:
    entry = _extract(response, form)
    return json.loads(entry["text"]), json.loads(entry["additional_values"])


def _write(response: dict[str, Any], form: str, data: dict[str, Any], meta: dict[str, Any]) -> None:
    entry = _extract(response, form)
    entry["text"], entry["additional_values"] = json.dumps(data, ensure_ascii=False), json.dumps(meta, ensure_ascii=False)


def _rect(left: float, top: float) -> list[dict[str, float]]:
    right, bottom = round(left + 0.1, 4), round(top + 0.02, 4)
    return [{"x": left, "y": top}, {"x": right, "y": top}, {"x": right, "y": bottom}, {"x": left, "y": bottom}]


def _blank_meta() -> dict[str, Any]:
    # 실제 응답의 빈 칸 꼴
    return {"_value": "", "confidence": "low", "page": -1, "coordinates": [], "word_coordinates": [], "confidence_score": 0.9}


def _add_verdict_tokens(response: dict[str, Any], case: str) -> None:
    """판정 JSON 의 medium_risk_items 에 새 칸을 더한다(v3 정답지 꼴: 서식코드.접두어를_뗀_칸)."""
    entry = next(s for s in response["output"] if s["model"].startswith("Instruct - 판정_"))["content"][0]
    verdict = json.loads(entry["text"])
    verdict["medium_risk_items"] += [f"{form}.{key[2:]}" for form, key in V3_ROWS if form in FORMS_OF[case]]
    entry["text"] = json.dumps(verdict, ensure_ascii=False)


def v3_response(case: str, *, blank: bool = False) -> dict[str, Any]:
    """case_C·case_M 사본 → v3 응답 모양. blank 면 새 칸이 있지만 값이 비어 있고, 판정 목록에도 없다."""
    response = load(case)
    for form in FORMS_OF[case]:
        data, meta = _read(response, form)
        if form == FOREIGNER:
            data = {RENAMED.get(key, key): value for key, value in data.items()}
            meta = {RENAMED.get(key, key): value for key, value in meta.items()}
        for key, (source, page, left, top) in ADDED.get(form, {}).items():
            rect = _rect(left, top)
            data[key] = data[source]
            meta[key] = {"_value": data[source], "confidence": "high", "page": page, "coordinates": rect, "word_coordinates": [rect], "confidence_score": 0.99}
        if blank:
            for row_form, key in V3_ROWS:
                if row_form == form:
                    data[key], meta[key] = "", _blank_meta()
        _write(response, form, data, meta)
    if not blank:
        _add_verdict_tokens(response, case)
    return response


def _doc_index(view: dict[str, Any], form: str) -> int:
    return next(d["index"] for d in view["documents"] if d["type"] == form)


def _new_findings(view: dict[str, Any]) -> list[tuple[str, str]]:
    """보기에서 V3_ROWS 에 드는 (서식, 칸) — 값 없이."""
    types = {d["index"]: d["type"] for d in view["documents"]}
    return [(types[f["document_index"]], f["field"]) for f in view["findings"] if (types[f["document_index"]], f["field"]) in V3_ROWS]


def _rows_of(case: str) -> list[tuple[str, str]]:
    return sorted(row for row in V3_ROWS if row[0] in FORMS_OF[case])


# --- 칸 목록(키 이름뿐이라 값이 없다) ---------------------------------------------------------------


def test_v3_key_list_is_exactly_the_contract() -> None:
    raw = (FIXTURES / "config_v3_keys.json").read_bytes()
    rows = json.loads(raw.decode("utf-8"))
    assert b"\r" not in raw
    assert [(row["form"], row["key"]) for row in rows] == list(V3_ROWS)
    assert all(set(row) == {"form", "table", "key", "fmt"} and row["table"] is None and row["fmt"] is None for row in rows)
    assert {row["form"] for row in rows} <= set(V2_FORM_CODES)


def test_config60_key_list_stays_the_record_of_config_60() -> None:
    rows = json.loads((FIXTURES / "config60_keys.json").read_bytes().decode("utf-8"))
    pairs = {(row["form"], row["key"]) for row in rows}
    assert not pairs & set(V3_ROWS)
    assert {(FOREIGNER, old) for old in RENAMED} <= pairs  # 설정 60 에서는 접두어가 없다


# --- v3 응답 --------------------------------------------------------------------------------


@_value_free
def _new_item_facts(form: str, key: str) -> tuple[int, list[str]]:
    """새 칸 항목의 개수와, 표·Extract 와 다른 곳의 이름."""
    response = v3_response(CASE_OF[form])
    view = view_of(response)
    index = _doc_index(view, form)
    hits = [f for f in view["findings"] if f["document_index"] == index and f["field"] == key]
    if len(hits) != 1:
        return len(hits), []
    item = hits[0]
    data, meta = _read(response, form)
    category, label, subject = V3_ROWS[form, key]
    want = {
        "id": f"{index}:{key}",
        "category": category,
        "label": label,
        "subject": subject,
        "mapping_status": "ok",
        "risk": "medium",
        "risk_source": "workflow",
        "page": meta[key]["page"],
        "boxes": meta[key]["word_coordinates"],  # Extract 좌표 그대로
        "value": data[key],
        "masked": masking.masked(data[key], "name"),  # 이름 가림 규칙
    }
    wrong = [name for name, expected in want.items() if item[name] != expected]
    if not item["boxes"]:
        wrong.append("boxes 없음")
    if item["masked"] == item["value"]:
        wrong.append("masked 가 원문과 같음")
    return 1, wrong


@pytest.mark.parametrize(("form", "key"), V3_ROWS, ids=ROW_IDS)
def test_new_key_becomes_one_item_as_the_table_says(form: str, key: str) -> None:
    hit_count, wrong = _new_item_facts(form, key)
    assert hit_count == 1, key
    assert wrong == [], key


@_value_free
def _v3_view_facts(case: str) -> tuple[str | None, list[tuple[str, str]], list[str]]:
    """계약 위반 자리, 새 칸 (서식, 칸), 항목이 된 옛 이름."""
    view = view_of(v3_response(case))
    return _contract_problem(view), sorted(_new_findings(view)), sorted({f["field"] for f in view["findings"]} & set(RENAMED))


@pytest.mark.parametrize("case", FORMS_OF)
def test_v3_response_keeps_the_view_contract_and_has_every_new_key(case: str) -> None:
    problem, rows, old_names = _v3_view_facts(case)
    assert problem is None, case
    assert rows == _rows_of(case), case
    assert old_names == [], case


@_value_free
def _change_facts(case: str) -> tuple[list[str], int]:
    """v3 모양에서 원본과 달라진 곳의 이름, 늘어난 항목 수."""
    before, after = view_of(load(case)), view_of(v3_response(case))
    changed = [part for part in ("documents", "overall", "links", "bundle_check", "items") if before[part] != after[part]]
    types = {d["index"]: d["type"] for d in after["documents"]}
    old = [f for f in after["findings"] if (types[f["document_index"]], f["field"]) not in V3_ROWS]
    if old != before["findings"]:
        changed.append("옛 항목")
    return changed, len(after["findings"]) - len(before["findings"])


@pytest.mark.parametrize("case", FORMS_OF)
def test_new_keys_change_nothing_but_their_own_items(case: str) -> None:
    # 칸은 항목 목록에만 영향을 준다 — 검토사항·판정 흐름·연결은 그대로이고 옛 항목은 차례까지 그대로
    changed, added = _change_facts(case)
    assert changed == [], case
    assert added == len(_rows_of(case)), case


@_value_free
def _unlisted_tokens(case: str) -> list[str]:
    """판정 목록에 없는 새 칸의 토큰(서식코드.칸 — 값 없음)."""
    view = view_of(v3_response(case))
    tokens = view["decision"]["medium_risk_items"]
    return [f"{form}.{key[2:]}" for form, key in _new_findings(view) if f"{form}.{key[2:]}" not in tokens]


@pytest.mark.parametrize("case", FORMS_OF)
def test_verdict_tokens_of_new_keys_match_the_items(case: str, caplog: pytest.LogCaptureFixture) -> None:
    # 판정 목록의 토큰(서식코드.접두어를_뗀_칸)과 항목 칸이 같으면 차이 경고가 없다
    with caplog.at_level(logging.WARNING, logger="imask.findings"):
        unlisted = _unlisted_tokens(case)
    warned = GAP_WARNING in caplog.text
    assert not warned, case
    assert unlisted == [], case


@_value_free
def _blank_facts(case: str) -> tuple[list[str], str | None, list[tuple[str, str]], bool]:
    """비어 있지 않은 새 칸, 계약 위반 자리, 항목이 된 새 칸, 항목 전체가 원본과 같은지."""
    response = v3_response(case, blank=True)
    filled = [key for form in FORMS_OF[case] for row_form, key in V3_ROWS if row_form == form and _read(response, form)[0][key] != ""]
    view = view_of(response)
    return filled, _contract_problem(view), _new_findings(view), view["findings"] == view_of(load(case))["findings"]


@pytest.mark.parametrize("case", FORMS_OF)
def test_blank_new_keys_make_no_items(case: str) -> None:
    filled, problem, rows, same_findings = _blank_facts(case)
    assert filled == [], case  # 칸은 응답에 있고 값만 비었다
    assert problem is None, case
    assert rows == [], case
    assert same_findings, case


# --- incomplete_fields ----------------------------------------------------------------------


@_value_free
def _incomplete_facts(case: str, form: str, listed: list[str], want_id: str, label: str | None) -> tuple[str | None, list[tuple[str, str]], int, bool]:
    """계약 위반 자리, 새 칸 (서식, 칸), 판독 불가 항목 수, 그 제목에 칸 이름이 있는지."""
    response = v3_response(case)
    data, meta = _read(response, form)
    data["incomplete_fields"] = listed
    _write(response, form, data, meta)
    view = view_of(response)
    item_id = want_id.format(i=_doc_index(view, form))
    hits = [i for i in view["items"] if i["id"] == item_id]
    named = len(hits) == 1 and (label is None or label in hits[0]["title"])
    return _contract_problem(view), sorted(_new_findings(view)), len(hits), named


@pytest.mark.parametrize(
    ("case", "form", "listed", "want_id", "label"),
    [
        ("M", FOREIGNER, ["중_본인_성명"], "unreadable:{i}:중_본인_성명", "본인 성명"),  # v3 목록은 옛 칸만 — 새 칸 때문에 달라지지 않는다
        ("C", IRP_NEW, ["중_가입자명"], "unreadable:{i}:중_가입자명", "가입자명"),
        ("M", FOREIGNER, ["중_하단_본인_서명"], "unreadable:{i}:중_하단_본인_서명", "하단 본인 서명"),  # 새 칸이 들어와도 제 이름으로
        ("M", FOREIGNER, ["하단_담보제공자_서명"], "unreadable:{i}:중_하단_담보제공자_서명", "하단 담보제공자 서명"),  # 옛 이름은 접두어 무시로 찾는다
        ("C", CHECK_CARD, ["중_마이너스통장_본인성명"], "unreadable:{i}:중_마이너스통장_본인성명", "마이너스통장 확인 본인 성명"),
        ("M", FOREIGNER, ["없는_칸"], "unreadable:{i}", None),  # 칸을 못 가리키는 항목
    ],
    ids=["옛칸-외국인", "옛칸-IRP", "새칸-외국인", "옛이름", "새칸-체크카드", "모르는칸"],
)
def test_incomplete_fields_does_not_break_on_new_keys(case: str, form: str, listed: list[str], want_id: str, label: str | None) -> None:
    problem, rows, hit_count, named = _incomplete_facts(case, form, listed, want_id, label)
    assert problem is None, want_id
    assert rows == _rows_of(case), want_id
    assert hit_count == 1, want_id
    assert named, want_id


# --- 설정 60 응답은 그대로 ----------------------------------------------------------------------


@_value_free
def _config60_new_rows(case: str) -> list[tuple[str, str]]:
    return _new_findings(view_of(load(case)))


@pytest.mark.parametrize("case", CASES)
def test_config60_responses_have_no_v3_items(case: str) -> None:
    rows = _config60_new_rows(case)
    assert rows == [], case


@_value_free
def _unprefixed_facts(case: str) -> tuple[list[str], list[str]]:
    """값이 빈 옛 이름, 항목이 된 옛·새 이름."""
    response = load(case)
    data = _read(response, FOREIGNER)[0]
    empty = [old for old in RENAMED if not data.get(old)]
    names = {f["field"] for f in view_of(response)["findings"]} & (set(RENAMED) | set(RENAMED.values()))
    return empty, sorted(names)


@pytest.mark.parametrize("case", ["B", "M", "U"])
def test_unprefixed_signature_keys_stay_non_items_in_config60(case: str) -> None:
    empty, item_names = _unprefixed_facts(case)
    assert empty == [], case  # 값이 있는 칸인데도
    assert item_names == [], case


@_value_free
def _case_c_v3_keys() -> list[str]:
    response = load("C")
    return sorted(key for form, key in V3_ROWS if form in FORMS_OF["C"] and key in _read(response, form)[0])


def test_config60_case_c_has_no_v3_keys_in_its_extract() -> None:
    found = _case_c_v3_keys()
    assert found == []


# --- 실패 출력에 값이 없는지 --------------------------------------------------------------------------

FAILURE_FLAGS = [["-q"], ["-vv"], ["--tb=long"], ["--showlocals"], ["-vv", "--tb=long", "--showlocals"]]
CHILD_TIMEOUT_SECONDS = 300
# 망가뜨리는 방법 → 그때 반드시 실패해야 하는 시험. 값을 읽는 시험이 한 번씩은 실패하게 골랐다.
MUST_FAIL: dict[str, tuple[str, ...]] = {
    "duplicate": ("test_new_key_becomes_one_item_as_the_table_says",),  # 항목이 둘 — 검증 M1 의 자리
    "drop": ("test_new_key_becomes_one_item_as_the_table_says", "test_incomplete_fields_does_not_break_on_new_keys", "test_verdict_tokens_of_new_keys_match_the_items"),
    "reveal": ("test_new_key_becomes_one_item_as_the_table_says",),  # 가림 함수가 원문을 그대로
    "value_in_meta": ("test_new_key_becomes_one_item_as_the_table_says", "test_v3_response_keeps_the_view_contract_and_has_every_new_key"),  # 이름표 자리에 원문
    "side_effect": ("test_new_keys_change_nothing_but_their_own_items",),
    "phantom": ("test_blank_new_keys_make_no_items", "test_config60_responses_have_no_v3_items", "test_unprefixed_signature_keys_stay_non_items_in_config60"),
    "contract": ("test_v3_response_keeps_the_view_contract_and_has_every_new_key",),  # 키 구성이 틀림 — view_contract.py 가 항목 객체를 메시지에 넣는 자리
    "damaged_file": ("test_config60_responses_have_no_v3_items",),  # 준비 단계: json.loads 의 인자가 파일 원문
    "damaged_extract": ("test_config60_case_c_has_no_v3_keys_in_its_extract",),  # 준비 단계: json.loads 의 인자가 Extract 원문
}
# 하위 pytest 에만 싣는 플러그인(시험의 tmp_path 에 쓴다). 값은 응답에서 읽은 것뿐이다.
BREAK_PLUGIN = '''\
import json

import pytest

from imask_backend import findings


def _patch_items(monkeypatch, change):
    real = findings._v2_findings

    def patched(docs):
        items, tokens = real(docs)
        return change(items, docs), tokens

    monkeypatch.setattr(findings, "_v2_findings", patched)


def _new_keys(request):
    return {key for _, key in request.module.V3_ROWS}


def duplicate(request, monkeypatch, factory):
    new = _new_keys(request)
    _patch_items(monkeypatch, lambda items, docs: items + [dict(f) for f in items if f["field"] in new])


def drop(request, monkeypatch, factory):
    new = _new_keys(request)
    bare = {key[2:] for key in new}
    real = findings._v2_findings

    def patched(docs):
        items, tokens = real(docs)
        kept = {grade: {token for token in listed if token.split(".", 1)[1] not in bare} for grade, listed in tokens.items()}
        return [f for f in items if f["field"] not in new], kept

    monkeypatch.setattr(findings, "_v2_findings", patched)


def reveal(request, monkeypatch, factory):
    monkeypatch.setattr(findings, "masked", lambda value, kind: value)


def value_in_meta(request, monkeypatch, factory):
    new = _new_keys(request)
    show = lambda f: {**f, "category": f["value"], "label": f["value"], "subject": f["value"]}
    _patch_items(monkeypatch, lambda items, docs: [show(f) if f["field"] in new else f for f in items])


def side_effect(request, monkeypatch, factory):
    new = _new_keys(request)

    def change(items, docs):
        if not any(f["field"] in new for f in items):
            return items
        first_old = next(i for i, f in enumerate(items) if f["field"] not in new)
        return items[:first_old] + items[first_old + 1 :]

    _patch_items(monkeypatch, change)


def phantom(request, monkeypatch, factory):
    rows = request.module.V3_ROWS

    def change(items, docs):
        out = list(items)
        for doc in docs:
            own = [f for f in items if f["document_index"] == doc.index]
            for form, key in rows:
                if form == doc.type and own and not any(f["field"] == key for f in own):
                    out.append({**own[0], "id": f"{doc.index}:{key}", "field": key})
        return out

    _patch_items(monkeypatch, change)


def contract(request, monkeypatch, factory):
    def change(items, docs):
        return [{name: cell for name, cell in f.items() if name != "confidence"} for f in items]

    _patch_items(monkeypatch, change)


def _use_rewritten_fixtures(request, monkeypatch, factory, name, rewrite):
    folder = factory.getbasetemp() / name
    if not folder.exists():
        folder.mkdir()
        for path in sorted(request.module.FIXTURES.glob("case_*.json")):
            (folder / path.name).write_bytes(rewrite(path.read_bytes()))
    monkeypatch.setattr(request.module, "FIXTURES", folder)


def damaged_file(request, monkeypatch, factory):
    _use_rewritten_fixtures(request, monkeypatch, factory, "damaged_file", lambda raw: raw[: raw.rfind(b",", 0, len(raw) // 2)])


def _cut_extract_text(raw):
    response = json.loads(raw)
    for step in response["output"]:
        if step["model"].startswith("Information Extract - "):
            text = step["content"][0]["text"]
            step["content"][0]["text"] = text[: len(text) // 2]
    return json.dumps(response, ensure_ascii=False).encode("utf-8")


def damaged_extract(request, monkeypatch, factory):
    _use_rewritten_fixtures(request, monkeypatch, factory, "damaged_extract", _cut_extract_text)


SCENARIOS = {
    "duplicate": duplicate,
    "drop": drop,
    "reveal": reveal,
    "value_in_meta": value_in_meta,
    "side_effect": side_effect,
    "phantom": phantom,
    "contract": contract,
    "damaged_file": damaged_file,
    "damaged_extract": damaged_extract,
}


@pytest.fixture(autouse=True, params=list(SCENARIOS))
def break_scenario(request, monkeypatch, tmp_path_factory):
    SCENARIOS[request.param](request, monkeypatch, tmp_path_factory)
'''


class ChildReport(NamedTuple):
    """하위 pytest 결과 — 값 없는 사실만."""

    exit_code: int
    error_count: int
    not_failed: list[str]  # 실패해야 하는데 실패하지 않은 "방법 시험"
    leaked_keys: list[str]  # 출력에 값이 나온 칸 이름


def _string_leaves(value: Any, key: str = "") -> Iterator[tuple[str, str]]:
    """JSON 값 안의 (칸 이름, 문자열)."""
    if isinstance(value, str):
        yield key, value
    elif isinstance(value, list):
        for item in value:
            yield from _string_leaves(item, key)
    elif isinstance(value, Mapping):
        for name, item in value.items():
            yield from _string_leaves(item, name)


def _watched_values() -> dict[str, str]:
    """고정 응답 21건의 Extract 원문 값 → 칸 이름. 시험 코드에 그대로 있는 글자와 짧은 글자는 출력에서 값과 구별할 수 없어 뺀다."""
    source = THIS_FILE.read_bytes().decode("utf-8")
    watched: dict[str, str] = {}
    for case in CASES:
        for step in load(case)["output"]:
            if not step["model"].startswith(EXTRACT_MODEL):
                continue
            for key, value in _string_leaves(json.loads(step["content"][0]["text"])):
                plain = value.strip()
                has_hangul = any("가" <= ch <= "힣" for ch in plain)
                if key != "incomplete_fields" and (len(plain) >= 6 or (has_hangul and len(plain) >= 2)) and plain not in source:
                    watched.setdefault(plain, key)
    return watched


def _spellings(value: str) -> tuple[str, ...]:
    """출력에서 찾을 꼴(소문자) — 원문, Unicode escape, UTF-8 바이트 표현."""
    return (value.lower(), value.encode("unicode_escape").decode("ascii").lower(), repr(value.encode("utf-8"))[2:-1].lower())


def _leaked_keys(output: str, watched: Mapping[str, str]) -> list[str]:
    lowered = output.lower()
    return sorted({key for value, key in watched.items() if any(spelling in lowered for spelling in _spellings(value))})


def _not_failed(output: str) -> list[str]:
    failed: set[tuple[str, str]] = set()
    for name, test_id in re.findall(r"^FAILED \S*::(test_\w+)\[(\S*)\]", output, re.MULTILINE):
        failed.update((part, name) for part in test_id.split("-") if part in MUST_FAIL)
    return [f"{scenario} {name}" for scenario, names in MUST_FAIL.items() for name in names if (scenario, name) not in failed]


@_value_free
def _run_broken_child(tmp_path: Path, flags: list[str]) -> ChildReport:
    (tmp_path / "imask_v3_break.py").write_bytes(BREAK_PLUGIN.encode("utf-8"))
    env = {name: value for name, value in os.environ.items() if name != "PYTEST_ADDOPTS"}
    env.update(PYTHONPATH=os.pathsep.join([str(tmp_path), str(ROOT)]), PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    command = [sys.executable, "-X", "utf8", "-m", "pytest", str(THIS_FILE), "-p", "imask_v3_break", "-p", "no:cacheprovider"]
    command += [f"--basetemp={tmp_path / 'child'}", "-k", "not failure_output", "--color=no", *flags]
    done = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, timeout=CHILD_TIMEOUT_SECONDS, check=False)
    output = (done.stdout + done.stderr).decode("utf-8", "replace")
    return ChildReport(done.returncode, len(re.findall(r"^ERROR ", output, re.MULTILINE)), _not_failed(output), _leaked_keys(output, _watched_values()))


@pytest.mark.parametrize("flags", FAILURE_FLAGS, ids=lambda flags: " ".join(flags))
def test_failure_output_has_no_raw_values(flags: list[str], tmp_path: Path) -> None:
    report = _run_broken_child(tmp_path, flags)
    assert report.exit_code == 1, flags  # 시험이 실패했을 때의 종료 코드(수집 오류·사용법 오류가 아니다)
    assert report.error_count == 0, flags  # 플러그인이 망가지지 않았다
    assert report.not_failed == [], flags
    assert report.leaked_keys == [], flags


@_value_free
def _scan_facts() -> tuple[int, list[str], list[str]]:
    """지켜보는 값의 수, 새 칸 중 지켜보지 못하는 칸, 세 꼴로 넣어도 찾지 못하는 칸."""
    watched = _watched_values()
    unwatched, unseen = [], []
    for form, key in V3_ROWS:
        value = _read(v3_response(CASE_OF[form]), form)[0][key].strip()
        if value not in watched:
            unwatched.append(key)
        for spelling in (value, ascii(value), repr(value.encode("utf-8"))):
            if not _leaked_keys(f"앞 {spelling} 뒤", {value: key}):
                unseen.append(key)
    return len(watched), unwatched, unseen


def test_failure_output_scan_watches_the_new_keys_and_finds_every_spelling() -> None:
    # 위 시험이 헛돌지 않게: 새 칸의 값을 지켜보고 있고, 출력에 어떤 꼴로 있어도 찾는다
    watched_count, unwatched, unseen = _scan_facts()
    assert watched_count > 100
    assert unwatched == []
    assert unseen == []
