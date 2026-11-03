# ==========================================================================
#  iMASK FastAPI 백엔드 진입점 — Vercel Python 함수(api/index.py) · 로컬 uvicorn 공용
#  Vercel 은 api/ 안의 .py 파일마다 함수를 만들므로 이 폴더에는 이 파일 하나만 둔다.
#  업무 로직은 imask_backend/ 에 있고, 여기는 경로·의존성·오류 모양만 다룬다.
#
#  경로(모두 /api/py 아래. Next rewrites 가 /api/py/:path* 를 이 함수로 보낸다):
#    GET  /api/py/health                   설정이 있는지만(값은 넣지 않음)
#    POST /api/py/analyses                 분석 건 + 서명 업로드 URL 만들기 → 201
#    POST /api/py/analyses/{id}/start      Upstage 작업 시작(완료를 기다리지 않음) → 200
#    GET  /api/py/analyses/{id}            조회. running 이면 Upstage 상태를 한 번 확인 → 200
#                                          result 는 documents·findings·overall(?include=stages 면 stages 도),
#                                          review 는 검토 블록(검토할 수 있는 분석만, 검토 행을 읽지 못하면 null)
#    GET  /api/py/analyses/{id}/file       원본 파일 서명 다운로드 URL(10분) → 200, Cache-Control: no-store
#    POST /api/py/analyses/{id}/review-actions
#                                          검토 동작 하나 저장(imask_backend.reviews) → 200 {"analysis", "changed"}
#                                          본문은 직접 읽는다: 65,536 바이트를 넘으면 그 자리에서 413(Content-Length 없이도),
#                                          JSON·필드 검사 400. Upstage 를 부르지 않는다(의존성도 받지 않음).
#  분석 건·원본 파일 응답은 _json_out 한 곳을 지난다 — 짝 없는 서로게이트가 있을 때만 ASCII escape JSON(이름·값 원문
#  그대로), 없으면 정상 경로 그대로(바이트 불변). 상태 코드·헤더는 같다.
#  접근 코드(X-Demo-Code)는 받지 않는다(2026-11-03 없앰 — 팀만 아는 주소, 대회용 API). 오류 본문은 늘 {"detail": "<짧은 한국어 문장>"}.
#  설정은 요청 때 읽는다(get_settings 캐시) — 환경변수가 빠져도 import 는 실패하지 않는다.
#
#  로컬: .venv\Scripts\python.exe -m uvicorn api.index:app --port 8000 --env-file .env
# ==========================================================================

from __future__ import annotations

import logging
import sys
import traceback
from collections.abc import Iterator, Mapping
from http import HTTPStatus
from pathlib import Path
from typing import Annotated, Any

# Vercel 은 프로젝트 파일을 같은 상대 경로로 묶고 작업 폴더를 프로젝트 루트로 둔다.
# 저장소 루트를 sys.path 에 넣어 imask_backend 를 import 한다(로컬 uvicorn 도 같다).
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import Depends, FastAPI, Query, Request  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.responses import JSONResponse, Response  # noqa: E402
from pydantic import BaseModel, Field, StrictInt, StrictStr  # noqa: E402
from starlette.concurrency import run_in_threadpool  # noqa: E402
from starlette.exceptions import HTTPException as StarletteHTTPException  # noqa: E402
from starlette.requests import ClientDisconnect  # noqa: E402

from imask_backend.analyses import (  # noqa: E402
    ApiError,
    UpstageFactory,
    analysis_out,
    create_analysis,
    file_link,
    poll_analysis,
    start_analysis,
)
from imask_backend.config import ConfigError  # noqa: E402
from imask_backend.redaction import redact  # noqa: E402
from imask_backend.reviews import (  # noqa: E402
    MAX_BODY_BYTES,
    MSG_BODY_TOO_LARGE,
    analysis_read_out,
    parse_action,
    review_action_out,
)
from imask_backend.settings import Settings, get_settings  # noqa: E402
from imask_backend.store import Store, StoreError, cached_store  # noqa: E402
from imask_backend.textsafe import escaped_json_bytes, has_unpaired_surrogates  # noqa: E402
from imask_backend.upstage import UpstageClient  # noqa: E402

MSG_BAD_REQUEST = "요청 형식이 올바르지 않습니다."
MSG_CONFIG_MISSING = "서버 설정이 빠졌습니다: {names}"
MSG_STORE_FAILED = "데이터 저장소에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요."
MSG_SERVER_ERROR = "서버 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
# Starlette 기본 영어 문구 → 한국어
DEFAULT_DETAILS = {
    404: "요청한 주소를 찾을 수 없습니다.",
    405: "허용되지 않은 요청 방식입니다.",
}


def _setup_logging() -> None:
    """imask.* 로그를 표준 오류로(Vercel 함수 로그·uvicorn 콘솔에 보인다). 값은 넣지 않는다."""
    logger = logging.getLogger("imask")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False


_setup_logging()
logger = logging.getLogger("imask.api")

