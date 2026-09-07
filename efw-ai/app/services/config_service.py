from sqlmodel import Session, select
from ..models import ConfigItem


def get_config(session: Session, key: str) -> str | None:
    item = session.get(ConfigItem, key)
    return item.value if item else None


def set_config(session: Session, key: str, value: str) -> None:
    item = session.get(ConfigItem, key)
    if item is None:
        item = ConfigItem(key=key, value=value)
        session.add(item)
    else:
        item.value = value
    session.commit()


def get_all_config(session: Session) -> dict:
    return {c.key: c.value for c in session.exec(select(ConfigItem)).all()}


def get_bool(session: Session, key: str, default: bool = False) -> bool:
    val = get_config(session, key)
    if val is None:
        return default
    return val.lower() in ("1", "true", "yes", "on")
