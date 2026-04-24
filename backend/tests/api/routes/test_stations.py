from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.core.security import get_password_hash
from app.models import Station, User
from tests.utils.utils import random_email, random_lower_string


def _seed_station(db: Session) -> Station:
    user = User(
        email=random_email(),
        hashed_password=get_password_hash(random_lower_string()),
        full_name="Jane Birder",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    station = Station(latitude=0.0, longitude=0.0, owner_id=user.id)
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
