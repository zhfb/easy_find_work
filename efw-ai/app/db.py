from pathlib import Path
from sqlmodel import SQLModel, Session, create_engine
from .config import get_settings

Path(get_settings().data_dir).mkdir(parents=True, exist_ok=True)
engine = create_engine(f"sqlite:///{get_settings().db_path}", connect_args={"check_same_thread": False})

def init_db() -> None:
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session
