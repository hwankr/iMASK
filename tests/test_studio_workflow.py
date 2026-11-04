# ==========================================================================
#  scripts/studio_workflow.py 테스트 — 가짜 Studio 서버(httpx.MockTransport)로 하위 명령
#  list·show·export·diff·create 를 부른다. 네트워크·실제 .env 는 쓰지 않는다(BRIEF §3).
#  - 목록 넘김(after), 설정 없음, 400·401·404·연결 오류, 응답 모양이 틀린 경우
#  - create 는 --yes 없이 요청을 하나도 보내지 않음, 같은 이름 에이전트가 둘이면 멈춤
#  - 출력(표준 출력·오류)에 키·프로젝트 id·전체 에이전트/설정 id 가 없음, x-project-id 헤더
#  저장소 정의의 무결성 시험은 tests/test_workflow_definition.py 에 있다(T7 이 옮김 — 여기서는 중복하지 않는다).
# ==========================================================================

from __future__ import annotations

import copy
import importlib.util
import io
import json
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / "workflows" / "final_imask_workflow.json"

# 가짜 값은 실행 중에 조립한다(키 꼴 리터럴을 두지 않는다)
FAKE_KEY = "fake-studio-key-" + "q" * 24
FAKE_PROJECT = "proj_" + "fakeproject" * 2
AGENT_ID = "agt_" + "a" * 18 + "Ab12Cd"
AGENT2_ID = "agt_" + "b" * 18 + "Ef34Gh"
CONFIG_ID = "cfg_" + "c" * 18 + "Ij56Kl"
CONFIG2_ID = "cfg_" + "d" * 18 + "Mn78Op"
NEW_AGENT_ID = "agt_" + "n" * 18 + "Qr90St"
NEW_CONFIG_ID = "cfg_" + "m" * 18 + "Uv12Wx"
FULL_IDS = (AGENT_ID, AGENT2_ID, CONFIG_ID, CONFIG2_ID, NEW_AGENT_ID, NEW_CONFIG_ID, FAKE_PROJECT)
NAME = "final_imask_workflow"


