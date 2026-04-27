"""Smoke tests proving the integration harness is wired correctly.

The full WI-INT-3 worker→Redis→Minio→TF Lite→Observation flow lives in
a follow-up; these only assert that the conftest fixtures bring up a
working Minio with the seeded model + labels. If these pass, the
harness is alive.
"""

import tensorflow as tf
from minio import Minio

from app.core.config import settings


def test_seeded_model_loads_from_minio(minio_client: Minio) -> None:
    response = minio_client.get_object(
        settings.GARAGE_BUCKET_NAME,
        settings.CLASSIFICATION_MODEL_OBJECT_NAME,
    )
    try:
        model_bytes = response.read()
    finally:
        response.close()
        response.release_conn()

    interpreter = tf.lite.Interpreter(model_content=model_bytes)
    interpreter.allocate_tensors()
    assert tuple(interpreter.get_input_details()[0]["shape"]) == (1, 32, 32, 3)
    assert tuple(interpreter.get_output_details()[0]["shape"]) == (1, 2)


def test_seeded_labels_match_fixture(minio_client: Minio) -> None:
    response = minio_client.get_object(
        settings.GARAGE_BUCKET_NAME,
        settings.CLASSIFICATION_LABELS_OBJECT_NAME,
    )
    try:
        labels = response.read().decode("utf-8")
    finally:
        response.close()
        response.release_conn()

    assert labels.splitlines()[:2] == ["Negative", "Positive"]
