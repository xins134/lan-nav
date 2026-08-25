"""YAML 原子读写、备份与恢复。"""

from __future__ import annotations

import logging
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Callable, TypeVar

import yaml
from pydantic import ValidationError

from app.config import settings
from app.models import Category, Link, NavigationData, SiteConfig, new_id

logger = logging.getLogger("lan-nav.storage")

T = TypeVar("T")

UNCATEGORIZED_ID = "00000000-0000-4000-8000-000000000000"
UNCATEGORIZED_NAME = "未分类"

_lock = threading.RLock()


class StorageError(Exception):
    """存储层错误。"""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def _build_demo_data() -> NavigationData:
    """首次运行时的演示数据：至少 4 分类、12 链接。"""
    cats = [
        Category(
            id=new_id(),
            name="家庭服务",
            description="媒体、存储与自动化",
            icon="house",
            color="#8b5cf6",
            order=10,
        ),
        Category(
            id=new_id(),
            name="开发工具",
            description="代码、文档与调试",
            icon="code-2",
            color="#06b6d4",
            order=20,
        ),
        Category(
            id=new_id(),
            name="网络设备",
            description="路由、交换机与监控",
            icon="router",
            color="#10b981",
            order=30,
        ),
        Category(
            id=new_id(),
            name="娱乐休闲",
            description="影音与个人站点",
            icon="clapperboard",
            color="#f59e0b",
            order=40,
        ),
        Category(
            id=UNCATEGORIZED_ID,
            name=UNCATEGORIZED_NAME,
            description="尚未归类的链接",
            icon="inbox",
            color="#64748b",
            order=9999,
        ),
    ]
    c0, c1, c2, c3 = cats[0], cats[1], cats[2], cats[3]
    links = [
        Link(
            category_id=c0.id,
            title="NAS",
            url="http://192.168.1.10:5000",
            description="家庭存储与文件管理",
            tags=["存储", "家庭"],
            icon="hard-drive",
            color="#6366f1",
            pinned=True,
            order=10,
        ),
        Link(
            category_id=c0.id,
            title="Home Assistant",
            url="http://192.168.1.20:8123",
            description="智能家居控制中心",
            tags=["自动化", "IoT"],
            icon="home",
            color="#18bcf2",
            pinned=True,
            order=20,
        ),
        Link(
            category_id=c0.id,
            title="打印机",
            url="http://192.168.1.30",
            description="局域网打印机管理页",
            tags=["打印"],
            icon="printer",
            color="#a78bfa",
            order=30,
        ),
        Link(
            category_id=c1.id,
            title="GitLab",
            url="http://192.168.1.40:8080",
            description="私有代码仓库",
            tags=["Git", "CI"],
            icon="git-branch",
            color="#fc6d26",
            pinned=True,
            order=10,
        ),
        Link(
            category_id=c1.id,
            title="文档站",
            url="http://192.168.1.40:3000",
            description="团队内部 Wiki",
            tags=["文档"],
            icon="book-open",
            color="#3b82f6",
            order=20,
        ),
        Link(
            category_id=c1.id,
            title="Portainer",
            url="http://192.168.1.50:9000",
            description="容器管理面板",
            tags=["Docker"],
            icon="container",
            color="#0ea5e9",
            order=30,
        ),
        Link(
            category_id=c1.id,
            title="API 调试",
            url="http://192.168.1.40:9090",
            description="本地接口调试工具",
            tags=["API"],
            icon="terminal",
            color="#22c55e",
            status="warning",
            order=40,
        ),
        Link(
            category_id=c2.id,
            title="主路由",
            url="http://192.168.1.1",
            description="网关与 Wi-Fi 管理",
            tags=["网络"],
            icon="wifi",
            color="#14b8a6",
            pinned=True,
            order=10,
        ),
        Link(
            category_id=c2.id,
            title="交换机",
            url="http://192.168.1.2",
            description="核心交换管理",
            tags=["网络"],
            icon="network",
            color="#84cc16",
            order=20,
        ),
        Link(
            category_id=c2.id,
            title="流量监控",
            url="http://192.168.1.3:3001",
            description="带宽与设备流量",
            tags=["监控"],
            icon="activity",
            color="#ef4444",
            order=30,
        ),
        Link(
            category_id=c3.id,
            title="Jellyfin",
            url="http://192.168.1.10:8096",
            description="家庭影音库",
            tags=["影音"],
            icon="film",
            color="#aa5cc3",
            order=10,
        ),
        Link(
            category_id=c3.id,
            title="音乐服务器",
            url="http://192.168.1.10:4533",
            description="本地音乐流媒体",
            tags=["音乐"],
            icon="music",
            color="#ec4899",
            order=20,
        ),
        Link(
            category_id=c3.id,
            title="个人博客",
            url="https://example.com",
            description="对外博客站点",
            tags=["博客"],
            icon="globe",
            color="#64748b",
            status="offline",
            order=30,
        ),
    ]
    return NavigationData(
        site=SiteConfig(
            title="我的局域网导航",
            subtitle="常用服务与工具",
            theme="system",
        ),
        categories=cats,
        links=links,
    )


