"""BrowserManager Cookie 持久化测试（不启动真实浏览器）。"""
import json

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
