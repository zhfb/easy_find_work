"""风控五层控制器：节奏/频率/配额/会话/验证码。"""

import random
from datetime import date


class RiskController:
    """投递风控控制器，独立于业务流程使用。

    五层防护：
    1. 会话掉线检测（session 为 None 时跳过）
    2. 人机验证（验证码）标志
    3. 每日投递配额
    4. 投递间隔节奏（next_delay_seconds）
    5. 连续投递冷却（cool_off_seconds，每 5 次后调用）
    """

    def __init__(self, session, daily_limit: int = 20):
        self.session = session
        self.daily_limit = daily_limit
        self._captcha_detected = False
        self._daily_counts: dict[str, int] = {}
        self._consecutive = 0

    # ---- 状态查询 ----

    def should_pause(self) -> tuple[bool, str]:
        """按优先级返回是否应暂停及原因。

        顺序：会话掉线 → 验证码 → 日配额用尽。
        """
        # 1. 会话掉线（session 为 None 表示测试/离线模式，不判定掉线）
        if self.session is not None and not getattr(self.session, "is_connected", True):
            return True, "掉线"

        # 2. 人机验证标志
        if self._captcha_detected:
            return True, "验证码"

        # 3. 今日配额用尽
        if self._today_count() >= self.daily_limit:
            return True, "限额"

        return False, ""

    def next_delay_seconds(self) -> float:
        """两次投递之间的随机间隔，模拟人类操作节奏。"""
        return random.uniform(8, 25)

    def cool_off_seconds(self) -> float:
        """连续投递后的冷却时长，建议每 5 次投递后调用。"""
        return random.uniform(120, 300)

    # ---- 计数与标志 ----

    def record_delivery(self) -> None:
        """记录一次成功投递：今日次数 +1，连续次数 +1。"""
        key = date.today().isoformat()
        self._daily_counts[key] = self._daily_counts.get(key, 0) + 1
        self._consecutive += 1

    def set_captcha_detected(self, detected: bool) -> None:
        """设置或清除人机验证标志。"""
        self._captcha_detected = detected

    def reset_daily(self) -> None:
        """跨天清零：清空每日计数与连续计数，进程启动时调用。"""
        self._daily_counts.clear()
        self._consecutive = 0

    # ---- 内部辅助 ----

    def _today_count(self) -> int:
        return self._daily_counts.get(date.today().isoformat(), 0)
