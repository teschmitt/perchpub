from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from minio.error import S3Error

from app.core.config import settings
from app.main import app


def _fake_response(payload: bytes) -> MagicMock:
    fake_resp = MagicMock()
    fake_resp.stream.return_value = iter([payload])
    return fake_resp


def test_existing_object_streams_with_cache_headers(client: TestClient) -> None:
    payload = b"\x00\x01fakebytes"
    fake_garage = MagicMock()
    fake_garage.get_object.return_value = _fake_response(payload)

    with patch("app.api.routes.media.garage_client", fake_garage):
        r = client.get(f"{settings.API_V1_STR}/media/ab/cd/abcd1234.mp4")

    assert r.status_code == 200, r.text
    assert r.content == payload
    assert r.headers["content-type"] == "video/mp4"
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"
    fake_garage.get_object.assert_called_once_with(
        bucket_name=settings.GARAGE_BUCKET_NAME,
        object_name="ab/cd/abcd1234.mp4",
    )


def test_existing_jpeg_object_uses_extension_content_type(
    client: TestClient,
) -> None:
    payload = b"\xff\xd8\xff\xe0jpegbytes"
    fake_garage = MagicMock()
    fake_garage.get_object.return_value = _fake_response(payload)

    with patch("app.api.routes.media.garage_client", fake_garage):
        r = client.get(f"{settings.API_V1_STR}/media/ab/cd/abcd1234.jpg")

    assert r.status_code == 200, r.text
    assert r.content == payload
    assert r.headers["content-type"] == "image/jpeg"


def test_missing_object_returns_404(client: TestClient) -> None:
    fake_garage = MagicMock()
    fake_garage.get_object.side_effect = S3Error(
        code="NoSuchKey",
        message="The specified key does not exist.",
        resource="/ab/cd/missing.mp4",
        request_id="req-1",
        host_id="host-1",
        response=MagicMock(status=404),
    )

    with patch("app.api.routes.media.garage_client", fake_garage):
        r = client.get(f"{settings.API_V1_STR}/media/ab/cd/missing.mp4")

    assert r.status_code == 404
    assert r.json()["detail"] == "Media not found"


def test_missing_bucket_is_not_masked_as_404() -> None:
    # A missing / misconfigured bucket is a deployment error (wrong or empty
    # GARAGE_BUCKET_NAME), not a per-object miss — it must surface as a 5xx so
    # operators notice, not a benign 404 that hides whole-storage breakage.
    fake_garage = MagicMock()
    fake_garage.get_object.side_effect = S3Error(
        code="NoSuchBucket",
        message="The specified bucket does not exist.",
        resource="/missing-bucket",
        request_id="req-2",
        host_id="host-2",
        response=MagicMock(status=404),
    )

    with (
        TestClient(app, raise_server_exceptions=False) as plain_client,
        patch("app.api.routes.media.garage_client", fake_garage),
    ):
        r = plain_client.get(f"{settings.API_V1_STR}/media/ab/cd/whatever.mp4")

    assert r.status_code == 500
    assert b"Media not found" not in r.content
