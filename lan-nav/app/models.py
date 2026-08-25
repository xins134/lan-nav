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
        v = (v or "").strip()
        if not v:
            return ""
        return normalize_url(v)

    @field_validator("icon")
    @classmethod
    def icon_trim(cls, v: str) -> str:
        return (v or "").strip()[:64]

    @field_validator("color")
    @classmethod
    def color_ok(cls, v: str) -> str:
        return normalize_color(v, "#6366f1")


class NavigationData(BaseModel):
    site: SiteConfig = Field(default_factory=SiteConfig)
    categories: list[Category] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_ids(self) -> NavigationData:
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
            "links": [lk.model_dump() for lk in self.sorted_links()],
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


class ReorderPayload(BaseModel):
    ids: list[str]
