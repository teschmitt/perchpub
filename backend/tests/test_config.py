import pytest

from app.core.config import Settings

_BASE_KWARGS = {
    "PROJECT_NAME": "perchpub-test",
    "POSTGRES_SERVER": "db",
    "POSTGRES_USER": "u",
    "POSTGRES_PASSWORD": "p",
    "FIRST_SUPERUSER": "admin@example.com",
    "FIRST_SUPERUSER_PASSWORD": "pw",
    "STATION_EDGE_URL": "https://api.example.test",
}
_VALID_HMAC = "d793ba482eb774a6d0d62dc05f5608f5839cc01f6e1160696a937c8613e6d969"
_VALID_SECRET = "OSuIw3deJ29NfwfZNM4GMta4tdKQpU2ETfK1GB5W50Y"


def test_missing_secret_key_fails_in_production() -> None:
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            SECRET_KEY="",
            ENROLLMENT_HMAC_KEY_HEX=_VALID_HMAC,
            **_BASE_KWARGS,
        )


def test_missing_hmac_key_fails_in_production() -> None:
    with pytest.raises(ValueError, match="ENROLLMENT_HMAC_KEY_HEX"):
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            SECRET_KEY=_VALID_SECRET,
            ENROLLMENT_HMAC_KEY_HEX="",
            **_BASE_KWARGS,
        )


def test_short_hmac_key_fails_in_production() -> None:
    with pytest.raises(ValueError, match="ENROLLMENT_HMAC_KEY_HEX"):
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            SECRET_KEY=_VALID_SECRET,
            ENROLLMENT_HMAC_KEY_HEX="deadbeef",
            **_BASE_KWARGS,
        )


def test_non_hex_hmac_key_fails_in_production() -> None:
    with pytest.raises(ValueError, match="ENROLLMENT_HMAC_KEY_HEX"):
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            SECRET_KEY=_VALID_SECRET,
            ENROLLMENT_HMAC_KEY_HEX="z" * 64,
            **_BASE_KWARGS,
        )


def test_valid_secrets_load_in_production() -> None:
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="production",
        SECRET_KEY=_VALID_SECRET,
        ENROLLMENT_HMAC_KEY_HEX=_VALID_HMAC,
        **_BASE_KWARGS,
    )
    assert settings.SECRET_KEY == _VALID_SECRET
    assert settings.ENROLLMENT_HMAC_KEY_HEX == _VALID_HMAC


def test_default_secret_key_fails_in_production() -> None:
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            SECRET_KEY="changethis",
            ENROLLMENT_HMAC_KEY_HEX=_VALID_HMAC,
            **_BASE_KWARGS,
        )


def test_default_postgres_password_fails_in_production() -> None:
    kwargs = {**_BASE_KWARGS, "POSTGRES_PASSWORD": "changethis"}
    with pytest.raises(ValueError, match="POSTGRES_PASSWORD"):
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            SECRET_KEY=_VALID_SECRET,
            ENROLLMENT_HMAC_KEY_HEX=_VALID_HMAC,
            **kwargs,
        )


def test_default_first_superuser_password_fails_in_production() -> None:
    kwargs = {**_BASE_KWARGS, "FIRST_SUPERUSER_PASSWORD": "changethis"}
    with pytest.raises(ValueError, match="FIRST_SUPERUSER_PASSWORD"):
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            SECRET_KEY=_VALID_SECRET,
            ENROLLMENT_HMAC_KEY_HEX=_VALID_HMAC,
            **kwargs,
        )


def test_missing_secret_key_warns_in_local() -> None:
    with pytest.warns(UserWarning, match="SECRET_KEY"):
        settings = Settings(
            _env_file=None,
            ENVIRONMENT="local",
            SECRET_KEY="",
            ENROLLMENT_HMAC_KEY_HEX=_VALID_HMAC,
            **_BASE_KWARGS,
        )
    assert settings.SECRET_KEY == ""


def _valid_prod_settings(**overrides: object) -> Settings:
    kwargs = {
        **_BASE_KWARGS,
        "SECRET_KEY": _VALID_SECRET,
        "ENROLLMENT_HMAC_KEY_HEX": _VALID_HMAC,
    }
    kwargs.update(overrides)
    return Settings(_env_file=None, ENVIRONMENT="production", **kwargs)  # type: ignore[arg-type]


def test_missing_station_edge_url_fails_in_production() -> None:
    with pytest.raises(ValueError, match="STATION_EDGE_URL"):
        _valid_prod_settings(STATION_EDGE_URL="")


def test_missing_station_edge_url_warns_in_local() -> None:
    kwargs = {**_BASE_KWARGS, "STATION_EDGE_URL": ""}
    with pytest.warns(UserWarning, match="STATION_EDGE_URL"):
        settings = Settings(
            _env_file=None,
            ENVIRONMENT="local",
            SECRET_KEY=_VALID_SECRET,
            ENROLLMENT_HMAC_KEY_HEX=_VALID_HMAC,
            **kwargs,
        )
    assert settings.STATION_EDGE_URL == ""


def test_station_edge_url_strips_trailing_slash() -> None:
    """The emitted origin never carries a trailing slash — normalized at load."""
    settings = _valid_prod_settings(STATION_EDGE_URL="https://api.perchpub.example/")
    assert settings.STATION_EDGE_URL == "https://api.perchpub.example"


def test_station_edge_url_kept_verbatim_when_already_origin() -> None:
    settings = _valid_prod_settings(STATION_EDGE_URL="https://api.perchpub.example")
    assert settings.STATION_EDGE_URL == "https://api.perchpub.example"
