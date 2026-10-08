"""HTTP 路由与 API。"""

from __future__ import annotations

import hmac
import logging
import re
from typing import Any, Callable

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.config import ROOT_DIR, settings
from app.icons import delete_icon_file, persist_icon
from app.models import (
    Category,
    CategoryCreate,
    CategoryUpdate,
    Link,
    LinkCreate,
    LinkUpdate,
    ReorderPayload,
    public_link_dict,
)
from app.storage import (
    UNCATEGORIZED_ID,
    StorageError,
    export_archive,
    import_payload,
    load_data,
    mutate,
)

logger = logging.getLogger("lan-nav.api")

templates = Jinja2Templates(directory=str(ROOT_DIR / "app" / "templates"))
_ICON_FILENAME = re.compile(r"^[A-Za-z0-9._-]+\.png$")

api = APIRouter(prefix="/api")
pages = APIRouter()


def ok(data: Any = None, status_code: int = 200) -> JSONResponse:
    return JSONResponse({"success": True, "data": data}, status_code=status_code)


def err(code: str, message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        {"success": False, "error": {"code": code, "message": message}},
        status_code=status_code,
    )


# ---------- 访问密钥 / 鉴权 ----------

KEY_HEADER = "X-Nav-Key"


def key_required() -> bool:
    """是否启用了访问密钥（KEY 为空则完全不鉴权）。"""
    return bool(settings.key)


def key_matches(request: Request) -> bool:
    """请求头中的密钥是否正确（未开启鉴权时恒为 True）。"""
    if not key_required():
        return True
    supplied = request.headers.get(KEY_HEADER, "")
    return hmac.compare_digest(supplied, settings.key)


def guard(request: Request) -> JSONResponse | None:
    """校验写操作权限，未通过时返回 401 响应。"""
    if key_matches(request):
        return None
    return err("UNAUTHORIZED", "需要正确的访问密钥", 401)


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
            icon_url="",
            icon=body.icon,
            color=body.color,
            pinned=body.pinned,
            status=body.status,
            order=order,
        )
        try:
            link.icon_url = persist_icon(link.id, body.icon_url)
        except ValueError as exc:
            raise StorageError("VALIDATION_ERROR", str(exc)) from exc
        data.links.append(link)
        return public_link_dict(link)

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
        if "icon_url" in payload:
            try:
                payload["icon_url"] = persist_icon(link.id, payload.get("icon_url") or "")
            except ValueError as exc:
                raise StorageError("VALIDATION_ERROR", str(exc)) from exc
        updated = Link.model_validate({**link.model_dump(), **payload})
        idx = data.links.index(link)
        data.links[idx] = updated
        return public_link_dict(updated)

    return mutate(_fn)


def _apply_link_delete(link_id: str) -> dict[str, Any]:
    def _fn(data):
        before = len(data.links)
        data.links = [lk for lk in data.links if lk.id != link_id]
        if len(data.links) == before:
            raise StorageError("NOT_FOUND", "链接不存在")
        delete_icon_file(link_id)
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


def _apply_pin_reorder(ids: list[str]) -> dict[str, Any]:
    """置顶区独立排序：只写入 pin_order，不影响链接在分类中的顺序。"""

    def _fn(data):
        by_id = {lk.id: lk for lk in data.links}
        missing = [i for i in ids if i not in by_id]
        if missing:
            raise StorageError("NOT_FOUND", f"链接不存在: {missing[0]}")
        base = 10
        for i, lid in enumerate(ids):
            by_id[lid].pin_order = base + i * 10
        return {"ids": ids}

    return mutate(_fn)


def _safe(fn: Callable[[], Any]):
    try:
        return ok(fn())
    except StorageError as exc:
        status = 404 if exc.code == "NOT_FOUND" else 403 if exc.code == "FORBIDDEN" else 400
        if exc.code in {"CORRUPT_DATA", "IO_ERROR"}:
            status = 503
        return err(exc.code, exc.message, status)
    except ValidationError as exc:
        return err("VALIDATION_ERROR", str(exc), 400)
    except ValueError as exc:
        return err("VALIDATION_ERROR", str(exc), 400)


def _asset_ver(rel: str) -> str:
    path = ROOT_DIR / "app" / "static" / rel
    try:
        return str(int(path.stat().st_mtime))
    except OSError:
        return "1"


@pages.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "css_ver": _asset_ver("css/app.css"),
            "js_ver": _asset_ver("js/app.js"),
            "icons_ver": _asset_ver("js/icons.js"),
        },
    )


