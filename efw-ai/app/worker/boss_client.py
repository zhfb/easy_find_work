"""Boss 直聘客户端骨架：岗位列表解析 + 页面操作方法。

- parse_job_list 是纯函数，从 Boss 搜索接口 JSON 提取岗位字段，
  不依赖浏览器，可单测。
- BossClient 所有方法接受外部注入的 page 对象，方法体内不做
  浏览器生命周期管理（由 BrowserManager 负责）。
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

SEARCH_URL_TEMPLATE = "https://www.zhipin.com/web/geek/job?query={keyword}&city={city_code}"

# Boss 接口字段名可能因版本/接口不同而变化，按优先级兜底。
_FIELD_ALIASES = {
    "boss_job_id": ("encryptJobId", "jobId", "id"),
    "title": ("jobName", "jobTitle", "name", "title"),
    "company": ("brandName", "companyName", "company", "brand"),
    "salary_text": ("salaryDesc", "salary", "salaryText"),
    "city": ("cityName", "city", "location"),
    "boss_user_id": ("encryptUserId", "bossId", "userId", "encryptBossId"),
    "job_url": ("jobUrl", "link", "url", "positionURL"),
}


def _pick(item: dict, key: str) -> str:
    """按别名优先级从原始 dict 中取第一个非空值。"""
    for alias in _FIELD_ALIASES[key]:
        val = item.get(alias)
        if val not in (None, ""):
            return str(val)
    return ""


def parse_job_list(json_str: str) -> list[dict]:
    """从 Boss 搜索接口 JSON 提取岗位列表（纯函数）。

    输出字段统一为：
      boss_job_id, title, company, salary_text, city, boss_user_id, job_url

    解析失败或无数据时返回空列表，不抛异常。
    """
    if not json_str:
        return []
    try:
        data = json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return []

    zp_data = data.get("zpData") or data.get("data") or {}
    raw_list = zp_data.get("jobList") or zp_data.get("list") or []
    if not isinstance(raw_list, list):
        return []

    result: list[dict] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        boss_job_id = _pick(item, "boss_job_id")
        if not boss_job_id:
            # 没有加密岗位 ID 的条目无法后续操作，跳过
            continue
        result.append({
            "boss_job_id": boss_job_id,
            "title": _pick(item, "title"),
            "company": _pick(item, "company"),
            "salary_text": _pick(item, "salary_text"),
            "city": _pick(item, "city"),
            "boss_user_id": _pick(item, "boss_user_id"),
            "job_url": _pick(item, "job_url"),
        })
    return result


class BossClient:
    """Boss 直聘页面操作客户端。所有方法接受注入的 page 对象。"""

    def __init__(self, timeout_ms: int = 15000):
        self.timeout_ms = timeout_ms

    # ------------------------------------------------------------------
    # 搜索
    # ------------------------------------------------------------------
    async def search(self, page, keyword: str, city: str = "101200100") -> list[dict]:
        """导航到搜索页，拦截 wapi/zpgeek/search JSON 响应并解析。

        失败时兜底用 DOM 定位 .job-card-wrapper 提取（骨架阶段返回空）。
        city 为 Boss 城市编码（如武汉 101200100）。
        """
        url = SEARCH_URL_TEMPLATE.format(keyword=keyword, city_code=city)
        interception_failed = False
        try:
            async with page.expect_response(
                lambda r: "wapi/zpgeek/search" in r.url, timeout=self.timeout_ms
            ) as resp_info:
                await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            response = await resp_info.value
            body = await response.text()
            jobs = parse_job_list(body)
            # JSON 拦截成功但无结果（正常空搜索），直接返回，不走 DOM 兜底
            return jobs
        except Exception:
            logger.exception("BossClient.search JSON interception failed")
            interception_failed = True

        # 仅在拦截失败时才尝试 DOM 兜底（骨架阶段暂未实现完整选择器，返回空）
        if interception_failed:
            logger.warning("BossClient.search falling back to DOM parsing (not implemented in skeleton)")
        return []

    # ------------------------------------------------------------------
    # 详情
    # ------------------------------------------------------------------
    async def get_detail(self, page, job_url: str) -> str:
        """访问岗位详情页，返回 JD 文本。骨架阶段返回空字符串。"""
        try:
            await page.goto(job_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            # 骨架阶段：尝试常见 JD 容器，失败返回空
            for selector in (".job-sec-text", ".detail-content", ".job-detail"):
                try:
                    text = await page.inner_text(selector, timeout=3000)
                    if text and text.strip():
                        return text.strip()
                except Exception:
                    continue
        except Exception:
            logger.exception("BossClient.get_detail failed")
        return ""

    # ------------------------------------------------------------------
    # 沟通 / 投递（骨架：记录日志，不实际操作）
    # ------------------------------------------------------------------
    async def send_greeting(self, page, job_id: str, message: str) -> None:
        """向 HR 发送打招呼消息。骨架阶段仅记录日志。"""
        logger.info("BossClient.send_greeting skeleton: job_id=%s, msg_len=%d", job_id, len(message))

    async def send_apply(self, page, job_id: str, message: str) -> None:
        """投递简历并附言。骨架阶段仅记录日志。"""
        logger.info("BossClient.send_apply skeleton: job_id=%s, msg_len=%d", job_id, len(message))

    async def read_messages(self, page) -> list[dict]:
        """读取消息列表。骨架阶段返回空列表。"""
        logger.info("BossClient.read_messages skeleton")
        return []

    async def mark_applied(self, page, job_id: str) -> None:
        """标记岗位已投递（本地状态同步）。骨架阶段仅记录日志。"""
        logger.info("BossClient.mark_applied skeleton: job_id=%s", job_id)
