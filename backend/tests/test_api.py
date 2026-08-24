from fastapi.testclient import TestClient

from app.main import create_app


def test_health_and_generation_contract(settings):
    with TestClient(create_app(settings)) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["mock_mode"] is True

        response = client.post(
            "/api/generations",
            json={"prompt": "A paper bird crossing a quiet blue sky", "final_resolution": "original"},
        )
        assert response.status_code == 202
        payload = response.json()
        assert payload["generation"]["mode"] == "t2v"
        assert payload["job"]["status"] == "queued"


def test_blank_prompt_is_rejected(settings):
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/generations", json={"prompt": "   "})
        assert response.status_code == 422