app = FastAPI(
    title="iMASK API",
    docs_url="/api/py/docs",
    redoc_url=None,
    openapi_url="/api/py/openapi.json",
)


# --- 의존성 (테스트는 app.dependency_overrides 로 바꾼다) ----------------------------


def get_store(settings: Annotated[Settings, Depends(get_settings)]) -> Store:
    """Supabase 저장소(설정마다 클라이언트 하나). 설정이 빠졌으면 ConfigError → 500."""
    return cached_store(settings)


def get_upstage(settings: Annotated[Settings, Depends(get_settings)]) -> Iterator[UpstageFactory]:
    """Upstage 클라이언트를 필요할 때 처음 한 번 만든다(조회가 Upstage 를 부르지 않으면 만들지 않음)."""
    clients: list[UpstageClient] = []

    def factory() -> UpstageClient:
        if not clients:
            # 서버 비밀값 전체(Supabase 비밀 키 포함)를 넘겨 오류 문구를 자르기 전에 가리게 한다
            clients.append(UpstageClient.from_settings(settings.upstage(), extra_secrets=settings.secrets()))
        return clients[0]

    try:
        yield factory
    finally:
        for client in clients:
            client.close()


SettingsDep = Annotated[Settings, Depends(get_settings)]
StoreDep = Annotated[Store, Depends(get_store)]
UpstageDep = Annotated[UpstageFactory, Depends(get_upstage)]


def _settings_for(request: Request) -> Settings:
    """미들웨어는 Depends 를 못 쓰므로 같은 의존성(바꿔 끼운 것 포함)을 직접 부른다."""
    provider = request.app.dependency_overrides.get(get_settings, get_settings)
    return provider()


def _detail(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail})


# --- 오류 모양 --------------------------------------------------------------------


@app.exception_handler(ApiError)
def _api_error(_: Request, exc: ApiError) -> JSONResponse:
    return _detail(exc.status_code, exc.detail)


@app.exception_handler(RequestValidationError)
def _validation_error(_: Request, __: RequestValidationError) -> JSONResponse:
    # FastAPI 기본 422 대신 400(본문이 JSON 이 아니거나 필드 타입이 틀림)
    return _detail(400, MSG_BAD_REQUEST)


@app.exception_handler(ConfigError)
def _config_error(_: Request, exc: ConfigError) -> JSONResponse:
    # 이름만 알린다(값은 ConfigError 에 들어 있지 않다)
    logger.error("환경변수가 빠짐: %s", ", ".join(exc.missing))
    return _detail(500, MSG_CONFIG_MISSING.format(names=", ".join(exc.missing)))


@app.exception_handler(StoreError)
def _store_error(_: Request, exc: StoreError) -> JSONResponse:
    logger.warning("저장소 오류: %s", exc.message)  # 이미 가린 문구
    return _detail(502, MSG_STORE_FAILED)


@app.exception_handler(StarletteHTTPException)
def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail
    try:
        phrase = HTTPStatus(exc.status_code).phrase
    except ValueError:
        phrase = ""
    if not isinstance(detail, str) or detail == phrase:
        detail = DEFAULT_DETAILS.get(exc.status_code, MSG_SERVER_ERROR if exc.status_code >= 500 else MSG_BAD_REQUEST)
    return JSONResponse(status_code=exc.status_code, content={"detail": detail}, headers=exc.headers)


@app.middleware("http")
async def catch_unexpected(request: Request, call_next: Any) -> Any:
    """처리하지 못한 예외 → 500 JSON. 맨 바깥 미들웨어(나중에 붙인 것이 바깥)라 모든 처리를 감싼다.

    Exception 처리기를 쓰면 Starlette 가 응답 뒤 예외를 다시 던져 서버가 가리지 않은 traceback 을
    찍으므로, 여기서 잡아 가린 traceback 만 남긴다(예외 문구에 요청 정보가 섞일 수 있어서).
    """
    try:
        return await call_next(request)
    except Exception as exc:
        try:
            secrets = _settings_for(request).secrets()
        except Exception:
            secrets = {}
        logger.error("처리하지 못한 오류:\n%s", redact("".join(traceback.format_exception(exc)), secrets))
        return _detail(500, MSG_SERVER_ERROR)


# --- 요청 모양 --------------------------------------------------------------------


class CreateAnalysisIn(BaseModel):
    """타입만 엄격히 본다(문자열 숫자·불리언 크기 거부). 값 범위는 imask_backend.files 가 본다."""

    name: StrictStr | None = None
    filename: StrictStr
    size: StrictInt = Field(...)
    mime_type: StrictStr


# --- 응답 도우미 -------------------------------------------------------------------


