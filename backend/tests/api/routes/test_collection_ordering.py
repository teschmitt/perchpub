"""Deterministic, most-recent-first collection ordering
(add-frontend-api-prerequisites).

Each list endpoint must apply an explicit total ORDER BY so "most recent" is
meaningful and repeated identical requests over an unchanged dataset return the
identical order. ``id`` is the final tiebreaker, so the order is total even when
the primary sort key ties.

These tests run against the shared session DB, so other tests' rows are also
present. The assertions are therefore written to hold over *any* superset: the
returned page must be globally sorted by the contract's keys, and the rows this
test seeds must appear in the expected relative order.
"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.core.security import get_password_hash
from app.models import ClassifyTask, Observation, Species, Station, Upload, User
from tests.utils.utils import random_email, random_lower_string

# A fixed, distant base time so seeded rows are unambiguous and clearly distinct
# from the "now()" defaults other tests' rows carry.
_BASE = datetime(2021, 1, 1, tzinfo=timezone.utc)


def _positions(data: list[dict], ids: list[str]) -> list[int]:
    """Return the index of each id within ``data`` (asserting all are present)."""
    index = {row["id"]: i for i, row in enumerate(data)}
    missing = [i for i in ids if i not in index]
    assert not missing, f"seeded ids absent from response: {missing}"
    return [index[i] for i in ids]


def _seed_owner(db: Session) -> User:
    user = User(
        email=random_email(),
        hashed_password=get_password_hash(random_lower_string()),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _seed_station(
    db: Session,
    owner: User,
    *,
    is_private: bool = False,
    created_at: datetime | None = None,
    id: uuid.UUID | None = None,
) -> Station:
    kwargs: dict = {
        "latitude": 0.0,
        "longitude": 0.0,
        "owner_id": owner.id,
        "is_private": is_private,
    }
    if created_at is not None:
        kwargs["created_at"] = created_at
    if id is not None:
        kwargs["id"] = id
    station = Station(**kwargs)
    db.add(station)
    db.commit()
    db.refresh(station)
    return station


def _seed_species(db: Session, name: str, *, id: uuid.UUID | None = None) -> Species:
    kwargs: dict = {"scientific_name": name, "classification_id": 1}
    if id is not None:
        kwargs["id"] = id
    sp = Species(**kwargs)
    db.add(sp)
    db.commit()
    db.refresh(sp)
    return sp


def _seed_observation(
    db: Session,
    station: Station,
    species: Species,
    observed_at: datetime,
    *,
    id: uuid.UUID | None = None,
) -> Observation:
    kwargs: dict = {
        "confidence_score": 0.5,
        "classification_result": [],
        "station_id": station.id,
        "species_id": species.id,
        "object_name": "test/object.jpg",
        "observed_at": observed_at,
        "latitude": 0.0,
        "longitude": 0.0,
    }
    if id is not None:
        kwargs["id"] = id
    obs = Observation(**kwargs)
    db.add(obs)
    db.commit()
    db.refresh(obs)
    return obs


def _seed_classify_task(
    db: Session,
    upload: Upload,
    observation_id: uuid.UUID,
    created_at: datetime,
    *,
    id: uuid.UUID | None = None,
) -> ClassifyTask:
    kwargs: dict = {
        "object_name": "test/object.jpg",
        "upload_id": upload.id,
        "observation_id": observation_id,
        "created_at": created_at,
    }
    if id is not None:
        kwargs["id"] = id
    task = ClassifyTask(**kwargs)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _ordered_id_pair() -> tuple[uuid.UUID, uuid.UUID]:
    """Two unique-per-run UUIDs with a *fixed* relative order: ``(lo, hi)`` where
    ``lo < hi``. They differ only in the last byte, so which is larger is
    deterministic, while a random high part keeps them unique in the shared DB.
    Postgres orders ``uuid`` byte-wise, matching Python ``uuid.UUID`` ordering."""
    base = uuid.uuid4().int & ~0xFF
    return uuid.UUID(int=base | 0x01), uuid.UUID(int=base | 0x02)


# --------------------------------------------------------------------------- #
# Observations — observed_at DESC, id DESC tiebreaker
# --------------------------------------------------------------------------- #
def test_observations_returned_most_recent_first(
    client: TestClient, db: Session
) -> None:
    owner = _seed_owner(db)
    station = _seed_station(db, owner)
    species = _seed_species(db, random_lower_string())

    # Insert oldest-first so insertion (heap) order is the opposite of the
    # required newest-first order — guarantees the test fails without ORDER BY.
    oldest = _seed_observation(db, station, species, _BASE)
    middle = _seed_observation(db, station, species, _BASE + timedelta(hours=1))
    newest = _seed_observation(db, station, species, _BASE + timedelta(hours=2))

    r = client.get(f"{settings.API_V1_STR}/observation/", params={"limit": 1000})
    assert r.status_code == 200
    data = r.json()["data"]

    # The full page is globally ordered by (observed_at DESC, id DESC).
    keys = [
        (datetime.fromisoformat(o["observed_at"]), uuid.UUID(o["id"])) for o in data
    ]
    assert keys == sorted(keys, reverse=True)

    # The three seeded rows appear newest -> oldest.
    pos = _positions(data, [str(newest.id), str(middle.id), str(oldest.id)])
    assert pos == sorted(pos)


def test_observations_id_breaks_ties_descending(
    client: TestClient, db: Session
) -> None:
    owner = _seed_owner(db)
    station = _seed_station(db, owner)
    species = _seed_species(db, random_lower_string())

    tie = _BASE + timedelta(hours=5)
    lo, hi = _ordered_id_pair()
    # Insert lo first so heap (insertion) order is [lo, hi] — the OPPOSITE of the
    # required id-DESC order, so this fails deterministically without the tiebreaker.
    _seed_observation(db, station, species, tie, id=lo)
    _seed_observation(db, station, species, tie, id=hi)

    r = client.get(f"{settings.API_V1_STR}/observation/", params={"limit": 1000})
    data = r.json()["data"]
    pos_hi, pos_lo = _positions(data, [str(hi), str(lo)])
    assert pos_hi < pos_lo


def test_observations_order_is_reproducible(client: TestClient, db: Session) -> None:
    owner = _seed_owner(db)
    station = _seed_station(db, owner)
    species = _seed_species(db, random_lower_string())
    for h in range(3):
        _seed_observation(db, station, species, _BASE + timedelta(hours=10 + h))

    first = client.get(f"{settings.API_V1_STR}/observation/", params={"limit": 1000})
    second = client.get(f"{settings.API_V1_STR}/observation/", params={"limit": 1000})
    first_ids = [o["id"] for o in first.json()["data"]]
    second_ids = [o["id"] for o in second.json()["data"]]
    assert first_ids == second_ids
    # And that reproducible order is the contract's descending order.
    times = [datetime.fromisoformat(o["observed_at"]) for o in first.json()["data"]]
    assert times == sorted(times, reverse=True)


# --------------------------------------------------------------------------- #
# Species — scientific_name ASC, id ASC tiebreaker
# --------------------------------------------------------------------------- #
def test_species_ordered_by_scientific_name_ascending(
    client: TestClient, db: Session
) -> None:
    suffix = random_lower_string()
    n_a, n_m, n_z = f"Aaa-{suffix}", f"Mmm-{suffix}", f"Zzz-{suffix}"
    # Insert in reverse so heap order is the opposite of alphabetical.
    sp_z = _seed_species(db, n_z)
    sp_m = _seed_species(db, n_m)
    sp_a = _seed_species(db, n_a)

    r = client.get(f"{settings.API_V1_STR}/species/", params={"limit": 1000})
    assert r.status_code == 200
    data = r.json()["data"]

    # Assert the relative order of the three seeded rows: Aaa < Mmm < Zzz.
    # (A global Python-sorted comparison is avoided on purpose — text ordering
    # is the DB's collation, which need not match Python's code-point order for
    # the mixed-case names other tests seed into the shared DB.)
    pos = _positions(data, [str(sp_a.id), str(sp_m.id), str(sp_z.id)])
    assert pos == sorted(pos)


def test_species_id_breaks_ties_ascending(client: TestClient, db: Session) -> None:
    name = f"Tie-{random_lower_string()}"
    lo, hi = _ordered_id_pair()
    # Insert hi first so heap order is [hi, lo] — the OPPOSITE of the required
    # id-ASC order, so this fails deterministically without the tiebreaker.
    _seed_species(db, name, id=hi)
    _seed_species(db, name, id=lo)

    r = client.get(f"{settings.API_V1_STR}/species/", params={"limit": 1000})
    data = r.json()["data"]
    pos_lo, pos_hi = _positions(data, [str(lo), str(hi)])
    assert pos_lo < pos_hi


# --------------------------------------------------------------------------- #
# Stations — created_at DESC, id DESC tiebreaker (visibility filter applies).
# created_at is not exposed on StationPublic, so ordering is asserted via the
# relative order of rows seeded with controlled created_at values.
# --------------------------------------------------------------------------- #
def test_stations_returned_newest_first_for_anon(
    client: TestClient, db: Session
) -> None:
    owner = _seed_owner(db)
    # Insert oldest-first; expect the response newest-first.
    old = _seed_station(db, owner, created_at=_BASE)
    mid = _seed_station(db, owner, created_at=_BASE + timedelta(hours=1))
    new = _seed_station(db, owner, created_at=_BASE + timedelta(hours=2))

    r = client.get(f"{settings.API_V1_STR}/station/", params={"limit": 1000})
    assert r.status_code == 200
    data = r.json()["data"]

    pos = _positions(data, [str(new.id), str(mid.id), str(old.id)])
    assert pos == sorted(pos)


def test_stations_ordering_composes_with_visibility(
    client: TestClient, db: Session
) -> None:
    owner = _seed_owner(db)
    public = _seed_station(db, owner, is_private=False, created_at=_BASE)
    private = _seed_station(db, owner, is_private=True, created_at=_BASE + timedelta(1))

    r = client.get(f"{settings.API_V1_STR}/station/", params={"limit": 1000})
    ids = {row["id"] for row in r.json()["data"]}
    # The private station is excluded for an anonymous caller; ordering does not
    # change which rows are returned.
    assert str(public.id) in ids
    assert str(private.id) not in ids


def test_stations_id_breaks_ties_descending(client: TestClient, db: Session) -> None:
    owner = _seed_owner(db)
    tie = _BASE + timedelta(hours=20)
    lo, hi = _ordered_id_pair()
    # Insert lo first so heap order is [lo, hi] — opposite of the required
    # id-DESC order, so this fails deterministically without the tiebreaker.
    _seed_station(db, owner, created_at=tie, id=lo)
    _seed_station(db, owner, created_at=tie, id=hi)

    r = client.get(f"{settings.API_V1_STR}/station/", params={"limit": 1000})
    data = r.json()["data"]
    pos_hi, pos_lo = _positions(data, [str(hi), str(lo)])
    assert pos_hi < pos_lo


# --------------------------------------------------------------------------- #
# Classify tasks — created_at DESC, id DESC tiebreaker (scoped by observation).
# --------------------------------------------------------------------------- #
def _seed_observation_with_upload(db: Session) -> tuple[Observation, Upload]:
    owner = _seed_owner(db)
    station = _seed_station(db, owner)
    species = _seed_species(db, random_lower_string())
    observation = _seed_observation(db, station, species, _BASE)
    upload = Upload(station_id=station.id, object_name="test/object.jpg")
    db.add(upload)
    db.commit()
    db.refresh(upload)
    return observation, upload


def test_classify_tasks_for_observation_most_recent_first(
    client: TestClient, db: Session
) -> None:
    observation, upload = _seed_observation_with_upload(db)
    # Insert oldest-first; expect the response newest-first.
    oldest = _seed_classify_task(db, upload, observation.id, _BASE)
    middle = _seed_classify_task(db, upload, observation.id, _BASE + timedelta(hours=1))
    newest = _seed_classify_task(db, upload, observation.id, _BASE + timedelta(hours=2))

    r = client.get(
        f"{settings.API_V1_STR}/classify-task/",
        params={"observation": str(observation.id), "limit": 1000},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    returned_ids = [t["id"] for t in data]
    assert returned_ids == [str(newest.id), str(middle.id), str(oldest.id)]


def test_classify_tasks_id_breaks_ties_descending(
    client: TestClient, db: Session
) -> None:
    observation, upload = _seed_observation_with_upload(db)
    tie = _BASE + timedelta(hours=7)
    lo, hi = _ordered_id_pair()
    # Insert lo first so heap order is [lo, hi] — opposite of the required
    # id-DESC order, so this fails deterministically without the tiebreaker.
    _seed_classify_task(db, upload, observation.id, tie, id=lo)
    _seed_classify_task(db, upload, observation.id, tie, id=hi)

    r = client.get(
        f"{settings.API_V1_STR}/classify-task/",
        params={"observation": str(observation.id), "limit": 1000},
    )
    returned_ids = [t["id"] for t in r.json()["data"]]
    assert returned_ids == [str(hi), str(lo)]
