import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_health_endpoint():
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "cutoff_utc" in data


def test_metrics_endpoint():
    r = client.get("/api/metrics")
    assert r.status_code == 200
    data = r.json()
    assert "mae" in data
    assert "rmse" in data
    assert "bias" in data
    assert "wape_pct" in data
    assert "by_hour" in data


def test_day_endpoint_valid():
    r = client.get("/api/day?date=2026-01-15")
    assert r.status_code == 200
    data = r.json()
    assert "cutoff" in data
    assert "points" in data
    assert "summary" in data
    assert len(data["points"]) == 48


def test_day_endpoint_out_of_range():
    # Outside January 2026: before
    r1 = client.get("/api/day?date=2025-12-31")
    assert r1.status_code == 400
    assert "Date must be in January 2026" in r1.json()["detail"]

    # Outside January 2026: after
    r2 = client.get("/api/day?date=2026-02-01")
    assert r2.status_code == 400
    assert "Date must be in January 2026" in r2.json()["detail"]


def test_day_endpoint_invalid_date_format():
    r = client.get("/api/day?date=not-a-date")
    assert r.status_code == 422


def test_day_endpoint_missing_date_parameter():
    r = client.get("/api/day")
    assert r.status_code == 422
