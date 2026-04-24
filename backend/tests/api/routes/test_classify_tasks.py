import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.core.security import get_password_hash
from app.models import ClassifyTask, Observation, Species, Station, Upload, User
from tests.utils.utils import random_email, random_lower_string


def _create_classify_task(
    db: Session, *, with_observation: bool = False
) -> ClassifyTask:
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

    upload = Upload(station_id=station.id, object_name="test/object.jpg")
    db.add(upload)
    db.commit()
    db.refresh(upload)

    observation_id: uuid.UUID | None = None
    if with_observation:
        species = Species(
            scientific_name=random_lower_string(),
            classification_id=1,
        )
        db.add(species)
        db.commit()
        db.refresh(species)

        observation = Observation(
            confidence_score=0.9,
            classification_result=[{"label": "bird", "score": 0.9}],
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
        observation_id = observation.id

    task = ClassifyTask(
        object_name="test/object.jpg",
        upload_id=upload.id,
        observation_id=observation_id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def test_read_classify_task(client: TestClient, db: Session) -> None:
    task = _create_classify_task(db)
    r = client.get(f"{settings.API_V1_STR}/classify-task/{task.id}")
    assert r.status_code == 200
    assert r.json()["id"] == str(task.id)


def test_read_classify_task_not_found(client: TestClient) -> None:
    r = client.get(f"{settings.API_V1_STR}/classify-task/{uuid.uuid4()}")
    assert r.status_code == 404
    assert r.json()["detail"] == "Classify task not found"


def test_read_classify_task_upload_shape(client: TestClient, db: Session) -> None:
    task = _create_classify_task(db)
    r = client.get(f"{settings.API_V1_STR}/classify-task/{task.id}")
    assert r.status_code == 200
    body = r.json()
    assert set(body["upload"].keys()) == {
        "id",
        "created_at",
        "updated_at",
        "station_id",
        "object_name",
    }


def test_read_classify_task_observation_none(client: TestClient, db: Session) -> None:
    task = _create_classify_task(db)
    r = client.get(f"{settings.API_V1_STR}/classify-task/{task.id}")
    assert r.status_code == 200
    assert r.json()["observation"] is None


def test_read_classify_task_observation_shape(client: TestClient, db: Session) -> None:
    task = _create_classify_task(db, with_observation=True)
    r = client.get(f"{settings.API_V1_STR}/classify-task/{task.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["observation"] is not None
    observation_keys = set(body["observation"].keys())
    assert observation_keys == {
        "id",
        "confidence_score",
        "classification_result",
        "species",
        "station",
        "observed_at",
        "object_name",
    }
