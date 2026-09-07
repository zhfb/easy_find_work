from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_path: str = "data/efw.db"
    data_dir: str = "data"
    host: str = "127.0.0.1"
    port: int = 8888


@lru_cache
def get_settings() -> Settings:
    return Settings()
