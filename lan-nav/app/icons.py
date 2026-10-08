"""链接图标：以 PNG 文件存到 navigation.yml 同级的 icon/ 目录。"""

from __future__ import annotations

import base64
import logging
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config import settings

logger = logging.getLogger("lan-nav.icons")

MAX_ICON_BYTES = 512 * 1024
_FETCH_TIMEOUT = 8.0
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_SAFE_ID = re.compile(r"[^A-Za-z0-9_-]")
_ALLOWED_MIME = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
    "image/gif",
}


def icon_dir() -> Path:
    path = settings.icon_dir
    path.mkdir(parents=True, exist_ok=True)
    return path


def icon_filename(link_id: str) -> str:
    stem = _SAFE_ID.sub("", link_id or "")[:64] or "icon"
    return f"{stem}.png"


def icon_ref(link_id: str) -> str:
    return f"icon/{icon_filename(link_id)}"


def _guess_mime(content_type: str, content: bytes) -> str:
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    if mime == "image/jpg":
        mime = "image/jpeg"
    if mime in _ALLOWED_MIME:
        return mime
    if content.startswith(_PNG_MAGIC):
        return "image/png"
    if content.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if content.startswith(b"RIFF") and b"WEBP" in content[:16]:
        return "image/webp"
    if content.startswith(b"GIF8"):
        return "image/gif"
    return ""


def decode_data_url(value: str) -> tuple[str, bytes] | None:
    raw = (value or "").strip()
    if not raw.lower().startswith("data:image/"):
        return None
    header, sep, payload = raw.partition(",")
    if not sep:
        return None
    mime = header[5:].split(";", 1)[0].strip().lower()
    try:
        content = base64.b64decode(payload, validate=False)
    except Exception:
        return None
    if not content or len(content) > MAX_ICON_BYTES:
        return None
    guessed = _guess_mime(mime, content)
    if not guessed:
        return None
    return guessed, content


def fetch_icon_bytes(url: str) -> tuple[str, bytes] | None:
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        return None
    try:
        req = Request(url, headers={"User-Agent": "lan-nav/1"})
        with urlopen(req, timeout=_FETCH_TIMEOUT) as response:
            content = response.read(MAX_ICON_BYTES + 1)
            if not content or len(content) > MAX_ICON_BYTES:
                return None
            mime = _guess_mime(response.headers.get("Content-Type", ""), content)
            if not mime:
                return None
            return mime, content
    except (URLError, HTTPError, TimeoutError, ValueError, OSError) as exc:
        logger.warning("拉取图标失败 %s: %s", url, exc)
        return None


def _write_png(link_id: str, content: bytes) -> str:
    if len(content) > MAX_ICON_BYTES:
        raise ValueError("图标过大")
    dest = icon_dir() / icon_filename(link_id)
    dest.write_bytes(content)
    return icon_ref(link_id)


def delete_icon_file(link_id: str) -> None:
    path = icon_dir() / icon_filename(link_id)
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("删除图标失败 %s: %s", path, exc)


def persist_icon(link_id: str, raw: str) -> str:
    """把请求里的图标落成 icon/{id}.png，返回相对路径；空则删除。"""
    value = (raw or "").strip()
    if value.startswith("/icon/"):
        value = value[1:]
    dest = icon_dir() / icon_filename(link_id)
    if not value:
        delete_icon_file(link_id)
        return ""
    if value.startswith("data:"):
        decoded = decode_data_url(value)
        if not decoded:
            raise ValueError("无法解析图标数据")
        return _write_png(link_id, decoded[1])
    if value.startswith(("http://", "https://")):
        fetched = fetch_icon_bytes(value)
        if not fetched:
            delete_icon_file(link_id)
            return ""
        return _write_png(link_id, fetched[1])
    if value.startswith("icon/"):
        src = icon_dir() / Path(value).name
        if src.exists() and src.resolve() != dest.resolve():
            dest.write_bytes(src.read_bytes())
        return icon_ref(link_id)
    raise ValueError("图标路径无效")


def prune_icons(keep_ids: set[str]) -> None:
    keep = {icon_filename(i) for i in keep_ids}
    folder = icon_dir()
    for path in folder.glob("*.png"):
        if path.name not in keep:
            try:
                path.unlink()
            except OSError:
                pass
