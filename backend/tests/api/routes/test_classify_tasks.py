import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.core.security import get_password_hash
from app.models import ClassifyTask, Station, Upload, User
from tests.utils.utils import random_email, random_lower_string


def _create_classify_task(db: Session) -> ClassifyTask:
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

    task = ClassifyTask(object_name="test/object.jpg", upload_id=upload.id)
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
