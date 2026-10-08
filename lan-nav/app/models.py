"""数据模型与校验。"""

from __future__ import annotations

import re
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

LinkStatus = Literal["normal", "warning", "offline"]
ThemeMode = Literal["system", "light", "dark"]

_HTTP_RE = re.compile(r"^https?://", re.IGNORECASE)
_COLOR_RE = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_ICON_PATH_RE = re.compile(r"^icon/[A-Za-z0-9._-]+\.png$")


def new_id() -> str:
    return str(uuid4())


def normalize_url(url: str) -> str:
    value = (url or "").strip()
    if not value:
        raise ValueError("URL 不能为空")
    if "://" in value:
        scheme = value.split("://", 1)[0].lower()
        if scheme not in {"http", "https"}:
            raise ValueError("URL 仅允许 http:// 或 https://")
    else:
        # 无协议时补全为 https；已含其他协议的已在上方拒绝
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", value):
            raise ValueError("URL 仅允许 http:// 或 https://")
        value = "https://" + value.lstrip("/")
    if not _HTTP_RE.match(value):
        raise ValueError("URL 仅允许 http:// 或 https://")
    return value


def normalize_icon_data(value: str | None) -> str:
    """允许空、icon/ 相对路径、data URL（保存前会落成 png 文件）或 http(s)。"""
    raw = (value or "").strip()
    if not raw:
        return ""
    if raw.startswith("/icon/"):
        raw = raw[1:]
    if _ICON_PATH_RE.match(raw):
        return raw
    if raw.lower().startswith("data:"):
        header, sep, payload = raw.partition(",")
        if not sep:
            raise ValueError("图标数据格式无效")
        payload = re.sub(r"\s+", "", payload)
        compact = f"{header},{payload}"
        if len(compact) > 100_000:
            raise ValueError("图标数据过大")
        if not re.match(
            r"^data:image/(png|jpeg|jpg|webp|gif);base64,[A-Za-z0-9+/]+=*$",
            compact,
            re.IGNORECASE,
        ):
            raise ValueError("图标仅支持 PNG / JPEG / WebP / GIF")
        return compact
    if raw.startswith(("http://", "https://")):
        return normalize_url(raw)
    raise ValueError("图标路径无效")


def public_icon_url(ref: str) -> str:
    raw = (ref or "").strip()
    if raw.startswith("icon/"):
        return "/" + raw
    return raw


def normalize_color(color: str | None, default: str = "#6366f1") -> str:
    value = (color or "").strip() or default
    if not _COLOR_RE.match(value):
        raise ValueError("颜色必须是合法的十六进制值，例如 #6366f1")
    return value


class SiteConfig(BaseModel):
    title: str = "我的局域网导航"
    subtitle: str = "常用服务与工具"
    theme: ThemeMode = "system"

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("站点标题不能为空")
        return v[:80]

    @field_validator("subtitle")
    @classmethod
    def subtitle_trim(cls, v: str) -> str:
        return (v or "").strip()[:160]


