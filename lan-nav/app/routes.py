"""HTTP 路由与 API。"""

from __future__ import annotations

import logging
from typing import Any, Callable

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.config import ROOT_DIR, settings
from app.models import (
    Category,
    CategoryCreate,
    CategoryUpdate,
    Link,
    LinkCreate,
    LinkUpdate,
    ReorderPayload,
)
from app.storage import UNCATEGORIZED_ID, StorageError, load_data, mutate

logger = logging.getLogger("lan-nav.api")

templates = Jinja2Templates(directory=str(ROOT_DIR / "app" / "templates"))

api = APIRouter(prefix="/api")
pages = APIRouter()


def ok(data: Any = None, status_code: int = 200) -> JSONResponse:
    return JSONResponse({"success": True, "data": data}, status_code=status_code)


def err(code: str, message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        {"success": False, "error": {"code": code, "message": message}},
        status_code=status_code,
    )


def require_admin(x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")) -> None:
    """写入接口鉴权。不记录 Token。"""
    if not settings.admin_protected:
        return
    provided = (x_admin_token or "").strip()
    if not provided or provided != settings.admin_token:
        # 故意不记录 header 内容
        logger.warning("写入请求鉴权失败")
        raise AdminAuthError()


class AdminAuthError(Exception):
    pass


def _apply_category_create(body: CategoryCreate) -> dict[str, Any]:
    def _fn(data):
        order = body.order
        if order is None:
            orders = [c.order for c in data.categories if c.id != UNCATEGORIZED_ID]
            order = (max(orders) + 10) if orders else 10
        cat = Category(
            name=body.name,
            description=body.description,
            icon=body.icon,
            color=body.color,
            order=order,
        )
        data.categories.append(cat)
        return cat.model_dump()

    return mutate(_fn)


def _apply_category_update(cat_id: str, body: CategoryUpdate) -> dict[str, Any]:
    def _fn(data):
        cat = next((c for c in data.categories if c.id == cat_id), None)
        if cat is None:
            raise StorageError("NOT_FOUND", "分类不存在")
        payload = body.model_dump(exclude_unset=True)
        updated = cat.model_copy(update=payload)
        # 重新校验
        updated = Category.model_validate(updated.model_dump())
        idx = data.categories.index(cat)
        data.categories[idx] = updated
        return updated.model_dump()

    return mutate(_fn)


def _apply_category_delete(cat_id: str, action: str) -> dict[str, Any]:
    if action not in {"delete_links", "move_uncategorized"}:
        raise StorageError("VALIDATION_ERROR", "action 必须是 delete_links 或 move_uncategorized")
    if cat_id == UNCATEGORIZED_ID:
        raise StorageError("FORBIDDEN", "不能删除「未分类」")

    def _fn(data):
        cat = next((c for c in data.categories if c.id == cat_id), None)
        if cat is None:
            raise StorageError("NOT_FOUND", "分类不存在")
        if action == "delete_links":
            data.links = [lk for lk in data.links if lk.category_id != cat_id]
        else:
            for lk in data.links:
                if lk.category_id == cat_id:
                    lk.category_id = UNCATEGORIZED_ID
        data.categories = [c for c in data.categories if c.id != cat_id]
        return {"deleted_id": cat_id, "action": action}

    return mutate(_fn)


def _apply_category_reorder(ids: list[str]) -> dict[str, Any]:
    def _fn(data):
        by_id = {c.id: c for c in data.categories}
        missing = [i for i in ids if i not in by_id]
        if missing:
            raise StorageError("NOT_FOUND", f"分类不存在: {missing[0]}")
        # 按传入顺序重排，未出现的保持相对顺序接在后面
        ordered: list = []
        seen: set[str] = set()
        base = 10
        for i, cid in enumerate(ids):
            cat = by_id[cid]
            cat.order = base + i * 10
            ordered.append(cat)
            seen.add(cid)
        for cat in data.categories:
            if cat.id not in seen:
                ordered.append(cat)
        data.categories = ordered
        return {"ids": [c.id for c in data.sorted_categories()]}

    return mutate(_fn)


def _apply_link_create(body: LinkCreate) -> dict[str, Any]:
    def _fn(data):
        cat_id = (body.category_id or "").strip() or UNCATEGORIZED_ID
        if not any(c.id == cat_id for c in data.categories):
            raise StorageError("VALIDATION_ERROR", "所属分类不存在")
        order = body.order
        if order is None:
            siblings = [lk.order for lk in data.links if lk.category_id == cat_id]
            order = (max(siblings) + 10) if siblings else 10
        link = Link(
            title=body.title,
            url=body.url,
            description=body.description,
            category_id=cat_id,
            tags=body.tags,  # type: ignore[arg-type]
            icon_url=body.icon_url,
            icon=body.icon,
            color=body.color,
            pinned=body.pinned,
            status=body.status,
            order=order,
        )
        data.links.append(link)
        return link.model_dump()

    return mutate(_fn)


def _apply_link_update(link_id: str, body: LinkUpdate) -> dict[str, Any]:
    def _fn(data):
        link = next((lk for lk in data.links if lk.id == link_id), None)
        if link is None:
            raise StorageError("NOT_FOUND", "链接不存在")
        payload = body.model_dump(exclude_unset=True)
        if "category_id" in payload:
            cat_id = (payload["category_id"] or "").strip() or UNCATEGORIZED_ID
            if not any(c.id == cat_id for c in data.categories):
                raise StorageError("VALIDATION_ERROR", "所属分类不存在")
            payload["category_id"] = cat_id
        updated = Link.model_validate({**link.model_dump(), **payload})
        idx = data.links.index(link)
        data.links[idx] = updated
        return updated.model_dump()

    return mutate(_fn)


def _apply_link_delete(link_id: str) -> dict[str, Any]:
    def _fn(data):
        before = len(data.links)
        data.links = [lk for lk in data.links if lk.id != link_id]
        if len(data.links) == before:
            raise StorageError("NOT_FOUND", "链接不存在")
        return {"deleted_id": link_id}

    return mutate(_fn)


def _apply_link_reorder(ids: list[str]) -> dict[str, Any]:
    def _fn(data):
        by_id = {lk.id: lk for lk in data.links}
        missing = [i for i in ids if i not in by_id]
        if missing:
            raise StorageError("NOT_FOUND", f"链接不存在: {missing[0]}")
        base = 10
        for i, lid in enumerate(ids):
            by_id[lid].order = base + i * 10
        return {"ids": ids}

    return mutate(_fn)


def _safe(fn: Callable[[], Any]):
    try:
        return ok(fn())
    except AdminAuthError:
        return err("UNAUTHORIZED", "需要有效的管理 Token", 401)
    except StorageError as exc:
        status = 404 if exc.code == "NOT_FOUND" else 403 if exc.code == "FORBIDDEN" else 400
        return err(exc.code, exc.message, status)
    except ValidationError as exc:
        return err("VALIDATION_ERROR", str(exc), 400)
    except ValueError as exc:
        return err("VALIDATION_ERROR", str(exc), 400)


@pages.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "admin_protected": settings.admin_protected,
            "site_title": "局域网导航",
        },
    )


