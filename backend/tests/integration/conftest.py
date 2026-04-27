"""Integration-test fixtures.

The compose stack must be up before pytest runs (use
`scripts/integration-test.sh`); this conftest connects to the running
services on the localhost-mapped ports declared in `.env.test` and
seeds the test Minio bucket with a fixture model + labels.

Per Decision B for WI-INT-3, the .tflite is generated on the fly via
`tf.lite.TFLiteConverter` rather than committed as a binary blob —
costs ~5s of Keras setup once per session, in exchange for not pinning
a binary in git.
"""

import io
from pathlib import Path

import pytest
import tensorflow as tf
from minio import Minio

from app.core.config import settings

_INTEGRATION_DIR = Path(__file__).resolve().parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Auto-mark every test under tests/integration/ as `integration`."""
    for item in items:
        if _INTEGRATION_DIR in Path(item.fspath).parents:
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def minio_client() -> Minio:
    return Minio(
        endpoint=settings.GARAGE_ENDPOINT,
        access_key=settings.GARAGE_KEY_ID,
        secret_key=settings.GARAGE_SECRET,
        secure=settings.GARAGE_USE_TLS,
    )


@pytest.fixture(scope="session")
def tflite_model_bytes() -> bytes:
    """Generate a tiny image classifier .tflite once per session.

    Conv2D(2, kernel=3) → GlobalAveragePooling2D → Softmax. Input
    [1, 32, 32, 3] float32; output [1, 2] float32 — two classes matching
    the seeded labels file. Weights are random; the model is a
    load-and-invoke fixture, not a real classifier. The float32 input
    matches `classify_image`'s `floating_model=True` normalize path.
    """
    inputs = tf.keras.Input(shape=(32, 32, 3), dtype=tf.float32, name="image")
    x = tf.keras.layers.Conv2D(2, 3, padding="same")(inputs)
    x = tf.keras.layers.GlobalAveragePooling2D()(x)
    outputs = tf.keras.layers.Softmax()(x)
    model = tf.keras.Model(inputs, outputs)
    return tf.lite.TFLiteConverter.from_keras_model(model).convert()


@pytest.fixture(scope="session", autouse=True)
def seed_minio(minio_client: Minio, tflite_model_bytes: bytes) -> None:
    """Upload model + labels to the test bucket once per session."""
    labels = b"Negative\nPositive\n"
    minio_client.put_object(
        bucket_name=settings.GARAGE_BUCKET_NAME,
        object_name=settings.CLASSIFICATION_MODEL_OBJECT_NAME,
        data=io.BytesIO(tflite_model_bytes),
        length=len(tflite_model_bytes),
    )
    minio_client.put_object(
        bucket_name=settings.GARAGE_BUCKET_NAME,
        object_name=settings.CLASSIFICATION_LABELS_OBJECT_NAME,
        data=io.BytesIO(labels),
        length=len(labels),
    )