def load_script():
    spec = importlib.util.spec_from_file_location("studio_workflow", ROOT / "scripts" / "studio_workflow.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


sw = load_script()


def workflow_body() -> dict:
    return json.loads(WORKFLOW.read_bytes().decode("utf-8"))


def studio_config(body: dict | None = None, *, external_id="1", config_id=CONFIG_ID, is_default=True) -> dict:
    """Studio 가 돌려주는 설정 하나(저장소 형식 + Studio 가 붙이는 필드)."""
    body = copy.deepcopy(body or workflow_body())
    steps = []
    for step in body["steps"]:
        steps.append({**step, "created_at": 1730000000, "config_id": config_id})
    return {"id": config_id, "name": body["name"], "external_id": external_id, "is_default": is_default,
            "agent_id": AGENT_ID, "project_id": FAKE_PROJECT, "steps": steps}


class FakeStudio:
    """요청을 기록하고 정해 둔 응답을 돌려주는 가짜 Studio."""

    def __init__(self, agents=None, configs=None, *, page_size=None, errors=None, list_body=None):
        self.agents = agents if agents is not None else [agent(AGENT_ID, NAME)]
        self.configs = configs if configs is not None else {AGENT_ID: [studio_config()]}
        self.page_size = page_size
        self.errors = errors or {}  # "METHOD path" → httpx.Response 또는 예외
        self.list_body = list_body
        self.requests: list[httpx.Request] = []
        self.posted: list[tuple[str, dict]] = []

    @property
    def calls(self) -> list[str]:
        out = []
        for r in self.requests:
            key = f"{r.method} {r.url.path.removeprefix('/v2')}"
            if r.url.query:
                key += "?" + r.url.query.decode()
            out.append(key)
        return out

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path.removeprefix("/v2")
        key = f"{request.method} {path}"
        if key in self.errors:
            err = self.errors[key]
            if isinstance(err, Exception):
                raise err
            return err
        parts = path.strip("/").split("/")
        if key == "GET /agents":
            if self.list_body is not None:
                return raw_json(self.list_body)
            items = self.agents
            if self.page_size:
                after = request.url.params.get("after")
                start = 0
                if after:
                    start = next(i for i, a in enumerate(items) if a.get("id") == after) + 1
                page = items[start:start + self.page_size]
                more = start + self.page_size < len(items)
                return raw_json({"object": "list", "data": page, "has_more": more,
                                 "last_id": page[-1]["id"] if page else None})
            return raw_json({"object": "list", "data": items, "has_more": False})
        if request.method == "GET" and len(parts) == 2:
            found = [a for a in self.agents if a.get("id") == parts[1]]
            return raw_json(found[0]) if found else not_found()
        if request.method == "GET" and len(parts) == 3:
            configs = self.configs.get(parts[1])
            if configs is None:
                return not_found()
            items = [{k: v for k, v in c.items() if k != "steps"} for c in configs]
            return raw_json({"data": items, "has_more": False})
        if request.method == "GET" and len(parts) == 4:
            found = [c for c in self.configs.get(parts[1], []) if c["id"] == parts[3]]
            return raw_json(found[0]) if found else not_found()
        if key == "POST /agents":
            body = json.loads(request.content)
            self.posted.append((key, body))
            created = agent(NEW_AGENT_ID, body["name"])
            self.agents.append(created)
            self.configs[NEW_AGENT_ID] = []
            return raw_json(created)
        if request.method == "POST" and len(parts) == 3:
            body = json.loads(request.content)
            self.posted.append((key, body))
            number = str(len(self.configs.setdefault(parts[1], [])) + 1)
            config = {"id": NEW_CONFIG_ID, "external_id": number, "is_default": True, "name": body["name"]}
            for a in self.agents:
                if a["id"] == parts[1]:
                    a["default_config_id"] = NEW_CONFIG_ID
            self.configs[parts[1]].append({**config, "steps": body["steps"]})
            return raw_json(config)
        return not_found()


def agent(agent_id: str, name: str, **extra) -> dict:
    return {"id": agent_id, "name": name, "visibility": "private", "project_id": FAKE_PROJECT,
            "default_config_id": CONFIG_ID, "default_config_external_id": "1",
            "used_steps": ["document-parse", "match", "merge"], **extra}


def raw_json(obj) -> httpx.Response:
    """NaN 같은 값도 그대로 싣는 응답(httpx 의 json= 은 NaN 을 거부한다)."""
    return httpx.Response(200, content=json.dumps(obj).encode(), headers={"content-type": "application/json"})


def not_found() -> httpx.Response:
    return httpx.Response(404, json={"error": {"message": "Not found", "code": "not_found"}})


@pytest.fixture
def env_file(tmp_path: Path) -> Path:
    path = tmp_path / "studio.env"
    path.write_bytes(f"# 주석\nUPSTAGE_API_KEY={FAKE_KEY}\nexport UPSTAGE_PROJECT_ID=\"{FAKE_PROJECT}\"\n".encode())
    return path


def json_strings(value) -> list[str]:
    """JSON 을 디코딩한 값 안의 모든 문자열(키 포함)."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for k, v in value.items() for s in json_strings(k) + json_strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in json_strings(v)]
    return []


def run(argv: list[str], fake: FakeStudio | None, env_file: Path | None = None, *, key: str | None = None,
        extra_secrets: tuple[str, ...] = ()):
    """(종료 코드, 표준 출력, 오류 출력). 출력(그리고 JSON 이면 디코딩한 값)에는 키·전체 id 가 없어야 한다.

    key 를 주면 환경 파일 대신 그 키로 실행한다(가림 경계 시험용).
    """
    stdout, stderr = io.StringIO(), io.StringIO()
    args = list(argv)
    environ = {}
    if key is not None:
        environ = {"UPSTAGE_API_KEY": key, "UPSTAGE_PROJECT_ID": FAKE_PROJECT}
        env_file = env_file or Path("none-such.env")
    if env_file is not None:
        args += ["--env-file", str(env_file)]
    transport = httpx.MockTransport(fake) if fake is not None else httpx.MockTransport(fail_if_called)
    code = sw.main(args, transport=transport, stdout=stdout, stderr=stderr, environ=environ)
    out, err = stdout.getvalue(), stderr.getvalue()
    texts = [out, err]
    try:
        texts += json_strings(json.loads(out))
    except ValueError:
        pass
    secrets = (FAKE_KEY, *(() if key is None else (key,)), *extra_secrets)
    for text in texts:
        for secret in secrets:
            assert secret not in text
        assert "bearer" not in text.lower()
        for full in FULL_IDS:
            assert full not in text, full
    return code, out, err


def fail_if_called(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"요청을 보내면 안 됩니다: {request.method} {request.url.path}")


# --- 헤더·환경 ----------------------------------------------------------------


def test_headers_and_project_id(env_file):
    fake = FakeStudio()
    code, _, _ = run(["list"], fake, env_file)
    assert code == 0
    assert fake.requests
    for request in fake.requests:
        assert request.headers["authorization"] == f"Bearer {FAKE_KEY}"
        assert request.headers["x-project-id"] == FAKE_PROJECT
        assert str(request.url).startswith("https://api.upstage.ai/v2/")


def test_no_project_header_when_missing(tmp_path):
    env = tmp_path / "only-key.env"
    env.write_bytes(f"UPSTAGE_API_KEY='{FAKE_KEY}'\n".encode())
    fake = FakeStudio()
    code, _, _ = run(["list"], fake, env)
    assert code == 0
    assert all("x-project-id" not in r.headers for r in fake.requests)


def test_missing_key_sends_nothing(tmp_path):
    env = tmp_path / "empty.env"
    env.write_bytes(b"UPSTAGE_PROJECT_ID=proj_x\n")
    code, out, err = run(["list"], None, env)
    assert code == 2
    assert "UPSTAGE_API_KEY" in err and out == ""


def test_bad_project_id_rejected(tmp_path):
    env = tmp_path / "bad.env"
    env.write_bytes(f"UPSTAGE_API_KEY={FAKE_KEY}\nUPSTAGE_PROJECT_ID=proj x\n".encode())
    code, _, err = run(["list"], None, env)
    assert code == 2 and "UPSTAGE_PROJECT_ID" in err


def test_env_file_parsing(tmp_path):
    env = tmp_path / "x.env"
    env.write_bytes("﻿# c\n\nexport A=\"1 2\"\nB='x'\nC=y # 설명\nD\nE = z \n".encode())
    assert sw.read_env_file(env) == {"A": "1 2", "B": "x", "C": "y", "E": "z"}
    assert sw.read_env_file(tmp_path / "none.env") == {}


# --- list ---------------------------------------------------------------------


def test_list_follows_pages_with_after(env_file):
    agents = [agent(AGENT_ID, NAME), agent(AGENT2_ID, "다른 워크플로우"), agent(NEW_AGENT_ID, "세 번째")]
    configs = {AGENT_ID: [studio_config()], AGENT2_ID: [studio_config(config_id=CONFIG2_ID)], NEW_AGENT_ID: []}
    fake = FakeStudio(agents, configs, page_size=2)
    code, out, _ = run(["list"], fake, env_file)
    assert code == 0
    assert "GET /agents" in fake.calls
    assert f"GET /agents?after={AGENT2_ID}" in fake.calls
    assert "에이전트 3개" in out
    assert NAME in out and "다른 워크플로우" in out and "세 번째" in out
    assert "…Ab12Cd" in out
    assert "설정 1개 · 기본 설정 1" in out and "설정 0개" in out
    assert "document-parse, match, merge" in out


def test_list_json_shortens_ids(env_file):
    code, out, _ = run(["list", "--json"], FakeStudio(), env_file)
    assert code == 0
    rows = json.loads(out)["agents"]
    assert rows == [{"name": NAME, "id": "…Ab12Cd", "visibility": "private", "config_count": 1,
                     "default_config": "1", "used_steps": ["document-parse", "match", "merge"]}]


def test_list_stops_when_next_page_unknown(env_file):
    fake = FakeStudio(list_body={"data": [agent(AGENT_ID, NAME)], "has_more": True})
    code, _, err = run(["list"], fake, env_file)
    assert code == 2 and "끝까지 읽지 못했습니다" in err


def test_list_skips_malformed_items(env_file):
    weird = [None, "x", 3, {"name": ["목록"], "id": 5}, {"id": AGENT_ID, "name": "가" * 5000, "used_steps": "문자열"}]
    fake = FakeStudio(list_body={"data": weird, "has_more": False}, configs={AGENT_ID: []})
    code, out, _ = run(["list"], fake, env_file)
    assert code == 0
    assert "에이전트 2개" in out
    assert max(len(line) for line in out.splitlines()) < 400


@pytest.mark.parametrize("body", [[1, 2], "문자열", {"data": "x"}, {"data": None}])
def test_list_odd_bodies(env_file, body):
    code, _, _ = run(["list"], FakeStudio(list_body=body), env_file)
    assert code in (0, 2)


# --- show ---------------------------------------------------------------------


def test_show_default_config_graph(env_file):
    fake = FakeStudio()
    code, out, _ = run(["show", "--agent", NAME], fake, env_file)
    assert code == 0
    assert f"GET /agents/{AGENT_ID}/configs/{CONFIG_ID}" in fake.calls
    assert "설정 1 '최종 흐름 v0 (전체 노드 시험용)' (…Ij56Kl, 기본) · step 13개" in out
    assert "[document-parse] step_1_parse  (첫 단계)" in out
    assert "→ Information Extract - 추출_위임장  text == power_of_attorney" in out
    assert "→ Instruct - 권장_조치  additional_values.enum == 상 | 중 | 하" in out
    assert "[match] Match - 서류_대조" in out


def test_show_picks_config_number(env_file):
    second = studio_config(external_id="2", config_id=CONFIG2_ID, is_default=False)
    second["name"] = "두 번째"
    fake = FakeStudio(configs={AGENT_ID: [studio_config(), second]})
    code, out, _ = run(["show", "--agent", NAME, "--config", "2", "--json"], fake, env_file)
    assert code == 0
    shown = json.loads(out)
    assert shown["config"] == {"number": "2", "name": "두 번째", "id": "…Mn78Op", "is_default": False}
    assert shown["agent"] == {"name": NAME, "id": "…Ab12Cd"}
    assert shown["steps"][0] == {"name": "step_1_parse", "type": "document-parse", "is_first": True,
                                 "next": [{"to": "step_2_classify", "condition": None, "values": []}]}


def test_show_unknown_config_number(env_file):
    code, _, err = run(["show", "--agent", NAME, "--config", "9"], FakeStudio(), env_file)
    assert code == 2 and "설정 번호 '9' 가 없습니다(있는 번호: 1)" in err


def test_show_agent_without_configs(env_file):
    code, _, err = run(["show", "--agent", NAME], FakeStudio(configs={AGENT_ID: []}), env_file)
    assert code == 2 and "설정이 없습니다" in err


def test_show_unknown_agent(env_file):
    code, _, err = run(["show", "--agent", "없는 이름"], FakeStudio(), env_file)
    assert code == 2 and "에이전트가 없습니다" in err


def test_show_two_agents_same_name(env_file):
    fake = FakeStudio([agent(AGENT_ID, NAME), agent(AGENT2_ID, NAME)])
    code, _, err = run(["show", "--agent", NAME], fake, env_file)
    assert code == 2 and "2개" in err


def test_show_steps_not_a_list(env_file):
    broken = studio_config()
    broken["steps"] = {"x": 1}
    code, _, err = run(["show", "--agent", NAME], FakeStudio(configs={AGENT_ID: [broken]}), env_file)
    assert code == 2 and "steps 가 목록이 아닙니다" in err


# --- 오류 ---------------------------------------------------------------------


def leaky(status: int) -> httpx.Response:
    """서버가 키·인증 헤더·프로젝트 id·에이전트 id 를 되돌려 보내는 최악의 경우."""
    return httpx.Response(status, json={"error": {
        "message": f"bad Authorization: Bearer {FAKE_KEY} project {FAKE_PROJECT} agent {AGENT_ID}",
        "code": "config_graph_rule_violation" if status == 400 else "unauthorized"}})


@pytest.mark.parametrize("status", [400, 401, 403, 404, 500])
def test_http_errors_are_short_and_redacted(env_file, status):
    fake = FakeStudio(errors={f"GET /agents/{AGENT_ID}/configs/{CONFIG_ID}": leaky(status)})
    code, out, err = run(["show", "--agent", NAME], fake, env_file)
    assert code == 2 and out == ""
    assert f"HTTP {status}" in err
    assert "…Ab12Cd" in err
    assert "<UPSTAGE_PROJECT_ID>" in err


def test_400_graph_rule_code_is_shown(env_file):
    fake = FakeStudio(errors={"GET /agents": httpx.Response(400, json={"error": {
        "message": "Match anchor must feed merge", "code": "config_graph_rule_violation"}})})
    code, _, err = run(["list"], fake, env_file)
    assert code == 2
    assert "HTTP 400 — Match anchor must feed merge [config_graph_rule_violation]" in err


def test_401_without_json_body(env_file):
    fake = FakeStudio(errors={"GET /agents": httpx.Response(401, text=f"<html>{FAKE_KEY}</html>")})
    code, _, err = run(["list"], fake, env_file)
    assert code == 2 and "HTTP 401" in err and "html" not in err


def test_404_agent_list(env_file):
    fake = FakeStudio(errors={"GET /agents": not_found()})
    code, _, err = run(["list"], fake, env_file)
    assert code == 2 and "HTTP 404 — Not found [not_found]" in err


@pytest.mark.parametrize("exc", [httpx.ConnectError("boom"), httpx.ReadTimeout("slow")])
def test_connection_errors(env_file, exc):
    fake = FakeStudio(errors={"GET /agents": exc})
    code, _, err = run(["list"], fake, env_file)
    assert code == 2
    assert ("연결하지 못했습니다" in err) or ("시간이 지났습니다" in err)


def test_non_json_success_body(env_file):
    fake = FakeStudio(errors={"GET /agents": httpx.Response(200, text="not json")})
    code, _, err = run(["list"], fake, env_file)
    assert code == 2 and "JSON 이 아닙니다" in err


def test_bad_id_in_response_not_used_in_path(env_file):
    fake = FakeStudio([agent("../../files", NAME)])
    code, _, err = run(["show", "--agent", NAME], fake, env_file)
    assert code == 2 and "id 모양이 다릅니다" in err
    assert fake.calls == ["GET /agents"]


# --- export -------------------------------------------------------------------


def test_export_writes_repo_format(env_file, tmp_path):
    out_path = tmp_path / "sub" / "exported.json"
    code, out, _ = run(["export", "--agent", NAME, "--config", "1", "--out", str(out_path)], FakeStudio(), env_file)
    assert code == 0 and "step 13개" in out
    data = out_path.read_bytes()
    assert data == WORKFLOW.read_bytes()  # 저장소 파일과 바이트까지 같다(Studio 가 붙인 필드는 빠진다)
    assert b"\r" not in data and not data.startswith(b"\xef\xbb\xbf")


def test_export_rejects_nan(env_file, tmp_path):
    bad = studio_config()
    bad["steps"][0]["data"] = {"x": float("nan")}
    code, _, err = run(["export", "--agent", NAME, "--config", "1", "--out", str(tmp_path / "o.json")],
                       FakeStudio(configs={AGENT_ID: [bad]}), env_file)
    assert code == 2 and "NaN" in err
    assert not (tmp_path / "o.json").exists()


# --- diff ---------------------------------------------------------------------


def test_diff_same(env_file):
    code, out, _ = run(["diff", "--agent", NAME, "--config", "1", str(WORKFLOW)], FakeStudio(), env_file)
    assert code == 0 and out.startswith("같음") and "step 13개" in out


def test_diff_ignores_step_order_and_next_order(env_file):
    body = workflow_body()
    body["steps"].reverse()
    for step in body["steps"]:
        step["next_steps"].reverse()
    code, _, _ = run(["diff", "--agent", NAME, "--config", "1", str(WORKFLOW)],
                     FakeStudio(configs={AGENT_ID: [studio_config(body)]}), env_file)
    assert code == 0


def test_diff_reports_changed_added_removed(env_file, tmp_path):
    body = workflow_body()
    by_name = {s["name"]: s for s in body["steps"]}
    by_name["Instruct - 위험도_판정"]["data"]["custom_name"] = "바뀜"
    by_name["Validate - 묶음_검증"]["is_first"] = True
    body["steps"] = [s for s in body["steps"] if s["name"] != "Instruct - 검토_안내"]
    body["steps"].append({**copy.deepcopy(by_name["Instruct - 권장_조치"]), "name": "Instruct - 새_노드"})
    local = tmp_path / "local.json"
    local.write_bytes(json.dumps(body, ensure_ascii=False).encode())
    fake = FakeStudio()
    code, out, _ = run(["diff", "--agent", NAME, "--config", "1", str(local)], fake, env_file)
    assert code == 1
    assert out.startswith("다름") and "다른 step 4개" in out
    assert "~ Instruct - 위험도_판정: data 다름" in out
    assert "~ Validate - 묶음_검증: is_first 다름" in out
    assert "+ Instruct - 새_노드 (파일에만)" in out
    assert "- Instruct - 검토_안내 (Studio 에만)" in out
    code, out, _ = run(["diff", "--agent", NAME, "--config", "1", str(local), "--json"], FakeStudio(), env_file)
    assert code == 1
    result = json.loads(out)
    assert result["same"] is False and len(result["differences"]) == 4


def test_diff_ids_only_with_flag(env_file, tmp_path):
    body = workflow_body()
    body["steps"][0]["node_id"] = "nd_other"
    local = tmp_path / "ids.json"
    local.write_bytes(json.dumps(body, ensure_ascii=False).encode())
    code, _, _ = run(["diff", "--agent", NAME, "--config", "1", str(local)], FakeStudio(), env_file)
    assert code == 0
    code, out, _ = run(["diff", "--agent", NAME, "--config", "1", str(local), "--ids"], FakeStudio(), env_file)
    assert code == 1 and "~ step_1_parse: node_id 다름" in out


def test_diff_bad_file_sends_nothing(env_file, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"[1, 2]")
    code, _, err = run(["diff", "--agent", NAME, "--config", "1", str(bad)], None, env_file)
    assert code == 2 and "파일 모양이 다릅니다" in err


def test_diff_steps_duplicates_and_unnamed():
    steps = [{"name": "a", "type": "x"}, {"name": "a", "type": "y"}, {"type": "z"}]
    diffs = sw.diff_steps(steps, [{"name": "a", "type": "x"}])
    assert {"step": "a", "problem": "파일에서 이름이 겹침"} in diffs
    assert any(d.get("only_in") == "file" and d["step"].startswith("<이름 없음") for d in diffs)


# --- create -------------------------------------------------------------------


def test_create_without_yes_sends_nothing(env_file):
    code, out, _ = run(["create", str(WORKFLOW), "--agent", "새_워크플로우"], None, env_file)
    assert code == 0
    assert "보내지 않음" in out and "--yes" in out and "step 13개" in out


def test_create_without_yes_needs_no_env(tmp_path):
    code, out, _ = run(["create", str(WORKFLOW), "--agent", "새", "--json"], None, tmp_path / "none.env")
    assert code == 0
    assert json.loads(out) == {"dry_run": True, "agent": "새", "config_name": "최종 흐름 v0 (전체 노드 시험용)", "steps": 13}


def test_create_new_agent_then_config(env_file):
    fake = FakeStudio()
    code, out, _ = run(["create", str(WORKFLOW), "--agent", "새_워크플로우", "--yes"], fake, env_file)
    assert code == 0
    assert [k for k, _ in fake.posted] == ["POST /agents", f"POST /agents/{NEW_AGENT_ID}/configs"]
    assert fake.posted[0][1] == {"name": "새_워크플로우", "visibility": "private"}
    assert fake.posted[1][1] == workflow_body()
    assert "새로 만듦(private)" in out and "기본 설정이 됨" in out and "…Uv12Wx" in out


def test_create_existing_agent_adds_config_only(env_file):
    fake = FakeStudio()
    code, out, _ = run(["create", str(WORKFLOW), "--agent", NAME, "--yes", "--json"], fake, env_file)
    assert code == 0
    assert [k for k, _ in fake.posted] == [f"POST /agents/{AGENT_ID}/configs"]
    result = json.loads(out)
    assert result["agent"] == {"name": NAME, "id": "…Ab12Cd", "created": False}
    assert result["config"] == {"number": "2", "id": "…Uv12Wx", "steps": 13, "is_default": True}


def test_create_stops_on_duplicate_agent_names(env_file):
    fake = FakeStudio([agent(AGENT_ID, NAME), agent(AGENT2_ID, NAME)])
    code, _, err = run(["create", str(WORKFLOW), "--agent", NAME, "--yes"], fake, env_file)
    assert code == 2 and "2개" in err and "멈춥니다" in err
    assert fake.posted == [] and all(r.method == "GET" for r in fake.requests)


def test_create_stops_when_list_incomplete(env_file):
    fake = FakeStudio(list_body={"data": [], "has_more": True})
    code, _, _ = run(["create", str(WORKFLOW), "--agent", NAME, "--yes"], fake, env_file)
    assert code == 2 and fake.posted == []


def test_create_invalid_file_sends_nothing(env_file, tmp_path):
    body = workflow_body()
    body["steps"][0]["next_steps"] = [{"step_name": "없는 노드", "condition": None}]
    body["steps"][1]["is_first"] = True
    bad = tmp_path / "bad.json"
    bad.write_bytes(json.dumps(body, ensure_ascii=False).encode())
    code, _, err = run(["create", str(bad), "--agent", NAME, "--yes"], None, env_file)
    assert code == 2
    assert "1번째 step 의 next_steps[1] 이 없는 step 을 가리킵니다" in err and "첫 step(is_first)이 2개" in err
    assert "없는 노드" not in err  # 문구에는 위치만, 입력 값은 넣지 않는다


def test_create_config_error_is_reported(env_file):
    fake = FakeStudio(errors={f"POST /agents/{AGENT_ID}/configs": leaky(400)})
    code, _, err = run(["create", str(WORKFLOW), "--agent", NAME, "--yes"], fake, env_file)
    assert code == 2 and "HTTP 400" in err and "config_graph_rule_violation" in err


# --- 응답 경계 ------------------------------------------------------------------


def test_deeply_nested_response_is_an_error_not_a_crash(env_file):
    deep = b'{"data": ' + b"[" * 100000 + b"]" * 100000 + b"}"
    fake = FakeStudio(errors={"GET /agents": httpx.Response(200, content=deep, headers={"content-type": "application/json"})})
    code, _, err = run(["list"], fake, env_file)
    assert code == 2 and "JSON 이 아닙니다" in err


def test_too_many_agents(env_file):
    many = [agent(f"agt_{i:024d}", f"a{i}") for i in range(sw.MAX_ITEMS + 1)]
    code, _, err = run(["list"], FakeStudio(list_body={"data": many, "has_more": False}), env_file)
    assert code == 2 and "너무 많습니다" in err


def test_too_many_steps(env_file):
    big = studio_config()
    big["steps"] = big["steps"] * (sw.MAX_STEPS // 13 + 1)
    code, _, err = run(["show", "--agent", NAME], FakeStudio(configs={AGENT_ID: [big]}), env_file)
    assert code == 2 and "너무 많습니다" in err


def test_odd_step_values_are_shown_safely(env_file):
    odd = studio_config()
    odd["steps"] = [
        {"name": "가" * 10000, "type": None, "is_first": "yes", "next_steps": "x"},
        {"name": "\ud800짝없는", "type": "instruct", "next_steps": [None, {"step_name": 3, "condition": {"field": "text", "operator": "==", "value": float("inf")}},
                                                                      {"step_name": "z", "condition": ["모르는", "모양"]}]},
        "문자열 step",
    ]
    code, out, _ = run(["show", "--agent", NAME], FakeStudio(configs={AGENT_ID: [odd]}), env_file)
    assert code == 0
    assert "step 2개" in out and max(len(line) for line in out.splitlines()) < 400
    assert "→ ?  text == Infinity" in out and "→ z  조건" in out


def test_unknown_default_config_needs_number(env_file):
    odd = agent(AGENT_ID, NAME, default_config_id=None, default_config_external_id=None)
    configs = {AGENT_ID: [studio_config(is_default=False), studio_config(external_id=2, config_id=CONFIG2_ID, is_default=False)]}
    code, _, err = run(["show", "--agent", NAME], FakeStudio([odd], configs), env_file)
    assert code == 2 and "--config" in err
    code, out, _ = run(["show", "--agent", NAME, "--config", "2"], FakeStudio([odd], configs), env_file)
    assert code == 0 and "설정 2 " in out


# --- T2-fix1: 가림 순서(M1)·모르는 식별자(M2)·깨진 목록으로 만들기 금지(M3)·처리 안 된 예외(m1) -----------

# 가짜 키(실행 중에 조립). 긴 키는 표시·오류 길이 경계에 걸치게, 따옴표 키는 JSON 이스케이프를 시험한다
LONG_KEY = "generated-" + "z" * 90
QUOTE_KEY = "generated-" + chr(34) + "r" * 20
UNKNOWN_AGENT = "agt_" + "verification" * 2  # 응답에서 미리 본 적 없는 id


def fragments(secret: str, size: int = 16) -> list[str]:
    return [secret[i:i + size] for i in range(0, len(secret) - size + 1, 4)]


def assert_no_fragment(texts, secret):
    for text in texts:
        for piece in fragments(secret):
            assert piece not in text


def test_key_after_long_whitespace_in_error_is_hidden():
    fake = FakeStudio(errors={"GET /agents": httpx.Response(500, json={"error": {
        "message": " " * 1150 + LONG_KEY, "code": "\t" * 300 + LONG_KEY}})})
    code, out, err = run(["list"], fake, key=LONG_KEY)
    assert code == 2 and out == ""
    assert_no_fragment([err], LONG_KEY)
    assert "<UPSTAGE_API_KEY>" in err and "HTTP 500" in err


def test_key_at_display_boundary_is_hidden():
    name = "x" * 90 + LONG_KEY  # 키가 120자 표시 경계에 걸친다
    for argv in (["list"], ["list", "--json"]):
        code, out, _ = run(argv, FakeStudio([agent(AGENT_ID, name)], {AGENT_ID: []}), key=LONG_KEY)
        assert code == 0
        texts = [out] + (json_strings(json.loads(out)) if "--json" in argv else [])
        assert_no_fragment(texts, LONG_KEY)
        assert "<UPSTAGE_API" in out


def test_quoted_key_is_hidden_after_json_decoding():
    fake = FakeStudio([agent(AGENT_ID, "앞 " + QUOTE_KEY + " 뒤")], {AGENT_ID: []})
    code, out, _ = run(["list", "--json"], fake, key=QUOTE_KEY)
    assert code == 0
    name = json.loads(out)["agents"][0]["name"]
    assert QUOTE_KEY not in name and name == "앞 <UPSTAGE_API_KEY> 뒤"


def test_known_secret_is_replaced_before_redaction_rules():
    key = "abcd" + "token=" + "Q" * 20  # 정규식 규칙(token=)이 키 일부를 먼저 바꾸면 앞 조각이 남는다
    scrubber = sw.Scrubber({key: "<K>"})
    assert scrubber.scrub("값 " + key + " 끝") == "값 <K> 끝"
    assert scrubber.text("a" * (sw.MAX_RAW + 1)) == sw.TOO_LONG


def test_unknown_id_in_first_list_error_is_shortened():
    fake = FakeStudio(errors={"GET /agents": httpx.Response(400, json={"error": {"message": "agent " + UNKNOWN_AGENT,
                                                                                 "code": UNKNOWN_AGENT}})})
    code, _, err = run(["list"], fake, key=FAKE_KEY, extra_secrets=(UNKNOWN_AGENT,))
    assert code == 2 and "…cation" in err


def test_direct_client_errors_hide_ids_and_key():
    fake = FakeStudio(errors={"GET /agents": httpx.Response(400, json={"error": {
        "message": f"agent {UNKNOWN_AGENT} key {FAKE_KEY} project {FAKE_PROJECT}"}})})
    with sw.StudioClient(FAKE_KEY, FAKE_PROJECT, transport=httpx.MockTransport(fake)) as client:
        with pytest.raises(sw.StudioError) as caught:
            client.list_agents()
    text = str(caught.value)
    for secret in (UNKNOWN_AGENT, FAKE_KEY, FAKE_PROJECT):
        assert secret not in text
    assert "…cation" in text and "<UPSTAGE_PROJECT_ID>" in text


def test_direct_client_hides_request_ids_without_prefix():
    plain_id = "x" * 20 + "Q1w2E3"  # 접두어 없는 id 도 요청에 썼으면 줄인다
    fake = FakeStudio(errors={f"GET /agents/{plain_id}": httpx.Response(404, json={"error": {"message": f"no {plain_id}"}})})
    with sw.StudioClient(FAKE_KEY, transport=httpx.MockTransport(fake)) as client:
        with pytest.raises(sw.StudioError) as caught:
            client.get_agent(plain_id)
    assert plain_id not in str(caught.value) and "…Q1w2E3" in str(caught.value)


def test_new_id_first_seen_in_error_is_shortened(env_file):
    other = "cfg_" + "z" * 20 + "Yy99Zz"
    fake = FakeStudio(errors={f"GET /agents/{AGENT_ID}/configs/{CONFIG_ID}": httpx.Response(
        404, json={"error": {"message": f"config {CONFIG_ID} moved to {other}"}})})
    code, _, err = run(["show", "--agent", NAME], fake, env_file, extra_secrets=(other,))
    assert code == 2 and "…Yy99Zz" in err and "…Ij56Kl" in err


@pytest.mark.parametrize("body", [
    {"data": None, "has_more": False},
    {"data": [], "has_more": "true", "last_id": AGENT_ID},
    {"data": ["broken"], "has_more": False},
    {"data": [{"id": AGENT_ID, "name": ["목록"]}], "has_more": False},
    {"data": [{"id": 5, "name": NAME}], "has_more": False},
    {"data": [{"id": AGENT_ID, "name": NAME}]},  # has_more 없음
    [{"id": AGENT_ID, "name": NAME}],  # 객체가 아님
])
def test_create_refuses_broken_agent_list(env_file, body):
    fake = FakeStudio(list_body=body)
    code, out, err = run(["create", str(WORKFLOW), "--agent", NAME, "--yes"], fake, env_file)
    assert code == 2 and out == ""
    assert "목록이 온전하지 않습니다" in err
    assert fake.posted == [] and [r.method for r in fake.requests] == ["GET"]


def test_id_holding_a_secret_shows_no_tail(env_file):
    key_like_id = FAKE_KEY  # 응답 id 자리에 키가 온 최악의 경우 — 끝 6자도 보이지 않는다
    code, out, _ = run(["list", "--json"], FakeStudio([agent(key_like_id, "x")], {key_like_id: []}), env_file)
    assert code == 0
    assert json.loads(out)["agents"][0]["id"] == "?" and FAKE_KEY[-6:] not in out


def test_list_still_skips_broken_items(env_file):
    fake = FakeStudio(list_body={"data": [agent(AGENT_ID, NAME), "broken"], "has_more": "true"}, configs={AGENT_ID: []})
    code, out, _ = run(["list"], fake, env_file)
    assert code == 0 and "에이전트 1개" in out


def test_export_unpaired_surrogate_is_short_error(env_file, tmp_path):
    bad = studio_config()
    bad["name"] = "이름" + chr(0xD800)
    out_path = tmp_path / "o.json"
    code, out, err = run(["export", "--agent", NAME, "--config", "1", "--out", str(out_path)],
                         FakeStudio(configs={AGENT_ID: [bad]}), env_file)
    assert code == 2 and out == "" and "서로게이트" in err
    assert not out_path.exists()


def test_unicode_digit_config_number(env_file):
    odd = studio_config(external_id=chr(0x00B2), config_id=CONFIG2_ID, is_default=False)
    code, _, err = run(["show", "--agent", NAME, "--config", "9"], FakeStudio(configs={AGENT_ID: [studio_config(), odd]}), env_file)
    assert code == 2 and "있는 번호: 1, " + chr(0x00B2) in err
    assert sw._number_key(chr(0x00B2)) == (1, 0, chr(0x00B2))


def test_huge_int_config_number_is_none():
    huge = 10 ** 5000  # 글자로 바꿀 수 있는 자릿수 한도를 넘는다
    assert sw.config_number({"external_id": huge}) is None
    assert sw.number_text(huge) is None and sw.number_text(True) is None and sw.number_text(12) == "12"


def bad_next_file(tmp_path: Path) -> Path:
    body = workflow_body()
    body["steps"][0]["next_steps"][0]["step_name"] = ["목록"]
    body["steps"][1]["name"] = {"객체": 1}
    path = tmp_path / "bad-next.json"
    path.write_bytes(json.dumps(body, ensure_ascii=False).encode())
    return path


def test_create_preview_with_non_string_step_name(tmp_path):
    path = bad_next_file(tmp_path)
    for extra in ([], ["--yes"]):
        code, out, err = run(["create", str(path), "--agent", NAME, *extra], None, tmp_path / "none.env")
        assert code == 2 and out == ""
        assert "step_name 이 문자열이 아닙니다" in err and "2번째 step 에 이름이 없습니다" in err


def test_diff_with_non_string_step_name(env_file, tmp_path):
    """R2: 잘못된 로컬 파일은 조회 전에 코드 2(요청 0개, 짧은 문구, traceback 없음)."""
    for extra in ([], ["--json"]):
        code, out, err = run(["diff", "--agent", NAME, "--config", "1", str(bad_next_file(tmp_path)), *extra], None, env_file)
        assert code == 2 and out == ""
        assert "1번째 step 의 next_steps[1].step_name 이 문자열이 아닙니다" in err and "Traceback" not in err


def test_cli_process_has_no_traceback(tmp_path):
    """실제 프로세스로(요청 없는 경로) — 종료 코드 2, 짧은 한국어 문구, traceback 없음."""
    import os
    import subprocess
    import sys

    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    env.pop("UPSTAGE_API_KEY", None)
    done = subprocess.run([sys.executable, str(ROOT / "scripts" / "studio_workflow.py"), "create", str(bad_next_file(tmp_path)),
                           "--agent", NAME], capture_output=True, env=env, timeout=60, cwd=str(tmp_path))
    err = done.stderr.decode("utf-8")
    assert done.returncode == 2 and "Traceback" not in err and "문자열이 아닙니다" in err


# --- T2-fix2: N1·R1·N2·R2 회귀 -------------------------------------------------------


def test_preflight_error_hides_key_from_env_before_settings(tmp_path):
    """N1: 파일 검사 오류가 설정 읽기보다 먼저 나와도 환경 파일·환경변수의 키는 가린다."""
    body = workflow_body()
    body["steps"][0]["next_steps"][0]["step_name"] = "앞 " + FAKE_KEY + " 뒤"
    body["name"] = FAKE_KEY
    path = tmp_path / "preflight.json"
    path.write_bytes(json.dumps(body, ensure_ascii=False).encode())
    env = tmp_path / "k.env"
    env.write_bytes(f"UPSTAGE_API_KEY={FAKE_KEY}\n".encode())
    for extra in ([], ["--yes"], ["--json"]):
        code, out, err = run(["create", str(path), "--agent", NAME, *extra], None, env)
        assert code == 2 and "없는 step 을 가리킵니다" in err
        code, out, err = run(["create", str(path), "--agent", NAME, *extra], None, key=FAKE_KEY)
        assert code == 2


@pytest.mark.parametrize("condition", [
    {"context": QUOTE_KEY},
    {"field": "text", "operator": "==", "value": {"context": QUOTE_KEY}},
    {"field": "text", "operator": "==", "value": [QUOTE_KEY, {"k": QUOTE_KEY}]},
])
def test_condition_objects_are_scrubbed_before_json(condition):
    """R1: 조건 객체·비문자열 조건 값은 값마다 가린 뒤 표시용 JSON 이 된다(디코딩해도 키 없음)."""
    full = studio_config()
    full["steps"][1]["next_steps"][0]["condition"] = condition
    for extra in ([], ["--json"]):
        code, out, _ = run(["show", "--agent", NAME, *extra], FakeStudio(configs={AGENT_ID: [full]}), key=QUOTE_KEY)
        assert code == 0 and "<UPSTAGE_API_KEY>" in out
        assert_clean([out], QUOTE_KEY, "조건")  # 표시용 JSON 문자열까지 다시 풀어서 본다


@pytest.mark.parametrize("text", ["Bearer " + FAKE_KEY, "authorization: Bearer " + FAKE_KEY, "Authorization", "x bearer"])
def test_auth_words_never_remain(env_file, text):
    """N2: 알려진 값을 자리표시자로 바꾼 뒤에도 'Bearer <…>'·홀로 남은 인증 낱말을 통째로 가린다."""
    error = FakeStudio(errors={"GET /agents": httpx.Response(401, json={"error": {"message": text}})})
    code, _, err = run(["list"], error, env_file)
    assert code == 2 and "<REDACTED_AUTH>" in err
    code, out, _ = run(["list", "--json"], FakeStudio([agent(AGENT_ID, text)], {AGENT_ID: []}), env_file)
    assert code == 0 and "<REDACTED_AUTH>" in json.loads(out)["agents"][0]["name"]


def test_condition_display_scrubs_before_serializing_layer_alone():
    """R1 층만 따로: 원문 꼴만 아는 Scrubber 로도 조건 객체·값을 가린다(직렬화가 이스케이프하기 전에 가림)."""
    scrubber = sw.Scrubber()
    scrubber.secrets = {QUOTE_KEY: "<K>"}  # 이스케이프 꼴 등록(다른 층)을 일부러 뺀다
    escaped = json.dumps(QUOTE_KEY)[1:-1]
    head, value = sw._condition_text({"context": QUOTE_KEY}, scrubber)
    assert escaped not in value and QUOTE_KEY not in value and "<K>" in value
    head, value = sw._condition_text({"field": "f", "operator": "==", "value": {"c": QUOTE_KEY}}, scrubber)
    assert escaped not in value and "<K>" in value
    assert escaped not in scrubber.dump([QUOTE_KEY, {QUOTE_KEY: 1}])


def test_output_json_scrubs_each_value_layer_alone():
    """Output.json 층만 따로: 가리지 않은 값이 넘어와도 값마다(키 포함) 가린 뒤 직렬화한다."""
    stdout = io.StringIO()
    out = sw.Output(stdout, io.StringIO(), sw.Scrubber({QUOTE_KEY: "<K>"}))
    out.json({"name": "앞 " + QUOTE_KEY, QUOTE_KEY: ["Bearer " + QUOTE_KEY, UNKNOWN_AGENT]})
    text = stdout.getvalue()
    assert_clean([text], QUOTE_KEY, "Output.json")
    assert json.loads(text)["name"] == "앞 <K>"


def test_scrubber_registers_escaped_and_stripped_forms():
    key = "  Ab" + chr(34) + "Cd" + chr(92) + "Ef1234  "
    scrubber = sw.Scrubber({key: "<K>"})
    for form in (key, key.strip(), json.dumps(key.strip())[1:-1]):
        assert scrubber.scrub("[" + form + "]") == "[<K>]"


# --- T2-fix2: 전수 시험 — 가짜 키·전체 id 를 모든 문자열 칸에 하나씩 넣고 모든 하위 명령을 돈다 -----------

SWEEP_KEYS = (
    "Kq7Zx9Lp3Vb8Nm2Tr6Yc4Wd",  # 보통
    "Qa" + chr(34) + "Rb5Sc6Td7Ue8Vf9Wg",  # 따옴표
    "Hb" + chr(92) + "Jc4Kd5Le6Mf7Ng8Ph",  # 역슬래시
    " " * 40 + "Mn3Bv4Cx5Zl6Kj7Hg" + "\t" * 20,  # 긴 공백 앞뒤(설정에서는 앞뒤를 뺀 값이 키)
)
SPACE_KEY = "Xy4 Zw5Uv6Ts7Rq8Po"  # 가운데 공백 — 헤더로 못 써 설정 오류(2)가 되지만 출력에서는 가려야 한다
SWEEP_IDS = ("agt_Aa1Zz9Yy8Xx7Ww6Vv5Uu4", "cfg_Bb2Tt3Ss4Rr5Qq6Pp7Oo8", "proj_Cc3Nn4Mm5Ll6Kk7Jj8Ii9",
             "file_Dd4Hh5Gg6Ff7Ee8Dd9Cc0", "job_Ee5Bb6Aa7Zz8Yy9Xx0Ww1")
SWEEP_ALL_IDS = SWEEP_IDS + FULL_IDS


def sweep_world() -> dict:
    """가짜 Studio 의 문서 6개(작은 설정 — 조건 객체·비문자열 조건 값 포함)."""
    item = {"id": CONFIG_ID, "name": "설정", "external_id": "1", "is_default": True, "agent_id": AGENT_ID}
    steps = [
        {"id": "st-1", "name": "시작", "type": "document-parse", "data": {"model": "m", "note": "n"},
         "next_steps": [{"step_name": "분류", "condition": None}], "is_first": True, "node_id": "nd_1"},
        {"id": "st-2", "name": "분류", "type": "document-classify", "data": {"text": "t"},
         "next_steps": [{"step_name": "끝", "condition": {"field": "text", "operator": "==", "value": "loan"}},
                        {"step_name": "끝", "condition": {"field": "text", "operator": "==", "value": {"nested": "v", "list": ["w"]}}},
                        {"step_name": "끝", "condition": {"custom": "c", "deep": {"x": "y"}}}],
         "is_first": False, "node_id": "nd_2"},
        {"id": "st-3", "name": "끝", "type": "instruct", "data": {"input": "i"}, "next_steps": [], "is_first": False, "node_id": "nd_3"},
    ]
    one = agent(AGENT_ID, NAME, description="설명")
    return {
        "agents": {"object": "list", "data": [one], "has_more": False, "last_id": AGENT_ID},
        "agent": copy.deepcopy(one),
        "configs": {"data": [item], "has_more": False},
        "config": {**item, "steps": steps},
        "new_agent": {"id": NEW_AGENT_ID, "name": "새", "visibility": "private"},
        "new_config": {"id": NEW_CONFIG_ID, "external_id": "2", "name": "설정", "is_default": True},
    }


def sweep_local() -> dict:
    world = sweep_world()
    return {"name": "설정", "steps": copy.deepcopy(world["config"]["steps"])}


def world_handler(world: dict, errors: dict | None = None):
    """경로 모양만 보고 문서를 돌려준다(id 가 바뀌어도 같은 문서)."""
    def handle(request: httpx.Request) -> httpx.Response:
        parts = request.url.path.removeprefix("/v2").strip("/").split("/")
        route = {("GET", 1): "agents", ("GET", 2): "agent", ("GET", 3): "configs", ("GET", 4): "config",
                 ("POST", 1): "new_agent", ("POST", 3): "new_config"}.get((request.method, len(parts)))
        if route is None:
            return not_found()
        if errors and route in errors:
            err = errors[route]
            if isinstance(err, Exception):
                raise err
            return err
        return raw_json(world[route])
    return handle


def leaves(obj, path=()):
    """모든 문자열 칸의 경로."""
    if isinstance(obj, str):
        yield path
    elif isinstance(obj, dict):
        for key, value in obj.items():
            yield from leaves(value, path + (key,))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            yield from leaves(value, path + (index,))


def put(obj, path, value):
    for step in path[:-1]:
        obj = obj[step]
    obj[path[-1]] = value


def composite(key: str) -> str:
    """키(홀로 'Bearer' 뒤에도)·전체 id 다섯 가지를 한 칸에."""
    return "앞 Bearer " + key + " 가운데 " + key + " " + " ".join(SWEEP_IDS) + " 뒤"


def decoded(text: str, depth: int = 0) -> list[str]:
    """글과, JSON 이면 그 안의 문자열(그 안의 JSON 꼴 문자열도 다시 풀어서)."""
    out = [text]
    stripped = text.strip()
    if depth < 6 and stripped[:1] in ("{", "[", chr(34)):
        try:
            parsed = json.loads(stripped)
        except ValueError:
            return out
        for piece in json_strings(parsed):
            out += decoded(piece, depth + 1)
    return out


def assert_clean(texts: list[str], key: str, label: str) -> None:
    core = key.strip()
    forms = {core, json.dumps(core)[1:-1]}
    # 8자 조각(공백이 둘 이상인 조각은 JSON 들여쓰기와 겹치므로 뺀다)
    pieces = {form[i:i + 8] for form in forms for i in range(len(form) - 7)}
    pieces = {p for p in pieces if sum(c.isspace() for c in p) < 2}
    found = []
    for text in texts:
        for item in decoded(text):
            lower = item.lower()
            if any(form in item for form in forms) or any(p in item for p in pieces):
                found.append("키(또는 8자 조각)")
            if any(full in item for full in SWEEP_ALL_IDS):
                found.append("전체 id")
            if "bearer" in lower or "authorization" in lower:
                found.append("인증 낱말")
            if "traceback" in lower:
                found.append("traceback")
    assert not found, f"{label}: {sorted(set(found))}"


def sweep_run(argv, handler, key: str, env_mode: str, tmp: Path, label: str) -> int:
    """명령 하나. env_mode 'file' 은 tmp/sweep.env(sweep_all 이 한 번 쓴다), 'environ' 은 환경변수로 키를 준다."""
    stdout, stderr = io.StringIO(), io.StringIO()
    args = list(argv)
    if env_mode == "file":
        env = tmp / "sweep.env"
        environ = {}
    else:
        env = tmp / "absent.env"
        environ = {"UPSTAGE_API_KEY": key, "UPSTAGE_PROJECT_ID": FAKE_PROJECT}
    try:
        code = sw.main(args + ["--env-file", str(env)], transport=httpx.MockTransport(handler),
                       stdout=stdout, stderr=stderr, environ=environ)
    except Exception as exc:  # 처리 안 된 예외 = 실패(traceback 이 나갔을 경로)
        raise AssertionError(f"{label}: 처리 안 된 예외 {type(exc).__name__}") from None
    assert code in (0, 1, 2), f"{label}: 종료 코드 {code}"
    assert_clean([stdout.getvalue(), stderr.getvalue()], key, label)
    return code


def sweep_commands(tmp: Path, local: Path) -> list[list[str]]:
    return [
        ["list"],
        ["show", "--agent", NAME],
        ["show", "--agent", NAME, "--config", "1"],
        ["export", "--agent", NAME, "--config", "1", "--out", str(tmp / "exported.json")],
        ["diff", "--agent", NAME, "--config", "1", str(local)],
        ["create", str(local), "--agent", NAME],
        ["create", str(local), "--agent", NAME, "--yes"],
        ["create", str(local), "--agent", "새_워크플로우", "--yes"],
    ]


def routes_served(argv: list[str], tmp: Path) -> frozenset[str]:
    """기본 세계에서 그 명령이 받아 가는 문서 종류(자동 계산)."""
    served: set[str] = set()
    base = world_handler(sweep_world())

    def record(request: httpx.Request) -> httpx.Response:
        parts = request.url.path.removeprefix("/v2").strip("/").split("/")
        served.add({("GET", 1): "agents", ("GET", 2): "agent", ("GET", 3): "configs", ("GET", 4): "config",
                    ("POST", 1): "new_agent", ("POST", 3): "new_config"}[(request.method, len(parts))])
        return base(request)

    sw.main(argv + ["--env-file", str(tmp / "absent.env")], transport=httpx.MockTransport(record),
            stdout=io.StringIO(), stderr=io.StringIO(), environ={"UPSTAGE_API_KEY": FAKE_KEY})
    return frozenset(served)


def sweep_all(world: dict, local_body: dict, key: str, tmp: Path, label: str, errors: dict | None = None,
              only: str | None = None, routes: list | None = None) -> int:
    """하위 명령 × (--json 있음·없음) × (환경 파일·환경변수). 돈 횟수를 돌려준다.

    only='<문서 종류>' 면 기본 세계에서 그 문서를 받아 가는 명령만 돈다(받지 않는 명령은 그 문서를 출력할 수 없다).
    'local' 이면 로컬 파일을 읽는 명령(diff·create)만.
    """
    local = tmp / "local.json"
    local.write_bytes(json.dumps(local_body, ensure_ascii=False).encode())
    (tmp / "sweep.env").write_bytes(("UPSTAGE_API_KEY=" + key + "\nUPSTAGE_PROJECT_ID=" + FAKE_PROJECT + "\n").encode())
    count = 0
    for index, argv in enumerate(sweep_commands(tmp, local)):
        if only == "local" and argv[0] not in ("diff", "create"):
            continue
        if only not in (None, "local") and only not in (routes or [])[index]:
            continue
        for extra in ([], ["--json"]):
            for env_mode in ("file", "environ"):
                sweep_run(argv + extra, world_handler(world, errors), key, env_mode, tmp, f"{label} {argv[0]} {extra} {env_mode}")
                count += 1
    return count


def direct_client(world: dict, key: str, label: str, errors: dict | None = None) -> None:
    """클라이언트를 직접 쓸 때의 예외 문구도 같은 검사."""
    with sw.StudioClient(key.strip(), FAKE_PROJECT, transport=httpx.MockTransport(world_handler(world, errors))) as client:
        calls = (client.list_agents, lambda: client.list_agents(strict=True), lambda: client.get_agent(AGENT_ID),
                 lambda: client.list_configs(AGENT_ID), lambda: client.get_config(AGENT_ID, CONFIG_ID),
                 lambda: client.create_agent("새"), lambda: client.create_config(AGENT_ID, {"name": "x", "steps": []}))
        for call in calls:
            try:
                call()
            except sw.StudioError as exc:
                assert_clean([str(exc), exc.message, repr(exc)], key, label + " 직접 클라이언트")


WORLD_LEAVES = [(doc,) + path for doc, value in sweep_world().items() for path in leaves(value)]
LOCAL_LEAVES = list(leaves(sweep_local()))


@pytest.fixture(scope="module")
def routes(tmp_path_factory) -> list:
    """명령(sweep_commands 순서)마다 기본 세계에서 받아 가는 문서 종류 — 한 번만 계산한다."""
    tmp = tmp_path_factory.mktemp("routes")
    local = tmp / "local.json"
    local.write_bytes(json.dumps(sweep_local(), ensure_ascii=False).encode())
    return [routes_served(argv, tmp) for argv in sweep_commands(tmp, local)]


@pytest.mark.parametrize("leaf", WORLD_LEAVES, ids=lambda p: "/".join(map(str, p)))
def test_sweep_response_fields(leaf, tmp_path, routes):
    """가짜 응답의 문자열 칸 하나에 키·전체 id(합친 글)와 키 그대로를 넣고 모든 명령을 돈다."""
    key = SWEEP_KEYS[WORLD_LEAVES.index(leaf) % len(SWEEP_KEYS)]
    runs = 0
    for value in (composite(key), key):
        world = sweep_world()
        put(world, leaf, value)
        runs += sweep_all(world, sweep_local(), key, tmp_path, "/".join(map(str, leaf)), only=leaf[0], routes=routes)
        direct_client(world, key, "/".join(map(str, leaf)))
    assert runs >= 2 * 2 * 2  # 그 문서를 받아 가는 명령이 적어도 하나


@pytest.mark.parametrize("leaf", LOCAL_LEAVES, ids=lambda p: "local/" + "/".join(map(str, p)))
def test_sweep_local_file_fields(leaf, tmp_path):
    """로컬 설정 파일의 문자열 칸 하나에 넣는다(공백 든 키 포함 — 설정 오류 경로에서도 가린다)."""
    keys = SWEEP_KEYS + (SPACE_KEY,)
    key = keys[LOCAL_LEAVES.index(leaf) % len(keys)]
    for value in (composite(key), key):
        local = sweep_local()
        put(local, leaf, value)
        runs = sweep_all(sweep_world(), local, key, tmp_path, "local/" + "/".join(map(str, leaf)), only="local")
        assert runs == 4 * 2 * 2  # diff·create(미리보기·있는 에이전트·새 에이전트)


ERROR_BODIES = {
    "message+code": lambda v: {"error": {"message": v, "code": v}},
    "code": lambda v: {"error": {"code": v}},
    "error-str": lambda v: {"error": v},
    "message": lambda v: {"message": v},
    "detail": lambda v: {"detail": v},
}


@pytest.mark.parametrize("route", ["agents", "agent", "configs", "config", "new_agent", "new_config"])
@pytest.mark.parametrize("shape", sorted(ERROR_BODIES))
def test_sweep_error_bodies(route, shape, tmp_path, routes):
    """오류 본문의 message·code·detail(그리고 error 문자열)에 넣는다 — 명령 출력과 직접 클라이언트 예외."""
    key = SWEEP_KEYS[(len(route) + len(shape)) % len(SWEEP_KEYS)]
    for status in (400, 500):
        for value in (composite(key), "Authorization: Bearer " + key.strip()):
            errors = {route: httpx.Response(status, json=ERROR_BODIES[shape](value))}
            assert sweep_all(sweep_world(), sweep_local(), key, tmp_path, f"{route}/{shape}/{status}", errors,
                             only=route, routes=routes) >= 4
            direct_client(sweep_world(), key, f"{route}/{shape}/{status}", errors)


def test_sweep_transport_exception_text(tmp_path, routes):
    """연결 오류 예외 문구에 키·id 가 있어도 출력에는 형식 이름만."""
    key = SWEEP_KEYS[1]
    errors = {"agents": httpx.ConnectError(composite(key))}
    assert sweep_all(sweep_world(), sweep_local(), key, tmp_path, "connect-error", errors, only="agents", routes=routes) >= 4 * 7
    direct_client(sweep_world(), key, "connect-error", errors)


def test_sweep_counts(routes):
    """전수 시험의 범위 — 칸 수가 줄거나 어떤 문서도 받아 가지 않는 명령 구성이면 시험이 약해진 것이다."""
    assert len(WORLD_LEAVES) >= 55 and len(LOCAL_LEAVES) >= 25
    served = set().union(*routes)
    assert served == {"agents", "agent", "configs", "config", "new_agent", "new_config"}
    assert routes[5] == frozenset()  # 미리보기는 요청 0개


# --- T2-fix3: 명령줄 해석 오류(R3) — 실제 프로세스로 돌려 프로세스의 stdout·stderr·종료 코드를 본다 ------------

CLI_BASES = {
    "list": ["list"],
    "show": ["show", "--agent", NAME],
    "export": ["export", "--agent", NAME, "--config", "1", "--out", "exported.json"],
    "diff": ["diff", "--agent", NAME, "--config", "1", "local.json"],
    "create": ["create", "local.json", "--agent", NAME],
}
# 잘못된 인자 꼴(키를 명령줄에 넣는다) — 'missing-value' 는 --env-file 바로 뒤가 다른 옵션이라 값이 빠진 꼴
CLI_BAD_FORMS = {
    "unknown-option": lambda base, key: base + ["--unrecognized", key],
    "api-key": lambda base, key: base + ["--api-key", key],
    "extra-arg": lambda base, key: base + [key],
    "unknown-subcommand": lambda base, key: [key] + base[1:],
    "missing-value": lambda base, key: base + ["--env-file", "--json", key],
}


def cli_process(argv: list[str], key: str, env_mode: str, tmp: Path):
    """스크립트를 새 프로세스로 실행 — (종료 코드, stdout, stderr). 키는 환경 파일 또는 환경변수로 준다."""
    import os
    import subprocess
    import sys

    env = {k: v for k, v in os.environ.items() if not k.startswith("UPSTAGE_")}
    env.update({"PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"})
    if env_mode == "environ":
        env.update({"UPSTAGE_API_KEY": key, "UPSTAGE_PROJECT_ID": FAKE_PROJECT})
    else:
        envfile = tmp / "cli.env"
        envfile.write_bytes(("UPSTAGE_API_KEY=" + key + "\nUPSTAGE_PROJECT_ID=" + FAKE_PROJECT + "\n").encode())
        argv = argv[:1] + ["--env-file", str(envfile)] + argv[1:]
    done = subprocess.run([sys.executable, str(ROOT / "scripts" / "studio_workflow.py"), *argv], cwd=str(tmp),
                          env=env, capture_output=True, timeout=120)
    return done.returncode, done.stdout.decode("utf-8", "replace"), done.stderr.decode("utf-8", "replace")


@pytest.mark.parametrize("form", sorted(CLI_BAD_FORMS))
def test_cli_parse_errors_never_quote_arguments(form, tmp_path):
    """R3: 다섯 하위 명령 × (--json 있음·없음) × (환경 파일·환경변수) — 프로세스 출력에 키·8자 조각·Bearer·traceback 없음."""
    from concurrent.futures import ThreadPoolExecutor

    key = SWEEP_KEYS[sorted(CLI_BAD_FORMS).index(form) % 3]  # 보통·따옴표·역슬래시 키를 돌려 쓴다
    cases = []
    for name, base in CLI_BASES.items():
        for extra in ([], ["--json"]):
            for env_mode in ("file", "environ"):
                folder = tmp_path / f"{name}-{bool(extra)}-{env_mode}"
                folder.mkdir()
                cases.append((f"{form} {name} json={bool(extra)} {env_mode}", CLI_BAD_FORMS[form](base + extra, key), env_mode, folder))
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda c: (c[0], cli_process(c[1], key, c[2], c[3])), cases))
    assert len(results) == 20
    for label, (code, out, err) in results:
        assert code == 2, f"{label}: 종료 코드 {code}"
        assert "--help 를 보세요" in err and out == "", label
        assert_clean([out, err], key, label)  # 키 원문·이스케이프 꼴·8자 조각·전체 id·인증 낱말·traceback


def test_cli_help_is_unchanged(tmp_path):
    """--help 는 그대로(종료 코드 0, 표준 출력에 usage)."""
    for argv in (["--help"], ["list", "--help"], ["diff", "-h"]):
        code, out, err = cli_process(argv, SWEEP_KEYS[0], "environ", tmp_path)
        assert code == 0 and out.startswith("usage: studio_workflow.py") and err == ""


def test_cli_parse_error_goes_through_given_stream(tmp_path, capfd):
    """main 을 직접 불러도 해석 오류는 넘겨준 stderr 로만(프로세스 stderr 에는 아무것도 안 씀), 받은 값 없이."""
    stdout, stderr = io.StringIO(), io.StringIO()
    code = sw.main(["list", "--api-key", FAKE_KEY], stdout=stdout, stderr=stderr, environ={"UPSTAGE_API_KEY": FAKE_KEY})
    process = capfd.readouterr()
    assert code == 2 and stdout.getvalue() == "" and process.out == "" and process.err == ""
    assert stderr.getvalue() == "오류: 알 수 없는 옵션이나 인자가 있습니다 — --help 를 보세요\n"
    for message in ("unrecognized arguments: x", "argument command: invalid choice: 'x'", "expected one argument",
                    "the following arguments are required: --agent", "ambiguous option: --a", "다른 문구 x"):
        assert "x" not in sw.CliUsageError(message).message.replace("--help", "")
