"""API 测试。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_ROOT = Path(__file__).resolve().parent
TMP = TEST_ROOT / "_tmp_api"
TMP.mkdir(exist_ok=True)

os.environ["ADMIN_TOKEN"] = "test-secret-token"
os.environ["DATA_FILE"] = str(TMP / "navigation.yml")
os.environ["DEBUG"] = "false"
os.environ["HOST"] = "127.0.0.1"

from app import config  # noqa: E402

config.settings.admin_token = "test-secret-token"
config.settings.data_file = TMP / "navigation.yml"
config.settings.data_backup = TMP / "navigation.yml.bak"
config.settings.example_file = (
    Path(__file__).resolve().parent.parent / "data" / "navigation.yml.example"
)

from app.main import app  # noqa: E402
from app.storage import initialize_storage  # noqa: E402


@pytest.fixture(autouse=True)
def reset_data():
    for p in [TMP / "navigation.yml", TMP / "navigation.yml.bak"]:
        if p.exists():
            p.unlink()
    initialize_storage()
    yield
    for p in [TMP / "navigation.yml", TMP / "navigation.yml.bak"]:
        if p.exists():
            p.unlink()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def auth():
    return {"X-Admin-Token": "test-secret-token"}


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
    assert body["data"]["meta"]["admin_protected"] is True


def test_write_requires_token(client: TestClient):
    r = client.post("/api/categories", json={"name": "X"})
    assert r.status_code == 401
    assert r.json()["success"] is False


def test_create_update_delete_category(client: TestClient):
    r = client.post(
        "/api/categories",
        json={"name": "新分类", "icon": "star", "color": "#ff0000"},
        headers=auth(),
    )
    assert r.status_code == 200
    cat = r.json()["data"]
    cat_id = cat["id"]

    r = client.put(
        f"/api/categories/{cat_id}",
        json={"name": "改名"},
        headers=auth(),
    )
    assert r.status_code == 200
    assert r.json()["data"]["name"] == "改名"

    # 先加链接再测移动
    r = client.post(
        "/api/links",
        json={"title": "T", "url": "http://127.0.0.1", "category_id": cat_id},
        headers=auth(),
    )
    assert r.status_code == 200

    r = client.delete(
        f"/api/categories/{cat_id}?action=move_uncategorized",
        headers=auth(),
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
        headers=auth(),
    )
    assert r.status_code == 200
    link = r.json()["data"]
    assert link["url"].startswith("https://")
    link_id = link["id"]

    r = client.put(
        f"/api/links/{link_id}",
        json={"description": "更新描述", "status": "warning"},
        headers=auth(),
    )
    assert r.status_code == 200
    assert r.json()["data"]["description"] == "更新描述"

    # 持久化：重新读
    nav2 = client.get("/api/navigation").json()["data"]
    found = next(lk for lk in nav2["links"] if lk["id"] == link_id)
    assert found["status"] == "warning"

    r = client.delete(f"/api/links/{link_id}", headers=auth())
    assert r.status_code == 200


def test_reorder_categories(client: TestClient):
    nav = client.get("/api/navigation").json()["data"]
    ids = [c["id"] for c in nav["categories"]]
    ids = list(reversed(ids))
    r = client.post("/api/categories/reorder", json={"ids": ids}, headers=auth())
    assert r.status_code == 200


def test_index_page(client: TestClient):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert b"lan-nav" in r.content or "导航".encode() in r.content
