# ==========================================================================
#  Upstage Agent API 클라이언트 (httpx, 동기)
#  BRIEF §4 의 Studio 'API로 이용하기' 안내 그대로 부른다(OpenAI SDK 를 쓰지 않는 이유:
#  config_id · include[] 를 안내와 똑같이 보내기 위해).
#    1. POST   /files              multipart file + purpose=user_data   → id(file id)
#    2. POST   /responses          model·config_id·include["all"]·input → id(job id), status
#    3. GET    /responses/{id}?include[]=last|all                       → status, output[]
#    4. DELETE /files/{id}                                              → 404 도 지워진 것으로 본다
#  - 오류는 UpstageError(message, status_code) 하나로 감싼다. 메시지는 짧게(HTTP 상태와
#    응답의 error.message 정도) 두고, API 키·Authorization 헤더·요청 전체를 넣지 않는다.
#  - 가림은 redaction.redact 한 곳에서: 클라이언트는 자기 API 키와 에이전트 id(생성자 agent_id,
#    또는 create_job 으로 한 번 보낸 값)를 기억해 모든 UpstageError 메시지에서 가린다.
#    길이 제한(300자)은 가림 뒤에 적용한다. UpstageError 자체도 인증 문구는 늘 지운다.
#  - job_failure_message(job, secrets): 실패한 작업의 이유를 가린 짧은 문구로(화면·로그용).
#  - 테스트는 transport(httpx.MockTransport)를 넣어 네트워크 없이 확인한다.
# ==========================================================================

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import quote

import httpx

from .redaction import AGENT_ID_PLACEHOLDER, Secrets, redact, upstage_secrets

if TYPE_CHECKING:
    from .config import UpstageSettings

# 아직 끝나지 않은 상태(이 밖의 상태는 모두 '끝')
PENDING_STATUSES = frozenset({"queued", "in_progress"})
SUCCESS_STATUS = "completed"

# 연결 10초, 읽기·쓰기 60초
DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=10.0)

# 오류 메시지 최대 길이(응답 본문이 길어도 로그가 넘치지 않게). 가림 뒤에 자른다.
MAX_MESSAGE = 300


def is_terminal(status: object) -> bool:
    """queued · in_progress 가 아니면 끝난 상태."""
    return status not in PENDING_STATUSES


def is_success(status: object) -> bool:
    """completed 만 성공."""
    return status == SUCCESS_STATUS


class UpstageError(Exception):
    """Upstage 호출 오류. status_code 는 HTTP 상태(연결 오류 등은 None).

    message·str·repr·args 는 모두 같은 가린 문구다. 알려진 값(키·에이전트 id)은 만드는 쪽
    (UpstageClient)이 가려서 넘기고, 여기서는 인증 문구를 한 번 더 지우고 길이를 줄인다.
    """

    def __init__(self, message: str, status_code: int | None = None):
        message = redact(message, limit=MAX_MESSAGE)
        super().__init__(message)
        self.message = message
        self.status_code = status_code

    def __repr__(self) -> str:
        return f"UpstageError({self.message!r}, status_code={self.status_code!r})"


def _error_detail(response: httpx.Response) -> str:
    """응답 본문에서 error.message(없으면 message·detail)만 짧게 꺼낸다."""
    try:
        body = response.json()
    except ValueError:
        return ""
    if not isinstance(body, dict):
        return ""
    error = body.get("error")
    if isinstance(error, dict):
        message = error.get("message") or error.get("code")
        if message:
            return str(message)
    elif isinstance(error, str) and error:
        return error
    for key in ("message", "detail"):
        value = body.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def job_failure_message(job: Any, secrets: Secrets | None = None, *, limit: int = MAX_MESSAGE) -> str:
    """끝났지만 성공하지 못한 작업의 이유를 사람이 읽을 짧은 문구로(가림·길이 제한 적용).

    읽는 순서: error.message → error.code → incomplete_details(reason·message, 문자열이면 그대로)
    → 상태. 응답 원문을 통째로 넣지 않는다.
    """
    reason = ""
    status = None
    if isinstance(job, Mapping):
        status = job.get("status")
        error = job.get("error")
        if isinstance(error, Mapping):
            reason = _text(error.get("message")) or _text(error.get("code"))
        elif isinstance(error, str):
            reason = _text(error)
        if not reason:
            details = job.get("incomplete_details")
            if isinstance(details, Mapping):
                reason = _text(details.get("reason")) or _text(details.get("message"))
            elif isinstance(details, str):
                reason = _text(details)
    if not reason:
        shown = status if isinstance(status, str) and status else "알 수 없음"
        reason = f"Upstage 작업이 성공하지 못했습니다(상태: {shown})"
    return redact(reason, secrets, limit=limit)


