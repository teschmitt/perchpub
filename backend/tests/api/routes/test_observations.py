import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.core.security import get_password_hash
from app.models import Observation, Species, Station, User
from tests.utils.utils import random_email, random_lower_string


def _seed_station_and_species(db: Session) -> tuple[Station, Species]:
    user = User(
        email=random_email(),
        hashed_password=get_password_hash(random_lower_string()),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    station = Station(latitude=0.0, longitude=0.0, owner_id=user.id)
    db.add(station)
    db.commit()
    db.refresh(station)

    species = Species(
        scientific_name=random_lower_string(),
        classification_id=1,
    )
    db.add(species)
    db.commit()
    db.refresh(species)
    return station, species


def _observation_payload(station_id: uuid.UUID, species_id: uuid.UUID) -> dict:
    return {
        "confidence_score": 0.9,
        "classification_result": [{"label": "bird", "score": 0.9}],
        "station_id": str(station_id),
        "species_id": str(species_id),
        "object_name": "test/object.jpg",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "latitude": 0.0,
        "longitude": 0.0,
    }


def test_create_observation_unauthenticated(client: TestClient, db: Session) -> None:
    station, species = _seed_station_and_species(db)
    r = client.post(
        f"{settings.API_V1_STR}/observation/",
        json=_observation_payload(station.id, species.id),
    )
    assert r.status_code == 401


def test_create_observation_superuser(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str]
) -> None:
    station, species = _seed_station_and_species(db)
    r = client.post(
        f"{settings.API_V1_STR}/observation/",
        json=_observation_payload(station.id, species.id),
        headers=superuser_token_headers,
    )
    assert r.status_code == 200


def test_update_observation_unauthenticated(client: TestClient, db: Session) -> None:
    station, species = _seed_station_and_species(db)
    observation = Observation(
        confidence_score=0.1,
        classification_result=[],
        station_id=station.id,
        species_id=species.id,
        object_name="test/object.jpg",
        observed_at=datetime.now(timezone.utc),
        latitude=0.0,
        longitude=0.0,
    )
    db.add(observation)
    db.commit()
    db.refresh(observation)

    r = client.put(
        f"{settings.API_V1_STR}/observation/{observation.id}",
        json={
            "confidence_score": 0.95,
            "classification_result": [],
            "species_id": str(species.id),
        },
    )
    assert r.status_code == 401
