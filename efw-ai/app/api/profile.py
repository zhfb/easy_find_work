from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..db import get_session
from ..schemas import ProfileIn
from ..services.profile_service import get_profile, update_profile

router = APIRouter()


def _to_dict(p) -> dict:
    return {
        "id": p.id,
        "skills": p.skills,
        "experience_years": p.experience_years,
        "expected_salary_min": p.expected_salary_min,
        "expected_salary_max": p.expected_salary_max,
        "target_city": p.target_city,
        "intention": p.intention,
        "resume_summary": p.resume_summary,
    }


@router.get("/profile")
def read_profile(session: Session = Depends(get_session)) -> dict:
    p = get_profile(session)
    if p is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return _to_dict(p)


@router.put("/profile")
def update_profile_route(body: ProfileIn, session: Session = Depends(get_session)) -> dict:
    p = update_profile(session, body)
    return _to_dict(p)
