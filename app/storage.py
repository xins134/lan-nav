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
from app.archive import ArchiveError, build_export_zip, extract_import_zip
from app.icons import persist_icon, prune_icons
from app.models import Category, Link, NavigationData, SiteConfig, new_id

logger = logging.getLogger("lan-nav.storage")

T = TypeVar("T")

UNCATEGORIZED_ID = "00000000-0000-4000-8000-000000000000"
UNCATEGORIZED_NAME = "未分类"

_lock = threading.RLock()

# 内存缓存：以 (mtime, size, inode) 为键，命中时不再重复解析 YAML + 校验模型。
_cache: "NavigationData | None" = None
_cache_key: tuple[int, int, int] | None = None


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
    """确保存在「未分类」分类，并把孤立链接归入其中。"""
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
            old_id = found.id
            found.id = UNCATEGORIZED_ID
            found.order = max(found.order, 9999)
            if old_id != UNCATEGORIZED_ID:
                for lk in data.links:
                    if lk.category_id == old_id:
                        lk.category_id = UNCATEGORIZED_ID
    valid_ids = {c.id for c in data.categories}
    for lk in data.links:
        if lk.category_id not in valid_ids:
            lk.category_id = UNCATEGORIZED_ID
    return data


def _parse_yaml_text(text: str) -> NavigationData:
    try:
        raw = yaml.safe_load((text or "").lstrip("\ufeff"))
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
        width=10000,
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
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise StorageError("IO_ERROR", f"无法读取数据文件: {exc}") from exc
    return _parse_yaml_text(text)


def _stat_key(path: Path) -> tuple[int, int, int] | None:
    """文件状态指纹；用于判断磁盘数据是否变化。"""
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size, st.st_ino)


def _remember(data: NavigationData) -> NavigationData:
    """写入内存缓存并返回该对象。"""
    global _cache, _cache_key
    _cache = data
    _cache_key = _stat_key(settings.data_file)
    return data


def invalidate_cache() -> None:
    """外部改动磁盘数据后，强制下次重新解析。"""
    global _cache, _cache_key
    _cache = None
    _cache_key = None


def initialize_storage() -> NavigationData:
    """启动时初始化：生成、恢复或加载数据。"""
    with _lock:
        data_file = settings.data_file
        backup = settings.data_backup
        example = settings.example_file
        data_file.parent.mkdir(parents=True, exist_ok=True)
        settings.icon_dir.mkdir(parents=True, exist_ok=True)
        for tmp in data_file.parent.glob(data_file.name + ".*.tmp"):
            try:
                tmp.unlink()
            except OSError:
                pass

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
            return _remember(data)

        try:
            data = _read_file(data_file)
            logger.info("已加载导航数据: %s", data_file)
            if any(
                (lk.icon_url or "").startswith(("data:", "http://", "https://"))
                for lk in data.links
            ):
                return save_data(data)
            return _remember(data)
        except StorageError as exc:
            logger.error("主 YAML 损坏: %s", exc.message)
            if backup.exists():
                try:
                    data = _read_file(backup)
                    logger.warning("已从备份恢复: %s", backup)
                    _atomic_write(data_file, _dump_yaml(data))
                    return _remember(data)
                except StorageError as bak_exc:
                    logger.error("备份也无效: %s", bak_exc.message)
            raise StorageError(
                "CORRUPT_DATA",
                "导航数据损坏且无法从备份恢复，请检查 data/navigation.yml",
            ) from exc


def load_data() -> NavigationData:
    """读取导航数据。命中内存缓存时不做磁盘 IO。"""
    with _lock:
        data_file = settings.data_file
        if not data_file.exists():
            invalidate_cache()
            return initialize_storage()
        key = _stat_key(data_file)
        if _cache is not None and key is not None and key == _cache_key:
            return _cache
        data = _read_file(data_file)
        if any(
            (lk.icon_url or "").startswith(("data:", "http://", "https://"))
            for lk in data.links
        ):
            return save_data(data)
        return _remember(data)


def save_data(data: NavigationData) -> NavigationData:
    """校验并原子写入；写入前备份。"""
    with _lock:
        data = ensure_uncategorized(data)
        data = _materialize_icons(data)
        # 再次校验
        data = NavigationData.model_validate(data.model_dump())
        content = _dump_yaml(data)
        data_file = settings.data_file
        backup = settings.data_backup
        data_file.parent.mkdir(parents=True, exist_ok=True)
        if data_file.exists():
            shutil.copy2(data_file, backup)
        try:
            _atomic_write(data_file, content)
        except OSError as exc:
            raise StorageError("IO_ERROR", f"无法写入数据文件: {exc}") from exc
        return _remember(data)


MAX_IMPORT_BYTES = 16 * 1024 * 1024


def _materialize_icons(data: NavigationData) -> NavigationData:
    for link in data.links:
        try:
            link.icon_url = persist_icon(link.id, link.icon_url)
        except ValueError as exc:
            raise StorageError("VALIDATION_ERROR", str(exc)) from exc
    prune_icons({lk.id for lk in data.links if lk.icon_url})
    return data


def export_archive() -> bytes:
    """导出 zip：navigation.yml + icon/*.png。"""
    data = load_data()
    return build_export_zip(data, settings.icon_dir)


def import_yaml(text: str) -> NavigationData:
    """校验并导入 YAML，覆盖当前数据。"""
    raw = (text or "").strip()
    if not raw:
        raise StorageError("EMPTY_DATA", "配置文件内容为空")
    if len(raw.encode("utf-8")) > MAX_IMPORT_BYTES:
        raise StorageError("VALIDATION_ERROR", "配置文件过大（上限 16MB）")
    data = _parse_yaml_text(raw)
    return save_data(data)


def import_payload(raw: bytes, filename: str = "") -> NavigationData:
    """导入 zip 或 YAML 文本。"""
    name = (filename or "").lower()
    if raw.startswith(b"PK") or name.endswith(".zip"):
        try:
            text = extract_import_zip(raw, settings.icon_dir)
        except ArchiveError as exc:
            raise StorageError("VALIDATION_ERROR", exc.message) from exc
        return import_yaml(text)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StorageError("INVALID_DATA", "配置文件不是 UTF-8 文本或 zip") from exc
    return import_yaml(text)


def mutate(fn: Callable[[NavigationData], T]) -> T:
    """在锁内读取、修改、保存。"""
    with _lock:
        data = load_data()
        result = fn(data)
        save_data(data)
        return result
