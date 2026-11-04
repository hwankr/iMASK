# ==========================================================================
#  Upstage Studio 워크플로우 관리 스크립트 (로컬 전용)
#  Studio 의 에이전트(워크플로우)·설정을 보고(list·show), 저장소 파일로 내보내고(export),
#  파일과 비교하고(diff), 파일로 새 설정을 더한다(create). 저장소 정의: workflows/final_imask_workflow.json
#
#  실행(저장소 루트에서, 공통 옵션 --env-file <경로>(기본: 저장소 루트 .env) · --json(표 대신 JSON)):
#    .venv\Scripts\python.exe scripts\studio_workflow.py list
#    … show   --agent final_imask_workflow [--config 1]
#    … export --agent final_imask_workflow --config 1 --out workflows/final_imask_workflow.json
#    … diff   --agent final_imask_workflow --config 1 workflows/final_imask_workflow.json [--ids]
#    … create workflows/final_imask_workflow.json --agent <이름> [--yes]
#
#  Studio API(https://api.upstage.ai/v2) — **공개 문서에 없는 경로**(Studio 콘솔이 쓰는 것, 2026-11-04 확인):
#    GET  /agents                         목록 {data, has_more, last_id} → 다음 쪽은 ?after=<last_id>
#    GET  /agents/{id}                    에이전트(default_config_id·default_config_external_id·used_steps …)
#    GET  /agents/{id}/configs            설정 목록(external_id = 설정 번호 "1"·"2"…, is_default)
#    GET  /agents/{id}/configs/{cfg_id}   설정 하나(steps 포함)
#    POST /agents                         {name, visibility:"private"} → 새 에이전트
#    POST /agents/{id}/configs            {name, steps} → 새 설정 번호가 생기고 기본 설정이 된다.
#                                         설정은 고쳐 쓰지 않는다 — 늘 새 번호.
#    그래프 규칙 위반은 400 config_graph_rule_violation(예: Match 의 기준은 Merge 에 바로 들어오는 Extract).
#  헤더: Authorization: Bearer <UPSTAGE_API_KEY>, x-project-id: <UPSTAGE_PROJECT_ID>(없으면 생략).
#  환경: --env-file 의 KEY=VALUE 를 읽고, 파일에 없는 이름만 OS 환경변수에서 채운다.
#
#  비밀값(BRIEF §2) — 가림 경계는 Scrubber 하나. **원래 문자열에 먼저** 가리고, 그 다음에 한 줄·길이 자르기·
#    JSON 직렬화를 한다(잘린 조각·이스케이프된 키가 남지 않게, T2-fix1 M1). 순서:
#    알려진 비밀값(키·프로젝트 id) → 인증 문구·토큰·JWT(imask_backend.redaction.redact)
#    → Studio 식별자 꼴(agt_·cfg_·proj_·file_·job_·resp_·vs_ + 영숫자 12자 이상) → 응답·요청에서 본 id.
#    id 는 끝 6자만(…abc123). 미리 모은 값에 기대지 않으므로 첫 요청의 오류·오류에서 처음 나온 id·
#    클라이언트를 직접 쓸 때의 StudioError 도 같다(M2). 오류는 HTTP 상태와 error.message(+ error.code)만.
#  명령줄 해석 오류(T2-fix3, R3): 잘못된 옵션·하위 명령·여분 인자·값 빠짐 모두 받은 값을 인용하지 않는 고정 한국어
#    한 줄(가림 경계를 지남)·종료 코드 2·traceback 없음(CliParser). --help 는 그대로.
#  main 순서(T2-fix2): ① 가릴 값 모으기(환경 파일·환경변수의 키·프로젝트 id — 요청·필수 검사 없이, 없어도 오류 아님)
#    → ② 로컬 파일 검사(diff·create — 형식이 틀리면 요청 없이 2, 문구에는 위치(step 번호·키 이름)만)
#    → ③ 필수 설정 → ④ 요청. 화면에 JSON 글이 되는 길은 Scrubber.dump·Output.json 둘뿐(둘 다 값마다 먼저 가림).
#  create 는 --yes 가 없으면 요청을 하나도 보내지 않고 할 일만 출력한다. --yes 면 에이전트 목록을 **엄격하게**
#    읽는다: data 가 목록·has_more 가 bool·항목이 객체이고 이름·id 가 문자열·쪽 넘김 완료가 아니면 POST 없이
#    멈춘다(M3). 같은 이름 에이전트가 둘 이상이어도 멈춘다. 읽기 명령은 틀린 항목을 건너뛴다.
#  응답 모양이 틀려도 예외 없이 짧은 한국어 오류(종료 코드 2)로 끝낸다. 길이·개수 한도는 아래 상수.
#  종료 코드: 0 성공(diff: 같음), 1 diff 다름, 2 오류(설정·연결·HTTP·파일·응답 모양).
#  표준 라이브러리 + httpx. 테스트는 main(argv, transport=httpx.MockTransport(…)) 로 네트워크 없이 부른다.
# ==========================================================================

from __future__ import annotations

import argparse
import functools
import json
import os
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, NoReturn, TextIO

import httpx

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from imask_backend.redaction import API_KEY_PLACEHOLDER, AUTH_PLACEHOLDER, MIN_SECRET_LENGTH, redact  # noqa: E402
from imask_backend.upstage import MAX_MESSAGE, PROJECT_HEADER  # noqa: E402

DEFAULT_BASE_URL = "https://api.upstage.ai/v2"
DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
API_KEY_ENV = "UPSTAGE_API_KEY"
PROJECT_ID_ENV = "UPSTAGE_PROJECT_ID"
PROJECT_PLACEHOLDER = "<UPSTAGE_PROJECT_ID>"

EXIT_OK = 0
EXIT_DIFFERENT = 1
EXIT_ERROR = 2

# 응답 경계 한도
MAX_PAGES = 50  # 목록 쪽 수
MAX_ITEMS = 1000  # 목록 항목 수
MAX_STEPS = 500  # 설정 하나의 step 수
MAX_NEXT = 500  # step 하나의 next_steps 수
MAX_TEXT = 120  # 화면에 보일 이름·값 길이
MAX_CODE = 100  # 오류 코드 길이
MAX_RAW = 100_000  # 이보다 긴 글은 가리기 전에 자르지 않고 통째로 버린다(자른 조각이 남지 않게)
SHORT_ID = 6  # id 는 끝 6자만
TOO_LONG = "(너무 긺)"

