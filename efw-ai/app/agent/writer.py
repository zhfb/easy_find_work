import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

MAX_LEN = 200


def _parse_skills(skills_str: str) -> list[str]:
    return [s.strip() for s in (skills_str or "").split(",") if s.strip()]


def _overlap(profile: Any, jd_parsed: Any) -> list[str]:
    mine = {s.lower() for s in _parse_skills(getattr(profile, "skills", ""))}
    jd_tech = [str(t).strip() for t in getattr(jd_parsed, "tech_stack", []) or []]
    return [t for t in jd_tech if t.lower() in mine]


def build_by_template(profile: Any, jd_parsed: Any, title: str = "") -> list[str]:
    """Pure template fallback: 3 条 ≤200 字的 Boss 直聘首条消息候选。"""
    title = title or "该"
    n = getattr(profile, "experience_years", 0) or 0
    hit = _overlap(profile, jd_parsed)

    if hit:
        kw1 = hit[0]
        if len(hit) > 1:
            kw2 = hit[1]
            templates = [
                f"您好，我看到贵司{title}岗位，我熟悉{kw1}、{kw2}，有{n}年经验，方便了解一下吗？",
                f"您好！关注到贵司{title}职位，我在{kw1}和{kw2}方面有{n}年实战经验，想和您聊聊这个机会，可以吗？",
                f"你好，贵司{title}岗位很吸引我，我擅长{kw1}、{kw2}，积累了{n}年经验，请问还在招人吗？",
            ]
        else:
            templates = [
                f"您好，我看到贵司{title}岗位，我熟悉{kw1}，有{n}年经验，方便了解一下吗？",
                f"您好！关注到贵司{title}职位，我在{kw1}方面有{n}年实战经验，想和您聊聊这个机会，可以吗？",
                f"你好，贵司{title}岗位很吸引我，我擅长{kw1}，积累了{n}年经验，请问还在招人吗？",
            ]
    else:
        templates = [
            f"您好，看到贵司{title}岗位，我有{n}年相关工作经验，对这个机会很感兴趣，方便沟通一下吗？",
            f"您好！关注到贵司{title}职位，我有{n}年行业经验，想了解一下岗位详情，可以聊聊吗？",
            f"你好，贵司{title}岗位很吸引我，我有{n}年相关经验，请问目前还在招聘吗？",
        ]

    return [t[:MAX_LEN] for t in templates]


class Writer:
    """LLM 生成 3 条候选文案，失败时回退到模板。"""

    def __init__(self, llm: Any):
        self.llm = llm

    async def write(self, profile: Any, job: Any, jd_parsed: Any) -> list[str]:
        title = (job or {}).get("title", "") if isinstance(job, dict) else getattr(job, "title", "")
        skills = _parse_skills(getattr(profile, "skills", ""))
        n = getattr(profile, "experience_years", 0) or 0
        summary = getattr(profile, "resume_summary", "") or ""
        tech = getattr(jd_parsed, "tech_stack", []) or []

        system = (
            "你是 Boss 直聘求职助手。根据候选人简历和岗位信息，生成 3 条首条打招呼消息候选。"
            "要求：每条 ≤200 字，点名 1-2 个具体技能，开放问句收尾，语气真诚不油腻。"
            "只输出 JSON：{\"messages\": [\"...\", \"...\", \"...\"]}"
        )
        user = (
            f"岗位：{title}\n"
            f"岗位技术栈：{', '.join(tech)}\n"
            f"候选人技能：{', '.join(skills)}\n"
            f"经验：{n}年\n"
            f"简历摘要：{summary}\n"
        )

        try:
            result = await self.llm.complete(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.7,
                json_mode=True,
            )
            data = json.loads(result.content)
            msgs = data.get("messages", [])
            if not isinstance(msgs, list) or not msgs:
                raise ValueError("empty messages")
            cleaned = [str(m).strip()[:MAX_LEN] for m in msgs if str(m).strip()]
            if not cleaned:
                raise ValueError("all empty")
            # 强制恰好 3 条：不足用模板补齐，超出截断
            if len(cleaned) < 3:
                fallback = build_by_template(profile, jd_parsed, title=title)
                for extra in fallback:
                    if extra not in cleaned:
                        cleaned.append(extra)
                    if len(cleaned) == 3:
                        break
            return cleaned[:3]
        except Exception as e:
            logger.warning("Writer LLM 失败，回退模板: %s", e)
            return build_by_template(profile, jd_parsed, title=title)