class UpstageClient:
    """Upstage Agent API 동기 클라이언트. with 문으로 쓰거나 close() 를 부른다.

    agent_id 를 주면(또는 create_job 을 한 번 부르면) 그 값도 오류 메시지에서 가린다.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.upstage.ai/v2",
        *,
        agent_id: str | None = None,
        timeout: httpx.Timeout | float | None = DEFAULT_TIMEOUT,
        transport: httpx.BaseTransport | None = None,
    ):
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("api_key 가 비었습니다")
        # 가릴 값 → 자리표시자. create_job 으로 보낸 에이전트 id 도 여기에 더한다.
        self._secrets: dict[str, str] = upstage_secrets(api_key, agent_id)
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
            transport=transport,
        )

    @classmethod
    def from_settings(cls, settings: UpstageSettings, **kwargs: Any) -> UpstageClient:
        """config.UpstageSettings 로 만든다(에이전트 id 가림 포함)."""
        return cls(settings.api_key, settings.base_url, agent_id=settings.agent_id, **kwargs)

    # --- 수명 -----------------------------------------------------------------

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> UpstageClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"UpstageClient(base_url={self._base_url!r})"

    # --- 내부 -----------------------------------------------------------------

    def redact(self, text: Any, *, limit: int | None = MAX_MESSAGE) -> str:
        """이 클라이언트가 아는 값(키·에이전트 id)과 인증 문구를 가린다(공용 경계)."""
        return redact(text, self._secrets, limit=limit)

    def failure_message(self, job: Any) -> str:
        """job_failure_message 를 이 클라이언트가 아는 값으로 가려서."""
        return job_failure_message(job, self._secrets)

    def _error(self, message: str, status_code: int | None = None) -> UpstageError:
        """UpstageError 를 만드는 유일한 길 — 알려진 값을 가린 뒤 길이를 줄인다."""
        return UpstageError(self.redact(message), status_code)

    def _send(self, method: str, url: str, action: str, **kwargs: Any) -> httpx.Response:
        """요청을 보내고 연결 오류를 UpstageError 로 바꾼다(HTTP 상태 판정은 부른 쪽에서)."""
        try:
            return self._client.request(method, url, **kwargs)
        except httpx.TimeoutException:
            raise self._error(f"{action}: Upstage 응답 시간 초과") from None
        except httpx.HTTPError as exc:
            # 예외 문자열에도 요청 정보가 섞일 수 있어 종류 이름만 남긴다.
            raise self._error(f"{action}: Upstage 연결 오류({type(exc).__name__})") from None

    def _fail(self, response: httpx.Response, action: str) -> UpstageError:
        detail = _error_detail(response)
        message = f"{action}: HTTP {response.status_code}"
        if detail:
            message += f" — {detail}"
        return self._error(message, response.status_code)

    def _json(self, response: httpx.Response, action: str) -> dict[str, Any]:
        if not response.is_success:
            raise self._fail(response, action)
        try:
            body = response.json()
        except ValueError:
            raise self._error(f"{action}: 응답이 JSON 이 아닙니다", response.status_code) from None
        if not isinstance(body, dict):
            raise self._error(f"{action}: 응답 모양이 다릅니다", response.status_code)
        return body

    @staticmethod
    def _path_id(value: str, what: str) -> str:
        if not isinstance(value, str) or not value:
            raise ValueError(f"{what} 가 비었습니다")
        return quote(value, safe="")

    # --- API ------------------------------------------------------------------

    def upload_file(self, filename: str, content: bytes, mime_type: str) -> str:
        """POST /files (multipart file + purpose=user_data) → file id."""
        action = "파일 올리기"
        response = self._send(
            "POST",
            "/files",
            action,
            files={"file": (filename, content, mime_type)},
            data={"purpose": "user_data"},
        )
        body = self._json(response, action)
        file_id = body.get("id")
        if not isinstance(file_id, str) or not file_id:
            raise self._error(f"{action}: 응답에 id 가 없습니다", response.status_code)
        return file_id

    def create_job(self, agent_id: str, config_id: str, file_id: str) -> dict[str, Any]:
        """POST /responses → 응답 dict(id = job id, status)."""
        action = "작업 만들기"
        if not isinstance(config_id, str) or not config_id.strip():
            # config_id 없이(빈 값·공백만) 실행하면 Studio 최신 설정이 돈다(BRIEF §4). 보내지 않는다.
            raise ValueError("config_id 가 비었습니다")
        if not isinstance(agent_id, str) or not agent_id.strip():
            raise ValueError("agent_id 가 비었습니다")
        # 보낸 에이전트 id 는 이 호출과 이후 모든 오류 메시지에서 가린다.
        self._secrets.setdefault(agent_id, AGENT_ID_PLACEHOLDER)
        payload = {
            "model": agent_id,
            "config_id": config_id.strip(),
            "include": ["all"],
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_file", "file_id": file_id}],
                }
            ],
        }
        response = self._send("POST", "/responses", action, json=payload)
        body = self._json(response, action)
        if not isinstance(body.get("id"), str) or not body.get("id"):
            raise self._error(f"{action}: 응답에 id 가 없습니다", response.status_code)
        return body

    def get_job(self, job_id: str, include: Literal["last", "all"]) -> dict[str, Any]:
        """GET /responses/{job_id}?include[]=last|all → 응답 dict."""
        if include not in ("last", "all"):
            raise ValueError("include 는 'last' 또는 'all' 입니다")
        action = "작업 조회"
        # 안내 문서 그대로 include[] 를 대괄호째 보낸다(httpx 는 쿼리의 [] 를 그대로 둔다).
        url = f"/responses/{self._path_id(job_id, 'job_id')}?include[]={include}"
        response = self._send("GET", url, action)
        return self._json(response, action)

    def delete_file(self, file_id: str) -> bool:
        """DELETE /files/{file_id}. 지워졌거나 이미 없으면(404) True."""
        action = "파일 지우기"
        response = self._send("DELETE", f"/files/{self._path_id(file_id, 'file_id')}", action)
        if response.status_code == 404:
            return True
        if not response.is_success:
            raise self._fail(response, action)
        try:
            body = response.json()
        except ValueError:
            return True
        if isinstance(body, dict) and body.get("deleted") is False:
            return False
        return True

    def file_exists(self, file_id: str) -> bool | None:
        """(확인용) GET /files/{file_id}: 200 → True, 404 → False, 그 밖·연결 오류 → None."""
        try:
            response = self._send("GET", f"/files/{self._path_id(file_id, 'file_id')}", "파일 확인")
        except UpstageError:
            return None
        if response.status_code == 200:
            return True
        if response.status_code == 404:
            return False
        return None
