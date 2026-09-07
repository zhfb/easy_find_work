import pytest
from sqlalchemy.exc import IntegrityError
from app.models import Task, Application, Job, Profile, Blacklist, ConfigItem

def test_profile_insert_and_read(session):
    p = Profile(skills="Linux,K8s", experience_years=3, expected_salary_min=15, expected_salary_max=25)
    session.add(p); session.commit()
    got = session.get(Profile, p.id)
    assert got.skills == "Linux,K8s"
    assert got.experience_years == 3

def test_job_boss_id_unique(session):
    session.add(Job(boss_job_id="abc", title="t1")); session.commit()
    with pytest.raises(IntegrityError):
        session.add(Job(boss_job_id="abc", title="t2")); session.commit()

def test_application_job_task_unique(session):
    session.add(Application(job_id=1, task_id=1)); session.commit()
    with pytest.raises(IntegrityError):
        session.add(Application(job_id=1, task_id=1)); session.commit()
