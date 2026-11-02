# ==========================================================================
#  UpstageClient 요청 모양 테스트 — httpx.MockTransport 로 네트워크 없이 확인한다.
#  가짜 키(FAKE_KEY)가 오류 메시지·repr 에 섞이지 않는지도 본다.
# ==========================================================================

from __future__ import annotations

import json

import httpx
import pytest

from imask_backend.config import UpstageSettings
from imask_backend.upstage import (
    UpstageClient,
    UpstageError,
    is_success,
    is_terminal,
    job_failure_message,
)

FAKE_KEY = "up-test-FAKE-KEY-0123456789"
FAKE_AGENT = "agent-test-FAKE-ID-4242"
BASE = "https://api.upstage.ai/v2"
LEAKY = f"Authorization: Bearer {FAKE_KEY}; invalid agent {FAKE_AGENT}"


def assert_no_secret(text: str) -> None:
    assert FAKE_KEY not in text
    assert FAKE_AGENT not in text
    assert "authorization" not in text.lower()
    assert "bearer" not in text.lower()


def assert_error_clean(exc: UpstageError) -> None:
    for text in (str(exc), repr(exc), exc.message, *map(str, exc.args)):
        assert_no_secret(text)


def make_client(handler) -> tuple[UpstageClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        request.read()
        seen.append(request)
        return handler(request)

    return UpstageClient(FAKE_KEY, BASE, transport=httpx.MockTransport(wrapped)), seen


def test_upload_file_sends_multipart_with_purpose_user_data():
    client, seen = make_client(lambda r: httpx.Response(200, json={"id": "file-abc", "object": "file"}))
    file_id = client.upload_file("bundle.pdf", b"%PDF-1.7 fake", "application/pdf")

    assert file_id == "file-abc"
    (req,) = seen
    assert req.method == "POST"
    assert str(req.url) == f"{BASE}/files"
    assert req.headers["authorization"] == f"Bearer {FAKE_KEY}"
    assert req.headers["content-type"].startswith("multipart/form-data; boundary=")
    body = req.content
    assert b'name="purpose"\r\n\r\nuser_data\r\n' in body
    assert b'name="file"; filename="bundle.pdf"' in body
    assert b"Content-Type: application/pdf" in body
    assert b"%PDF-1.7 fake" in body


def test_upload_file_without_id_is_error():
    client, _ = make_client(lambda r: httpx.Response(200, json={"object": "file"}))
    with pytest.raises(UpstageError):
        client.upload_file("a.pdf", b"x", "application/pdf")


def test_create_job_body_matches_brief():
    client, seen = make_client(lambda r: httpx.Response(200, json={"id": "resp_1", "status": "queued"}))
    job = client.create_job("agent-xyz", "3", "file-abc")

    assert job == {"id": "resp_1", "status": "queued"}
    (req,) = seen
    assert req.method == "POST"
    assert str(req.url) == f"{BASE}/responses"
    body = json.loads(req.content)
    assert body["model"] == "agent-xyz"
    assert body["config_id"] == "3"
    assert body["include"] == ["all"]
    assert body["input"] == [
        {"role": "user", "content": [{"type": "input_file", "file_id": "file-abc"}]}
    ]
    assert set(body) == {"model", "config_id", "include", "input"}


@pytest.mark.parametrize("config_id", ["", " ", "\t", " \t \n", None, 3])
def test_create_job_refuses_blank_config_id(config_id):
    client, seen = make_client(lambda r: httpx.Response(200, json={"id": "x"}))
    with pytest.raises(ValueError):
        client.create_job("agent-xyz", config_id, "file-abc")  # type: ignore[arg-type]
    assert seen == []  # 요청을 하나도 보내지 않았다


@pytest.mark.parametrize("agent_id", ["", "  ", None])
def test_create_job_refuses_blank_agent_id(agent_id):
    client, seen = make_client(lambda r: httpx.Response(200, json={"id": "x"}))
    with pytest.raises(ValueError):
        client.create_job(agent_id, "3", "file-abc")  # type: ignore[arg-type]
    assert seen == []


def test_create_job_strips_config_id():
    client, seen = make_client(lambda r: httpx.Response(200, json={"id": "resp_1", "status": "queued"}))
    client.create_job("agent-xyz", " 3 ", "file-abc")
    assert json.loads(seen[0].content)["config_id"] == "3"


@pytest.mark.parametrize("include", ["last", "all"])
def test_get_job_include_query(include):
    client, seen = make_client(lambda r: httpx.Response(200, json={"id": "resp_1", "status": "in_progress"}))
    job = client.get_job("resp_1", include)

    assert job["status"] == "in_progress"
    (req,) = seen
    assert req.method == "GET"
    assert req.url.path == "/v2/responses/resp_1"
    assert req.url.params.get_list("include[]") == [include]
    # 안내 문서처럼 대괄호를 그대로 보낸다
    assert req.url.query.decode() == f"include[]={include}"


def test_get_job_rejects_other_include():
    client, seen = make_client(lambda r: httpx.Response(200, json={}))
    with pytest.raises(ValueError):
        client.get_job("resp_1", "everything")  # type: ignore[arg-type]
    assert seen == []


def test_get_job_quotes_job_id_in_path():
    client, seen = make_client(lambda r: httpx.Response(200, json={"id": "a/b"}))
    client.get_job("a/b", "last")
    assert seen[0].url.raw_path.startswith(b"/v2/responses/a%2Fb?")


def test_delete_file_path_and_result():
    client, seen = make_client(lambda r: httpx.Response(200, json={"id": "file-abc", "deleted": True}))
    assert client.delete_file("file-abc") is True
    (req,) = seen
    assert req.method == "DELETE"
    assert str(req.url) == f"{BASE}/files/file-abc"


def test_delete_file_404_counts_as_deleted():
    client, _ = make_client(lambda r: httpx.Response(404, json={"error": {"message": "not found"}}))
    assert client.delete_file("file-gone") is True


def test_delete_file_deleted_false():
    client, _ = make_client(lambda r: httpx.Response(200, json={"deleted": False}))
    assert client.delete_file("file-abc") is False


def test_delete_file_server_error_raises():
    client, _ = make_client(lambda r: httpx.Response(500, json={"error": {"message": "boom"}}))
    with pytest.raises(UpstageError) as info:
        client.delete_file("file-abc")
    assert info.value.status_code == 500


@pytest.mark.parametrize(("status", "expected"), [(200, True), (404, False), (405, None), (500, None)])
def test_file_exists(status, expected):
    client, seen = make_client(lambda r: httpx.Response(status, json={}))
    assert client.file_exists("file-abc") is expected
    assert seen[0].method == "GET"
    assert seen[0].url.path == "/v2/files/file-abc"


def test_file_exists_connection_error_is_none():
    def handler(request):
        raise httpx.ConnectError("boom", request=request)

    client, _ = make_client(handler)
    assert client.file_exists("file-abc") is None


def test_http_error_message_is_short_and_has_no_key():
    # 서버가 오류 메시지에 키를 되돌려 보내도 가린다
    def handler(request):
        return httpx.Response(
            401,
            json={"error": {"message": f"Invalid API key {FAKE_KEY}", "type": "auth"}},
        )

    client, _ = make_client(handler)
    with pytest.raises(UpstageError) as info:
        client.create_job("agent-xyz", "3", "file-abc")
    exc = info.value
    assert exc.status_code == 401
    assert "HTTP 401" in exc.message
    assert "Invalid API key" in exc.message
    for text in (str(exc), repr(exc), exc.message):
        assert FAKE_KEY not in text
        assert "Bearer" not in text
        assert "authorization" not in text.lower()


def test_long_error_body_is_truncated():
    client, _ = make_client(lambda r: httpx.Response(400, json={"error": {"message": "x" * 5000}}))
    with pytest.raises(UpstageError) as info:
        client.get_job("resp_1", "last")
    assert len(info.value.message) <= 300


def test_non_json_error_body():
    client, _ = make_client(lambda r: httpx.Response(502, text="<html>bad gateway</html>"))
    with pytest.raises(UpstageError) as info:
        client.get_job("resp_1", "last")
    assert info.value.status_code == 502
    assert "<html>" not in info.value.message


@pytest.mark.parametrize("exc_type", [httpx.ConnectError, httpx.ReadTimeout])
def test_transport_errors_are_wrapped_without_request_details(exc_type):
    def handler(request):
        raise exc_type(f"failed for {request.url} with {request.headers}", request=request)

    client, _ = make_client(handler)
    with pytest.raises(UpstageError) as info:
        client.upload_file("a.pdf", b"x", "application/pdf")
    exc = info.value
    assert exc.status_code is None
    for text in (str(exc), repr(exc)):
        assert FAKE_KEY not in text
        assert "Bearer" not in text
    # 원래 예외(요청 헤더를 담고 있을 수 있음)를 체인으로 끌고 다니지 않는다
    assert exc.__cause__ is None
    assert exc.__suppress_context__ is True


def test_client_repr_has_no_key():
    client, _ = make_client(lambda r: httpx.Response(200, json={}))
    assert FAKE_KEY not in repr(client)


def test_empty_api_key_rejected():
    with pytest.raises(ValueError):
        UpstageClient("", BASE)


@pytest.mark.parametrize(
    ("status", "terminal", "success"),
    [
        ("queued", False, False),
        ("in_progress", False, False),
        ("completed", True, True),
        ("failed", True, False),
        ("cancelled", True, False),
        ("incomplete", True, False),
    ],
)
def test_status_helpers(status, terminal, success):
    assert is_terminal(status) is terminal
    assert is_success(status) is success


# --- M1: 오류·실패 문구의 가림 ---------------------------------------------------------


@pytest.mark.parametrize("status", [401, 500])
def test_create_job_http_error_hides_key_agent_and_auth(status):
    client, _ = make_client(lambda r: httpx.Response(status, json={"error": {"message": LEAKY}}))
    with pytest.raises(UpstageError) as info:
        client.create_job(FAKE_AGENT, "3", "file-abc")
    exc = info.value
    assert exc.status_code == status
    assert f"HTTP {status}" in exc.message
    assert "<UPSTAGE_AGENT_ID>" in exc.message
    assert_error_clean(exc)


@pytest.mark.parametrize("status", [401, 500])
def test_agent_from_constructor_is_hidden_in_other_calls(status):
    def handler(request):
        return httpx.Response(status, json={"error": {"message": LEAKY}})

    client = UpstageClient(FAKE_KEY, BASE, agent_id=FAKE_AGENT, transport=httpx.MockTransport(handler))
    for call in (
        lambda: client.get_job("resp_1", "last"),
        lambda: client.upload_file("a.pdf", b"x", "application/pdf"),
        lambda: client.delete_file("file-abc"),
    ):
        with pytest.raises(UpstageError) as info:
            call()
        assert_error_clean(info.value)


def test_agent_sent_by_create_job_is_remembered_for_later_errors():
    responses = iter(
        [
            httpx.Response(200, json={"id": "resp_1", "status": "queued"}),
            httpx.Response(500, json={"error": {"message": LEAKY}}),
        ]
    )
    client, _ = make_client(lambda r: next(responses))
    client.create_job(FAKE_AGENT, "3", "file-abc")
    with pytest.raises(UpstageError) as info:
        client.get_job("resp_1", "last")
    assert_error_clean(info.value)


def test_from_settings_hides_agent():
    settings = UpstageSettings(api_key=FAKE_KEY, agent_id=FAKE_AGENT, config_id="3", base_url=BASE)
    client = UpstageClient.from_settings(
        settings, transport=httpx.MockTransport(lambda r: httpx.Response(400, json={"error": {"message": LEAKY}}))
    )
    with pytest.raises(UpstageError) as info:
        client.get_job("resp_1", "all")
    assert_error_clean(info.value)
    assert_no_secret(client.redact(LEAKY))


def test_truncation_happens_after_redaction():
    # 키가 300자 경계에 걸쳐도 잘린 키 조각이 남지 않는다
    message = "x" * 270 + FAKE_KEY + " " + FAKE_AGENT + "y" * 200
    client, _ = make_client(lambda r: httpx.Response(400, json={"error": {"message": message}}))
    with pytest.raises(UpstageError) as info:
        client.get_job("resp_1", "last")
    exc = info.value
    assert len(exc.message) <= 300
    assert FAKE_KEY[:10] not in exc.message
    assert_error_clean(exc)


def test_upstage_error_itself_strips_auth_phrases():
    exc = UpstageError(f"boom Authorization: Bearer {FAKE_KEY}", 401)
    assert_error_clean(exc)
    assert exc.args == (exc.message,)


def test_non_json_and_shape_errors_go_through_redaction():
    client, _ = make_client(lambda r: httpx.Response(200, text="not json"))
    with pytest.raises(UpstageError) as info:
        client.get_job("resp_1", "last")
    assert "JSON" in info.value.message
    assert_error_clean(info.value)


# --- job_failure_message ------------------------------------------------------------

SECRETS = {FAKE_KEY: "<UPSTAGE_API_KEY>", FAKE_AGENT: "<UPSTAGE_AGENT_ID>"}


@pytest.mark.parametrize(
    ("job", "expected"),
    [
        ({"status": "failed", "error": {"message": "파싱 실패", "code": "E1"}}, "파싱 실패"),
        ({"status": "failed", "error": {"code": "rate_limited"}}, "rate_limited"),
        ({"status": "failed", "error": "문자열 오류"}, "문자열 오류"),
        ({"status": "incomplete", "incomplete_details": {"reason": "max_tokens"}}, "max_tokens"),
        ({"status": "incomplete", "incomplete_details": "잘림"}, "잘림"),
        ({"status": "cancelled"}, "Upstage 작업이 성공하지 못했습니다(상태: cancelled)"),
        ({}, "Upstage 작업이 성공하지 못했습니다(상태: 알 수 없음)"),
        (None, "Upstage 작업이 성공하지 못했습니다(상태: 알 수 없음)"),
    ],
)
def test_job_failure_message_order(job, expected):
    assert job_failure_message(job, SECRETS) == expected


@pytest.mark.parametrize(
    "job",
    [
        {"status": "failed", "error": {"message": LEAKY}},
        {"status": "failed", "error": {"code": LEAKY}},
        {"status": "incomplete", "incomplete_details": {"reason": LEAKY}},
        {"status": "incomplete", "incomplete_details": LEAKY},
    ],
)
def test_job_failure_message_redacts(job):
    assert_no_secret(job_failure_message(job, SECRETS))
    # 클라이언트 경유(자기 키·에이전트 id 로 가림)도 같다
    assert_no_secret(UpstageClient(FAKE_KEY, BASE, agent_id=FAKE_AGENT).failure_message(job))


def test_job_failure_message_limit_after_redaction():
    job = {"status": "failed", "error": {"message": "z" * 280 + FAKE_KEY + "w" * 100}}
    text = job_failure_message(job, SECRETS, limit=300)
    assert len(text) <= 300
    assert FAKE_KEY[:10] not in text
