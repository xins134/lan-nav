"""存储层测试。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

# 在导入 app 前设置测试环境
TEST_ROOT = Path(__file__).resolve().parent
TMP = TEST_ROOT / "_tmp_storage"
TMP.mkdir(exist_ok=True)

os.environ["DATA_FILE"] = str(TMP / "navigation.yml")
os.environ["DEBUG"] = "false"

from app import config  # noqa: E402

config.settings.data_file = TMP / "navigation.yml"
config.settings.data_backup = TMP / "navigation.yml.bak"
config.settings.icon_dir = TMP / "icon"
config.settings.example_file = (
    Path(__file__).resolve().parent.parent / "data" / "navigation.yml.example"
)

from app.archive import build_export_zip, extract_import_zip
from app.models import Category, Link, NavigationData, SiteConfig  # noqa: E402
from app.storage import (  # noqa: E402
    UNCATEGORIZED_ID,
    StorageError,
    import_yaml,
    initialize_storage,
    load_data,
    save_data,
)


@pytest.fixture(autouse=True)
def clean_files():
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
    yield
    for p in [TMP / "navigation.yml", TMP / "navigation.yml.bak"]:
        if p.exists():
            p.unlink()
    if icon_dir.exists():
        for p in icon_dir.glob("*"):
            if p.is_file():
                p.unlink()


def test_initialize_creates_demo_or_example():
    data = initialize_storage()
    assert len(data.categories) >= 4
    assert len(data.links) >= 12
    assert config.settings.data_file.exists()
    assert any(c.id == UNCATEGORIZED_ID for c in data.categories)


def test_atomic_save_and_backup():
    data = initialize_storage()
    data.site.title = "测试标题"
    save_data(data)
    assert config.settings.data_backup.exists()
    loaded = load_data()
    assert loaded.site.title == "测试标题"


def test_recover_from_backup():
    data = initialize_storage()
    data.site.title = "可恢复"
    save_data(data)
    # 再次保存以产生备份
    data.site.title = "最新"
    save_data(data)
    # 损坏主文件
    config.settings.data_file.write_text("{ broken", encoding="utf-8")
    recovered = initialize_storage()
    assert recovered.site.title in {"最新", "可恢复"}
    assert isinstance(recovered, NavigationData)


def test_reject_invalid_url():
    with pytest.raises(Exception):
        Link(title="x", url="javascript:alert(1)")


def test_icon_path_accepted():
    link = Link(title="x", url="http://127.0.0.1", icon_url="icon/abc.png")
    assert link.icon_url == "icon/abc.png"


def test_icon_rejects_non_image_data():
    with pytest.raises(Exception):
        Link(
            title="x",
            url="http://127.0.0.1",
            icon_url="data:text/html;base64,PGg+PC9oPg==",
        )


def test_icon_saved_as_png_file():
    png = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    data = initialize_storage()
    assert data.links
    target_id = data.links[0].id
    data.links[0].icon_url = png
    save_data(data)
    loaded = load_data()
    found = next(lk for lk in loaded.links if lk.id == target_id)
    assert found.icon_url == f"icon/{target_id}.png"
    png_path = config.settings.icon_dir / f"{target_id}.png"
    assert png_path.exists()
    assert png_path.read_bytes().startswith(b"\x89PNG")
    raw = config.settings.data_file.read_text(encoding="utf-8")
    assert "data:image" not in raw


def test_normalize_url_adds_https():
    link = Link(title="x", url="example.com/path")
    assert link.url.startswith("https://")


def test_yaml_readable():
    data = NavigationData(
        site=SiteConfig(title="A"),
        categories=[Category(name="C1", order=1)],
        links=[Link(title="L1", url="http://127.0.0.1", category_id="")],
    )
    save_data(data)
    raw = yaml.safe_load(config.settings.data_file.read_text(encoding="utf-8"))
    assert raw["site"]["title"] == "A"
    assert isinstance(raw["categories"], list)


def test_import_yaml():
    data = initialize_storage()
    data.site.title = "导入前"
    save_data(data)
    exported = config.settings.data_file.read_text(encoding="utf-8")
    data.site.title = "导入后应恢复"
    save_data(data)
    imported = import_yaml(exported)
    assert imported.site.title == "导入前"


def test_export_zip_contains_icon_png():
    png = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    data = initialize_storage()
    target_id = data.links[0].id
    data.links[0].icon_url = png
    save_data(data)
    data = load_data()
    blob = build_export_zip(data, config.settings.icon_dir)
    import io
    import zipfile

    zf = zipfile.ZipFile(io.BytesIO(blob))
    names = zf.namelist()
    assert "navigation.yml" in names
    icon_files = [n for n in names if n.startswith("icon/") and n.endswith(".png")]
    assert icon_files == [f"icon/{target_id}.png"]
    assert zf.read(icon_files[0]).startswith(b"\x89PNG")
    yml = zf.read("navigation.yml").decode("utf-8")
    assert "data:image" not in yml
    assert f"icon/{target_id}.png" in yml

    restored = extract_import_zip(blob, config.settings.icon_dir)
    imported = import_yaml(restored)
    found = next(lk for lk in imported.links if lk.id == target_id)
    assert found.icon_url == f"icon/{target_id}.png"
    assert (config.settings.icon_dir / f"{target_id}.png").exists()


def test_orphan_links_moved_to_uncategorized():
    data = NavigationData(
        site=SiteConfig(title="A"),
        categories=[Category(name="C1", order=1)],
        links=[Link(title="孤立", url="http://127.0.0.1", category_id="missing-id")],
    )
    saved = save_data(data)
    found = next(lk for lk in saved.links if lk.title == "孤立")
    assert found.category_id == UNCATEGORIZED_ID
    loaded = load_data()
    found2 = next(lk for lk in loaded.links if lk.title == "孤立")
    assert found2.category_id == UNCATEGORIZED_ID
