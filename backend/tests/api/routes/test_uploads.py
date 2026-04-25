import io
import uuid
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.config import settings
from app.core.security import get_password_hash
from app.models import ClassifyTask, Station, User
from tests.utils.utils import random_email, random_lower_string

# Matches the hard-coded station_id in app/api/routes/uploads.py.
# WI-09 leaves that TODO in place; WI-17 (mTLS) will replace it.
HARDCODED_STATION_ID = uuid.UUID("e26042ab-a0b8-4264-90a4-f79da829d2ac")


def _ensure_hardcoded_station(db: Session) -> None:
    existing = db.get(Station, HARDCODED_STATION_ID)
    if existing is not None:
        return
    owner = User(
        email=random_email(),
        hashed_password=get_password_hash(random_lower_string()),
    )
    db.add(owner)
    db.commit()
    db.refresh(owner)
    db.add(
        Station(
            id=HARDCODED_STATION_ID,
            latitude=0.0,
            longitude=0.0,
            owner_id=owner.id,
        )
    )
    db.commit()


def test_upload_unauthenticated(client: TestClient) -> None:
    r = client.post(
        f"{settings.API_V1_STR}/upload/",
        files={"file": ("clip.mp4", b"hello", "video/mp4")},
    )
    assert r.status_code == 401


def test_upload_creates_classify_task_and_enqueues(
    client: TestClient,
    db: Session,
    superuser_token_headers: dict[str, str],
) -> None:
    _ensure_hardcoded_station(db)
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
            headers=superuser_token_headers,
        )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "Prepared"

    task_id = uuid.UUID(body["id"])
    persisted = db.get(ClassifyTask, task_id)
    assert persisted is not None
    assert persisted.status.value == "Prepared"

    fake_garage.put_object.assert_called_once()
    fake_classify_video.assert_called_once()
    args, _kwargs = fake_classify_video.call_args
    assert args[0] == fake_write_result.object_name
    assert args[1] == task_id


def test_upload_rejects_oversize_payload(
    client: TestClient,
    db: Session,
    superuser_token_headers: dict[str, str],
) -> None:
    _ensure_hardcoded_station(db)
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
            headers=superuser_token_headers,
        )

    assert r.status_code == 413
    fake_garage.put_object.assert_not_called()
    fake_classify_video.assert_not_called()
    post_count = db.exec(select(ClassifyTask)).all()
    assert len(post_count) == len(pre_count)
