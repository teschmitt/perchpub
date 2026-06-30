"""The bearer-token authentication contract (add-frontend-api-prerequisites).

Authentication failures on JWT-protected endpoints must return ``401`` with the
generic detail ``"Could not validate credentials"`` so a backend-for-frontend
can treat any ``401`` as "session is dead → clear the cookie". Authorization
failures for a *successfully* authenticated user must stay ``403``.
"""

import uuid
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.core.security import create_access_token
from app.crud import create_user, update_user
from app.models import UserCreate, UserUpdate
from tests.utils.utils import random_email, random_lower_string

ME_URL = f"{settings.API_V1_STR}/users/me"
SUPERUSER_URL = f"{settings.API_V1_STR}/users/"
GENERIC_DETAIL = "Could not validate credentials"


def test_expired_token_returns_401(client: TestClient) -> None:
    token = create_access_token(uuid.uuid4(), expires_delta=timedelta(minutes=-5))
    r = client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    assert r.json()["detail"] == GENERIC_DETAIL


def test_malformed_token_returns_401(client: TestClient) -> None:
    r = client.get(ME_URL, headers={"Authorization": "Bearer not-a-valid-jwt"})
    assert r.status_code == 401
    assert r.json()["detail"] == GENERIC_DETAIL


def test_token_for_deleted_user_returns_401(client: TestClient) -> None:
    # A correctly-signed, unexpired token whose subject is not (or no longer) a
    # user. Must be 401, not 404, and must not disclose that the user is missing.
    token = create_access_token(uuid.uuid4(), expires_delta=timedelta(minutes=60))
    r = client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    assert r.json()["detail"] == GENERIC_DETAIL


def test_token_for_inactive_user_returns_401(client: TestClient, db: Session) -> None:
    user = create_user(
        session=db,
        user_create=UserCreate(
            email=random_email(), password=random_lower_string(), is_active=False
        ),
    )
    try:
        token = create_access_token(user.id, expires_delta=timedelta(minutes=60))
        r = client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401
        assert r.json()["detail"] == GENERIC_DETAIL
    finally:
        # keep the inactive user out of later tests' fixtures
        update_user(session=db, db_user=user, user_in=UserUpdate(is_active=True))


def test_missing_token_returns_401(client: TestClient) -> None:
    r = client.get(ME_URL)
    assert r.status_code == 401


def test_non_superuser_on_superuser_route_stays_403(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    # Regression: authorization failures are untouched by the auth contract.
    r = client.get(SUPERUSER_URL, headers=normal_user_token_headers)
    assert r.status_code == 403
