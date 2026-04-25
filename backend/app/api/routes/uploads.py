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

router = APIRouter(prefix="/upload", tags=["upload"])

garage_client = Minio(
    endpoint=settings.GARAGE_ENDPOINT,
    access_key=settings.GARAGE_KEY_ID,
    secret_key=settings.GARAGE_SECRET,
    secure=False,
    region="garage",
)

_CHUNK_SIZE = 64 * 1024


@router.post("/", response_model=ClassifyTaskPublic)
def upload_file(
    session: SessionDep, current_user: CurrentUser, file: UploadFile = File(...)
) -> ClassifyTask:

    # TODO(WI-17): derive station_id from the authenticated station's mTLS cert.
    station_id = uuid.UUID("e26042ab-a0b8-4264-90a4-f79da829d2ac")

    max_bytes = settings.MAX_UPLOAD_BYTES
    buffer = bytearray()
    while True:
        chunk = file.file.read(_CHUNK_SIZE)
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Upload exceeds maximum size of {max_bytes} bytes",
            )

    file_content = bytes(buffer)
    file_size = len(file_content)
    file_hash = hashlib.sha256(file_content).hexdigest()
    file_ext = Path(file.filename or "").suffix.lower()
    object_key = f"{file_hash[:2]}/{file_hash[2:4]}/{file_hash}{file_ext}"
    content_type = file.content_type or "application/octet-stream"

    try:
        write_result = garage_client.put_object(
            bucket_name=settings.GARAGE_BUCKET_NAME,
            object_name=object_key,
            data=io.BytesIO(file_content),
            length=file_size,
            content_type=content_type,
            metadata={
                "original_filename": file.filename or "",
                "file_size": str(file_size),
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
        "content_type": content_type,
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
        )
    )
    session.add(upload)
    session.add(task)
    session.commit()
    session.refresh(task)

    # Imported lazily so the API process does not pay the TF Lite / Garage
    # init cost paid by the worker container (see app/tasks.py module init).
    from app.tasks import classify_video

    try:
        classify_video(write_result.object_name, task.id)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error while starting classification task: '{e}'"
        )

    return task
