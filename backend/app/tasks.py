import functools
import logging
import tempfile
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import cv2 as cv
import numpy as np
import tensorflow as tf
from fastapi import HTTPException
from huey import RedisHuey
from minio import Minio
from sqlmodel import Session, select

from app.core.config import settings
from app.core.db import engine
from app.models.classify_task import ClassifyTask, ClassifyTaskStatus
from app.models.observation import Observation, ObservationCreate
from app.models.species import Species
from app.models.station import Station

logger = logging.getLogger(__name__)


class PerchpubTaskError(Exception):
    def __init__(self, error_str: str) -> None:
        self.error_str = error_str
        super().__init__(f"Error while running a Perchpub task: {self.error_str}")


# Construct unconditionally at import: redis-py connects lazily, and the Minio
# client only opens sockets when a method is called. The legacy try/except
# around these used to swallow ConfigurationError/ValueError/S3Error, but a
# real network failure (urllib3 MaxRetryError) would still escape and break
# module import — the worker container then died on startup.
huey_client = RedisHuey(
    name=settings.HUEY_CLIENT_NAME,
    host=settings.HUEY_REDIS_HOST,
    port=settings.HUEY_REDIS_PORT,
)

garage_client = Minio(
    endpoint=settings.GARAGE_ENDPOINT,
    access_key=settings.GARAGE_KEY_ID,
    secret_key=settings.GARAGE_SECRET,
    secure=settings.GARAGE_USE_TLS,
    region="garage",
)


@dataclass
class Classifier:
    interpreter: Any
    labels: list[str]
    width: int
    height: int
    floating_model: bool
    input_details: list[dict[str, Any]]
    output_details: list[dict[str, Any]]
    input_mean: float = 127.5
    input_std: float = 127.5


@functools.lru_cache(maxsize=1)
def _get_classifier() -> Classifier:
    """Fetch model + labels from Garage and build the TF Lite interpreter on first call.

    Cached so subsequent classifications reuse the loaded model. If the load
    raises, nothing is cached — the next call retries.
    """
    model_content = garage_client.get_object(
        bucket_name=settings.GARAGE_BUCKET_NAME,
        object_name=settings.CLASSIFICATION_MODEL_OBJECT_NAME,
    ).data
    labels_content = garage_client.get_object(
        bucket_name=settings.GARAGE_BUCKET_NAME,
        object_name=settings.CLASSIFICATION_LABELS_OBJECT_NAME,
    ).data

    interpreter = tf.lite.Interpreter(model_content=model_content)
    interpreter.allocate_tensors()
    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()
    return Classifier(
        interpreter=interpreter,
        labels=labels_content.decode("utf-8").split("\n"),
        width=int(input_details[0]["shape"][2]),
        height=int(input_details[0]["shape"][1]),
        floating_model=input_details[0]["dtype"] == np.float32,
        input_details=input_details,
        output_details=output_details,
    )


def _lookup_species_id(session: Session, label_id: int) -> uuid.UUID | None:
    """Resolve a classifier label index to a `Species.id`, or `None` if unknown."""
    species = session.exec(
        select(Species).where(Species.classification_id == label_id)
    ).first()
    return species.id if species is not None else None


def classify_image(image_array: Any, classifier: Classifier) -> dict[str, float]:
    image_rgb = cv.cvtColor(image_array, cv.COLOR_BGR2RGB)
    image_resized = cv.resize(image_rgb, (classifier.width, classifier.height))
    input_data: Any = np.expand_dims(image_resized, axis=0)

    if classifier.floating_model:
        input_data = (np.float32(input_data) - classifier.input_mean) / classifier.input_std

    classifier.interpreter.set_tensor(classifier.input_details[0]["index"], input_data)
    classifier.interpreter.invoke()

    output_data = classifier.interpreter.get_tensor(
        classifier.output_details[0]["index"]
    )
    results = np.squeeze(output_data)
    top_k = results.argsort()[-5:][::-1]

    result: dict[str, float] = {}
    for i in top_k:
        if classifier.floating_model:
            result[classifier.labels[i]] = float(results[i])
        else:
            result[classifier.labels[i]] = float(results[i] / 255.0)
    return result


@huey_client.task()
def classify_video(object_name: str, task_id: uuid.UUID) -> Observation:
    with Session(engine) as session:
        task = session.get(ClassifyTask, task_id)
        if task is None:
            raise PerchpubTaskError(f"ClassifyTask {task_id} not found")

        try:
            classifier = _get_classifier()
        except Exception as e:
            logger.exception("Failed to load classifier for task %s", task_id)
            task.status = ClassifyTaskStatus.Failed
            session.add(task)
            session.commit()
            raise PerchpubTaskError(f"Classifier load failed: {e}")

        task.status = ClassifyTaskStatus.Processing
        session.add(task)
        session.commit()

        results = []
        # download video from S3 to temporary location:
        with tempfile.NamedTemporaryFile(delete_on_close=False) as fp:
            try:
                _stat = garage_client.fget_object(
                    bucket_name=settings.GARAGE_BUCKET_NAME,
                    object_name=object_name,
                    file_path=fp.name,
                )
            except Exception as e:
                with Session(engine) as session:
                    task.status = ClassifyTaskStatus.Failed
                    session.add(task)
                    session.commit()
                raise HTTPException(
                    status_code=500, detail=f"Error fetching resource: '{e}'"
                )

            cap = cv.VideoCapture(fp.name)
            total_frames = int(cap.get(cv.CAP_PROP_FRAME_COUNT))

            for frame_number in range(0, total_frames, 10):
                cap.set(cv.CAP_PROP_POS_FRAMES, frame_number)
                _, image = cap.read()
                results.append(classify_image(image, classifier))

        threshold = 0.3
        max_scores: dict[str, float] = defaultdict(float)
        for result in results:
            for k, v in result.items():
                if k == "None":
                    continue
                if v > max_scores[k]:
                    max_scores[k] = v

        # keep only labels above threshold, sorted by descending score
        birds = [
            {"species": species, "score": score}
            for species, score in sorted(
                ((k, v) for k, v in max_scores.items() if v > threshold),
                key=lambda item: item[1],
                reverse=True,
            )
        ]

        species_id: uuid.UUID | None = None
        if birds:
            top_label = str(birds[0]["species"])
            try:
                top_label_id = classifier.labels.index(top_label)
            except ValueError:
                top_label_id = -1
            if top_label_id >= 0:
                species_id = _lookup_species_id(session, top_label_id)

        station = session.get(Station, task.upload.station_id)
        if station is None:
            raise PerchpubTaskError(
                f"Station {task.upload.station_id} for upload {task.upload_id} not found"
            )

        obs_in = ObservationCreate(
            station_id=station.id,
            species_id=species_id,
            confidence_score=birds[0]["score"] if len(birds) > 0 else 0.0,
            classification_result=birds,
            observed_at=task.updated_at,
            latitude=station.latitude,
            longitude=station.longitude,
            object_name=object_name,
        )
        obs = Observation.model_validate(obs_in)
        session.add(obs)
        session.commit()
        session.refresh(obs)

        task.status = ClassifyTaskStatus.Success
        task.observation_id = obs.id
        session.add(task)
        session.commit()

    return obs
