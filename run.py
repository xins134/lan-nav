#!/usr/bin/env python3
"""本地启动入口。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int | None) -> int | None:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def main() -> None:
    import uvicorn

    # 同步时区环境变量，便于日志与系统行为一致
    if settings.tz:
        os.environ.setdefault("TZ", settings.tz)

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        reload_dirs=[str(ROOT / "app")] if settings.debug else None,
        # 精简运行时：单进程、纯 asyncio + h11、关闭 WebSocket，省内存与 CPU。
        # 如需更高吞吐可自行安装 uvloop/httptools 并通过环境变量切换。
        loop=os.getenv("UVICORN_LOOP", "asyncio"),
        http=os.getenv("UVICORN_HTTP", "h11"),
        ws="none",
        # 个人导航页无需逐请求访问日志，默认关闭以省 CPU / IO。
        access_log=_env_flag("ACCESS_LOG", False),
        server_header=False,
        date_header=False,
        proxy_headers=True,
        forwarded_allow_ips=os.getenv("FORWARDED_ALLOW_IPS", "127.0.0.1"),
        timeout_keep_alive=_env_int("KEEPALIVE_TIMEOUT", 5),
        limit_concurrency=_env_int("LIMIT_CONCURRENCY", None),
    )


if __name__ == "__main__":
    main()