@pages.get("/icon/{filename}")
async def serve_link_icon(filename: str):
    if not _ICON_FILENAME.match(filename):
        return err("NOT_FOUND", "图标不存在", 404)
    folder = settings.icon_dir.resolve()
    path = (settings.icon_dir / filename).resolve()
    try:
        path.relative_to(folder)
    except ValueError:
        return err("NOT_FOUND", "图标不存在", 404)
    if not path.is_file():
        return err("NOT_FOUND", "图标不存在", 404)
    return FileResponse(path, media_type="image/png")


@api.get("/health")
async def health() -> JSONResponse:
    try:
        load_data()
    except StorageError as exc:
        return err(exc.code, exc.message, 503)
    return ok({"status": "ok"})


@api.get("/navigation")
async def get_navigation(request: Request) -> JSONResponse:
    def _fn():
        data = load_data()
        payload = data.to_public_dict()
        payload["meta"] = {
            "uncategorized_id": UNCATEGORIZED_ID,
            "requires_key": key_required(),
            "authenticated": key_matches(request),
        }
        return payload

    return _safe(_fn)


@api.post("/login")
async def login(request: Request) -> JSONResponse:
    """校验访问密钥；成功后前端即可携带密钥调用写接口。"""
    if key_matches(request):
        return ok({"authenticated": True, "requires_key": key_required()})
    return err("UNAUTHORIZED", "访问密钥错误", 401)


@api.post("/categories")
async def create_category(request: Request, body: CategoryCreate) -> JSONResponse:
    denied = guard(request)
    if denied:
        return denied
    return _safe(lambda: _apply_category_create(body))


@api.put("/categories/{cat_id}")
async def update_category(request: Request, cat_id: str, body: CategoryUpdate) -> JSONResponse:
    denied = guard(request)
    if denied:
        return denied
    return _safe(lambda: _apply_category_update(cat_id, body))


@api.delete("/categories/{cat_id}")
async def delete_category(
    request: Request,
    cat_id: str,
    action: str = "move_uncategorized",
) -> JSONResponse:
    denied = guard(request)
    if denied:
        return denied
    return _safe(lambda: _apply_category_delete(cat_id, action))


@api.post("/categories/reorder")
async def reorder_categories(request: Request, body: ReorderPayload) -> JSONResponse:
    denied = guard(request)
    if denied:
        return denied
    return _safe(lambda: _apply_category_reorder(body.ids))


@api.post("/links")
async def create_link(request: Request, body: LinkCreate) -> JSONResponse:
    denied = guard(request)
    if denied:
        return denied
    return _safe(lambda: _apply_link_create(body))


@api.put("/links/{link_id}")
async def update_link(request: Request, link_id: str, body: LinkUpdate) -> JSONResponse:
    denied = guard(request)
    if denied:
        return denied
    return _safe(lambda: _apply_link_update(link_id, body))


@api.delete("/links/{link_id}")
async def delete_link(request: Request, link_id: str) -> JSONResponse:
    denied = guard(request)
    if denied:
        return denied
    return _safe(lambda: _apply_link_delete(link_id))


@api.post("/links/reorder")
async def reorder_links(request: Request, body: ReorderPayload) -> JSONResponse:
    denied = guard(request)
    if denied:
        return denied
    return _safe(lambda: _apply_link_reorder(body.ids))


@api.post("/links/pin-reorder")
async def reorder_pinned_links(request: Request, body: ReorderPayload) -> JSONResponse:
    denied = guard(request)
    if denied:
        return denied
    return _safe(lambda: _apply_pin_reorder(body.ids))


@api.get("/export", response_model=None)
async def export_navigation(request: Request):
    denied = guard(request)
    if denied:
        return denied
    try:
        content = export_archive()
        return Response(
            content=content,
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="navigation.zip"'},
        )
    except StorageError as exc:
        status = 503 if exc.code in {"CORRUPT_DATA", "IO_ERROR"} else 400
        return err(exc.code, exc.message, status)


@api.post("/import")
async def import_navigation(request: Request, file: UploadFile = File(...)) -> JSONResponse:
    denied = guard(request)
    if denied:
        return denied
    raw = await file.read()

    def _fn():
        data = import_payload(raw, file.filename or "")
        return {
            "categories": len(data.categories),
            "links": len(data.links),
        }

    return _safe(_fn)
