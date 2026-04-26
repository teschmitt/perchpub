"""Behavioral tests for the mTLS-aware CurrentStation dependency.

The dependency is exercised directly (no test route) — its contract is a
plain function call: build a Request stub, get a Station back or an
HTTPException(401) with the same generic detail. Threat-model docstring
in app/api/deps.py covers why that single status is load-bearing.
"""

from __future__ import annotations

import urllib.parse
from collections.abc import Generator
from unittest.mock import MagicMock

import pytest
from cryptography.hazmat.primitives.serialization import Encoding
from fastapi import HTTPException
from sqlmodel import Session

from app.api.deps import _load_device_ca, get_current_station
from app.core.config import settings
from app.core.security import get_password_hash
from app.models import Station, User
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


def _request(headers: dict[str, str]) -> MagicMock:
    req = MagicMock()
    req.headers = headers
    return req


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


def test_missing_header_returns_401(db: Session, device_ca: mtls.TestCA) -> None:
    with pytest.raises(HTTPException) as exc:
        get_current_station(session=db, request=_request({}))
    assert exc.value.status_code == 401
    assert exc.value.detail == "client certificate required"


def test_malformed_header_returns_401(db: Session, device_ca: mtls.TestCA) -> None:
    with pytest.raises(HTTPException) as exc:
        get_current_station(
            session=db,
            request=_request({settings.MTLS_CLIENT_CERT_HEADER: "totally garbage"}),
        )
    assert exc.value.status_code == 401
    assert exc.value.detail == "client certificate required"


def test_leaf_signed_by_different_ca_returns_401(
    db: Session, device_ca: mtls.TestCA
) -> None:
    foreign_ca = mtls.make_ca("Other CA")
    foreign_leaf = mtls.make_leaf(foreign_ca, "imposter.local")
    encoded = urllib.parse.quote(foreign_leaf.cert_pem)
    with pytest.raises(HTTPException) as exc:
        get_current_station(
            session=db,
            request=_request({settings.MTLS_CLIENT_CERT_HEADER: encoded}),
        )
    assert exc.value.status_code == 401
    assert exc.value.detail == "client certificate required"


def test_no_station_with_matching_pin_returns_401(
    db: Session, device_ca: mtls.TestCA
) -> None:
    leaf = mtls.make_leaf(device_ca, "unenrolled.local")
    encoded = urllib.parse.quote(leaf.cert_pem)
    with pytest.raises(HTTPException) as exc:
        get_current_station(
            session=db,
            request=_request({settings.MTLS_CLIENT_CERT_HEADER: encoded}),
        )
    assert exc.value.status_code == 401
    assert exc.value.detail == "client certificate required"


def test_valid_leaf_returns_matching_station(
    db: Session, device_ca: mtls.TestCA
) -> None:
    leaf = mtls.make_leaf(device_ca, "device-mtls04.local")
    persisted = _persist_station(db, spki_pin=leaf.spki_sha256_hex)
    encoded = urllib.parse.quote(leaf.cert_pem)
    station = get_current_station(
        session=db,
        request=_request({settings.MTLS_CLIENT_CERT_HEADER: encoded}),
    )
    assert station.id == persisted.id
    assert station.spki_sha256 == leaf.spki_sha256_hex


def test_valid_leaf_body_only_no_armor_returns_matching_station(
    db: Session, device_ca: mtls.TestCA
) -> None:
    """Traefik 3.x's `passTLSClientCert.pem: true` strips the BEGIN/END armor.

    The dependency has to reattach it before parsing — surfaced during the
    end-to-end smoke against a real proxy.
    """
    leaf = mtls.make_leaf(device_ca, "device-traefik3.local")
    persisted = _persist_station(db, spki_pin=leaf.spki_sha256_hex)
    body_only = (
        leaf.cert_pem.replace("-----BEGIN CERTIFICATE-----\n", "")
        .replace("\n-----END CERTIFICATE-----\n", "")
        .replace("-----END CERTIFICATE-----\n", "")
    )
    encoded = urllib.parse.quote(body_only)
    station = get_current_station(
        session=db,
        request=_request({settings.MTLS_CLIENT_CERT_HEADER: encoded}),
    )
    assert station.id == persisted.id
