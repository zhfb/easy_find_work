"""浏览器会话管理：Playwright 持久化上下文 + Cookie 持久化。

测试只覆盖 save_cookie_raw / load_cookie_raw（纯 DB 操作），
不启动真实浏览器。start/stop/is_logged_in/heartbeat/save_cookie
为运行时方法，用 try/except 包裹避免异常扩散。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from sqlmodel import Session, select

from app.models import Cookie

logger = logging.getLogger(__name__)

LOGIN_CHECK_URL = "https://www.zhipin.com/web/user/?ka=header-login"
LOGIN_COOKIE_NAMES = ("wt2", "__zp_stoken__", "last_login_phone")


class BrowserManager:
    """管理单个 Playwright 持久化浏览器上下文与 Cookie 落库。"""

    def __init__(self, data_dir: str | Path = "data", session: Optional[Session] = None):
        self.data_dir = Path(data_dir)
        self.user_data_dir = self.data_dir / "browser_profile"
        self.session = session
        self._playwright = None
        self._context = None
        self.auth_probe_url = ""

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    async def start(self) -> None:
        """启动 Playwright 与 chromium 持久化上下文（headless=False 便于人工登录）。"""
        try:
            from playwright.async_api import async_playwright

            self.user_data_dir.mkdir(parents=True, exist_ok=True)
            self._playwright = await async_playwright().start()
            self._context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.user_data_dir),
                headless=False,
            )
            logger.info("BrowserManager started, profile=%s", self.user_data_dir)
        except Exception:
            logger.exception("BrowserManager.start failed")
            raise

    async def stop(self) -> None:
        """关闭上下文与 Playwright，忽略已关闭的异常。"""
        try:
            if self._context is not None:
                await self._context.close()
                self._context = None
        except Exception:
            logger.exception("BrowserManager.stop context close failed")
        try:
            if self._playwright is not None:
                await self._playwright.stop()
                self._playwright = None
        except Exception:
            logger.exception("BrowserManager.stop playwright stop failed")

    @property
    def context(self):
        return self._context

    async def new_page(self):
        """便捷方法：在当前上下文中新建页面。"""
        if self._context is None:
            raise RuntimeError("BrowserManager not started; call start() first")
        return await self._context.new_page()

    def get_page(self):
        """返回当前上下文中的第一个页面；未启动或无页面时抛 RuntimeError。

        同步方法：Playwright context.pages 是同步属性，无需 await。
        调用方应在 try/except 中包裹，浏览器不可用时跳过投递而非崩溃。
        """
        if self._context is None:
            raise RuntimeError("BrowserManager not started; call start() first")
        pages = self._context.pages
        if not pages:
            raise RuntimeError("No page available in browser context")
        return pages[0]

    # ------------------------------------------------------------------
    # 登录态 / 心跳
    # ------------------------------------------------------------------
    async def login_status(self, page) -> str:
        """非导航登录判定（轮询安全）：绝不 goto，避免打断用户登录窗口。

        - A 强否定: 当前 URL 为 passport 域名或 /login 路径 → logged_out
        - C 强肯定: 登录态 cookie（wt2/__zp_stoken__/last_login_phone）存在 → logged_in
        - B 强肯定: 当前页面 DOM 含「退出登录」 → logged_in
        - 其余 → unknown（保持等待，不打扰登录过程）
        """
        try:
            parsed = urlparse(page.url)
            if "passport" in parsed.netloc or parsed.path.startswith("/login"):
                return "logged_out"
        except Exception:
            pass
        try:
            cookies = await page.context.cookies()
            names = {c["name"] for c in cookies}
            if names & set(LOGIN_COOKIE_NAMES):
                return "logged_in"
        except Exception:
            pass
        try:
            body = await page.inner_text("body")
            if "退出登录" in body:
                return "logged_in"
        except Exception:
            pass
        return "unknown"

    async def is_logged_in(self, page) -> bool:
        return await self.login_status(page) == "logged_in"

    async def heartbeat(self, page) -> bool:
        """轻量心跳：访问首页判断页面是否可正常加载。"""
        try:
            resp = await page.goto("https://www.zhipin.com/", wait_until="domcontentloaded", timeout=15000)
            return resp is not None and resp.status < 500
        except Exception:
            logger.exception("heartbeat failed")
            return False

    # ------------------------------------------------------------------
    # Cookie 持久化
    # ------------------------------------------------------------------
    async def save_cookie(self, context) -> None:
        """从 Playwright context 导出 cookies 并写入 Cookie 表。"""
        try:
            cookies = await context.cookies()
            self.save_cookie_raw("boss", json.dumps(cookies, ensure_ascii=False))
        except Exception as exc:
            logger.exception("save_cookie: failed to export or persist cookies: %s", exc)

    def save_cookie_raw(self, platform: str, cookie_json: str) -> None:
        """将 cookie JSON 字符串 upsert 到 Cookie 表（按 platform 唯一）。"""
        if self.session is None:
            raise RuntimeError("BrowserManager requires a session for cookie persistence")
        stmt = select(Cookie).where(Cookie.platform == platform)
        existing = self.session.exec(stmt).first()
        if existing is None:
            row = Cookie(platform=platform, cookie_json=cookie_json, user_data_dir=str(self.user_data_dir))
            self.session.add(row)
        else:
            existing.cookie_json = cookie_json
            existing.user_data_dir = str(self.user_data_dir)
        self.session.commit()

    def load_cookie_raw(self, platform: str) -> Optional[str]:
        """按 platform 读取 cookie JSON 字符串，不存在返回 None。"""
        if self.session is None:
            raise RuntimeError("BrowserManager requires a session for cookie persistence")
        stmt = select(Cookie).where(Cookie.platform == platform)
        row = self.session.exec(stmt).first()
        return row.cookie_json if row is not None else None
