from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.config import settings
from app.core.security import get_password_hash
from app.models import Station, User
from app.models.enrollment import EnrollmentAudit, EnrollmentAuditEvent
from tests.utils.user import user_authentication_headers
from tests.utils.utils import random_email, random_lower_string


def _seed_user(db: Session, *, password: str) -> User:
    user = User(
        email=random_email(),
        hashed_password=get_password_hash(password),
        full_name="Jane Birder",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _seed_station(
    db: Session, *, owner: User | None = None, is_private: bool = False
) -> Station:
    if owner is None:
        owner = _seed_user(db, password=random_lower_string())

    station = Station(
        latitude=0.0,
        longitude=0.0,
        owner_id=owner.id,
        is_private=is_private,
    )
    db.add(station)
    db.commit()
    db.refresh(station)
    return station


def test_update_station_unauthenticated(client: TestClient, db: Session) -> None:
    station = _seed_station(db)
    r = client.put(
        f"{settings.API_V1_STR}/station/{station.id}",
        json={"latitude": 1.0, "longitude": 2.0},
    )
    assert r.status_code == 401


def test_update_station_superuser(
    client: TestClient,
    db: Session,
    superuser_token_headers: dict[str, str],
) -> None:
    station = _seed_station(db)
    r = client.put(
        f"{settings.API_V1_STR}/station/{station.id}",
        json={"latitude": 1.0, "longitude": 2.0},
        headers=superuser_token_headers,
    )
    assert r.status_code == 200


def test_update_station_owner_succeeds(client: TestClient, db: Session) -> None:
    password = random_lower_string()
    owner = _seed_user(db, password=password)
    station = _seed_station(db, owner=owner, is_private=False)

    headers = user_authentication_headers(
        client=client, email=owner.email, password=password
    )
    r = client.put(
        f"{settings.API_V1_STR}/station/{station.id}",
        json={"latitude": 1.5, "longitude": 2.5, "is_private": True},
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["latitude"] == 1.5
    assert body["longitude"] == 2.5
    assert body["is_private"] is True

    db.refresh(station)
    assert station.owner_id == owner.id


def test_update_station_other_user_public_returns_403(
    client: TestClient, db: Session
) -> None:
    station = _seed_station(db, is_private=False)

    other_password = random_lower_string()
    other = _seed_user(db, password=other_password)
    headers = user_authentication_headers(
        client=client, email=other.email, password=other_password
    )

    r = client.put(
        f"{settings.API_V1_STR}/station/{station.id}",
        json={"latitude": 1.0, "longitude": 2.0},
        headers=headers,
    )
    assert r.status_code == 403


def test_update_station_other_user_private_returns_404(
    client: TestClient, db: Session
) -> None:
    station = _seed_station(db, is_private=True)

    other_password = random_lower_string()
    other = _seed_user(db, password=other_password)
    headers = user_authentication_headers(
        client=client, email=other.email, password=other_password
    )

    r = client.put(
        f"{settings.API_V1_STR}/station/{station.id}",
        json={"latitude": 1.0, "longitude": 2.0},
        headers=headers,
    )
    assert r.status_code == 404


def test_read_station_owner_shape(client: TestClient, db: Session) -> None:
    station = _seed_station(db)
    r = client.get(f"{settings.API_V1_STR}/station/{station.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["owner"] is not None
    owner_keys = set(body["owner"].keys())
    assert owner_keys == {"id", "full_name"}


def test_read_stations_anon_excludes_private(client: TestClient, db: Session) -> None:
    public_station = _seed_station(db, is_private=False)
    private_station = _seed_station(db, is_private=True)

    r = client.get(f"{settings.API_V1_STR}/station/")
    assert r.status_code == 200
    ids = {item["id"] for item in r.json()["data"]}
    assert str(public_station.id) in ids
    assert str(private_station.id) not in ids


def test_read_station_anon_private_returns_404(client: TestClient, db: Session) -> None:
    station = _seed_station(db, is_private=True)
    r = client.get(f"{settings.API_V1_STR}/station/{station.id}")
    assert r.status_code == 404


def test_read_station_owner_sees_own_private(client: TestClient, db: Session) -> None:
    password = random_lower_string()
    owner = _seed_user(db, password=password)
    station = _seed_station(db, owner=owner, is_private=True)

    headers = user_authentication_headers(
        client=client, email=owner.email, password=password
    )

    r = client.get(
        f"{settings.API_V1_STR}/station/{station.id}",
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["id"] == str(station.id)


def test_read_station_other_user_private_returns_404(
    client: TestClient, db: Session
) -> None:
    owner = _seed_user(db, password=random_lower_string())
    station = _seed_station(db, owner=owner, is_private=True)

    other_password = random_lower_string()
    other = _seed_user(db, password=other_password)
    headers = user_authentication_headers(
        client=client, email=other.email, password=other_password
    )

    r = client.get(
        f"{settings.API_V1_STR}/station/{station.id}",
        headers=headers,
    )
    assert r.status_code == 404


def test_station_spki_sha256_is_unique(db: Session) -> None:
    owner = _seed_user(db, password=random_lower_string())
    pin = "a" * 64

    first = Station(latitude=0.0, longitude=0.0, owner_id=owner.id, spki_sha256=pin)
    db.add(first)
    db.commit()
    db.refresh(first)
    assert first.spki_sha256 == pin

    duplicate = Station(latitude=0.0, longitude=0.0, owner_id=owner.id, spki_sha256=pin)
    db.add(duplicate)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_read_stations_owner_excludes_revoked(
    client: TestClient, db: Session
) -> None:
    """A revoked station drops out of its owner's active station list (D1)."""
    password = random_lower_string()
    owner = _seed_user(db, password=password)
    live = _seed_station(db, owner=owner, is_private=False)
    revoked = _seed_station(db, owner=owner, is_private=False)
    revoked.revoked_at = datetime.now(timezone.utc)
    db.add(revoked)
    db.commit()

    headers = user_authentication_headers(
        client=client, email=owner.email, password=password
    )
    r = client.get(f"{settings.API_V1_STR}/station/", headers=headers)
    assert r.status_code == 200
    ids = {item["id"] for item in r.json()["data"]}
    assert str(live.id) in ids
    assert str(revoked.id) not in ids


def test_revoke_station_owner_succeeds(client: TestClient, db: Session) -> None:
    """An owner can revoke their own station; a station_revoked audit row is
    written attributing the revocation to the actor.
    """
    password = random_lower_string()
    owner = _seed_user(db, password=password)
    station = _seed_station(db, owner=owner, is_private=False)

    headers = user_authentication_headers(
        client=client, email=owner.email, password=password
    )
    r = client.post(
        f"{settings.API_V1_STR}/station/{station.id}/revoke", headers=headers
    )
    assert r.status_code == 200, r.text
    db.refresh(station)
    assert station.revoked_at is not None
    assert r.json()["revoked_at"] is not None

    rows = db.exec(
        select(EnrollmentAudit).where(
            EnrollmentAudit.station_id == station.id,
            EnrollmentAudit.event == EnrollmentAuditEvent.station_revoked,
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].actor_user_id == owner.id


def test_revoke_station_is_idempotent(client: TestClient, db: Session) -> None:
    """Re-revoking keeps the original revoked_at and writes no second audit row."""
    password = random_lower_string()
    owner = _seed_user(db, password=password)
    station = _seed_station(db, owner=owner, is_private=False)
    headers = user_authentication_headers(
        client=client, email=owner.email, password=password
    )

    r1 = client.post(
        f"{settings.API_V1_STR}/station/{station.id}/revoke", headers=headers
    )
    assert r1.status_code == 200, r1.text
    db.refresh(station)
    first_revoked_at = station.revoked_at
    assert first_revoked_at is not None

    r2 = client.post(
        f"{settings.API_V1_STR}/station/{station.id}/revoke", headers=headers
    )
    assert r2.status_code == 200, r2.text
    db.refresh(station)
    assert station.revoked_at == first_revoked_at  # timestamp unchanged

    rows = db.exec(
        select(EnrollmentAudit).where(
            EnrollmentAudit.station_id == station.id,
            EnrollmentAudit.event == EnrollmentAuditEvent.station_revoked,
        )
    ).all()
    assert len(rows) == 1  # one audit row despite two revoke calls


def test_revoke_station_superuser_succeeds(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str]
) -> None:
    """A superuser can revoke any station."""
    station = _seed_station(db, is_private=True)
    r = client.post(
        f"{settings.API_V1_STR}/station/{station.id}/revoke",
        headers=superuser_token_headers,
    )
    assert r.status_code == 200, r.text
    db.refresh(station)
    assert station.revoked_at is not None


def test_revoke_station_other_user_public_returns_403(
    client: TestClient, db: Session
) -> None:
    """A non-owner revoking a public station gets 403 and it stays unrevoked."""
    station = _seed_station(db, is_private=False)
    other_password = random_lower_string()
    other = _seed_user(db, password=other_password)
    headers = user_authentication_headers(
        client=client, email=other.email, password=other_password
    )
    r = client.post(
        f"{settings.API_V1_STR}/station/{station.id}/revoke", headers=headers
    )
    assert r.status_code == 403
    db.refresh(station)
    assert station.revoked_at is None


def test_revoke_station_other_user_private_returns_404(
    client: TestClient, db: Session
) -> None:
    """A non-owner revoking a private station gets 404 (existence-leak avoidance)."""
    station = _seed_station(db, is_private=True)
    other_password = random_lower_string()
    other = _seed_user(db, password=other_password)
    headers = user_authentication_headers(
        client=client, email=other.email, password=other_password
    )
    r = client.post(
        f"{settings.API_V1_STR}/station/{station.id}/revoke", headers=headers
    )
    assert r.status_code == 404
    db.refresh(station)
    assert station.revoked_at is None


def test_revoke_station_unauthenticated_returns_401(
    client: TestClient, db: Session
) -> None:
    station = _seed_station(db)
    r = client.post(f"{settings.API_V1_STR}/station/{station.id}/revoke")
    assert r.status_code == 401


def test_read_stations_owner_sees_own_and_public(
    client: TestClient, db: Session
) -> None:
    password = random_lower_string()
    owner = _seed_user(db, password=password)
    public_station = _seed_station(db, is_private=False)
    own_private = _seed_station(db, owner=owner, is_private=True)
    other_private = _seed_station(db, is_private=True)

    headers = user_authentication_headers(
        client=client, email=owner.email, password=password
    )
    r = client.get(f"{settings.API_V1_STR}/station/", headers=headers)
    assert r.status_code == 200
    ids = {item["id"] for item in r.json()["data"]}
    assert str(public_station.id) in ids
    assert str(own_private.id) in ids
    assert str(other_private.id) not in ids
