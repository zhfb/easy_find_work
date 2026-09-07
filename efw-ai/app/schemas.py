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
