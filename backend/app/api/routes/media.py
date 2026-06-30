import mimetypes
from collections.abc import Iterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from minio import Minio
from minio.error import S3Error

from app.core.config import settings

router = APIRouter(prefix="/media", tags=["media"])

garage_client = Minio(
    endpoint=settings.GARAGE_ENDPOINT,
    access_key=settings.GARAGE_KEY_ID,
    secret_key=settings.GARAGE_SECRET,
    secure=settings.GARAGE_USE_TLS,
    region=settings.GARAGE_REGION,
)

_CHUNK_SIZE = 64 * 1024

# S3 error codes that mean "the requested object is simply not there" and must
# surface as a 404 rather than a 500. Other S3 errors (auth, throttling, and a
# missing/misconfigured BUCKET — a deployment error, not a per-object miss) are
# re-raised so they surface loudly instead of being silently masked as a 404.
_NOT_FOUND_CODES = {"NoSuchKey", "NoSuchObject"}

_CACHE_CONTROL = "public, max-age=31536000, immutable"


@router.get("/{object_name:path}")
def get_media(object_name: str) -> StreamingResponse:
    # visibility seam: media is public in P0. A future per-observation /
    # per-station `is_private` visibility check belongs HERE (look up the
    # owning observation/station by object_name and 403/404 before streaming),
    # so the GET /media/{object_name} URL contract stays stable.
    try:
        response = garage_client.get_object(
            bucket_name=settings.GARAGE_BUCKET_NAME,
            object_name=object_name,
        )
    except S3Error as exc:
        if exc.code in _NOT_FOUND_CODES:
            raise HTTPException(status_code=404, detail="Media not found")
        raise

    def stream() -> Iterator[bytes]:
        try:
            yield from response.stream(_CHUNK_SIZE)
        finally:
            # minio's get_object returns a urllib3 response that must be
            # released back to the connection pool once consumed.
            response.close()
            response.release_conn()

    media_type = mimetypes.guess_type(object_name)[0] or "application/octet-stream"
    return StreamingResponse(
        stream(),
        media_type=media_type,
        headers={"Cache-Control": _CACHE_CONTROL},
    )
