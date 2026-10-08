"""导入导出 zip：navigation.yml + icon/*.png。"""

from __future__ import annotations

import io
import posixpath
import re
import zipfile
from pathlib import Path

import yaml

from app.models import NavigationData

MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 32 * 1024 * 1024
MAX_ARCHIVE_FILES = 4000
_SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


class ArchiveError(ValueError):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def build_export_zip(data: NavigationData, icon_folder: Path) -> bytes:
    """打包当前 YAML 与 icon/ 目录。"""
    payload = {
        "site": data.site.model_dump(),
        "categories": [c.model_dump() for c in data.sorted_categories()],
        "links": [lk.model_dump() for lk in data.sorted_links()],
    }
    yaml_text = yaml.safe_dump(
        payload,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=120,
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("navigation.yml", yaml_text.encode("utf-8"))
        zf.writestr("icon/", b"")
        if icon_folder.is_dir():
            for path in sorted(icon_folder.glob("*.png")):
                zf.write(path, f"icon/{path.name}")
    return buf.getvalue()


def _norm_zip_name(name: str) -> str:
    return name.replace("\\", "/").lstrip("./")


def _is_safe_zip_name(name: str) -> bool:
    path = _norm_zip_name(name).rstrip("/")
    if not path or path.startswith("/"):
        return False
    parts = path.split("/")
    return all(p not in ("", ".", "..") for p in parts)


def extract_import_zip(raw: bytes, icon_folder: Path) -> str:
    """解压 zip：写出 icon/*.png，返回 YAML 文本（img/ 会改写成 icon/）。"""
    if len(raw) > MAX_ARCHIVE_BYTES:
        raise ArchiveError("压缩包过大（上限 16MB）")
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise ArchiveError("不是有效的 zip 文件") from exc

    names = zf.namelist()
    if len(names) > MAX_ARCHIVE_FILES:
        raise ArchiveError("压缩包内文件过多")
    total = 0
    for info in zf.infolist():
        if not _is_safe_zip_name(info.filename):
            raise ArchiveError("压缩包包含非法路径")
        total += max(info.file_size, 0)
        if total > MAX_UNCOMPRESSED_BYTES:
            raise ArchiveError("压缩包解压后过大")

    yml_name = _pick_yaml_name(names)
    if not yml_name:
        raise ArchiveError("压缩包中未找到 navigation.yml")
    try:
        yaml_text = zf.read(yml_name).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ArchiveError("YAML 不是 UTF-8 编码") from exc

    icon_folder.mkdir(parents=True, exist_ok=True)
    for path in icon_folder.glob("*.png"):
        path.unlink(missing_ok=True)

    for name in names:
        path = _norm_zip_name(name)
        if path.endswith("/"):
            continue
        parts = path.split("/")
        if not any(p in {"icon", "img"} for p in parts[:-1]):
            continue
        filename = parts[-1]
        if not _SAFE_NAME.match(filename):
            continue
        stem = Path(filename).stem
        if not stem:
            continue
        content = zf.read(name)
        if not content:
            continue
        (icon_folder / f"{stem}.png").write_bytes(content)

    payload = yaml.safe_load(yaml_text)
    if not isinstance(payload, dict):
        raise ArchiveError("YAML 根节点必须是对象")
    links = payload.get("links")
    if isinstance(links, list):
        for item in links:
            if not isinstance(item, dict):
                continue
            item["icon_url"] = _rewrite_icon_ref(item.get("icon_url") or "")

    return yaml.safe_dump(payload, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _pick_yaml_name(names: list[str]) -> str:
    candidates: list[str] = []
    for name in names:
        path = _norm_zip_name(name)
        lower = path.lower()
        if lower.endswith("/"):
            continue
        if not (lower.endswith(".yml") or lower.endswith(".yaml")):
            continue
        parts = path.split("/")
        if any(p in {"icon", "img"} for p in parts[:-1]):
            continue
        candidates.append(path)
    if not candidates:
        return ""
    for path in candidates:
        if posixpath.basename(path).lower() in {"navigation.yml", "navigation.yaml"}:
            return next(n for n in names if _norm_zip_name(n) == path)
    path = sorted(candidates, key=lambda p: (p.count("/"), p))[0]
    return next(n for n in names if _norm_zip_name(n) == path)


def _rewrite_icon_ref(icon_url: str) -> str:
    src = (icon_url or "").strip()
    if not src or src.startswith("data:") or src.startswith(("http://", "https://")):
        return src
    name = posixpath.basename(src.replace("\\", "/"))
    if not name:
        return ""
    stem = Path(name).stem
    if not stem or not _SAFE_NAME.match(f"{stem}.png"):
        return ""
    return f"icon/{stem}.png"