# 내보내는 step 의 키(이 순서) — workflows/final_imask_workflow.json 과 같은 형식
STEP_KEYS = ("id", "name", "type", "data", "next_steps", "is_first", "node_id")
COMPARE_KEYS = ("type", "is_first", "data", "next_steps")
ID_KEYS = ("id", "node_id")

_PATH_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
_PROJECT_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
_API_KEY = re.compile(r"[!-~]{1,512}")  # 공백 없는 ASCII(헤더에 넣을 수 있는 글자)
# 줄일 id 를 모을 키: id, …_id (external_id = 설정 번호는 제외)
_ID_KEY = re.compile(r"^(?:id|(?!external)[a-z_]*_id)$")
# Studio 식별자 꼴(실제는 접두어 + 영숫자 22자). 'file_upload' 같은 낱말은 두려고 12자 이상만
_STUDIO_ID = re.compile(r"(?<![A-Za-z0-9])(?:agt|cfg|proj|file|job|resp|vs)_[A-Za-z0-9]{12,}")
_ASCII_DIGITS = re.compile(r"[0-9]{1,18}")
# 인증 낱말과 그 뒤에 붙은 구분자·'Bearer'·자리표시자(<…>)까지 한 덩이로. 알려진 값은 이미 자리표시자다.
# 진짜 토큰이 붙은 꼴은 redact() 가 먼저 가리므로 여기서는 낱말이 하나도 남지 않게만 한다(선형 시간).
_AUTH_WORDS = re.compile(
    r"(?i)\b(?:(?:proxy-)?authorization|bearer)\b[\s:='\"]{0,20}(?:bearer\b[\s'\"]{0,20})?(?:<[A-Za-z_]{1,40}>)?"
)


