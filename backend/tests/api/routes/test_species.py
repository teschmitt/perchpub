from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.models import Species
from tests.utils.utils import random_lower_string


def test_create_species_unauthenticated(client: TestClient) -> None:
    r = client.post(
        f"{settings.API_V1_STR}/species/",
        json={"scientific_name": random_lower_string(), "classification_id": 0},
    )
    assert r.status_code == 401


def test_create_species_superuser_succeeds(
    client: TestClient,
    db: Session,
    superuser_token_headers: dict[str, str],
) -> None:
    payload = {
        "scientific_name": f"Testus {random_lower_string()}",
        "classification_id": 12345,
    }
    r = client.post(
        f"{settings.API_V1_STR}/species/",
        json=payload,
        headers=superuser_token_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scientific_name"] == payload["scientific_name"]
    persisted = db.get(Species, body["id"])
    assert persisted is not None
    assert persisted.classification_id == payload["classification_id"]


def test_create_species_rejects_missing_classification_id(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    r = client.post(
        f"{settings.API_V1_STR}/species/",
        json={"scientific_name": random_lower_string()},
        headers=superuser_token_headers,
    )
    assert r.status_code == 422
