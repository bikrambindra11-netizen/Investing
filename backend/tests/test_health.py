from fastapi.testclient import TestClient

from backend.app.main import app


def test_health():
    with TestClient(app) as client:
        r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"
    assert set(body["keys_configured"]) == {"upstox_api_key", "upstox_api_secret", "fred_api_key"}
