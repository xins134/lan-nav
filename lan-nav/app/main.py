"""FastAPI 应用入口。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import ROOT_DIR, settings
from app.routes import AdminAuthError, api, pages
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
        "lan-nav 已启动 | host=%s port=%s debug=%s admin_protected=%s",
        settings.host,
        settings.port,
        settings.debug,
        settings.admin_protected,
    )
    yield


app = FastAPI(title="lan-nav", docs_url=None, redoc_url=None, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(ROOT_DIR / "app" / "static")), name="static")
app.include_router(api)
app.include_router(pages)


@app.exception_handler(AdminAuthError)
async def admin_auth_handler(_request: Request, _exc: AdminAuthError) -> JSONResponse:
    return JSONResponse(
        {"success": False, "error": {"code": "UNAUTHORIZED", "message": "需要有效的管理 Token"}},
        status_code=401,
    )


@app.exception_handler(StorageError)
async def storage_handler(_request: Request, exc: StorageError) -> JSONResponse:
    status = 404 if exc.code == "NOT_FOUND" else 403 if exc.code == "FORBIDDEN" else 400
    return JSONResponse(
        {"success": False, "error": {"code": exc.code, "message": exc.message}},
        status_code=status,
    )
