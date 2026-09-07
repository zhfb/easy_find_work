import pytest
from fastapi.testclient import TestClient


def _make_client(tmp_path, monkeypatch, dist_exists: bool):
    from app import main as main_mod

    if dist_exists:
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "index.html").write_text("<div id='app'>EFW</div>", encoding="utf-8")
        monkeypatch.setattr(main_mod, "FRONTEND_DIST", str(dist))
    else:
        monkeypatch.setattr(main_mod, "FRONTEND_DIST", str(tmp_path / "missing"))
    return TestClient(main_mod.app)


def test_root_serves_spa_when_built(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch, dist_exists=True)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "<div id='app'>" in resp.text


def test_unknown_path_falls_back_to_spa(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch, dist_exists=True)
    resp = client.get("/some/random/page")
    assert resp.status_code == 200
    assert "<div id='app'>" in resp.text


def test_api_routes_untouched(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch, dist_exists=True)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_missing_dist_returns_503(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch, dist_exists=False)
    resp = client.get("/")
    assert resp.status_code == 503
    assert "前端" in resp.json()["detail"]


def test_path_with_extension_returns_404_when_missing(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch, dist_exists=True)
    resp = client.get("/nonexistent.js")
    assert resp.status_code == 404


def test_path_traversal_blocked(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch, dist_exists=True)
    resp = client.get("/../../app/main.py")
    assert resp.status_code == 404


def test_existing_static_file_served(tmp_path, monkeypatch):
    from app import main as main_mod

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<div id='app'>EFW</div>", encoding="utf-8")
    assets = dist / "assets"
    assets.mkdir()
    (assets / "test.txt").write_text("hello-static", encoding="utf-8")
    monkeypatch.setattr(main_mod, "FRONTEND_DIST", str(dist))

    client = TestClient(main_mod.app)
    resp = client.get("/assets/test.txt")
    assert resp.status_code == 200
    assert resp.text == "hello-static"
