import importlib
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import Session, select

from app.core.config import settings
from app.core.security import get_password_hash
from app.models.classify_task import ClassifyTask, ClassifyTaskStatus
from app.models.enrollment import EnrollmentAudit, EnrollmentAuditEvent
from app.models.observation import Observation
from app.models.species import Species
from app.models.station import Station
from app.models.upload import Upload
from app.models.user import User
from app.tasks import _lookup_species_id, _purge_enrollment_audit
from tests.utils.utils import random_email, random_lower_string


@pytest.fixture(scope="module")
def tasks_module():
    """Import the real ``app.tasks`` for this module, undoing any conftest stub.

    Other test modules rely on patching ``app.tasks.classify_video``; that
    pattern needs the real module imported, but conftest used to install a
    ``MagicMock`` stub. After WI-13 the stub is gone, so this fixture is a
    no-op apart from the explicit reload it guards against.
    """
    if "app.tasks" in sys.modules and not hasattr(
        sys.modules["app.tasks"], "_get_classifier"
    ):
        del sys.modules["app.tasks"]
    return importlib.import_module("app.tasks")


def _make_task(db: Session) -> ClassifyTask:
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

    upload = Upload(station_id=station.id, object_name="ab/cd/abcd.mp4")
    db.add(upload)
    db.commit()
    db.refresh(upload)

    task = ClassifyTask(
        upload_id=upload.id,
        status=ClassifyTaskStatus.Prepared,
        object_name="ab/cd/abcd.mp4",
        file_metadata={},
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def test_huey_client_defined_at_import(tasks_module) -> None:
    """huey_client must be unconditionally defined so @huey_client.task() never NameErrors at import."""
    assert tasks_module.huey_client is not None


def test_classify_video_marks_task_failed_when_classifier_load_fails(
    db: Session, tasks_module
) -> None:
    task = _make_task(db)
    task_id = task.id
    object_name = task.object_name

    tasks_module._get_classifier.cache_clear()

    with patch.object(
        tasks_module, "_get_classifier", side_effect=RuntimeError("boom")
    ):
        with pytest.raises(Exception):
            tasks_module.classify_video.call_local(object_name, task_id)

    db.expire_all()
    refreshed = db.get(ClassifyTask, task_id)
    assert refreshed is not None
    assert refreshed.status == ClassifyTaskStatus.Failed
    assert refreshed.observation_id is None

    observations = db.exec(
        select(Observation).where(Observation.station_id == task.upload.station_id)
    ).all()
    assert observations == []


def test_classify_video_marks_task_failed_when_garage_fetch_fails(
    db: Session, tasks_module
) -> None:
    task = _make_task(db)
    task_id = task.id
    object_name = task.object_name

    tasks_module._get_classifier.cache_clear()

    with (
        patch.object(tasks_module, "_get_classifier", return_value=MagicMock()),
        patch.object(
            tasks_module.garage_client,
            "fget_object",
            side_effect=RuntimeError("garage unreachable"),
        ),
    ):
        with pytest.raises(tasks_module.PerchpubTaskError):
            tasks_module.classify_video.call_local(object_name, task_id)

    db.expire_all()
    refreshed = db.get(ClassifyTask, task_id)
    assert refreshed is not None
    assert refreshed.status == ClassifyTaskStatus.Failed


def test_lookup_species_id_returns_id_for_known_label(db: Session) -> None:
    label_id = 4242
    species = Species(
        scientific_name=f"Testus speciesus {label_id}", classification_id=label_id
    )
    db.add(species)
    db.commit()
    db.refresh(species)

    assert _lookup_species_id(db, label_id) == species.id


def test_lookup_species_id_returns_none_for_unknown_label(db: Session) -> None:
    unknown_label_id = 999_999
    assert (
        db.exec(
            select(Species).where(Species.classification_id == unknown_label_id)
        ).first()
        is None
    )

    assert _lookup_species_id(db, unknown_label_id) is None


def test_purge_enrollment_audit_deletes_only_rows_past_retention(db: Session) -> None:
    """The purge deletes audit rows older than the retention window and keeps
    rows within it (design D3).
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    stale = EnrollmentAudit(
        event=EnrollmentAuditEvent.session_created,
        source="stale",
        created_at=now - timedelta(days=settings.ENROLLMENT_AUDIT_RETENTION_DAYS + 5),
    )
    fresh = EnrollmentAudit(
        event=EnrollmentAuditEvent.session_created,
        source="fresh",
        created_at=now - timedelta(days=1),
    )
    db.add(stale)
    db.add(fresh)
    db.commit()
    stale_id, fresh_id = stale.id, fresh.id

    deleted = _purge_enrollment_audit(db)

    db.expire_all()
    assert db.get(EnrollmentAudit, stale_id) is None
    assert db.get(EnrollmentAudit, fresh_id) is not None
    assert deleted >= 1
