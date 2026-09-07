from datetime import datetime
from sqlmodel import SQLModel, Field
from sqlalchemy import UniqueConstraint
from typing import Optional

def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")

class ConfigItem(SQLModel, table=True):
    __tablename__ = "config"
    key: str = Field(primary_key=True)
    value: str = Field(default="{}")  # JSON
    updated_at: str = Field(default_factory=_now)

class Profile(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    skills: str = ""
    experience_years: int = 0
    expected_salary_min: float = 0.0
    expected_salary_max: float = 0.0
    target_city: str = ""
    intention: str = ""
    resume_summary: str = ""
    updated_at: str = Field(default_factory=_now)

class Task(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = ""
    keywords: str = "[]"  # JSON 数组
    city: str = ""
    mode: str = "auto"    # auto | semi
    max_deliveries: int = 50
    daily_limit: int = 20
    match_threshold: float = 7.0
    rules: str = "{}"     # JSON {salary_min, exclude_companies[]}
    status: str = "pending"  # pending|running|paused|finished|stopped|failed
    last_job_id: Optional[int] = None
    created_at: str = Field(default_factory=_now)
    finished_at: Optional[str] = None

class Job(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    boss_job_id: str = Field(index=True, unique=True)
    title: str = ""
    company: str = ""
    company_scale: str = ""
    financing_stage: str = ""
    industry: str = ""
    salary_text: str = ""
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    experience_req: str = ""
    education_req: str = ""
    city: str = ""
    jd_text: str = ""
    jd_parsed: str = "{}"
    job_url: str = ""
    created_at: str = Field(default_factory=_now)

class Application(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("job_id", "task_id"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(index=True)
    task_id: int = Field(index=True)
    mode: str = "auto"
    decision: str = "pending"   # deliver|skip|pending
    match_score: Optional[float] = None
    llm_reason: str = ""
    message: str = ""
    status: str = "skip"        # skip|pending_manual|applied|responded|interview|offer|rejected|withdrawn
    applied_at: Optional[str] = None
    updated_at: str = Field(default_factory=_now)

class ApplicationEvent(SQLModel, table=True):
    __tablename__ = "application_event"
    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(index=True)
    event_type: str = ""
    detail: str = ""
    created_at: str = Field(default_factory=_now)

class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_message"
    id: Optional[int] = Field(default=None, primary_key=True)
    role: str = ""  # user|assistant
    content: str = ""
    related_task_id: Optional[int] = None
    created_at: str = Field(default_factory=_now)

class Cookie(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    platform: str = "boss"
    cookie_json: str = "{}"
    user_data_dir: str = ""
    updated_at: str = Field(default_factory=_now)

class Blacklist(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    type: str = "company"  # company|job|recruiter
    value: str = ""
    reason: str = ""
    created_at: str = Field(default_factory=_now)
