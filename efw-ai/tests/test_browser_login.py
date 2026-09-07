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
    def __init__(self, url="https://www.zhipin.com/web/user/?ka=header-login",
                 body="", cookies=None):
        self._url = url
        self._body = body
        self._cookies = cookies or []

    @property
    def url(self):
        return self._url

    async def goto(self, url, **kw):
        # Simulate post-redirect state: the initial URL is the final URL.
        pass

    async def inner_text(self, sel, **kw):
        return self._body

    @property
    def context(self):
        return FakeContext(self._cookies)


@pytest.mark.asyncio
async def test_anon_cookies_are_not_logged_in():
    """Regression: 11 anonymous tracking cookies must be judged not logged in (current bug)."""
    bm = BrowserManager()
    page = FakePage(body="Boss直聘-招聘求职找工作", cookies=ANON_COOKIES)
    assert await bm.login_status(page) == "logged_out"


@pytest.mark.asyncio
async def test_passport_redirect_is_logged_out():
    bm = BrowserManager()
    page = FakePage(url="https://passport.zhipin.com/login", body="")
    assert await bm.login_status(page) == "logged_out"


@pytest.mark.asyncio
async def test_login_path_is_logged_out():
    bm = BrowserManager()
    page = FakePage(url="https://www.zhipin.com/login", body="")
    assert await bm.login_status(page) == "logged_out"


@pytest.mark.asyncio
async def test_dom_and_cookie_confirm_logged_in():
    bm = BrowserManager()
    cookies = ANON_COOKIES + [{"name": "wt2", "value": "abc"}]
    page = FakePage(body="个人中心 退出登录", cookies=cookies)
    assert await bm.login_status(page) == "logged_in"


@pytest.mark.asyncio
async def test_single_signal_is_unknown():
    bm = BrowserManager()
    page = FakePage(body="个人中心 退出登录", cookies=ANON_COOKIES)
    assert await bm.login_status(page) == "unknown"


@pytest.mark.asyncio
async def test_is_logged_in_wraps_login_status():
    bm = BrowserManager()
    page = FakePage(body="个人中心 退出登录",
                    cookies=ANON_COOKIES + [{"name": "__zp_stoken__", "value": "s"}])
    assert await bm.is_logged_in(page) is True


class GotoErrorPage(FakePage):
    async def goto(self, url, **kw):
        raise RuntimeError("browser crashed")


@pytest.mark.asyncio
async def test_goto_failure_returns_unknown():
    """login_status must be exception-safe: goto failure -> unknown, not raise."""
    bm = BrowserManager()
    page = GotoErrorPage()
    assert await bm.login_status(page) == "unknown"
    assert await bm.is_logged_in(page) is False
