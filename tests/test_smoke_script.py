# ==========================================================================
#  scripts/upstage_smoke.py 흐름 테스트 — 가짜 Upstage 서버(httpx.MockTransport)로
#  올리기 → 작업 만들기 → 조회 반복 → 전체 저장 → 파일 삭제·확인 순서와 종료 코드를 본다.
#  실패·오류·Ctrl+C 에서도 파일을 지우는지 확인한다. 네트워크·.env 는 쓰지 않는다.
# ==========================================================================

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import httpx
import pytest
from fake_responses import build_response

from imask_backend import upstage as upstage_module

ROOT = Path(__file__).resolve().parent.parent
FAKE_ENV = {"UPSTAGE_API_KEY": "fake-key-zzz", "UPSTAGE_AGENT_ID": "fake-agent", "UPSTAGE_CONFIG_ID": "3"}
FAKE_KEY = FAKE_ENV["UPSTAGE_API_KEY"]
FAKE_AGENT = FAKE_ENV["UPSTAGE_AGENT_ID"]
# 서버가 키·에이전트 id·인증 헤더를 되돌려 보내는 최악의 경우
LEAKY = f"Authorization: Bearer {FAKE_KEY}; agent={FAKE_AGENT}"


def assert_no_secret(text: str) -> None:
    assert FAKE_KEY not in text
    assert FAKE_AGENT not in text
    assert "authorization" not in text.lower()
    assert "bearer" not in text.lower()


