from fastapi.testclient import TestClient

from app.core.config import settings
from tests.utils.utils import random_lower_string


def test_create_species_unauthenticated(client: TestClient) -> None:
    r = client.post(
        f"{settings.API_V1_STR}/species/",
        json={"scientific_name": random_lower_string()},
    )
    assert r.status_code == 401


# Happy-path (superuser POST succeeds) is blocked by FU-06
# (SpeciesCreate omits the non-nullable classification_id column). Re-enable
# once that lands.