def ensure_uncategorized(data: NavigationData) -> NavigationData:
    """确保存在「未分类」分类。"""
    found = next((c for c in data.categories if c.id == UNCATEGORIZED_ID), None)
    if found is None:
        found = next((c for c in data.categories if c.name == UNCATEGORIZED_NAME), None)
        if found is None:
            data.categories.append(
                Category(
                    id=UNCATEGORIZED_ID,
                    name=UNCATEGORIZED_NAME,
                    description="尚未归类的链接",
                    icon="inbox",
                    color="#64748b",
                    order=9999,
                )
            )
        else:
            found.id = UNCATEGORIZED_ID
            found.order = max(found.order, 9999)
    return data


def _parse_yaml_text(text: str) -> NavigationData:
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise StorageError("INVALID_DATA", f"YAML 解析失败: {exc}") from exc
    if raw is None:
        raise StorageError("EMPTY_DATA", "YAML 内容为空")
    if not isinstance(raw, dict):
        raise StorageError("INVALID_DATA", "YAML 根节点必须是对象")
    try:
        data = NavigationData.model_validate(raw)
    except ValidationError as exc:
        raise StorageError("VALIDATION_ERROR", str(exc)) from exc
    return ensure_uncategorized(data)


def _dump_yaml(data: NavigationData) -> str:
    payload = {
        "site": data.site.model_dump(),
        "categories": [c.model_dump() for c in data.sorted_categories()],
        "links": [lk.model_dump() for lk in data.sorted_links()],
    }
    return yaml.safe_dump(
        payload,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with open(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            import os

            os.fsync(fh.fileno())
        tmp_path.replace(path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


def _read_file(path: Path) -> NavigationData:
    text = path.read_text(encoding="utf-8")
    return _parse_yaml_text(text)


def initialize_storage() -> NavigationData:
    """启动时初始化：生成、恢复或加载数据。"""
    with _lock:
        data_file = settings.data_file
        backup = settings.data_backup
        example = settings.example_file

        if not data_file.exists():
            if example.exists():
                try:
                    data = _read_file(example)
                    logger.info("从示例文件初始化数据: %s", example)
                except StorageError:
                    logger.warning("示例文件无效，改用内置演示数据")
                    data = _build_demo_data()
            else:
                data = _build_demo_data()
                logger.info("使用内置演示数据初始化")
            _atomic_write(data_file, _dump_yaml(data))
            return data

        try:
            data = _read_file(data_file)
            logger.info("已加载导航数据: %s", data_file)
            return data
        except StorageError as exc:
            logger.error("主 YAML 损坏: %s", exc.message)
            if backup.exists():
                try:
                    data = _read_file(backup)
                    logger.warning("已从备份恢复: %s", backup)
                    _atomic_write(data_file, _dump_yaml(data))
                    return data
                except StorageError as bak_exc:
                    logger.error("备份也无效: %s", bak_exc.message)
            raise StorageError(
                "CORRUPT_DATA",
                "导航数据损坏且无法从备份恢复，请检查 data/navigation.yml",
            ) from exc


def load_data() -> NavigationData:
    with _lock:
        if not settings.data_file.exists():
            return initialize_storage()
        return _read_file(settings.data_file)


def save_data(data: NavigationData) -> NavigationData:
    """校验并原子写入；写入前备份。"""
    with _lock:
        data = ensure_uncategorized(data)
        # 再次校验
        data = NavigationData.model_validate(data.model_dump())
        content = _dump_yaml(data)
        data_file = settings.data_file
        backup = settings.data_backup
        data_file.parent.mkdir(parents=True, exist_ok=True)
        if data_file.exists():
            shutil.copy2(data_file, backup)
        _atomic_write(data_file, content)
        return data


def mutate(fn: Callable[[NavigationData], T]) -> T:
    """在锁内读取、修改、保存。"""
    with _lock:
        data = load_data()
        result = fn(data)
        save_data(data)
        return result
