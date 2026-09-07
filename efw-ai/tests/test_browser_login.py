"""四信号登录判定（非导航版）：轮询检测绝不导航登录窗口。

回归用例：11 个匿名统计 cookie 不得误判为已登录（历史 bug）。
回归保护：login_status 不得调用 page.goto（否则每 5s 轮询会打断用户登录）。
"""
import pytest
from app.worker.browser import BrowserManager

ANON_COOKIES = [
    {"name": "HMACCOUNT", "value": "x"}, {"name": "HMACCOUNT_BFESS", "value": "x"},
    {"name": "Hm_lvt_194df3105ad7148dcf2b98a91b5e727a", "value": "x"},
    {"name": "Hm_lpvt_194df3105ad7148dcf2b98a91b5e727a", "value": "x"},
    {"name": "__a", "value": "x"}, {"name": "__c", "value": "x"}, {"name": "__g", "value": "x"},
    {"name": "__l", "value": "x"}, {"name": "ab_guid", "value": "x"},
    {"name": "isOHPC", "value": "x"}, {"name": "lastCity", "value": "101200100"},
]


class FakeContext:
    def __init__(self, cookies):
        self._cookies = cookies

    async def cookies(self):
        return self._cookies


class FakePage:
    def __init__(self, url="https://www.zhipin.com/", body="", cookies=None):
        self._url = url
        self._body = body
        self._cookies = cookies or []
        self.goto_calls = 0

    @property
    def url(self):
        return self._url

    async def goto(self, url, **kw):
        self.goto_calls += 1

    async def inner_text(self, sel, **kw):
        return self._body

    @property
    def context(self):
        return FakeContext(self._cookies)


@pytest.mark.asyncio
async def test_anon_cookies_are_not_logged_in():
    """回归：11 个匿名统计 cookie 不得判定已登录（历史误判 bug）。"""
    bm = BrowserManager()
    page = FakePage(body="Boss直聘-招聘求职找工作", cookies=ANON_COOKIES)
    assert await bm.login_status(page) != "logged_in"


@pytest.mark.asyncio
async def test_passport_url_is_logged_out():
    bm = BrowserManager()
    page = FakePage(url="https://passport.zhipin.com/login", cookies=ANON_COOKIES)
    assert await bm.login_status(page) == "logged_out"


@pytest.mark.asyncio
async def test_login_path_is_logged_out():
    bm = BrowserManager()
    page = FakePage(url="https://www.zhipin.com/login", cookies=ANON_COOKIES)
    assert await bm.login_status(page) == "logged_out"


@pytest.mark.asyncio
async def test_login_cookie_confirms_logged_in():
    bm = BrowserManager()
    cookies = ANON_COOKIES + [{"name": "wt2", "value": "abc"}]
    page = FakePage(body="Boss直聘-招聘求职找工作", cookies=cookies)
    assert await bm.login_status(page) == "logged_in"


@pytest.mark.asyncio
async def test_logout_dom_confirms_logged_in():
    bm = BrowserManager()
    page = FakePage(body="个人中心 退出登录", cookies=ANON_COOKIES)
    assert await bm.login_status(page) == "logged_in"


@pytest.mark.asyncio
async def test_is_logged_in_true_when_logged_in():
    bm = BrowserManager()
    cookies = ANON_COOKIES + [{"name": "__zp_stoken__", "value": "s"}]
    page = FakePage(body="Boss直聘-招聘求职找工作", cookies=cookies)
    assert await bm.is_logged_in(page) is True


@pytest.mark.asyncio
async def test_login_status_does_not_navigate():
    """回归保护：轮询检测绝不导航，避免打断用户登录。"""
    bm = BrowserManager()
    page = FakePage(body="个人中心 退出登录", cookies=ANON_COOKIES)
    await bm.login_status(page)
    assert page.goto_calls == 0