class Category(BaseModel):
    id: str = Field(default_factory=new_id)
    name: str
    description: str = ""
    icon: str = "folder"
    color: str = "#8b5cf6"
    order: int = 10

    @field_validator("name")
    @classmethod
    def name_required(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("分类名称不能为空")
        return v[:60]

    @field_validator("description")
    @classmethod
    def desc_trim(cls, v: str) -> str:
        return (v or "").strip()[:200]

    @field_validator("icon")
    @classmethod
    def icon_trim(cls, v: str) -> str:
        v = (v or "folder").strip() or "folder"
        return v[:64]

    @field_validator("color")
    @classmethod
    def color_ok(cls, v: str) -> str:
        return normalize_color(v, "#8b5cf6")


class Link(BaseModel):
    id: str = Field(default_factory=new_id)
    category_id: str = ""
    title: str
    url: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    icon_url: str = ""
    icon: str = ""
    color: str = "#6366f1"
    pinned: bool = False
    status: LinkStatus = "normal"
    order: int = 10

    @field_validator("title")
    @classmethod
    def title_required(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("链接标题不能为空")
        return v[:80]

    @field_validator("url")
    @classmethod
    def url_ok(cls, v: str) -> str:
        return normalize_url(v)

    @field_validator("description")
    @classmethod
    def desc_trim(cls, v: str) -> str:
        return (v or "").strip()[:300]

    @field_validator("tags", mode="before")
    @classmethod
    def tags_normalize(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            parts = [p.strip() for p in v.replace("，", ",").split(",")]
            return [p for p in parts if p][:20]
        if isinstance(v, list):
            out: list[str] = []
            for item in v:
                s = str(item).strip()
                if s:
                    out.append(s[:32])
            return out[:20]
        raise ValueError("标签格式无效")

    @field_validator("icon_url")
    @classmethod
    def icon_url_ok(cls, v: str) -> str:
        return normalize_icon_data(v)

    @field_validator("icon")
    @classmethod
    def icon_trim(cls, v: str) -> str:
        return (v or "").strip()[:64]

    @field_validator("color")
    @classmethod
    def color_ok(cls, v: str) -> str:
        return normalize_color(v, "#6366f1")


MAX_CATEGORIES = 200
MAX_LINKS = 2000


def public_link_dict(link: Link) -> dict[str, Any]:
    payload = link.model_dump()
    payload["icon_url"] = public_icon_url(payload.get("icon_url") or "")
    return payload


class NavigationData(BaseModel):
    site: SiteConfig = Field(default_factory=SiteConfig)
    categories: list[Category] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_ids(self) -> NavigationData:
        if len(self.categories) > MAX_CATEGORIES:
            raise ValueError(f"分类数量不能超过 {MAX_CATEGORIES}")
        if len(self.links) > MAX_LINKS:
            raise ValueError(f"链接数量不能超过 {MAX_LINKS}")
        cat_ids = [c.id for c in self.categories]
        if len(cat_ids) != len(set(cat_ids)):
            raise ValueError("分类 ID 存在重复")
        link_ids = [lk.id for lk in self.links]
        if len(link_ids) != len(set(link_ids)):
            raise ValueError("链接 ID 存在重复")
        return self

    def sorted_categories(self) -> list[Category]:
        return sorted(self.categories, key=lambda c: (c.order, c.name.lower()))

    def sorted_links(self, category_id: str | None = None) -> list[Link]:
        items = self.links
        if category_id is not None:
            items = [lk for lk in items if lk.category_id == category_id]
        return sorted(items, key=lambda lk: (not lk.pinned, lk.order, lk.title.lower()))

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "site": self.site.model_dump(),
            "categories": [c.model_dump() for c in self.sorted_categories()],
            "links": [public_link_dict(lk) for lk in self.sorted_links()],
        }


# ---------- 请求体 ----------


class CategoryCreate(BaseModel):
    name: str
    description: str = ""
    icon: str = "folder"
    color: str = "#8b5cf6"
    order: int | None = None


class CategoryUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    icon: str | None = None
    color: str | None = None
    order: int | None = None


class LinkCreate(BaseModel):
    title: str
    url: str
    description: str = ""
    category_id: str = ""
    tags: list[str] | str = Field(default_factory=list)
    icon_url: str = ""
    icon: str = ""
    color: str = "#6366f1"
    pinned: bool = False
    status: LinkStatus = "normal"
    order: int | None = None

    @field_validator("icon_url")
    @classmethod
    def icon_url_ok(cls, v: str) -> str:
        return normalize_icon_data(v)


class LinkUpdate(BaseModel):
    title: str | None = None
    url: str | None = None
    description: str | None = None
    category_id: str | None = None
    tags: list[str] | str | None = None
    icon_url: str | None = None
    icon: str | None = None
    color: str | None = None
    pinned: bool | None = None
    status: LinkStatus | None = None
    order: int | None = None

    @field_validator("icon_url")
    @classmethod
    def icon_url_ok(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return normalize_icon_data(v)


class ReorderPayload(BaseModel):
    ids: list[str]