class StudioError(Exception):
    """사용자에게 보일 짧은 오류. message 는 만드는 쪽이 Scrubber 로 가린 뒤 넘긴다."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# --- 명령줄 해석 오류(R3) ---------------------------------------------------------------
# argparse 는 오류 문구에 받은 인자 값을 그대로 인용하고(예: 'unrecognized arguments: <값>') 가림 경계를 거치지 않고
# sys.stderr 로 바로 쓴 뒤 끝낸다. 그래서 해석기의 error()·exit() 를 바꿔, argparse 문구의 **종류만** 보고 고정된
# 한국어 한 줄을 고른다(받은 값은 한 글자도 옮기지 않는다). main 이 그 줄을 가림 경계(Output)로 내보내고 2 로 끝낸다.
# 하위 파서는 add_subparsers 가 부모 해석기의 클래스로 만들므로 같은 규칙을 따른다. --help 는 그대로(종료 코드 0).

DEFAULT_ENV_FILE = ROOT / ".env"
CLI_HINT = " — --help 를 보세요"
# (argparse 영문 문구에 든 낱말, 한국어) — 위에서부터 처음 맞는 것. 맞는 것이 없으면 CLI_GENERIC
_CLI_MESSAGES = (
    ("unrecognized arguments", "알 수 없는 옵션이나 인자가 있습니다"),
    ("invalid choice", "알 수 없는 하위 명령입니다"),
    ("the following arguments are required", "필요한 인자가 빠졌습니다"),
    ("expected one argument", "옵션 값이 빠졌습니다"),
    ("ambiguous option", "옵션 이름이 여러 옵션과 겹칩니다"),
)
CLI_GENERIC = "명령줄 인자가 맞지 않습니다"


class CliUsageError(Exception):
    """명령줄 해석 오류. message 는 고정 문구뿐 — 받은 인자 값은 담지 않는다."""

    def __init__(self, argparse_message: object = None):
        text = argparse_message if isinstance(argparse_message, str) else ""
        korean = next((ko for needle, ko in _CLI_MESSAGES if needle in text), CLI_GENERIC)
        self.message = korean + CLI_HINT
        super().__init__(self.message)


class CliParser(argparse.ArgumentParser):
    """오류를 그대로 쓰고 끝내지 않고 CliUsageError 로 올리는 해석기(하위 파서도 이 클래스)."""

    def error(self, message: str) -> NoReturn:  # argparse 가 해석 오류마다 부른다
        raise CliUsageError(message)

    def exit(self, status: int = 0, message: str | None = None) -> NoReturn:
        if message or status:  # 글을 내며 끝내려는 경우 — 받은 값이 섞였을 수 있어 그 글은 내지 않는다
            raise CliUsageError(message)
        raise SystemExit(0)  # --help


# --- 가림 경계 -----------------------------------------------------------------


def short_id(value: Any) -> str:
    """id 를 끝 6자만 보이게(…abc123). 문자열이 아니면 '?'."""
    if not isinstance(value, str) or not value:
        return "?"
    return "…" + value[-SHORT_ID:]


def clip(text: str, limit: int) -> str:
    """**이미 가린** 글을 한 줄로 만들고 길면 자른다(선형 시간)."""
    line = " ".join(text.split())
    return line if len(line) <= limit else line[: max(limit - 1, 0)] + "…"


class Scrubber:
    """가림 경계 — 출력·오류·예외 문구로 나가는 **모든** 글이 지난다(T2-fix2 에서 구조로 고정).

    - scrub(): 원래 문자열 전체에 쓴다. 자르기(clip)·한 줄 만들기·직렬화는 그 뒤에만.
    - text(): 화면용 글(가림 → 한 줄 → 자르기). dump(): 화면에 JSON 글로 보일 값(값마다 가림 → 직렬화).
      화면에 JSON 글을 만드는 길은 dump() 와 Output.json() 둘뿐이다(둘 다 직렬화 전에 가린다).
    - 비밀값은 원문·앞뒤 공백을 뺀 값·JSON 이스케이프한 꼴을 모두 같은 자리표시자로 바꾼다.
    """

    def __init__(self, secrets: Mapping[str, str] | None = None):
        self.secrets: dict[str, str] = {}
        self._ids: set[str] = set()
        for secret, placeholder in (secrets or {}).items():
            self.add_secret(secret, placeholder)

    def add_secret(self, secret: Any, placeholder: str) -> None:
        """비밀값 하나를 원문·공백 뺀 값·JSON 이스케이프 꼴(ASCII·유니코드)로 등록한다."""
        if not isinstance(secret, str):
            return
        forms = {secret, secret.strip()}
        for form in list(forms):
            forms.add(json.dumps(form)[1:-1])
            forms.add(json.dumps(form, ensure_ascii=False)[1:-1])
        for form in forms:
            if len(form) >= MIN_SECRET_LENGTH:
                self.secrets[form] = placeholder

    def add_ids(self, *values: Any) -> None:
        for value in values:
            if isinstance(value, str) and len(value) > SHORT_ID:
                self._ids.add(value)

    def remember(self, obj: Any) -> None:
        """객체 맨 윗단의 id·…_id 값을 기억해 줄인다(steps 안은 보지 않는다)."""
        if isinstance(obj, Mapping):
            self.add_ids(*(v for k, v in obj.items() if isinstance(k, str) and _ID_KEY.match(k)))

    def scrub(self, text: Any) -> str:
        value = text if isinstance(text, str) else str(text)
        # 1) 알려진 비밀값을 먼저(정규식 규칙이 키 일부를 바꿔 전체 일치가 깨지기 전에), 긴 것부터
        for secret in sorted(self.secrets, key=len, reverse=True):
            if secret in value:
                value = value.replace(secret, self.secrets[secret])
        # 2) 인증 문구·서명 URL·토큰·JWT
        value = redact(value)
        # 2-1) 자리표시자가 붙은 'Bearer <…>'·'Authorization: …'·홀로 남은 인증 낱말도 통째로(N2)
        value = _AUTH_WORDS.sub(AUTH_PLACEHOLDER, value)
        # 3) Studio 식별자 꼴(미리 모으지 않은 id 도), 4) 응답·요청에서 본 id
        value = _STUDIO_ID.sub(lambda m: short_id(m.group(0)), value)
        for full in sorted(self._ids, key=len, reverse=True):
            if full in value:
                value = value.replace(full, short_id(full))
        return value

    def short_id(self, value: Any) -> str:
        """응답의 id 를 끝 6자로. 비밀값이 든 값이면 끝 조각도 보이지 않게 '?'."""
        if isinstance(value, str) and any(secret in value for secret in self.secrets):
            return "?"
        return short_id(value)

    def text(self, value: Any, limit: int = MAX_TEXT) -> str:
        """화면용 글: 문자열이 아니면 '?', 아주 길면 통째로 버림, 아니면 가린 뒤 한 줄·자르기."""
        if not isinstance(value, str):
            return "?"
        if len(value) > MAX_RAW:
            return TOO_LONG
        return clip(self.scrub(value), limit)

    def value(self, obj: Any, depth: int = 0) -> Any:
        """JSON 으로 내보낼 객체의 문자열(키 포함)을 값마다 가린다 — 직렬화는 그 뒤."""
        if isinstance(obj, str):
            return self.scrub(obj) if len(obj) <= MAX_RAW else TOO_LONG
        if depth > 50:
            return "?"
        if isinstance(obj, Mapping):
            return {self.value(k, depth + 1) if isinstance(k, str) else k: self.value(v, depth + 1) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self.value(v, depth + 1) for v in obj]
        return obj

    def dump(self, obj: Any, limit: int = MAX_TEXT) -> str:
        """화면에 JSON 글로 보일 값: 값마다 먼저 가리고 → 직렬화 → 한 줄·자르기. 못 쓰면 '?'."""
        try:
            text = json.dumps(self.value(obj), sort_keys=True, ensure_ascii=False)
        except (ValueError, TypeError, RecursionError):
            return "?"
        return clip(self.scrub(text), limit)


_PLAIN = Scrubber()  # 비밀값 없이 규칙·식별자 꼴만 — 순수 함수의 기본값


def collect_secrets(scrubber: Scrubber, values: Mapping[str, str], environ: Mapping[str, str]) -> None:
    """출력보다 **먼저**, 요청·필수 검사 없이 가릴 값을 모은다(N1). 없어도 오류가 아니다.

    환경 파일(values)과 환경변수 양쪽의 UPSTAGE_API_KEY·UPSTAGE_PROJECT_ID 를 모두 등록한다(어느 쪽을 쓰든).
    """
    for name, placeholder in ((API_KEY_ENV, API_KEY_PLACEHOLDER), (PROJECT_ID_ENV, PROJECT_PLACEHOLDER)):
        for source in (values, environ):
            value = source.get(name)
            if isinstance(value, str) and value.strip():
                scrubber.add_secret(value, placeholder)


class Output:
    """모든 출력의 유일한 길. 줄은 이미 가린 조각으로 만들고, 내보내기 전에 한 번 더 가린다."""

    def __init__(self, stdout: TextIO, stderr: TextIO, scrubber: Scrubber | None = None):
        self.stdout = stdout
        self.stderr = stderr
        self.scrubber = scrubber or Scrubber()

    def text(self, value: Any, limit: int = MAX_TEXT) -> str:
        return self.scrubber.text(value, limit)

    def id(self, value: Any) -> str:
        return self.scrubber.short_id(value)

    def say(self, line: str = "") -> None:
        self.stdout.write(self.scrubber.scrub(line) + "\n")

    def json(self, obj: Any) -> None:
        self.stdout.write(json.dumps(self.scrubber.value(obj), ensure_ascii=False, indent=2) + "\n")

    def error(self, message: str) -> None:
        self.stderr.write(self.scrubber.scrub("오류: " + message) + "\n")


# --- 환경 -------------------------------------------------------------------


def read_env_file(path: Path) -> dict[str, str]:
    """KEY=VALUE 줄만 읽는다(# 주석·빈 줄·export 앞말 무시, 따옴표 벗김). 없는 파일은 빈 dict. 값은 출력하지 않는다."""
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        raise StudioError(f"환경 파일을 읽지 못했습니다: {path.name}") from None
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        name, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        values[name.strip()] = value
    return values


def load_settings(env_file: Path, environ: Mapping[str, str], values: Mapping[str, str] | None = None) -> tuple[str, str | None]:
    """(API 키, 프로젝트 id 또는 None). values 는 이미 읽은 환경 파일(없으면 읽는다). 오류에는 이름만 담는다."""
    values = read_env_file(env_file) if values is None else values

    def pick(name: str) -> str:
        value = values.get(name)
        if not value:
            value = environ.get(name) or ""
        return value.strip()

    api_key = pick(API_KEY_ENV)
    if not api_key:
        raise StudioError(f"{API_KEY_ENV} 가 없습니다(환경 파일: {env_file.name})")
    if not _API_KEY.fullmatch(api_key):
        raise StudioError(f"{API_KEY_ENV} 형식이 맞지 않습니다")
    project_id = pick(PROJECT_ID_ENV) or None
    if project_id is not None and not _PROJECT_ID.fullmatch(project_id):
        raise StudioError(f"{PROJECT_ID_ENV} 형식이 맞지 않습니다")
    return api_key, project_id


# --- Studio API ---------------------------------------------------------------


def error_parts(response: httpx.Response) -> tuple[str, str]:
    """응답 본문의 (error.message, error.code) **원문**(자르지 않음). 없으면 message·detail, 그래도 없으면 ''."""
    try:
        body = response.json()
    except (ValueError, RecursionError):
        return "", ""
    if not isinstance(body, dict):
        return "", ""
    error = body.get("error")
    message = code = ""
    if isinstance(error, Mapping):
        message = error.get("message") if isinstance(error.get("message"), str) else ""
        code = error.get("code") if isinstance(error.get("code"), str) else ""
    elif isinstance(error, str):
        message = error
    if not message:
        for key in ("message", "detail"):
            if isinstance(body.get(key), str):
                message = body[key]
                break
    return message, code


class StudioClient:
    """Studio API 동기 클라이언트(with 문). transport 를 바꿔 끼우면 네트워크 없이 시험한다.

    scrubber 를 주지 않아도 키·프로젝트 id·Studio 식별자 꼴·요청에 쓴 id 를 가린 StudioError 만 낸다.
    """

    def __init__(
        self,
        api_key: str,
        project_id: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        transport: httpx.BaseTransport | None = None,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
        scrubber: Scrubber | None = None,
    ):
        headers = {"Authorization": f"Bearer {api_key}"}
        self.scrubber = scrubber or Scrubber()
        self.scrubber.add_secret(api_key, API_KEY_PLACEHOLDER)
        if project_id:
            headers[PROJECT_HEADER] = project_id
            self.scrubber.add_secret(project_id, PROJECT_PLACEHOLDER)
        self._http = httpx.Client(base_url=base_url.rstrip("/"), headers=headers, timeout=timeout, transport=transport)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> StudioClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return "StudioClient(<hidden>)"

    def _error(self, text: str, status_code: int | None = None) -> StudioError:
        """가린 뒤 한 줄·길이 제한 → StudioError(이 순서)."""
        return StudioError(clip(self.scrubber.scrub(text), MAX_MESSAGE), status_code)

    def _http_error(self, response: httpx.Response, action: str) -> StudioError:
        message, code = error_parts(response)
        # 원문 전체를 먼저 가리고 그 다음에 자른다. 너무 긴 원문은 자르지 않고 버린다
        message = clip(self.scrubber.scrub(message), MAX_MESSAGE) if len(message) <= MAX_RAW else "(오류 문구가 너무 깁니다)"
        code = clip(self.scrubber.scrub(code), MAX_CODE) if len(code) <= MAX_RAW else ""
        detail = (f"{message} [{code}]" if message else code) if code and code != message else message
        return self._error(f"{action}: HTTP {response.status_code}" + (f" — {detail}" if detail else ""), response.status_code)

    def _call(self, method: str, path: str, action: str, *, params: dict[str, str] | None = None, body: Any = None) -> Any:
        try:
            response = self._http.request(method, path, params=params, json=body)
        except httpx.TimeoutException:
            raise self._error(f"{action}: Upstage 응답 시간이 지났습니다") from None
        except httpx.HTTPError as exc:
            raise self._error(f"{action}: Upstage 에 연결하지 못했습니다({type(exc).__name__})") from None
        if response.status_code >= 400:
            raise self._http_error(response, action)
        try:
            return response.json()
        except (ValueError, RecursionError):
            raise self._error(f"{action}: 응답이 JSON 이 아닙니다(HTTP {response.status_code})", response.status_code) from None

    def _object(self, method: str, path: str, action: str, **kwargs: Any) -> dict[str, Any]:
        body = self._call(method, path, action, **kwargs)
        if not isinstance(body, dict):
            raise self._error(f"{action}: 응답 모양이 다릅니다(객체가 아님)")
        self.scrubber.remember(body)
        return body

    def _list(self, path: str, action: str, *, strict: bool = False) -> list[dict[str, Any]]:
        """has_more·last_id 로 끝까지 읽는다. 끝까지 못 읽으면 StudioError(일부만 쓰지 않는다).

        strict(만들기 판단용): data 목록·has_more bool·항목 객체·이름·id 문자열이 아니면 '온전하지 않음' 오류.
        아니면(읽기 명령) 틀린 항목을 건너뛴다.
        """
        broken = f"{action}: 목록이 온전하지 않습니다(응답 모양이 다름) — 아무것도 보내지 않고 멈춥니다"
        items: list[dict[str, Any]] = []
        after: str | None = None
        seen: set[str] = set()
        for _ in range(MAX_PAGES):
            body = self._call("GET", path, action, params={"after": after} if after else None)
            if strict:
                if not isinstance(body, dict) or not isinstance(body.get("data"), list) or not isinstance(body.get("has_more"), bool):
                    raise self._error(broken)
                for item in body["data"]:
                    if (not isinstance(item, dict) or not isinstance(item.get("name"), str)
                            or not isinstance(item.get("id"), str) or not _PATH_ID.fullmatch(item["id"])):
                        raise self._error(broken)
                data, more, last = body["data"], body["has_more"], body.get("last_id")
            elif isinstance(body, list):
                data, more, last = body, False, None
            elif isinstance(body, dict):
                data, more, last = body.get("data"), body.get("has_more") is True, body.get("last_id")
            else:
                raise self._error(f"{action}: 응답 모양이 다릅니다")
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        self.scrubber.remember(item)
                        items.append(item)
            if len(items) > MAX_ITEMS:
                raise self._error(f"{action}: 항목이 너무 많습니다(>{MAX_ITEMS})")
            if not more:
                return items
            if not isinstance(last, str) or not last or last in seen:
                raise self._error(f"{action}: 목록을 끝까지 읽지 못했습니다(다음 쪽 표시가 없음)")
            seen.add(last)
            after = last
        raise self._error(f"{action}: 목록을 끝까지 읽지 못했습니다(쪽 수 한도 {MAX_PAGES})")

    def _path_id(self, value: Any, what: str) -> str:
        if not isinstance(value, str) or not _PATH_ID.fullmatch(value):
            raise StudioError(f"{what} id 모양이 다릅니다")
        self.scrubber.add_ids(value)  # 요청에 쓴 id 는 오류 문구에서도 줄인다
        return value

    def list_agents(self, *, strict: bool = False) -> list[dict[str, Any]]:
        return self._list("/agents", "에이전트 목록", strict=strict)

    def get_agent(self, agent_id: str) -> dict[str, Any]:
        return self._object("GET", f"/agents/{self._path_id(agent_id, '에이전트')}", "에이전트 조회")

    def list_configs(self, agent_id: str) -> list[dict[str, Any]]:
        return self._list(f"/agents/{self._path_id(agent_id, '에이전트')}/configs", "설정 목록")

    def get_config(self, agent_id: str, config_id: str) -> dict[str, Any]:
        path = f"/agents/{self._path_id(agent_id, '에이전트')}/configs/{self._path_id(config_id, '설정')}"
        return self._object("GET", path, "설정 조회")

    def create_agent(self, name: str) -> dict[str, Any]:
        return self._object("POST", "/agents", "에이전트 만들기", body={"name": name, "visibility": "private"})

    def create_config(self, agent_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        path = f"/agents/{self._path_id(agent_id, '에이전트')}/configs"
        return self._object("POST", path, "설정 더하기", body=dict(body))


# --- 설정 다루기 ----------------------------------------------------------------


def config_number(config: Mapping[str, Any]) -> str | None:
    """설정 번호(external_id). 문자열·정수만(bool 제외). 글자로 못 바꾸는 큰 정수는 None."""
    return number_text(config.get("external_id"))


def number_text(value: Any) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        try:
            return str(value)
        except ValueError:  # 자릿수 한도를 넘는 정수
            return None
    return None


def _number_key(value: str) -> tuple[int, int, str]:
    """ASCII 십진수만 숫자로 정렬('²' 같은 유니코드 숫자는 글자로)."""
    return (0, int(value), "") if _ASCII_DIGITS.fullmatch(value) else (1, 0, value)


def find_agent(client: StudioClient, name: str, sc: Scrubber = _PLAIN) -> dict[str, Any]:
    matches = [a for a in client.list_agents() if a.get("name") == name]
    if not matches:
        raise StudioError(f"이름이 '{sc.text(name)}' 인 에이전트가 없습니다")
    if len(matches) > 1:
        raise StudioError(f"이름이 '{sc.text(name)}' 인 에이전트가 {len(matches)}개입니다 — 하나여야 합니다")
    agent = matches[0]
    client._path_id(agent.get("id"), "에이전트")
    return agent


def pick_config(configs: Sequence[Mapping[str, Any]], agent: Mapping[str, Any], number: str | None,
                sc: Scrubber = _PLAIN) -> Mapping[str, Any]:
    """번호로(없으면 기본 설정) 설정 목록 항목 하나를 고른다."""
    if not configs:
        raise StudioError("설정이 없습니다")
    if number is None:
        default_id = agent.get("default_config_id")
        default_ext = number_text(agent.get("default_config_external_id"))
        picks = [c for c in configs if isinstance(default_id, str) and c.get("id") == default_id]
        picks = picks or [c for c in configs if c.get("is_default") is True]
        picks = picks or [c for c in configs if default_ext is not None and config_number(c) == default_ext]
        if len(picks) != 1:
            raise StudioError("기본 설정을 찾지 못했습니다 — --config 로 번호를 주세요")
        return picks[0]
    picks = [c for c in configs if config_number(c) == number]
    if len(picks) != 1:
        have = sorted({n for n in (config_number(c) for c in configs) if n}, key=_number_key)
        what = "없습니다" if not picks else f"{len(picks)}개입니다"
        raise StudioError(f"설정 번호 '{sc.text(number, 20)}' 가 {what}(있는 번호: {sc.text(', '.join(have)) if have else '없음'})")
    return picks[0]


def load_config(client: StudioClient, agent_name: str, number: str | None, sc: Scrubber = _PLAIN) -> tuple[dict, Mapping, dict]:
    """(에이전트, 설정 목록 항목, 설정 전체)."""
    agent = find_agent(client, agent_name, sc)
    configs = client.list_configs(agent["id"])
    item = pick_config(configs, agent, number, sc)
    full = client.get_config(agent["id"], client._path_id(item.get("id"), "설정"))
    return agent, item, full


def config_steps(config: Mapping[str, Any], where: str) -> list[dict[str, Any]]:
    steps = config.get("steps")
    if not isinstance(steps, list):
        raise StudioError(f"{where}: steps 가 목록이 아닙니다")
    if len(steps) > MAX_STEPS:
        raise StudioError(f"{where}: step 이 너무 많습니다(>{MAX_STEPS})")
    return [s for s in steps if isinstance(s, dict)]


def next_list(step: Mapping[str, Any]) -> list[dict[str, Any]]:
    value = step.get("next_steps")
    if not isinstance(value, list):
        return []
    return [n for n in value[:MAX_NEXT] if isinstance(n, dict)]


def export_body(config: Mapping[str, Any], where: str = "Studio 설정") -> dict[str, Any]:
    """설정을 저장소 형식 {name, steps:[{id,name,type,data,next_steps,is_first,node_id}]} 로."""
    steps = [{k: s[k] for k in STEP_KEYS if k in s} for s in config_steps(config, where)]
    name = config.get("name") if isinstance(config.get("name"), str) else ""
    return {"name": name, "steps": steps}


def dump_config(body: Any) -> bytes:
    """2칸 들여쓰기, UTF-8(BOM 없음), LF, 끝 줄바꿈 — workflows/*.json 과 같은 모양."""
    try:
        return (json.dumps(body, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    except UnicodeError:
        raise StudioError("설정에 UTF-8 로 쓸 수 없는 글자(짝 없는 서로게이트)가 있습니다") from None
    except (ValueError, TypeError, RecursionError):
        raise StudioError("설정에 JSON 으로 쓸 수 없는 값(NaN·너무 깊은 중첩 등)이 있습니다") from None


def read_config_file(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError:
        raise StudioError(f"파일을 읽지 못했습니다: {path}") from None
    try:
        body = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise StudioError(f"JSON 파일이 아닙니다: {path}") from None
    if not isinstance(body, dict) or not isinstance(body.get("steps"), list):
        raise StudioError(f"파일 모양이 다릅니다 — {{name, steps:[…]}} 이어야 합니다: {path}")
    return body


def shape_problems(body: Mapping[str, Any]) -> list[str]:
    """로컬 설정 파일의 형식(타입) 검사 — diff·create 공통. 문구에는 **위치만**(step 번호·키 이름), 값은 넣지 않는다."""
    steps = body.get("steps")
    if not isinstance(steps, list):
        return ["steps 가 목록이 아닙니다"]
    if len(steps) > MAX_STEPS:
        return [f"step 이 너무 많습니다(>{MAX_STEPS})"]
    problems: list[str] = []
    for index, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            problems.append(f"{index}번째 step 이 객체가 아닙니다")
            continue
        if not isinstance(step.get("name"), str) or not step["name"]:
            problems.append(f"{index}번째 step 에 이름이 없습니다(name 이 문자열이 아님)")
        nexts = step.get("next_steps")
        if not isinstance(nexts, list):
            problems.append(f"{index}번째 step 의 next_steps 가 목록이 아닙니다")
            continue
        if len(nexts) > MAX_NEXT:
            problems.append(f"{index}번째 step 의 next_steps 가 너무 많습니다(>{MAX_NEXT})")
            continue
        for slot, nxt in enumerate(nexts, 1):
            if not isinstance(nxt, dict):
                problems.append(f"{index}번째 step 의 next_steps[{slot}] 이 객체가 아닙니다")
            elif not isinstance(nxt.get("step_name"), str):
                problems.append(f"{index}번째 step 의 next_steps[{slot}].step_name 이 문자열이 아닙니다")
    return problems


def check_config(body: Mapping[str, Any]) -> list[str]:
    """보내기 전에 파일을 검사한다(형식 + 그래프). 문제 목록(없으면 빈 목록). 문구에는 위치만."""
    problems: list[str] = []
    if not isinstance(body.get("name"), str) or not body["name"].strip():
        problems.append("설정 이름(name)이 없습니다")
    steps = body.get("steps")
    if not isinstance(steps, list) or not steps:
        return problems + ["steps 가 비었습니다"]
    problems += shape_problems(body)
    if len(steps) > MAX_STEPS:
        return problems
    first_index: dict[str, int] = {}
    for index, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            continue
        if not isinstance(step.get("type"), str) or not step["type"]:
            problems.append(f"{index}번째 step 에 type 이 없습니다")
        name = step.get("name")
        if isinstance(name, str) and name:
            if name in first_index:
                problems.append(f"{index}번째 step 의 이름이 {first_index[name]}번째 step 과 겹칩니다")
            else:
                first_index[name] = index
    firsts = [s for s in steps if isinstance(s, dict) and s.get("is_first") is True]
    if len(firsts) != 1:
        problems.append(f"첫 step(is_first)이 {len(firsts)}개입니다 — 하나여야 합니다")
    for index, step in enumerate(steps, 1):
        if not isinstance(step, dict) or not isinstance(step.get("next_steps"), list):
            continue
        for slot, nxt in enumerate(step["next_steps"][:MAX_NEXT], 1):
            if isinstance(nxt, dict) and isinstance(nxt.get("step_name"), str) and nxt["step_name"] not in first_index:
                problems.append(f"{index}번째 step 의 next_steps[{slot}] 이 없는 step 을 가리킵니다")
    return problems


def _canon(value: Any) -> str | None:
    """**비교 전용** 정규 JSON(키 정렬) — 화면에 내지 않는다(표시는 Scrubber.dump). 못 만들면 None(늘 다르다고 본다)."""
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    except (ValueError, TypeError, RecursionError):
        return None


def _same(key: str, left: Any, right: Any) -> bool:
    if key == "next_steps" and isinstance(left, list) and isinstance(right, list):
        a = [_canon(v) for v in left]
        b = [_canon(v) for v in right]
        if None in a or None in b:
            return False
        return sorted(a) == sorted(b)  # 순서는 보지 않는다
    a, b = _canon(left), _canon(right)
    return a is not None and a == b


def _by_name(steps: Sequence[Mapping[str, Any]], side: str) -> tuple[dict[str, Mapping[str, Any]], list[str], list[str]]:
    """(이름 → step, 이름 순서, 겹치는 이름)."""
    table: dict[str, Mapping[str, Any]] = {}
    order: list[str] = []
    dups: list[str] = []
    for index, step in enumerate(steps, 1):
        name = step.get("name") if isinstance(step.get("name"), str) else f"<이름 없음 {side} #{index}>"
        if name in table:
            dups.append(name)
            continue
        table[name] = step
        order.append(name)
    return table, order, dups


def diff_steps(file_steps: Sequence[Mapping[str, Any]], studio_steps: Sequence[Mapping[str, Any]], *, ids: bool = False) -> list[dict[str, Any]]:
    """step 이름 기준 차이 목록. 비교 키: type·is_first·data·next_steps(+ ids 면 id·node_id)."""
    keys = COMPARE_KEYS + (ID_KEYS if ids else ())
    left, left_order, left_dups = _by_name(file_steps, "파일")
    right, right_order, right_dups = _by_name(studio_steps, "Studio")
    out: list[dict[str, Any]] = []
    for name in left_dups:
        out.append({"step": name, "problem": "파일에서 이름이 겹침"})
    for name in right_dups:
        out.append({"step": name, "problem": "Studio 에서 이름이 겹침"})
    for name in left_order:
        if name not in right:
            out.append({"step": name, "only_in": "file"})
            continue
        fields = [k for k in keys if not _same(k, left[name].get(k), right[name].get(k))]
        if fields:
            out.append({"step": name, "fields": fields})
    for name in right_order:
        if name not in left:
            out.append({"step": name, "only_in": "studio"})
    return out


def _condition_text(cond: Any, sc: Scrubber) -> tuple[str, str] | None:
    """조건을 (묶을 머리, 값)으로. 조건 없음은 None."""
    if cond is None:
        return None
    if isinstance(cond, Mapping) and set(cond) <= {"field", "operator", "value"}:
        head = f"{sc.text(cond.get('field'))} {sc.text(cond.get('operator'))}"
        value = cond.get("value")
        return head, sc.text(value) if isinstance(value, str) else sc.dump(value)
    return "조건", sc.dump(cond)  # 값마다 가린 뒤 직렬화(R1)


def graph_lines(steps: Sequence[Mapping[str, Any]], sc: Scrubber = _PLAIN) -> list[dict[str, Any]]:
    """step 마다 {name, type, is_first, next:[{to, condition, values}]} — 같은 대상·조건 머리는 값끼리 묶는다."""
    out = []
    for step in steps:
        groups: dict[tuple[str, str | None], list[str]] = {}
        for nxt in next_list(step):
            cond = _condition_text(nxt.get("condition"), sc)
            key = (sc.text(nxt.get("step_name")), cond[0] if cond else None)
            groups.setdefault(key, [])
            if cond:
                groups[key].append(cond[1])
        out.append({
            "name": sc.text(step.get("name")),
            "type": sc.text(step.get("type")),
            "is_first": step.get("is_first") is True,
            "next": [{"to": to, "condition": head, "values": values} for (to, head), values in groups.items()],
        })
    return out


# --- 하위 명령 ----------------------------------------------------------------


def cmd_list(client: StudioClient, args: argparse.Namespace, out: Output, local: Any = None) -> int:
    rows = []
    for agent in client.list_agents():
        agent_id = agent.get("id")
        configs = client.list_configs(agent_id) if isinstance(agent_id, str) and _PATH_ID.fullmatch(agent_id) else []
        default = number_text(agent.get("default_config_external_id"))
        if default is None:
            chosen = [c for c in configs if c.get("is_default") is True]
            default = config_number(chosen[0]) if len(chosen) == 1 else None
        steps = agent.get("used_steps")
        rows.append({
            "name": out.text(agent.get("name")),
            "id": out.id(agent_id),
            "visibility": out.text(agent.get("visibility")) if agent.get("visibility") is not None else None,
            "config_count": len(configs),
            "default_config": out.text(default, 20) if default is not None else None,
            "used_steps": [out.text(s) for s in steps[:50]] if isinstance(steps, list) else None,
        })
    if args.json:
        out.json({"agents": rows})
        return EXIT_OK
    out.say(f"에이전트 {len(rows)}개")
    for row in rows:
        kinds = ", ".join(row["used_steps"]) if row["used_steps"] is not None else "?"
        out.say(f"- {row['name']} ({row['id']}) · 설정 {row['config_count']}개 · 기본 설정 {row['default_config'] or '?'} · 노드: {kinds}")
    return EXIT_OK


def cmd_show(client: StudioClient, args: argparse.Namespace, out: Output, local: Any = None) -> int:
    agent, item, full = load_config(client, args.agent, args.config, out.scrubber)
    steps = config_steps(full, "Studio 설정")
    graph = graph_lines(steps, out.scrubber)
    number = config_number(full) or config_number(item)
    number = out.text(number, 20) if number is not None else None
    is_default = full.get("is_default") if isinstance(full.get("is_default"), bool) else item.get("is_default") is True
    name = out.text(full.get("name") if isinstance(full.get("name"), str) else item.get("name"))
    config_id = out.id(full.get("id") if isinstance(full.get("id"), str) else item.get("id"))
    if args.json:
        out.json({
            "agent": {"name": out.text(agent.get("name")), "id": out.id(agent.get("id"))},
            "config": {"number": number, "name": name, "id": config_id, "is_default": bool(is_default)},
            "steps": graph,
        })
        return EXIT_OK
    out.say(f"에이전트 {out.text(agent.get('name'))} ({out.id(agent.get('id'))}) · 설정 {number or '?'} "
            f"'{name}' ({config_id}{', 기본' if is_default else ''}) · step {len(steps)}개")
    for index, step in enumerate(graph, 1):
        mark = "  (첫 단계)" if step["is_first"] else ("  (끝)" if not step["next"] else "")
        out.say(f"{index:2d}. [{step['type']}] {step['name']}{mark}")
        for nxt in step["next"]:
            cond = f"  {nxt['condition']} {' | '.join(nxt['values'])}" if nxt["condition"] else ""
            out.say(f"      → {nxt['to']}{cond}")
    return EXIT_OK


def cmd_export(client: StudioClient, args: argparse.Namespace, out: Output, local: Any = None) -> int:
    _, _, full = load_config(client, args.agent, args.config, out.scrubber)
    body = export_body(full)
    data = dump_config(body)
    path = Path(args.out)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    except OSError:
        raise StudioError(f"파일을 쓰지 못했습니다: {path}") from None
    if args.json:
        out.json({"out": str(path), "config": out.text(args.config, 20), "steps": len(body["steps"]), "bytes": len(data)})
    else:
        out.say(f"저장: {path} (설정 {out.text(args.config, 20)}, step {len(body['steps'])}개, {len(data):,} B)")
    return EXIT_OK


def cmd_diff(client: StudioClient, args: argparse.Namespace, out: Output, local: dict[str, Any] | None = None) -> int:
    """local 은 main 이 조회 전에 읽고 형식을 검사한 파일(없으면 여기서 읽고 검사한다)."""
    path = Path(args.file)
    if local is None:
        local = load_local(args, out)
        if local is None:
            return EXIT_ERROR
    _, _, full = load_config(client, args.agent, args.config, out.scrubber)
    studio_steps = config_steps(full, "Studio 설정")
    file_steps = [s for s in local["steps"] if isinstance(s, dict)]
    diffs = [{**d, "step": out.text(d["step"])} for d in diff_steps(file_steps, studio_steps, ids=args.ids)]
    keys = COMPARE_KEYS + (ID_KEYS if args.ids else ())
    if args.json:
        out.json({"same": not diffs, "file": str(path), "config": out.text(args.config, 20), "compared": list(keys),
                  "file_steps": len(file_steps), "studio_steps": len(studio_steps), "differences": diffs})
        return EXIT_OK if not diffs else EXIT_DIFFERENT
    where = f"{out.text(args.agent)} 설정 {out.text(args.config, 20)} ↔ {path}"
    if not diffs:
        out.say(f"같음 — {where} (step {len(studio_steps)}개, 비교: {'·'.join(keys)})")
        return EXIT_OK
    out.say(f"다름 — {where} (다른 step {len(diffs)}개, 비교: {'·'.join(keys)})")
    for d in diffs:
        if "fields" in d:
            out.say(f"  ~ {d['step']}: {', '.join(d['fields'])} 다름")
        elif d.get("only_in") == "file":
            out.say(f"  + {d['step']} (파일에만)")
        elif d.get("only_in") == "studio":
            out.say(f"  - {d['step']} (Studio 에만)")
        else:
            out.say(f"  ! {d['step']}: {d['problem']}")
    return EXIT_DIFFERENT


def load_local(args: argparse.Namespace, out: Output) -> dict[str, Any] | None:
    """diff·create 의 로컬 파일을 읽고 검사한다(설정·요청보다 먼저). 문제가 있으면 위치만 출력하고 None.

    create 는 형식 + 그래프(check_config), diff 는 형식(shape_problems) — 다른 내용은 diff 가 보여 준다.
    """
    body = read_config_file(Path(args.file))
    problems = check_config(body) if args.command == "create" else shape_problems(body)
    if problems:
        for problem in problems[:50]:
            out.error(problem)
        return None
    return body


def preview_create(body: Mapping[str, Any], args: argparse.Namespace, out: Output) -> int:
    """--yes 가 없을 때: 요청 0개, 할 일만 출력."""
    if args.json:
        out.json({"dry_run": True, "agent": out.text(args.agent), "config_name": out.text(body["name"]), "steps": len(body["steps"])})
        return EXIT_OK
    out.say("할 일(보내지 않음 — 실제로 하려면 --yes):")
    out.say(f"  1. 이름이 '{out.text(args.agent)}' 인 에이전트를 찾는다(없으면 private 로 만들고, 둘 이상이면 멈춘다)")
    out.say(f"  2. 설정 '{out.text(body['name'])}'(step {len(body['steps'])}개)을 더한다 — 새 설정 번호가 생기고 기본 설정이 된다")
    return EXIT_OK


def cmd_create(client: StudioClient, args: argparse.Namespace, out: Output, body: Mapping[str, Any] | None = None) -> int:
    """--yes 일 때. body 는 load_local 로 검사한 파일(없으면 여기서 읽고 검사한다)."""
    if body is None:
        body = load_local(args, out)
        if body is None:
            return EXIT_ERROR
    payload = {"name": body["name"], "steps": body["steps"]}
    agent_name = args.agent
    # 만들기 판단은 엄격하게 읽은 목록으로만(틀린 모양이면 POST 없이 멈춘다)
    matches = [a for a in client.list_agents(strict=True) if a["name"] == agent_name]
    if len(matches) > 1:
        raise StudioError(f"이름이 '{out.text(agent_name)}' 인 에이전트가 {len(matches)}개입니다 — 아무것도 보내지 않고 멈춥니다")
    created_agent = not matches
    agent = client.create_agent(agent_name) if created_agent else matches[0]
    agent_id = client._path_id(agent.get("id"), "에이전트")
    config = client.create_config(agent_id, payload)
    config_id = config.get("id")
    check = client.get_agent(agent_id)
    is_default = isinstance(config_id, str) and check.get("default_config_id") == config_id
    number = config_number(config)
    number = out.text(number, 20) if number is not None else None
    result = {
        "agent": {"name": out.text(agent_name), "id": out.id(agent_id), "created": created_agent},
        "config": {"number": number, "id": out.id(config_id), "steps": len(body["steps"]), "is_default": is_default},
    }
    if args.json:
        out.json(result)
        return EXIT_OK
    out.say(f"에이전트 {out.text(agent_name)} ({out.id(agent_id)}) — {'새로 만듦(private)' if created_agent else '이미 있음'}")
    out.say(f"설정 {number or '?'} ({out.id(config_id)}) 더함 · step {len(body['steps'])}개 · "
            f"{'기본 설정이 됨' if is_default else '기본 설정 아님 — Studio 에서 확인'}")
    return EXIT_OK


COMMANDS: dict[str, Callable[[StudioClient, argparse.Namespace, Output, Any], int]] = {
    "list": cmd_list,
    "show": cmd_show,
    "export": cmd_export,
    "diff": cmd_diff,
    "create": cmd_create,
}


@functools.lru_cache(maxsize=1)
def build_parser() -> argparse.ArgumentParser:
    """명령줄 해석기(한 번만 만든다 — parse_args 는 해석기를 바꾸지 않는다)."""
    common = CliParser(add_help=False)
    common.add_argument("--env-file", default=str(DEFAULT_ENV_FILE), help="UPSTAGE_API_KEY·UPSTAGE_PROJECT_ID 를 읽을 파일(기본: 저장소 루트 .env)")
    common.add_argument("--json", action="store_true", help="표 대신 JSON 으로 출력(id 는 줄여서)")
    parser = CliParser(prog="studio_workflow.py", description="Upstage Studio 워크플로우 보기·내보내기·비교·만들기")
    sub = parser.add_subparsers(dest="command", required=True, parser_class=CliParser)
    sub.add_parser("list", parents=[common], help="에이전트 목록")
    show = sub.add_parser("show", parents=[common], help="설정의 노드 그래프 요약")
    show.add_argument("--agent", required=True)
    show.add_argument("--config", help="설정 번호(external id). 없으면 기본 설정")
    export = sub.add_parser("export", parents=[common], help="설정을 파일로 저장")
    export.add_argument("--agent", required=True)
    export.add_argument("--config", required=True)
    export.add_argument("--out", required=True)
    diff = sub.add_parser("diff", parents=[common], help="파일과 Studio 설정 비교(같으면 0, 다르면 1)")
    diff.add_argument("--agent", required=True)
    diff.add_argument("--config", required=True)
    diff.add_argument("--ids", action="store_true", help="step id·node_id 도 비교")
    diff.add_argument("file")
    create = sub.add_parser("create", parents=[common], help="파일로 설정을 더한다(--yes 없으면 할 일만 출력)")
    create.add_argument("file")
    create.add_argument("--agent", required=True)
    create.add_argument("--yes", action="store_true", help="실제로 보낸다")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    transport: httpx.BaseTransport | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    environ: Mapping[str, str] | None = None,
) -> int:
    environ = os.environ if environ is None else environ
    try:
        args = build_parser().parse_args(argv)
    except CliUsageError as exc:
        # 해석 실패 — --env-file 을 알 수 없으므로 기본 환경 파일·환경변수에서 가릴 값을 모아 같은 경계로 낸다(R3)
        try:
            default_values = read_env_file(DEFAULT_ENV_FILE)
        except StudioError:
            default_values = {}
        scrubber = Scrubber()
        collect_secrets(scrubber, default_values, environ)
        Output(stdout or sys.stdout, stderr or sys.stderr, scrubber).error(exc.message)
        return EXIT_ERROR
    env_file = Path(args.env_file)
    # 1) 가릴 값부터(요청·필수 검사 없이, 없어도 오류 아님) — 이 뒤의 모든 출력이 이 Scrubber 를 지난다(N1)
    try:
        env_values, env_error = read_env_file(env_file), None
    except StudioError as exc:
        env_values, env_error = {}, exc
    scrubber = Scrubber()
    collect_secrets(scrubber, env_values, environ)
    out = Output(stdout or sys.stdout, stderr or sys.stderr, scrubber)
    try:
        # 2) 로컬 파일 검사(diff·create) — 문제가 있으면 설정·요청 없이 끝낸다
        local = None
        if args.command in ("create", "diff"):
            local = load_local(args, out)
            if local is None:
                return EXIT_ERROR
            if args.command == "create" and not args.yes:
                return preview_create(local, args, out)
        # 3) 필수 설정 → 요청
        if env_error is not None:
            raise env_error
        api_key, project_id = load_settings(env_file, environ, env_values)
        with StudioClient(api_key, project_id, transport=transport, scrubber=scrubber) as client:
            return COMMANDS[args.command](client, args, out, local)
    except StudioError as exc:
        out.error(exc.message)
        return EXIT_ERROR


def _setup_console() -> None:
    """Windows 콘솔·파이프에서 한글이 깨지지 않게 UTF-8 로 내보낸다."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    _setup_console()
    sys.exit(main())
