"""应用配置：从环境变量与 .env 加载。"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    """运行时配置。"""

    def __init__(self) -> None:
        self.host: str = os.getenv("HOST", "127.0.0.1").strip() or "127.0.0.1"
        try:
            self.port: int = int(os.getenv("PORT", "8090"))
        except ValueError:
            self.port = 8090
        self.debug: bool = _bool(os.getenv("DEBUG"), default=False)
        self.tz: str = os.getenv("TZ", "Asia/Shanghai").strip() or "Asia/Shanghai"

        # 访问密钥：为空表示不启用鉴权（保持旧的完全开放行为）
        self.key: str = os.getenv("KEY", "").strip()

        data_file = os.getenv("DATA_FILE", "data/navigation.yml").strip()
        path = Path(data_file)
        self.data_file: Path = path if path.is_absolute() else (ROOT_DIR / path)
        self.data_backup: Path = self.data_file.with_suffix(self.data_file.suffix + ".bak")
        self.icon_dir: Path = self.data_file.parent / "icon"

        example = os.getenv("EXAMPLE_FILE", "").strip()
        example_path = Path(example) if example else (ROOT_DIR / "data" / "navigation.yml.example")
        self.example_file: Path = (
            example_path if example_path.is_absolute() else (ROOT_DIR / example_path)
        )


settings = Settings()
