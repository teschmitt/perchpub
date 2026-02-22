import hashlib
import io
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from minio import Minio, S3Error

from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.models.classify_task import (
    ClassifyTask,
    ClassifyTaskCreate,
    ClassifyTaskPublic,
    ClassifyTaskStatus,
)
from app.models.upload import Upload, UploadCreate

# from app.tasks import classify_video

router = APIRouter(prefix="/upload", tags=["upload"])

garage_client = Minio(
    endpoint=settings.GARAGE_ENDPOINT,
    access_key=settings.GARAGE_KEY_ID,
    secret_key=settings.GARAGE_SECRET,
    secure=False,
    region="garage",
)


# TODO: clean this up a introduce a response model
@router.post("/", response_model=ClassifyTaskPublic)
async def upload_file(
    session: SessionDep, current_user: CurrentUser, file: UploadFile = File(...)
) -> ClassifyTaskPublic:

    # TODO: get station ID from mTLS cert or some other source
    station_id = uuid.UUID(
        "e26042ab-a0b8-4264-90a4-f79da829d2ac"
    )  # TODO: temp, replace with real station

    try:
        file_content = await file.read()
        file_size = len(file_content)
        file_hash = hashlib.sha256(file_content).hexdigest()
        file_ext = Path(file.filename).suffix.lower()
        object_key = f"{file_hash[:2]}/{file_hash[2:4]}/{file_hash}{file_ext}"

        write_result = garage_client.put_object(
            bucket_name=settings.GARAGE_BUCKET_NAME,
            object_name=object_key,
            data=io.BytesIO(file_content),
            length=file_size,
            content_type=file.content_type,
            metadata={
                "original_filename": file.filename,
                "file_size": file_size,
            },
        )
    except S3Error as e:
        raise HTTPException(status_code=500, detail=f"Storage error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Service error: {str(e)}")

    metadata = {
        "original_filename": file.filename,
        "object_name": write_result.object_name,
        "file_hash": file_hash,
        "size_bytes": file_size,
        "content_type": file.content_type,
    }

    upload = Upload.model_validate(
        UploadCreate(object_name=write_result.object_name, station_id=station_id)
    )

    task = ClassifyTask.model_validate(
        ClassifyTaskCreate(
            upload_id=upload.id,
            status=ClassifyTaskStatus.Prepared,
            object_name=write_result.object_name,
            file_metadata=metadata,
            observation_id=None,
        )
    )
    session.add(upload)
    session.add(task)
    session.commit()
    session.refresh(task)

    try:
        classify_video(
            write_result.object_name,
            task,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error while starting classification task: '{e}'"
        )

    return task
