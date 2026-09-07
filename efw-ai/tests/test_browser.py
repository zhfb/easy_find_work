"""BrowserManager Cookie 持久化测试（不启动真实浏览器）。"""
import json

import pytest
from sqlmodel import select

from app.models import Cookie
from app.worker.browser import BrowserManager


def test_save_and_load_cookie_raw(session):
    bm = BrowserManager(data_dir="data", session=session)
    payload = json.dumps([{"name": "x", "value": "1", "domain": ".zhipin.com"}])
    bm.save_cookie_raw("boss", payload)

    loaded = bm.load_cookie_raw("boss")
    assert loaded is not None
    assert loaded.startswith("[")
    assert json.loads(loaded)[0]["name"] == "x"

    cookie = session.get(Cookie, 1)
    assert cookie is not None
    assert cookie.platform == "boss"
    assert cookie.cookie_json == payload


def test_save_cookie_raw_upsert(session):
    bm = BrowserManager(data_dir="data", session=session)
    bm.save_cookie_raw("boss", '[{"name":"a","value":"1"}]')
    bm.save_cookie_raw("boss", '[{"name":"b","value":"2"}]')

    # 同一 platform 应只有一条记录（upsert）
    rows = list(session.exec(select(Cookie).where(Cookie.platform == "boss")).all())
    assert len(rows) == 1
    assert json.loads(rows[0].cookie_json)[0]["name"] == "b"


def test_load_cookie_raw_missing_returns_none(session):
    bm = BrowserManager(data_dir="data", session=session)
    assert bm.load_cookie_raw("nonexistent") is None


def test_multiple_platforms(session):
    bm = BrowserManager(data_dir="data", session=session)
    bm.save_cookie_raw("boss", '[{"name":"b"}]')
    bm.save_cookie_raw("lagou", '[{"name":"l"}]')

    assert json.loads(bm.load_cookie_raw("boss"))[0]["name"] == "b"
    assert json.loads(bm.load_cookie_raw("lagou"))[0]["name"] == "l"
    assert len(session.exec(select(Cookie)).all()) == 2


# ---------- 启动反检测 ----------

class _FakeContext:
    def __init__(self):
        self.scripts = []

    async def add_init_script(self, script):
        self.scripts.append(script)


class _FakeChromium:
    def __init__(self, captured):
        self.captured = captured
        self.context = None

    async def launch_persistent_context(self, **kw):
        self.captured.update(kw)
        self.context = _FakeContext()
        return self.context


class _FakePlaywright:
    def __init__(self, captured):
        self.chromium = _FakeChromium(captured)

    async def start(self):
        return self


@pytest.mark.asyncio
async def test_start_hides_automation_features(monkeypatch, tmp_path):
    """回归：启动浏览器必须隐藏自动化特征，降低 Boss 风控触发概率。"""
    import playwright.async_api as pa
    captured = {}
    fake_pw = _FakePlaywright(captured)
    monkeypatch.setattr(pa, "async_playwright", lambda: fake_pw)

    bm = BrowserManager(data_dir=tmp_path)
    await bm.start()

    assert captured.get("args") == ["--disable-blink-features=AutomationControlled"]
    assert "--enable-automation" in captured.get("ignore_default_args", [])
    assert fake_pw.chromium.context.scripts, "必须注入反 webdriver 检测脚本"
    assert "navigator" in fake_pw.chromium.context.scripts[0]
