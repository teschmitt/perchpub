"""WI-INT-3: real Huey worker against real Redis + Minio + TF Lite.

Test process and worker container talk to the same compose-managed
Redis, Postgres, and Minio. The test enqueues `classify_video` for
real (no `.call_local()`); the worker subprocess running
`huey_consumer.py app.tasks.huey_client` picks it up, fetches the
video from Minio, loads the seeded fixture model, runs inference, and
persists an Observation. The test polls the DB for the status flip.

Catches what the unit suite can't: Huey arg serialization (uuid.UUID
across pickle), worker-image vs api-image divergence, Redis client
config drift, and FU-08-class import-time regressions in app.tasks.
"""

import io
import time
import uuid

import pytest
from minio import Minio
from sqlmodel import Session

from app import tasks as tasks_module
from app.core.config import settings
from app.core.security import get_password_hash
from app.models.classify_task import ClassifyTask, ClassifyTaskStatus
from app.models.observation import Observation
from app.models.species import Species
from app.models.station import Station
from app.models.upload import Upload
from app.models.user import User


def _wait_for_terminal(
    db: Session, task_id: uuid.UUID, timeout_s: float
) -> ClassifyTask:
    """Poll the DB until the worker writes a terminal status, or fail."""
    deadline = time.monotonic() + timeout_s
    last_status: ClassifyTaskStatus | None = None
    while time.monotonic() < deadline:
        db.expire_all()
        task = db.get(ClassifyTask, task_id)
        if task is not None:
            last_status = task.status
            if task.status in (
                ClassifyTaskStatus.Success,
                ClassifyTaskStatus.Failed,
            ):
                return task
        time.sleep(0.5)
    pytest.fail(
        f"task {task_id} did not finish within {timeout_s}s; "
        f"last status={last_status}"
    )


def test_worker_classifies_video_and_persists_observation(
    db: Session,
    minio_client: Minio,
    video_bytes: bytes,
) -> None:
    object_name = f"int/{uuid.uuid4().hex}.mp4"

    # Seed both labels so whichever the random-weight model picks resolves
    # to a known Species. classification_id matches the labels file index
    # ("Negative\nPositive\n" → 0, 1).
    negative = Species(scientific_name="Test Negative", classification_id=0)
    positive = Species(scientific_name="Test Positive", classification_id=1)
    db.add_all([negative, positive])

    user = User(
        email=f"worker-int-{uuid.uuid4().hex}@example.com",
        hashed_password=get_password_hash("x"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.refresh(negative)
    db.refresh(positive)

    station = Station(latitude=12.34, longitude=56.78, owner_id=user.id)
    db.add(station)
    db.commit()
    db.refresh(station)

    upload = Upload(station_id=station.id, object_name=object_name)
    db.add(upload)
    db.commit()
    db.refresh(upload)

    task = ClassifyTask(
        upload_id=upload.id,
        status=ClassifyTaskStatus.Prepared,
        object_name=object_name,
        file_metadata={},
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    task_id = task.id

    minio_client.put_object(
        bucket_name=settings.GARAGE_BUCKET_NAME,
        object_name=object_name,
        data=io.BytesIO(video_bytes),
        length=len(video_bytes),
    )

    # Real enqueue (not call_local) — the worker container picks it up.
    tasks_module.classify_video(object_name, task_id)

    # 60s budget covers the worker's first-task classifier load (~5s) plus
    # inference. Subsequent tasks would be sub-second.
    completed = _wait_for_terminal(db, task_id, timeout_s=60.0)
    assert completed.status == ClassifyTaskStatus.Success
    assert completed.observation_id is not None

    obs = db.get(Observation, completed.observation_id)
    assert obs is not None
    assert obs.station_id == station.id
    assert obs.object_name == object_name
    # Either a Species whose classification_id matches one of the labels
    # (when the top label clears the 0.3 threshold) or NULL (random weights —
    # softmax may stay below it). Look up by FK rather than comparing UUIDs:
    # the compose-smoke test seeds the same labels, and `_lookup_species_id`
    # returns the oldest matching row, so its UUID may differ from ours.
    if obs.species_id is not None:
        resolved = db.get(Species, obs.species_id)
        assert resolved is not None
        assert resolved.classification_id in (0, 1)