def _json_out(content: Any, *, status_code: int = 200, headers: Mapping[str, str] | None = None) -> Any:
    """분석 건·원본 파일 응답의 한 경계(코디네이터 결정 T1-fix5).

    짝 없는 서로게이트가 **하나라도 있을 때만** ASCII escape JSON 본문(textsafe.escaped_json_bytes — 이름·값 원문 그대로,
    NaN·inf 는 null)을 Response 로 돌려준다(상태 코드·헤더 그대로). 없으면 지금 경로 그대로 — 헤더가 없으면 dict 를
    돌려줘 FastAPI 가 직렬화하고(정상 응답 바이트 불변), 헤더가 있으면 JSONResponse.
    """
    if has_unpaired_surrogates(content):
        body = escaped_json_bytes(content)
        return Response(content=body, status_code=status_code, media_type="application/json", headers=dict(headers or {}))
    if headers:
        return JSONResponse(content=content, status_code=status_code, headers=dict(headers))
    return content


# --- 경로 -------------------------------------------------------------------------


@app.get("/api/py/health")
def health(settings: SettingsDep) -> dict[str, Any]:
    return {"ok": True, "configured": settings.configured()}


# 분석 건 경로는 _json_out 이 Response 를 돌려줄 수 있어 반환 타입을 Any 로 두고 응답 모양은 response_model 로 적는다
@app.post("/api/py/analyses", status_code=201, response_model=dict[str, Any])
def create(body: CreateAnalysisIn, store: StoreDep) -> Any:
    row, upload = create_analysis(
        store, name=body.name, filename=body.filename, size=body.size, mime_type=body.mime_type
    )
    return _json_out({"analysis": analysis_out(row), "upload": upload}, status_code=201)


@app.post("/api/py/analyses/{analysis_id}/start", response_model=dict[str, Any])
def start(analysis_id: str, store: StoreDep, upstage: UpstageDep, settings: SettingsDep) -> Any:
    return _json_out(analysis_out(start_analysis(store, upstage, settings, analysis_id)))


def _include_tokens(values: list[str] | None) -> set[str]:
    """?include= 를 여러 번 또는 쉼표로. 모르는 값은 무시한다(오류 아님)."""
    return {token.strip().lower() for value in values or [] for token in value.split(",") if token.strip()}


@app.get("/api/py/analyses/{analysis_id}", response_model=dict[str, Any])
def read(
    analysis_id: str,
    store: StoreDep,
    upstage: UpstageDep,
    settings: SettingsDep,
    include: Annotated[list[str] | None, Query()] = None,
) -> Any:
    polled = poll_analysis(store, upstage, settings, analysis_id)
    # review 블록: 검토할 수 있는 분석만 검토 행을 읽는다(실패하면 review: null — 조회는 그대로 200)
    return _json_out(
        analysis_read_out(
            store,
            polled.row,
            include_stages="stages" in _include_tokens(include),
            upstage_status=polled.upstage_status,
            poll_error=polled.poll_error,
        )
    )


@app.get("/api/py/analyses/{analysis_id}/file")
def original_file(analysis_id: str, store: StoreDep) -> Response:
    # 서명 URL 은 10분짜리 권한이라 캐시에 남기지 않는다(로그에도 쓰지 않음)
    return _json_out(file_link(store, analysis_id), headers={"Cache-Control": "no-store"})


_DIGITS = frozenset("0123456789")


def _declared_too_large(length: str | None, limit: int) -> bool:
    """Content-Length(십진 숫자만)가 limit 을 넘는지. 앞 0 을 떼고 자릿수·값으로 비교한다(아주 긴 숫자도 정수로 바꾸지 않음).

    숫자가 아니면(없음·빈 값·다른 글자) False — 실제로 읽은 바이트로 판단한다.
    """
    if not length or not set(length) <= _DIGITS:
        return False
    digits = length.lstrip("0") or "0"
    bound = str(limit)
    return len(digits) > len(bound) or (len(digits) == len(bound) and digits > bound)


async def _read_body(request: Request, limit: int = MAX_BODY_BYTES) -> bytes:
    """본문을 limit 바이트까지만 읽는다. Content-Length 가 넘거나 실제로 읽은 바이트가 넘으면 그 자리에서 413.

    Content-Length 가 없어도(chunked) 다 읽기 전에 끊는다. 클라이언트가 끊으면 400.
    """
    if _declared_too_large(request.headers.get("content-length"), limit):
        raise ApiError(413, MSG_BODY_TOO_LARGE)
    body = bytearray()
    try:
        async for chunk in request.stream():
            body += chunk
            if len(body) > limit:
                raise ApiError(413, MSG_BODY_TOO_LARGE)
    except ClientDisconnect:
        raise ApiError(400, MSG_BAD_REQUEST) from None
    return bytes(body)


@app.post("/api/py/analyses/{analysis_id}/review-actions", response_model=dict[str, Any])
async def review_action(analysis_id: str, request: Request, store: StoreDep) -> Any:
    # 오류 순서: 413(본문 크기) → 400(본문) → 404·409(imask_backend.reviews). Upstage 의존성은 받지 않는다.
    action = parse_action(await _read_body(request))
    # 저장소 호출은 블로킹이라 스레드 풀에서(조회 경로처럼)
    return _json_out(await run_in_threadpool(review_action_out, store, analysis_id, action))
