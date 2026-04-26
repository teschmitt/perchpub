from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.core.security import verify_password
from app.crud import create_user, update_user
from app.models import UserCreate, UserUpdate
from app.utils import generate_password_reset_token
from tests.utils.user import user_authentication_headers
from tests.utils.utils import random_email, random_lower_string

GENERIC_LOGIN_ERROR = "Incorrect email or password"
GENERIC_RECOVERY_MESSAGE = (
    "If an account exists for this email, a password recovery link has been sent."
)


def test_get_access_token(client: TestClient) -> None:
    login_data = {
        "username": settings.FIRST_SUPERUSER,
        "password": settings.FIRST_SUPERUSER_PASSWORD,
    }
    r = client.post(f"{settings.API_V1_STR}/login/access-token", data=login_data)
    tokens = r.json()
    assert r.status_code == 200
    assert "access_token" in tokens
    assert tokens["access_token"]


def test_get_access_token_incorrect_password(client: TestClient) -> None:
    login_data = {
        "username": settings.FIRST_SUPERUSER,
        "password": "incorrect",
    }
    r = client.post(f"{settings.API_V1_STR}/login/access-token", data=login_data)
    assert r.status_code == 400
    assert r.json()["detail"] == GENERIC_LOGIN_ERROR


def test_get_access_token_inactive_user_matches_wrong_password(
    client: TestClient, db: Session
) -> None:
    email = random_email()
    password = random_lower_string()
    user = create_user(
        session=db,
        user_create=UserCreate(email=email, password=password, is_active=False),
    )
    try:
        r = client.post(
            f"{settings.API_V1_STR}/login/access-token",
            data={"username": email, "password": password},
        )
        assert r.status_code == 400
        assert r.json()["detail"] == GENERIC_LOGIN_ERROR
    finally:
        # keep the inactive user out of later tests' fixtures
        update_user(session=db, db_user=user, user_in=UserUpdate(is_active=True))


def test_use_access_token(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    r = client.post(
        f"{settings.API_V1_STR}/login/test-token",
        headers=superuser_token_headers,
    )
    result = r.json()
    assert r.status_code == 200
    assert "email" in result


def test_recovery_password_known_email(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    with (
        patch("app.core.config.settings.SMTP_HOST", "smtp.example.com"),
        patch("app.core.config.settings.SMTP_USER", "admin@example.com"),
        patch("app.api.routes.login.send_email") as send_email_mock,
    ):
        email = settings.EMAIL_TEST_USER
        r = client.post(
            f"{settings.API_V1_STR}/password-recovery/{email}",
            headers=normal_user_token_headers,
        )
        assert r.status_code == 200
        assert r.json() == {"message": GENERIC_RECOVERY_MESSAGE}
        send_email_mock.assert_called_once()


def test_recovery_password_unknown_email_matches_known_shape(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    with (
        patch("app.core.config.settings.SMTP_HOST", "smtp.example.com"),
        patch("app.core.config.settings.SMTP_USER", "admin@example.com"),
        patch("app.api.routes.login.send_email") as send_email_mock,
    ):
        email = f"{random_lower_string()}@example.com"
        r = client.post(
            f"{settings.API_V1_STR}/password-recovery/{email}",
            headers=normal_user_token_headers,
        )
        assert r.status_code == 200
        assert r.json() == {"message": GENERIC_RECOVERY_MESSAGE}
        send_email_mock.assert_not_called()


def test_reset_password(client: TestClient, db: Session) -> None:
    email = random_email()
    password = random_lower_string()
    new_password = random_lower_string()

    user_create = UserCreate(
        email=email,
        full_name="Test User",
        password=password,
        is_active=True,
        is_superuser=False,
    )
    user = create_user(session=db, user_create=user_create)
    token = generate_password_reset_token(email=email)
    headers = user_authentication_headers(client=client, email=email, password=password)
    data = {"new_password": new_password, "token": token}

    r = client.post(
        f"{settings.API_V1_STR}/reset-password/",
        headers=headers,
        json=data,
    )

    assert r.status_code == 200
    assert r.json() == {"message": "Password updated successfully"}

    db.refresh(user)
    assert verify_password(new_password, user.hashed_password)


def test_reset_password_invalid_token(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    data = {"new_password": "changethis", "token": "invalid"}
    r = client.post(
        f"{settings.API_V1_STR}/reset-password/",
        headers=superuser_token_headers,
        json=data,
    )
    response = r.json()

    assert "detail" in response
    assert r.status_code == 400
    assert response["detail"] == "Invalid token"


def test_reset_password_unknown_email_matches_invalid_token(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    # Forge a signed token for an email that is not in the DB — the signature
    # is valid but the user does not exist. The response must look identical
    # to an invalid-token reply so the caller cannot enumerate addresses.
    token = generate_password_reset_token(email=f"{random_lower_string()}@example.com")
    r = client.post(
        f"{settings.API_V1_STR}/reset-password/",
        headers=superuser_token_headers,
        json={"new_password": random_lower_string(), "token": token},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "Invalid token"


def test_reset_password_inactive_user_matches_invalid_token(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    email = random_email()
    user = create_user(
        session=db,
        user_create=UserCreate(
            email=email, password=random_lower_string(), is_active=False
        ),
    )
    try:
        token = generate_password_reset_token(email=email)
        r = client.post(
            f"{settings.API_V1_STR}/reset-password/",
            headers=superuser_token_headers,
            json={"new_password": random_lower_string(), "token": token},
        )
        assert r.status_code == 400
        assert r.json()["detail"] == "Invalid token"
    finally:
        update_user(session=db, db_user=user, user_in=UserUpdate(is_active=True))