def load_script():
    spec = importlib.util.spec_from_file_location("upstage_smoke", ROOT / "scripts" / "upstage_smoke.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeUpstage:
    """요청을 기록하고, 조회할 때마다 statuses 를 차례로 돌려주는 가짜 서버."""

    def __init__(
        self,
        statuses,
        full_response,
        *,
        poll_error=None,
        delete_response=None,
        keep_file=False,
        create_response=None,
        failure_body=None,
        interrupt_on_check=False,
    ):
        self.statuses = list(statuses)
        self.full_response = full_response
        self.poll_error = poll_error
        self.delete_response = delete_response
        self.keep_file = keep_file
        self.create_response = create_response
        self.failure_body = failure_body
        self.interrupt_on_check = interrupt_on_check
        self.calls: list[str] = []
        self.deleted = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/v2")
        key = f"{request.method} {path}"
        if request.url.query:
            key += "?" + request.url.query.decode()
        self.calls.append(key)
        if key == "POST /files":
            return httpx.Response(200, json={"id": "file-1"})
        if key == "POST /responses":
            if self.create_response is not None:
                return self.create_response
            return httpx.Response(200, json={"id": "resp_1", "status": "queued"})
        if key == "GET /responses/resp_1?include[]=last":
            if self.poll_error is not None:
                return self.poll_error
            status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
            body = {"id": "resp_1", "status": status}
            if status == "failed":
                body.update(self.failure_body or {"error": {"message": "가짜 실패"}})
            return httpx.Response(200, json=body)
        if key == "GET /responses/resp_1?include[]=all":
            return httpx.Response(200, json=self.full_response)
        if key == "DELETE /files/file-1":
            if self.delete_response is not None:
                return self.delete_response
            self.deleted = not self.keep_file
            return httpx.Response(200, json={"id": "file-1", "deleted": True})
        if key == "GET /files/file-1":
            if self.interrupt_on_check:
                raise KeyboardInterrupt
            return httpx.Response(404 if self.deleted else 200, json={})
        return httpx.Response(500, json={"error": {"message": f"unexpected {key}"}})


@pytest.fixture
def script(monkeypatch):
    module = load_script()
    monkeypatch.setattr(module, "_read_env", lambda root: dict(FAKE_ENV))
    monkeypatch.setattr(module.time, "sleep", lambda s: None)
    return module


def use_fake(monkeypatch, module, fake):
    real = upstage_module.UpstageClient

    def factory(api_key, base_url, **kwargs):
        return real(api_key, base_url, transport=httpx.MockTransport(fake))

    monkeypatch.setattr(module, "UpstageClient", factory)


def args_for(module, tmp_path, *extra):
    return [
        "--file", str(ROOT / "testdocs" / "iMASK_smoke_bundle.pdf"),
        "--interval", "0.01",
        "--timeout", "30",
        "--out-dir", str(tmp_path / "out"),
        *extra,
    ]


EXPECTED_TYPES = ("loan_application", "consent_form", "income_proof", "power_of_attorney", "debt_transaction", "Other")


def test_completed_flow_saves_full_response_and_deletes_file(script, monkeypatch, tmp_path, capsys):
    full = build_response(types=EXPECTED_TYPES)
    full["model"] = FAKE_ENV["UPSTAGE_AGENT_ID"]  # 실제 응답은 최상위 model 에 에이전트 id 를 되돌려 준다
    fake = FakeUpstage(["in_progress", "in_progress", "completed"], full)
    use_fake(monkeypatch, script, fake)

    code = script.main(args_for(script, tmp_path))

    out = capsys.readouterr().out
    # 기대값(서류 6·추출 5·위험도 상·권장_조치·기타 1)과 모두 같으므로 0
    assert code == 0, out
    assert "결과: 일치" in out
    assert fake.calls[0] == "POST /files"
    assert fake.calls[1] == "POST /responses"
    assert "GET /responses/resp_1?include[]=all" in fake.calls
    assert fake.calls[-2:] == ["DELETE /files/file-1", "GET /files/file-1"]
    saved = list((tmp_path / "out").glob("*_resp_1.json"))
    assert len(saved) == 1
    saved_text = saved[0].read_text(encoding="utf-8")
    assert FAKE_ENV["UPSTAGE_AGENT_ID"] not in saved_text
    assert FAKE_ENV["UPSTAGE_API_KEY"] not in saved_text
    assert json.loads(saved_text) == {**full, "model": "<UPSTAGE_AGENT_ID>"}
    assert "상태 queued → in_progress" in out
    assert "상태 in_progress → completed" in out
    assert out.count("상태 in_progress → in_progress") == 0
    assert "삭제 확인: 확인됨" in out
    assert "fake-key-zzz" not in out
    assert "fake-agent" not in out


def test_completed_but_different_values_exits_2(script, monkeypatch, tmp_path, capsys):
    fake = FakeUpstage(["completed"], build_response(types=EXPECTED_TYPES, risk="중"))
    use_fake(monkeypatch, script, fake)

    code = script.main(args_for(script, tmp_path))

    out = capsys.readouterr().out
    assert code == 2
    assert "불일치 위험도: 기대 상 / 실제 중" in out
    assert fake.deleted


@pytest.mark.parametrize(
    "fake_kwargs",
    [
        {"delete_response": httpx.Response(500, json={"error": {"message": "boom"}})},
        {"keep_file": True},  # 삭제 요청은 성공했지만 조회하면 아직 있다
    ],
)
def test_cleanup_failure_turns_success_into_exit_1(script, monkeypatch, tmp_path, capsys, fake_kwargs):
    fake = FakeUpstage(["completed"], build_response(types=EXPECTED_TYPES), **fake_kwargs)
    use_fake(monkeypatch, script, fake)

    code = script.main(args_for(script, tmp_path))

    out = capsys.readouterr().out
    assert "결과: 일치" in out
    assert code == 1


def test_failed_job_exits_1_and_deletes_file(script, monkeypatch, tmp_path, capsys):
    fake = FakeUpstage(["failed"], {})
    use_fake(monkeypatch, script, fake)

    code = script.main(args_for(script, tmp_path))

    out = capsys.readouterr().out
    assert code == 1
    assert "가짜 실패" in out
    assert "GET /responses/resp_1?include[]=all" not in fake.calls
    assert fake.deleted


def test_client_error_while_polling_still_deletes_file(script, monkeypatch, tmp_path, capsys):
    fake = FakeUpstage(["in_progress"], {}, poll_error=httpx.Response(403, json={"error": {"message": "no"}}))
    use_fake(monkeypatch, script, fake)

    code = script.main(args_for(script, tmp_path))

    assert code == 1
    assert fake.deleted
    assert "HTTP 403" in capsys.readouterr().out


def test_timeout_still_deletes_file(script, monkeypatch, tmp_path):
    fake = FakeUpstage(["in_progress"], {})
    use_fake(monkeypatch, script, fake)
    clock = iter(range(0, 10_000, 20))
    monkeypatch.setattr(script.time, "monotonic", lambda: next(clock))

    code = script.main(args_for(script, tmp_path))

    assert code == 1
    assert fake.deleted


def test_ctrl_c_still_deletes_file(script, monkeypatch, tmp_path, capsys):
    fake = FakeUpstage(["in_progress"], {})
    use_fake(monkeypatch, script, fake)

    def interrupt(seconds):
        raise KeyboardInterrupt

    monkeypatch.setattr(script.time, "sleep", interrupt)

    code = script.main(args_for(script, tmp_path))

    assert code == 1
    assert fake.deleted
    assert "중단" in capsys.readouterr().out


def test_missing_config_id_does_not_call_upstage(script, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(script, "_read_env", lambda root: {**FAKE_ENV, "UPSTAGE_CONFIG_ID": ""})
    fake = FakeUpstage(["completed"], {})
    use_fake(monkeypatch, script, fake)

    code = script.main(args_for(script, tmp_path))

    assert code == 1
    assert fake.calls == []
    assert "UPSTAGE_CONFIG_ID" in capsys.readouterr().out


def test_redact_secrets_walks_nested_values(script):
    secrets = {"sek-1234": "<K>", "agt-5678": "<A>"}
    value = {
        "model": "agt-5678",
        "list": ["x-sek-1234-y", 1, None, "Authorization: Bearer sek-1234"],
        "nested": {"agt-5678": "ok"},
    }
    assert script.redact_secrets(value, secrets) == {
        "model": "<A>",
        "list": ["x-<K>-y", 1, None, "<REDACTED_AUTH>"],
        "nested": {"<A>": "ok"},
    }


# --- M1: 실패·오류 출력과 저장 파일의 가림 -------------------------------------------------


def test_failed_job_hides_secrets_everywhere(script, monkeypatch, tmp_path, capsys):
    fake = FakeUpstage(
        ["failed"],
        {},
        failure_body={"error": {"message": LEAKY, "code": LEAKY}, "incomplete_details": {"reason": LEAKY}},
    )
    use_fake(monkeypatch, script, fake)

    code = script.main(args_for(script, tmp_path))

    captured = capsys.readouterr()
    assert code == 1
    assert fake.deleted
    assert "이유: <REDACTED_AUTH>; agent=<UPSTAGE_AGENT_ID>" in captured.out
    assert_no_secret(captured.out)
    assert_no_secret(captured.err)
    (saved,) = (tmp_path / "out").glob("*_resp_1.json")
    assert_no_secret(saved.read_text(encoding="utf-8"))


def test_failed_job_with_only_incomplete_details(script, monkeypatch, tmp_path, capsys):
    fake = FakeUpstage(["failed"], {}, failure_body={"incomplete_details": LEAKY})
    use_fake(monkeypatch, script, fake)

    assert script.main(args_for(script, tmp_path)) == 1

    captured = capsys.readouterr()
    assert "이유: <REDACTED_AUTH>" in captured.out
    assert_no_secret(captured.out + captured.err)


@pytest.mark.parametrize("status", [401, 500])
def test_http_error_on_create_job_hides_secrets(script, monkeypatch, tmp_path, capsys, status):
    fake = FakeUpstage(["completed"], {}, create_response=httpx.Response(status, json={"error": {"message": LEAKY}}))
    use_fake(monkeypatch, script, fake)

    code = script.main(args_for(script, tmp_path))

    captured = capsys.readouterr()
    assert code == 1
    assert fake.deleted
    assert f"HTTP {status}" in captured.out
    assert_no_secret(captured.out + captured.err)


def test_normal_summary_output_is_redacted_too(script, monkeypatch, tmp_path, capsys):
    full = build_response(types=EXPECTED_TYPES)
    full["model"] = FAKE_AGENT
    full["output"][0]["model"] = "step_1_parse " + LEAKY  # 응답 문자열이 그대로 찍히는 길도 가린다
    fake = FakeUpstage(["completed"], full)
    use_fake(monkeypatch, script, fake)

    script.main(args_for(script, tmp_path))

    captured = capsys.readouterr()
    assert "<REDACTED_AUTH>" in captured.out
    assert_no_secret(captured.out + captured.err)
    (saved,) = (tmp_path / "out").glob("*_resp_1.json")
    assert_no_secret(saved.read_text(encoding="utf-8"))


def test_unexpected_error_is_short_and_redacted(script, monkeypatch, tmp_path, capsys):
    fake = FakeUpstage(["completed"], build_response(types=EXPECTED_TYPES))
    use_fake(monkeypatch, script, fake)

    def boom(response):
        raise RuntimeError(LEAKY)

    monkeypatch.setattr(script, "print_summary", boom)

    code = script.main(args_for(script, tmp_path))

    captured = capsys.readouterr()
    assert code == 1
    assert fake.deleted
    assert "예상치 못한 오류(RuntimeError" in captured.out
    assert_no_secret(captured.out + captured.err)


def test_unexpected_multiline_long_error_is_one_capped_line(script, monkeypatch, tmp_path, capsys):
    fake = FakeUpstage(["completed"], build_response(types=EXPECTED_TYPES))
    use_fake(monkeypatch, script, fake)

    def boom(response):
        raise RuntimeError("첫 줄\n" + "x" * 1500 + "\r\n둘째 줄 " + LEAKY + "\n" + FAKE_KEY)

    monkeypatch.setattr(script, "print_summary", boom)

    code = script.main(args_for(script, tmp_path))

    captured = capsys.readouterr()
    assert code == 1
    assert fake.deleted  # finally 삭제는 그대로
    lines = [line for line in captured.out.splitlines() if "예상치 못한 오류" in line]
    assert len(lines) == 1  # 개행이 공백으로 바뀌어 한 줄
    line = lines[0]
    # 시각 접두 '[  0.0s] ' 를 뺀 진단은 300자 이하(가림 뒤에 자름)
    diagnostic = line.split("] ", 1)[1]
    assert len(diagnostic) <= 300
    assert diagnostic.endswith("…")
    assert "첫 줄 xxx" in diagnostic
    assert_no_secret(captured.out + captured.err)


def test_saved_json_text_with_authorization_key_stays_parseable(script, tmp_path):
    extract_text = json.dumps(
        {"Authorization": f"Bearer {FAKE_KEY}", "applicant_name": "가짜 이름", "applicant_rrn": ""},
        ensure_ascii=False,
    )
    raw = {
        "id": "resp_1",
        "status": "completed",
        "model": FAKE_AGENT,
        "output": [
            {"model": "Information Extract - 민감정보_추출", "status": "completed", "content": [{"text": extract_text}]}
        ],
    }
    secrets = {FAKE_KEY: "<UPSTAGE_API_KEY>", FAKE_AGENT: "<UPSTAGE_AGENT_ID>"}

    saved = script._save(tmp_path / "out", "resp_1", raw, secrets)

    text = saved.read_text(encoding="utf-8")
    assert_no_secret_values(text)
    reread = json.loads(text)
    inner = json.loads(reread["output"][0]["content"][0]["text"])  # 안쪽 JSON 도 그대로 풀린다
    assert inner == {"Authorization": "<REDACTED_AUTH>", "applicant_name": "가짜 이름", "applicant_rrn": ""}
    assert script.summarize(reread) == script.summarize(raw)
    assert script.summarize(reread)["extracted_document_count"] == 1


def assert_no_secret_values(text: str) -> None:
    assert FAKE_KEY not in text
    assert FAKE_AGENT not in text


# --- m3: 삭제 확인 중 Ctrl+C -------------------------------------------------------------


def test_ctrl_c_during_delete_verification(script, monkeypatch, tmp_path, capsys):
    fake = FakeUpstage(["completed"], build_response(types=EXPECTED_TYPES), interrupt_on_check=True)
    use_fake(monkeypatch, script, fake)

    code = script.main(args_for(script, tmp_path))  # KeyboardInterrupt 가 밖으로 나오지 않는다

    out = capsys.readouterr().out
    assert code == 1
    assert fake.deleted
    assert fake.calls[-2:] == ["DELETE /files/file-1", "GET /files/file-1"]
    assert "삭제 확인 중 중단" in out
    assert "결과: 일치" in out


def test_cleanup_returns_false_when_check_is_interrupted(script, capsys):
    class Interrupting:
        def delete_file(self, file_id):
            return True

        def file_exists(self, file_id):
            raise KeyboardInterrupt

    assert script._cleanup(Interrupting(), "file-x", script.time.monotonic()) is False
    assert "삭제 확인 못 함" in capsys.readouterr().out


def test_summarize_only_reads_saved_file(script, tmp_path, capsys):
    path = tmp_path / "saved.json"
    path.write_text(json.dumps({"id": "resp_1", "status": "completed", "output": []}), encoding="utf-8")

    code = script.main(["--summarize-only", str(path)])

    assert code == 2
    assert "(output 이 비었습니다)" in capsys.readouterr().out
