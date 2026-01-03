import tempfile
import uuid
from collections import defaultdict

import cv2 as cv
import numpy as np
import tensorflow as tf
from fastapi import HTTPException
from huey import RedisHuey
from minio import Minio
from sqlmodel import Session

from app.core.config import settings
from app.core.db import engine
from app.models.classify_task import ClassifyTask, ClassifyTaskStatus
from app.models.observation import Observation, ObservationCreate

huey = RedisHuey(
    name=settings.HUEY_CLIENT_NAME,
    host=settings.HUEY_REDIS_HOST,
    port=settings.HUEY_REDIS_PORT,
)

garage_client = Minio(
    endpoint=settings.GARAGE_ENDPOINT,
    access_key=settings.GARAGE_KEY_ID,
    secret_key=settings.GARAGE_SECRET,
    secure=False,
    region="garage",
)


model_content = garage_client.get_object(
    bucket_name=settings.GARAGE_BUCKET_NAME,
    object_name=settings.CLASSIFICATION_MODEL_OBJECT_NAME,
).data
labels_content = garage_client.get_object(
    bucket_name=settings.GARAGE_BUCKET_NAME,
    object_name=settings.CLASSIFICATION_LABELS_OBJECT_NAME,
).data

interpreter = tf.lite.Interpreter(model_content=model_content)
labels = labels_content.decode("utf-8").split("\n")

interpreter.allocate_tensors()

# Get model details
input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()

height = input_details[0]["shape"][1]
width = input_details[0]["shape"][2]

floating_model = input_details[0]["dtype"] == np.float32

input_mean = 127.5
input_std = 127.5


def classify_image(image_array):
    image_rgb = cv.cvtColor(image_array, cv.COLOR_BGR2RGB)
    image_resized = cv.resize(image_rgb, (width, height))
    input_data = np.expand_dims(image_resized, axis=0)

    if floating_model:
        input_data = (np.float32(input_data) - input_mean) / input_std

    interpreter.set_tensor(input_details[0]["index"], input_data)
    interpreter.invoke()

    output_data = interpreter.get_tensor(output_details[0]["index"])

    results = np.squeeze(output_data)

    top_k = results.argsort()[-5:][::-1]

    result = {}
    for i in top_k:
        if floating_model:
            result[labels[i]] = float(results[i])
        else:
            result[labels[i]] = float(results[i] / 255.0)

    return result


@huey.task()
def classify_video(object_name: str, task: ClassifyTask):

    with Session(engine) as session:
        task.status = ClassifyTaskStatus.Processing
        session.add(task)
        session.commit()

        results = []
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
                results.append(classify_image(image))

        threshold = 0.3
        max_scores = defaultdict(float)
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

        # TODO: get species from db
        species_id = uuid.UUID("e6b950cd-36e4-44f2-a397-7643a15a3f42")

        obs_in = ObservationCreate(
            station_id=task.upload.station.id,
            species_id=species_id,
            confidence_score=birds[0]["score"] if len(birds) > 0 else 0.0,
            classification_result=birds,
            observed_at=task.updated_at,
            latitude=task.upload.station.latitude,
            longitude=task.upload.station.longitude,
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
