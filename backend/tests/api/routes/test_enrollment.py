import uuid

from fastapi.testclient import TestClient

from app.core.config import settings


def test_confirm_unknown_session_returns_404(client: TestClient) -> None:
    r = client.post(
        f"{settings.API_V1_STR}/enrollment/confirm/{uuid.uuid4()}",
        json={"auth_token": "irrelevant"},
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "Unknown enrollment session"
