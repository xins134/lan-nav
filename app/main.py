"""FastAPI 应用入口。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import ROOT_DIR, settings
from app.routes import api, pages
from app.storage import StorageError, initialize_storage

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("lan-nav")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        initialize_storage()
    except StorageError as exc:
        logger.error("启动时数据初始化失败: %s", exc.message)
        raise
    logger.info(
        "lan-nav 已启动 | host=%s port=%s debug=%s",
        settings.host,
        settings.port,
        settings.debug,
    )
    yield


app = FastAPI(
    title="lan-nav",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=str(ROOT_DIR / "app" / "static")), name="static")
app.include_router(api)
app.include_router(pages)


def _error_payload(code: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        {"success": False, "error": {"code": code, "message": message}},
        status_code=status_code,
    )


@app.exception_handler(StorageError)
async def storage_handler(_request: Request, exc: StorageError) -> JSONResponse:
    status = 404 if exc.code == "NOT_FOUND" else 403 if exc.code == "FORBIDDEN" else 400
    if exc.code in {"CORRUPT_DATA", "IO_ERROR"}:
        status = 503
    return _error_payload(exc.code, exc.message, status)


@app.exception_handler(RequestValidationError)
async def validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    msg = "请求参数无效"
    errors = exc.errors()
    if errors:
        item = errors[0]
        loc = ".".join(str(part) for part in item.get("loc", []) if part != "body")
        detail = str(item.get("msg") or msg)
        msg = f"{loc}: {detail}" if loc else detail
    return _error_payload("VALIDATION_ERROR", msg, 422)


@app.exception_handler(StarletteHTTPException)
async def http_exc_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return _error_payload("HTTP_ERROR", str(exc.detail), exc.status_code)


@app.exception_handler(Exception)
async def unhandled_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("未处理异常: %s", exc)
    return _error_payload("INTERNAL", "服务器内部错误", 500)
