from fastapi import APIRouter

from app.api.routes import (
    classify_tasks,
    enrollment,
    login,
    observations,
    private,
    species,
    stations,
    uploads,
    users,
    utils,
)
from app.core.config import settings

api_router = APIRouter()

api_router.include_router(classify_tasks.router)
api_router.include_router(uploads.router)
api_router.include_router(enrollment.router)
api_router.include_router(species.router)
api_router.include_router(observations.router)
api_router.include_router(stations.router)
api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(utils.router)


if settings.ENVIRONMENT == "local":
    api_router.include_router(private.router)
