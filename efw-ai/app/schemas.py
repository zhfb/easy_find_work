from pydantic import BaseModel


class ConfigPut(BaseModel):
    key: str
    value: str


class ProfileIn(BaseModel):
    skills: str = ""
    experience_years: int = 0
    expected_salary_min: float = 0.0
    expected_salary_max: float = 0.0
    target_city: str = ""
    intention: str = ""
    resume_summary: str = ""


class TaskIn(BaseModel):
    name: str = ""
    keywords: str = "[]"       # JSON 数组
    city: str = ""
    mode: str = "auto"          # auto | semi
    max_deliveries: int = 50
    daily_limit: int = 20
    match_threshold: float = 7.0
    rules: str = "{}"           # JSON
