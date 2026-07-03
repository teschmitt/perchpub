import io
import urllib.parse
import uuid
from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from cryptography.hazmat.primitives.serialization import Encoding
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.api.deps import _load_device_ca
from app.core.config import settings
from app.core.security import get_password_hash
from app.main import app
from app.models import ClassifyTask, Station, User
from tests.utils import mtls
from tests.utils.utils import random_email, random_lower_string


@pytest.fixture
def device_ca(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> Generator[mtls.TestCA, None, None]:
    ca = mtls.make_ca()
    ca_pem_path = tmp_path / "device-ca.pem"
    ca_pem_path.write_bytes(ca.cert.public_bytes(Encoding.PEM))
    monkeypatch.setattr(settings, "DEVICE_CLIENT_CA_CERT_PATH", str(ca_pem_path))
    _load_device_ca.cache_clear()
    yield ca
    _load_device_ca.cache_clear()


def _persist_station(db: Session, spki_pin: str) -> Station:
    user = User(
        email=random_email(),
        hashed_password=get_password_hash(random_lower_string()),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    station = Station(
        latitude=0.0, longitude=0.0, owner_id=user.id, spki_sha256=spki_pin
    )
    db.add(station)
    db.commit()
    db.refresh(station)
    return station


def _cert_header(leaf: mtls.TestLeaf) -> dict[str, str]:
    return {settings.MTLS_CLIENT_CERT_HEADER: urllib.parse.quote(leaf.cert_pem)}


def test_upload_without_cert_header_returns_401(client: TestClient) -> None:
    r = client.post(
        f"{settings.API_V1_STR}/upload/",
        files={"file": ("clip.mp4", b"hello", "video/mp4")},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "client certificate required"


def test_upload_with_unenrolled_cert_returns_401(
    client: TestClient, device_ca: mtls.TestCA
) -> None:
    leaf = mtls.make_leaf(device_ca, "unenrolled.local")
    r = client.post(
        f"{settings.API_V1_STR}/upload/",
        files={"file": ("clip.mp4", b"hello", "video/mp4")},
        headers=_cert_header(leaf),
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "client certificate required"


def test_upload_creates_classify_task_bound_to_authenticated_station(
    client: TestClient, db: Session, device_ca: mtls.TestCA
) -> None:
    leaf = mtls.make_leaf(device_ca, "device-upload.local")
    station = _persist_station(db, spki_pin=leaf.spki_sha256_hex)
    payload = b"a-tiny-payload"

    fake_write_result = MagicMock()
    fake_write_result.object_name = "ab/cd/abcd1234.mp4"
    fake_garage = MagicMock()
    fake_garage.put_object.return_value = fake_write_result

    fake_classify_video = MagicMock()

    with (
        patch("app.api.routes.uploads.garage_client", fake_garage),
        patch("app.tasks.classify_video", fake_classify_video),
    ):
        r = client.post(
            f"{settings.API_V1_STR}/upload/",
            files={"file": ("clip.mp4", payload, "video/mp4")},
            headers=_cert_header(leaf),
        )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "Prepared"

    task_id = uuid.UUID(body["id"])
    persisted = db.get(ClassifyTask, task_id)
    assert persisted is not None
    assert persisted.upload.station_id == station.id

    fake_garage.put_object.assert_called_once()
    fake_classify_video.assert_called_once()
    args, _kwargs = fake_classify_video.call_args
    assert args[0] == fake_write_result.object_name
    assert args[1] == task_id


def test_upload_leaf_spoofed_san_binds_only_to_spki_station(
    client: TestClient, db: Session, device_ca: mtls.TestCA
) -> None:
    """A leaf whose CN/SAN names another tenant's station still authenticates
    ONLY as the station matching its SHA-256(SPKI).

    step-ca copies CSR-requested SANs verbatim into the leaf, so any station
    can obtain a cert bearing an arbitrary SAN — including one naming another
    tenant's device. This locks in that a SAN never sways which account a
    request touches; identity is the enrollment-time SPKI pin alone.
    """
    # Another tenant's station is present in the DB; the spoofed SAN names it.
    victim_leaf = mtls.make_leaf(device_ca, "victim-station.example")
    victim = _persist_station(db, spki_pin=victim_leaf.spki_sha256_hex)

    # Attacker holds its own device key and requests a leaf whose SAN spoofs the
    # victim's hostname — but the leaf's OWN SPKI is what is pinned.
    spoof_leaf = mtls.make_leaf(
        device_ca, "victim-station.example", dns_sans=["victim-station.example"]
    )
    attacker_station = _persist_station(db, spki_pin=spoof_leaf.spki_sha256_hex)
    assert attacker_station.id != victim.id

    fake_write_result = MagicMock()
    fake_write_result.object_name = "ab/cd/spoof.mp4"
    fake_garage = MagicMock()
    fake_garage.put_object.return_value = fake_write_result

    with (
        patch("app.api.routes.uploads.garage_client", fake_garage),
        patch("app.tasks.classify_video", MagicMock()),
    ):
        r = client.post(
            f"{settings.API_V1_STR}/upload/",
            files={"file": ("clip.mp4", b"payload", "video/mp4")},
            headers=_cert_header(spoof_leaf),
        )

    assert r.status_code == 200, r.text
    task = db.get(ClassifyTask, uuid.UUID(r.json()["id"]))
    assert task is not None
    # Bound to the SPKI-matched station, never to the SAN-named victim.
    assert task.upload.station_id == attacker_station.id
    assert task.upload.station_id != victim.id


def test_upload_leaf_spoofed_san_without_spki_match_returns_401(
    client: TestClient, db: Session, device_ca: mtls.TestCA
) -> None:
    """A valid device-CA leaf whose CN/SAN names a real enrolled station but
    whose OWN SPKI matches no station is refused with the generic 401 — the
    CN/SAN cannot stand in for a missing SPKI pin.
    """
    victim_leaf = mtls.make_leaf(device_ca, "victim-station.example")
    _persist_station(db, spki_pin=victim_leaf.spki_sha256_hex)

    # Fresh (unenrolled) key, but CN + SAN both name the enrolled victim.
    orphan_leaf = mtls.make_leaf(
        device_ca, "victim-station.example", dns_sans=["victim-station.example"]
    )

    r = client.post(
        f"{settings.API_V1_STR}/upload/",
        files={"file": ("clip.mp4", b"hello", "video/mp4")},
        headers=_cert_header(orphan_leaf),
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "client certificate required"


def test_upload_returns_generic_500_on_unexpected_storage_error(
    db: Session, device_ca: mtls.TestCA
) -> None:
    leaf = mtls.make_leaf(device_ca, "device-error.local")
    _persist_station(db, spki_pin=leaf.spki_sha256_hex)

    fake_garage = MagicMock()
    fake_garage.put_object.side_effect = RuntimeError("connection reset by peer")
    fake_classify_video = MagicMock()

    # raise_server_exceptions=False so FastAPI's default 500 handler runs
    # in-process instead of propagating the exception out of TestClient.
    with (
        TestClient(app, raise_server_exceptions=False) as plain_client,
        patch("app.api.routes.uploads.garage_client", fake_garage),
        patch("app.tasks.classify_video", fake_classify_video),
    ):
        r = plain_client.post(
            f"{settings.API_V1_STR}/upload/",
            files={"file": ("clip.mp4", b"hello", "video/mp4")},
            headers=_cert_header(leaf),
        )

    assert r.status_code == 500
    assert b"connection reset" not in r.content
    fake_classify_video.assert_not_called()


def test_upload_returns_generic_500_on_classify_enqueue_failure(
    db: Session, device_ca: mtls.TestCA
) -> None:
    leaf = mtls.make_leaf(device_ca, "device-enqueue.local")
    _persist_station(db, spki_pin=leaf.spki_sha256_hex)

    fake_write_result = MagicMock()
    fake_write_result.object_name = "ab/cd/abcd1234.mp4"
    fake_garage = MagicMock()
    fake_garage.put_object.return_value = fake_write_result

    fake_classify_video = MagicMock(side_effect=RuntimeError("redis unavailable"))

    with (
        TestClient(app, raise_server_exceptions=False) as plain_client,
        patch("app.api.routes.uploads.garage_client", fake_garage),
        patch("app.tasks.classify_video", fake_classify_video),
    ):
        r = plain_client.post(
            f"{settings.API_V1_STR}/upload/",
            files={"file": ("clip.mp4", b"hello", "video/mp4")},
            headers=_cert_header(leaf),
        )

    assert r.status_code == 500
    assert b"redis unavailable" not in r.content
    fake_classify_video.assert_called_once()


def test_upload_rejects_oversize_payload(
    client: TestClient, db: Session, device_ca: mtls.TestCA
) -> None:
    leaf = mtls.make_leaf(device_ca, "device-oversize.local")
    _persist_station(db, spki_pin=leaf.spki_sha256_hex)
    payload = b"x" * 200

    fake_garage = MagicMock()
    pre_count = db.exec(select(ClassifyTask)).all()

    fake_classify_video = MagicMock()

    with (
        patch("app.api.routes.uploads.garage_client", fake_garage),
        patch("app.api.routes.uploads.settings.MAX_UPLOAD_BYTES", 100),
        patch("app.tasks.classify_video", fake_classify_video),
    ):
        r = client.post(
            f"{settings.API_V1_STR}/upload/",
            files={"file": ("big.mp4", io.BytesIO(payload), "video/mp4")},
            headers=_cert_header(leaf),
        )

    assert r.status_code == 413
    fake_garage.put_object.assert_not_called()
    fake_classify_video.assert_not_called()
    post_count = db.exec(select(ClassifyTask)).all()
    assert len(post_count) == len(pre_count)
