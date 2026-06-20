import importlib

from app.core.config import Settings, settings


def test_garage_region_defaults_to_garage() -> None:
    # Default preserves Garage/dev + Minio/test behaviour (no signature change).
    assert settings.GARAGE_REGION == "garage"


def test_garage_region_reads_from_env(monkeypatch) -> None:
    monkeypatch.setenv("GARAGE_REGION", "gra")
    # Pass the other required/secret fields explicitly so construction is
    # warning-free regardless of the ambient env; leave GARAGE_REGION unset
    # as a kwarg so it is sourced from the environment we just set.
    s = Settings(
        PROJECT_NAME="t",
        POSTGRES_SERVER="db",
        POSTGRES_USER="u",
        POSTGRES_PASSWORD="pw",
        FIRST_SUPERUSER="a@b.co",
        FIRST_SUPERUSER_PASSWORD="pw",
        SECRET_KEY="x" * 43,
        ENROLLMENT_HMAC_KEY_HEX="ab" * 32,
    )
    assert s.GARAGE_REGION == "gra"


def test_uploads_client_uses_configured_region(monkeypatch) -> None:
    # Reloading the module re-runs the module-level Minio(...) construction
    # with the patched setting, proving the region is read from config (a
    # hardcoded "garage" would not become "test-region-xyz").
    monkeypatch.setattr(settings, "GARAGE_REGION", "test-region-xyz")
    from app.api.routes import uploads

    importlib.reload(uploads)
    try:
        assert uploads.garage_client._base_url.region == "test-region-xyz"
    finally:
        monkeypatch.setattr(settings, "GARAGE_REGION", "garage")
        importlib.reload(uploads)


def test_tasks_client_uses_settings_region() -> None:
    from app import tasks

    assert tasks.garage_client._base_url.region == settings.GARAGE_REGION
