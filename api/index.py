# ==========================================================================
#  iMASK FastAPI 백엔드 진입점 — Vercel Python 함수(api/index.py) · 로컬 uvicorn 공용
#  Vercel 은 api/ 안의 .py 파일마다 함수를 만들므로 이 폴더에는 이 파일 하나만 둔다.
#  업무 로직은 imask_backend/ 에 있고, 여기는 경로·의존성·접근 코드·오류 모양만 다룬다.
#
#  경로(모두 /api/py 아래. Next rewrites 가 /api/py/:path* 를 이 함수로 보낸다):
#    GET  /api/py/health                   접근 코드 없이. 설정이 있는지만(값은 넣지 않음)
#    POST /api/py/analyses                 분석 건 + 서명 업로드 URL 만들기 → 201
#    POST /api/py/analyses/{id}/start      Upstage 작업 시작(완료를 기다리지 않음) → 200
#    GET  /api/py/analyses/{id}            조회. running 이면 Upstage 상태를 한 번 확인 → 200
#  /api/py/analyses 로 시작하는 요청은 본문 검사·404 판정보다 먼저 X-Demo-Code 를 DEMO_ACCESS_CODE 와
#  hmac.compare_digest 로 비교한다(미들웨어). 오류 본문은 늘 {"detail": "<짧은 한국어 문장>"}.
#  설정은 요청 때 읽는다(get_settings 캐시) — 환경변수가 빠져도 import 는 실패하지 않는다.
#
#  로컬: .venv\Scripts\python.exe -m uvicorn api.index:app --port 8000 --env-file .env
# ==========================================================================

from __future__ import annotations

import hmac
import logging
import sys
import traceback
from collections.abc import Iterator
from http import HTTPStatus
from pathlib import Path
from typing import Annotated, Any

# Vercel 은 프로젝트 파일을 같은 상대 경로로 묶고 작업 폴더를 프로젝트 루트로 둔다.
# 저장소 루트를 sys.path 에 넣어 imask_backend 를 import 한다(로컬 uvicorn 도 같다).
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import Depends, FastAPI, Request  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from pydantic import BaseModel, Field, StrictInt, StrictStr  # noqa: E402
from starlette.exceptions import HTTPException as StarletteHTTPException  # noqa: E402

from imask_backend.analyses import (  # noqa: E402
    ApiError,
    UpstageFactory,
    analysis_out,
    create_analysis,
    poll_analysis,
    start_analysis,
)
from imask_backend.config import ConfigError  # noqa: E402
from imask_backend.redaction import redact  # noqa: E402
from imask_backend.settings import Settings, get_settings  # noqa: E402
from imask_backend.store import Store, StoreError, cached_store  # noqa: E402
from imask_backend.upstage import UpstageClient  # noqa: E402

ACCESS_HEADER = "x-demo-code"
GUARDED_PREFIX = "/api/py/analyses"

MSG_BAD_ACCESS = "접근 코드가 맞지 않습니다."
MSG_NO_ACCESS_CODE = "서버에 접근 코드가 설정되지 않았습니다."
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
            # 서버 비밀값 전체(Supabase 비밀 키·접근 코드 포함)를 넘겨 오류 문구를 자르기 전에 가리게 한다
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


# --- 접근 코드 (본문 검사·라우팅보다 먼저) ---------------------------------------------


@app.middleware("http")
async def require_access_code(request: Request, call_next: Any) -> Any:
    if request.url.path.startswith(GUARDED_PREFIX):
        expected = _settings_for(request).access_code
        if not expected:
            return _detail(500, MSG_NO_ACCESS_CODE)
        given = request.headers.get(ACCESS_HEADER, "")
        # 헤더는 latin-1 로 풀려 오므로 같은 방식으로 바이트로 되돌려 비교한다(비 ASCII 도 예외 없이)
        if not hmac.compare_digest(given.encode("latin-1", "replace"), expected.encode("utf-8")):
            return _detail(401, MSG_BAD_ACCESS)
    return await call_next(request)


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
    """처리하지 못한 예외 → 500 JSON. 맨 바깥 미들웨어(나중에 붙인 것이 바깥)라 접근 코드 검사도 감싼다.

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


# --- 경로 -------------------------------------------------------------------------


@app.get("/api/py/health")
def health(settings: SettingsDep) -> dict[str, Any]:
    return {"ok": True, "configured": settings.configured()}


@app.post("/api/py/analyses", status_code=201)
def create(body: CreateAnalysisIn, store: StoreDep) -> dict[str, Any]:
    row, upload = create_analysis(
        store, name=body.name, filename=body.filename, size=body.size, mime_type=body.mime_type
    )
    return {"analysis": analysis_out(row), "upload": upload}


@app.post("/api/py/analyses/{analysis_id}/start")
def start(analysis_id: str, store: StoreDep, upstage: UpstageDep, settings: SettingsDep) -> dict[str, Any]:
    return analysis_out(start_analysis(store, upstage, settings, analysis_id))


@app.get("/api/py/analyses/{analysis_id}")
def read(analysis_id: str, store: StoreDep, upstage: UpstageDep, settings: SettingsDep) -> dict[str, Any]:
    polled = poll_analysis(store, upstage, settings, analysis_id)
    return analysis_out(polled.row, upstage_status=polled.upstage_status, poll_error=polled.poll_error)
