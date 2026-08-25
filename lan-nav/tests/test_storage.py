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

os.environ["ADMIN_TOKEN"] = ""
os.environ["DATA_FILE"] = str(TMP / "navigation.yml")
os.environ["DEBUG"] = "false"

from app import config  # noqa: E402

config.settings.data_file = TMP / "navigation.yml"
config.settings.data_backup = TMP / "navigation.yml.bak"
config.settings.example_file = (
    Path(__file__).resolve().parent.parent / "data" / "navigation.yml.example"
)

from app.models import Category, Link, NavigationData, SiteConfig  # noqa: E402
from app.storage import (  # noqa: E402
    UNCATEGORIZED_ID,
    StorageError,
    initialize_storage,
    load_data,
    save_data,
)


@pytest.fixture(autouse=True)
def clean_files():
    for p in [TMP / "navigation.yml", TMP / "navigation.yml.bak"]:
        if p.exists():
            p.unlink()
    yield
    for p in [TMP / "navigation.yml", TMP / "navigation.yml.bak"]:
        if p.exists():
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
