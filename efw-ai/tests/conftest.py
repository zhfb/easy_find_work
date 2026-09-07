import pytest
from sqlmodel import Session, SQLModel, create_engine

@pytest.fixture()
def engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path/'t.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    return eng

@pytest.fixture()
def session(engine):
    with Session(engine) as s:
        yield s