@api.get("/health")
async def health() -> JSONResponse:
    return ok({"status": "ok"})


@api.get("/auth/verify")
async def verify_auth(_: None = Depends(require_admin)) -> JSONResponse:
    """校验管理 Token（不修改数据）。未启用保护时始终成功。"""
    return ok({"authenticated": True, "admin_protected": settings.admin_protected})


@api.get("/navigation")
async def get_navigation() -> JSONResponse:
    def _fn():
        data = load_data()
        payload = data.to_public_dict()
        payload["meta"] = {
            "admin_protected": settings.admin_protected,
            "uncategorized_id": UNCATEGORIZED_ID,
        }
        return payload

    return _safe(_fn)


@api.post("/categories")
async def create_category(
    body: CategoryCreate,
    _: None = Depends(require_admin),
) -> JSONResponse:
    return _safe(lambda: _apply_category_create(body))


@api.put("/categories/{cat_id}")
async def update_category(
    cat_id: str,
    body: CategoryUpdate,
    _: None = Depends(require_admin),
) -> JSONResponse:
    return _safe(lambda: _apply_category_update(cat_id, body))


@api.delete("/categories/{cat_id}")
async def delete_category(
    cat_id: str,
    action: str = "move_uncategorized",
    _: None = Depends(require_admin),
) -> JSONResponse:
    return _safe(lambda: _apply_category_delete(cat_id, action))


@api.post("/categories/reorder")
async def reorder_categories(
    body: ReorderPayload,
    _: None = Depends(require_admin),
) -> JSONResponse:
    return _safe(lambda: _apply_category_reorder(body.ids))


@api.post("/links")
async def create_link(
    body: LinkCreate,
    _: None = Depends(require_admin),
) -> JSONResponse:
    return _safe(lambda: _apply_link_create(body))


@api.put("/links/{link_id}")
async def update_link(
    link_id: str,
    body: LinkUpdate,
    _: None = Depends(require_admin),
) -> JSONResponse:
    return _safe(lambda: _apply_link_update(link_id, body))


@api.delete("/links/{link_id}")
async def delete_link(
    link_id: str,
    _: None = Depends(require_admin),
) -> JSONResponse:
    return _safe(lambda: _apply_link_delete(link_id))


@api.post("/links/reorder")
async def reorder_links(
    body: ReorderPayload,
    _: None = Depends(require_admin),
) -> JSONResponse:
    return _safe(lambda: _apply_link_reorder(body.ids))


# AdminAuthError 由 main 中的异常处理器统一返回 401
