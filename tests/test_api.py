"""API 测试。"""

from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_ROOT = Path(__file__).resolve().parent
TMP = TEST_ROOT / "_tmp_api"
TMP.mkdir(exist_ok=True)

os.environ["DATA_FILE"] = str(TMP / "navigation.yml")
os.environ["DEBUG"] = "false"
os.environ["HOST"] = "127.0.0.1"

from app import config  # noqa: E402

config.settings.data_file = TMP / "navigation.yml"
config.settings.data_backup = TMP / "navigation.yml.bak"
config.settings.icon_dir = TMP / "icon"
config.settings.example_file = (
    Path(__file__).resolve().parent.parent / "data" / "navigation.yml.example"
)

from app.main import app  # noqa: E402
from app.storage import initialize_storage  # noqa: E402


@pytest.fixture(autouse=True)
def reset_data():
    config.settings.data_file = TMP / "navigation.yml"
    config.settings.data_backup = TMP / "navigation.yml.bak"
    config.settings.icon_dir = TMP / "icon"
    icon_dir = config.settings.icon_dir
    for p in [TMP / "navigation.yml", TMP / "navigation.yml.bak"]:
        if p.exists():
            p.unlink()
    if icon_dir.exists():
        for p in icon_dir.glob("*"):
            if p.is_file():
                p.unlink()
    initialize_storage()
    yield
    for p in [TMP / "navigation.yml", TMP / "navigation.yml.bak"]:
        if p.exists():
            p.unlink()
    if icon_dir.exists():
        for p in icon_dir.glob("*"):
            if p.is_file():
                p.unlink()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_health(client: TestClient):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["status"] == "ok"


def test_get_navigation(client: TestClient):
    r = client.get("/api/navigation")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert len(body["data"]["categories"]) >= 4
    assert len(body["data"]["links"]) >= 12
    assert "uncategorized_id" in body["data"]["meta"]


def test_create_update_delete_category(client: TestClient):
    r = client.post(
        "/api/categories",
        json={"name": "新分类", "icon": "star", "color": "#ff0000"},
    )
    assert r.status_code == 200
    cat = r.json()["data"]
    cat_id = cat["id"]

    r = client.put(
        f"/api/categories/{cat_id}",
        json={"name": "改名"},
    )
    assert r.status_code == 200
    assert r.json()["data"]["name"] == "改名"

    r = client.post(
        "/api/links",
        json={"title": "T", "url": "http://127.0.0.1", "category_id": cat_id},
    )
    assert r.status_code == 200

    r = client.delete(
        f"/api/categories/{cat_id}?action=move_uncategorized",
    )
    assert r.status_code == 200

    nav = client.get("/api/navigation").json()["data"]
    assert all(c["id"] != cat_id for c in nav["categories"])


def test_link_crud_and_persist(client: TestClient):
    nav = client.get("/api/navigation").json()["data"]
    cat_id = nav["categories"][0]["id"]

    r = client.post(
        "/api/links",
        json={
            "title": "测试链接",
            "url": "example.org",
            "category_id": cat_id,
            "tags": "a,b",
            "pinned": True,
        },
    )
    assert r.status_code == 200
    link = r.json()["data"]
    assert link["url"].startswith("https://")
    link_id = link["id"]

    r = client.put(
        f"/api/links/{link_id}",
        json={"description": "更新描述", "status": "warning"},
    )
    assert r.status_code == 200
    assert r.json()["data"]["description"] == "更新描述"

    nav2 = client.get("/api/navigation").json()["data"]
    found = next(lk for lk in nav2["links"] if lk["id"] == link_id)
    assert found["status"] == "warning"

    r = client.delete(f"/api/links/{link_id}")
    assert r.status_code == 200


def test_link_icon_saved_as_png(client: TestClient):
    nav = client.get("/api/navigation").json()["data"]
    cat_id = nav["categories"][0]["id"]
    png = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    r = client.post(
        "/api/links",
        json={"title": "带图标", "url": "http://127.0.0.1", "category_id": cat_id, "icon_url": png},
    )
    assert r.status_code == 200
    body = r.json()["data"]
    link_id = body["id"]
    assert body["icon_url"] == f"/icon/{link_id}.png"
    png_path = config.settings.icon_dir / f"{link_id}.png"
    assert png_path.exists()
    assert png_path.read_bytes().startswith(b"\x89PNG")
    yml = config.settings.data_file.read_text(encoding="utf-8")
    assert "data:image" not in yml
    served = client.get(body["icon_url"])
    assert served.status_code == 200
    assert "image/png" in served.headers.get("content-type", "")
    assert served.content.startswith(b"\x89PNG")


def test_reorder_categories(client: TestClient):
    nav = client.get("/api/navigation").json()["data"]
    ids = [c["id"] for c in nav["categories"]]
    ids = list(reversed(ids))
    r = client.post("/api/categories/reorder", json={"ids": ids})
    assert r.status_code == 200


def test_index_page(client: TestClient):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert b"lan-nav" in r.content or "导航".encode() in r.content


def test_export_zip(client: TestClient):
    r = client.get("/api/export")
    assert r.status_code == 200
    assert "zip" in r.headers["content-type"]
    assert "navigation.zip" in r.headers.get("content-disposition", "")
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = zf.namelist()
    assert "navigation.yml" in names
    assert any(n == "icon/" or n.startswith("icon/") for n in names)
    yaml_text = zf.read("navigation.yml").decode("utf-8")
    assert "site:" in yaml_text
    assert "categories:" in yaml_text


def test_import_zip(client: TestClient):
    export = client.get("/api/export")
    assert export.status_code == 200
    nav = client.get("/api/navigation").json()["data"]
    client.delete(f"/api/links/{nav['links'][0]['id']}")

    r = client.post(
        "/api/import",
        files={"file": ("navigation.zip", export.content, "application/zip")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["links"] >= 12

    nav2 = client.get("/api/navigation").json()["data"]
    assert len(nav2["links"]) >= len(nav["links"])


def test_import_invalid_yaml(client: TestClient):
    r = client.post(
        "/api/import",
        files={"file": ("navigation.yml", b"{ broken", "text/yaml")},
    )
    assert r.status_code == 400
    assert r.json()["success"] is False


def test_openapi_disabled(client: TestClient):
    r = client.get("/openapi.json")
    assert r.status_code == 404
    body = r.json()
    assert body.get("success") is False


def test_validation_error_shape(client: TestClient):
    r = client.post("/api/categories", json={})
    assert r.status_code == 422
    body = r.json()
    assert body["success"] is False
    assert body["error"]["code"] == "VALIDATION_ERROR"
