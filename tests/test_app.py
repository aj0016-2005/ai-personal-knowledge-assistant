from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_homepage() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Knowledge Assistant" in response.text


def test_chat_rejects_empty_message() -> None:
    response = client.post("/api/chat", json={"message": "  "})
    assert response.status_code == 400
