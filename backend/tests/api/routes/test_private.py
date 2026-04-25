from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.config import settings
from app.models import User

DEBUG_KEY_HEADER = "X-Perchpub-Debug-Key"
TEST_DEBUG_KEY = "test-debug-key"


def test_private_create_user_unauthenticated(client: TestClient) -> None:
    with patch("app.api.routes.private.settings.DEBUG_KEY", TEST_DEBUG_KEY):
        r = client.post(
            f"{settings.API_V1_STR}/private/users/",
            json={
                "email": "noauth@example.com",
                "password": "password123",
                "full_name": "No Auth",
            },
        )
    assert r.status_code == 401


def test_private_create_user_missing_debug_key_header(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    with patch("app.api.routes.private.settings.DEBUG_KEY", TEST_DEBUG_KEY):
        r = client.post(
            f"{settings.API_V1_STR}/private/users/",
            json={
                "email": "noheader@example.com",
                "password": "password123",
                "full_name": "No Header",
            },
            headers=superuser_token_headers,
        )
    assert r.status_code == 403


def test_private_create_user_wrong_debug_key(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    with patch("app.api.routes.private.settings.DEBUG_KEY", TEST_DEBUG_KEY):
        r = client.post(
            f"{settings.API_V1_STR}/private/users/",
            json={
                "email": "wrongkey@example.com",
                "password": "password123",
                "full_name": "Wrong Key",
            },
            headers={**superuser_token_headers, DEBUG_KEY_HEADER: "nope"},
        )
    assert r.status_code == 403


def test_private_create_user_disabled_when_debug_key_unset(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    with patch("app.api.routes.private.settings.DEBUG_KEY", ""):
        r = client.post(
            f"{settings.API_V1_STR}/private/users/",
            json={
                "email": "disabled@example.com",
                "password": "password123",
                "full_name": "Disabled",
            },
            headers={**superuser_token_headers, DEBUG_KEY_HEADER: "anything"},
        )
    assert r.status_code == 403


def test_private_create_user_happy_path(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str]
) -> None:
    with patch("app.api.routes.private.settings.DEBUG_KEY", TEST_DEBUG_KEY):
        r = client.post(
            f"{settings.API_V1_STR}/private/users/",
            json={
                "email": "pollo@listo.com",
                "password": "password123",
                "full_name": "Pollo Listo",
            },
            headers={**superuser_token_headers, DEBUG_KEY_HEADER: TEST_DEBUG_KEY},
        )

    assert r.status_code == 200, r.text
    data = r.json()
    user = db.exec(select(User).where(User.id == data["id"])).first()
    assert user
    assert user.email == "pollo@listo.com"
    assert user.full_name == "Pollo Listo"
