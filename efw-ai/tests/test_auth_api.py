import pytest
from fastapi.testclient import TestClient


class FakeBrowserSession:
    def __init__(self, state="not_started"):
        self._state = state; self.calls = []
    @property
    def state(self): return self._state
    def status(self):
        return {"state": self._state, "last_checked_at": None,
                "started_at": None, "detail": ""}
    async def start_login(self):
        self.calls.append("start_login"); self._state = "waiting_login"
        return self._state
    async def check_now(self):
        self.calls.append("check_now"); self._state = "expired"
        return self._state
    async def shutdown(self): self.calls.append("shutdown")


@pytest.fixture()
def auth_client(client, monkeypatch):
    from app.main import app
    monkeypatch.setattr(app.state, "browser_session", FakeBrowserSession())
    return client


def test_status_not_started(auth_client):
    resp = auth_client.get("/api/auth/status")
    assert resp.status_code == 200
    assert resp.json()["state"] == "not_started"


def test_login_starts_and_returns_state(auth_client):
    resp = auth_client.post("/api/auth/login")
    assert resp.status_code == 200
    data = resp.json()
    assert data["state"] == "waiting_login"
    assert data["message"]


def test_check_now_updates_state(auth_client):
    auth_client.post("/api/auth/login")
    resp = auth_client.post("/api/auth/check")
    assert resp.status_code == 200
    assert resp.json()["state"] == "expired"
