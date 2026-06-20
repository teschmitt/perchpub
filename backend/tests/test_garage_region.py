import importlib

from app.core.config import settings


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
