from sqlmodel import Session, select
from ..models import Profile
from ..schemas import ProfileIn


def get_profile(session: Session) -> Profile | None:
    return session.exec(select(Profile)).first()


def update_profile(session: Session, data: ProfileIn) -> Profile:
    p = session.exec(select(Profile)).first()
    if p is None:
        p = Profile()
        session.add(p)
    p.skills = data.skills
    p.experience_years = data.experience_years
    p.expected_salary_min = data.expected_salary_min
    p.expected_salary_max = data.expected_salary_max
    p.target_city = data.target_city
    p.intention = data.intention
    p.resume_summary = data.resume_summary
    session.commit()
    session.refresh(p)
    return p
