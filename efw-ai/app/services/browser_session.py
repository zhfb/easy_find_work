"""Boss login session management: state machine + background polling + cookie persistence."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL = 5.0
DEFAULT_TIMEOUT_SECONDS = 300
DEFAULT_CONSISTENT_ROUNDS = 3

BrowserFactory = Callable[[], Awaitable[object]]


async def _default_browser_factory():
    """Real browser: start persistent context and bind DB session."""
    from sqlmodel import Session
    from app.db import engine
    from app.worker.browser import BrowserManager

    bm = BrowserManager(data_dir="data", session=Session(engine))
    await bm.start()
    return bm


class BrowserSessionManager:
    def __init__(self, browser_factory: Optional[BrowserFactory] = None,
                 poll_interval: float = DEFAULT_POLL_INTERVAL,
                 timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
                 consistent_rounds: int = DEFAULT_CONSISTENT_ROUNDS):
        self._factory = browser_factory or _default_browser_factory
        self._poll_interval = poll_interval
        self._timeout_seconds = timeout_seconds
        self._consistent_rounds = consistent_rounds
        self._browser = None
        self._page = None
        self._lock = asyncio.Lock()
        self._loop_task: Optional[asyncio.Task] = None
        self._state = "not_started"
        self._started_at: Optional[str] = None
        self._last_checked_at: Optional[str] = None
        self._detail = ""
        self._signal_window: list[str] = []
        self._window_start: Optional[float] = None

    @property
    def state(self) -> str:
        return self._state

    def status(self) -> dict:
        return {
            "state": self._state,
            "last_checked_at": self._last_checked_at,
            "started_at": self._started_at,
            "detail": self._detail,
        }

    async def start_login(self) -> str:
        async with self._lock:
            if self._state in ("starting", "waiting_login"):
                return self._state
            if self._loop_task is not None and not self._loop_task.done():
                self._loop_task.cancel()
            # 已有旧浏览器实例（已登录/过期/超时后再次发起）：先关闭，避免重复实例与窗口竞争
            if self._browser is not None:
                try:
                    await self._browser.stop()
                except Exception:
                    logger.exception("browser stop before restart failed")
                self._browser = None
                self._page = None
            self._state = "starting"
            self._started_at = time.strftime("%Y-%m-%d %H:%M:%S")
            self._detail = ""
            try:
                self._browser = await self._factory()
                self._page = await self._browser.new_page()
                await self._page.goto("https://www.zhipin.com/",
                                      wait_until="domcontentloaded", timeout=30000)
            except Exception as exc:
                logger.exception("browser start failed")
                if self._browser is not None:
                    try:
                        await self._browser.stop()
                    except Exception:
                        logger.exception("browser stop after start failure failed")
                    self._browser = None
                self._state = "error"
                self._detail = str(exc)[:200]
                return self._state
            self._state = "waiting_login"
            self._window_start = time.monotonic()
            self._signal_window = []
            self._loop_task = asyncio.create_task(self._run_loop())
            return self._state

    async def tick(self) -> str:
        """Single poll: four-signal判定 + state transition. Driven directly by tests."""
        if self._state != "waiting_login":
            return self._state
        try:
            result = await self._browser.login_status(self._page)
        except Exception:
            logger.exception("login probe failed")
            result = "unknown"
        self._last_checked_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self._signal_window.append(result)
        if len(self._signal_window) > self._consistent_rounds:
            self._signal_window.pop(0)
        if result == "logged_in" and self._signal_window.count("logged_in") >= self._consistent_rounds:
            await self._on_logged_in()
        elif result == "logged_out":
            # Strong negative signal: clear window immediately
            self._signal_window = []
        if (time.monotonic() - (self._window_start or time.monotonic())
                > self._timeout_seconds and self._state == "waiting_login"):
            self._state = "timeout"
            self._detail = "login timeout, please retry"
            self._stop_loop()
        return self._state if self._state != "waiting_login" else result

    async def _on_logged_in(self) -> None:
        try:
            await self._browser.save_cookie(self._page.context)
        except Exception:
            logger.exception("save cookie failed")
        self._state = "logged_in"
        self._detail = "login success, cookie saved"
        self._stop_loop()

    async def check_now(self) -> str:
        """Immediate recheck: only valid for logged_in state (401 -> expired)."""
        if self._state != "logged_in":
            return self._state
        try:
            result = await self._browser.login_status(self._page)
        except Exception:
            logger.exception("recheck failed")
            result = "unknown"
        self._last_checked_at = time.strftime("%Y-%m-%d %H:%M:%S")
        if result in ("logged_out", "unknown"):
            self._state = "expired"
            self._detail = "login expired, please re-login"
        return self._state

    async def _run_loop(self) -> None:
        while self._state == "waiting_login":
            await asyncio.sleep(self._poll_interval)
            try:
                await self.tick()
            except Exception:
                logger.exception("tick failed in loop")

    def _stop_loop(self) -> None:
        if self._loop_task is not None and not self._loop_task.done():
            self._loop_task.cancel()

    async def shutdown(self) -> None:
        self._stop_loop()
        if self._browser is not None:
            try:
                await self._browser.stop()
            except Exception:
                logger.exception("browser stop failed")
        self._state = "closed"
