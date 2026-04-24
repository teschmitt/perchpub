from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.core.security import get_password_hash
from app.models import Station, User
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


def test_read_station_anon_private_returns_404(
    client: TestClient, db: Session
) -> None:
    station = _seed_station(db, is_private=True)
    r = client.get(f"{settings.API_V1_STR}/station/{station.id}")
    assert r.status_code == 404


def test_read_station_owner_sees_own_private(
    client: TestClient, db: Session
) -> None:
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
