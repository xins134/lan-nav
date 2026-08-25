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
    )


if __name__ == "__main__":
    main()
