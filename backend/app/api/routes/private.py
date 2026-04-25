import secrets
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app.api.deps import SessionDep, get_current_active_superuser
from app.core.config import settings
from app.core.security import get_password_hash
from app.models import (
    User,
    UserPublic,
)


def verify_debug_key(
    x_perchpub_debug_key: Annotated[str | None, Header()] = None,
) -> None:
    expected = settings.DEBUG_KEY
    if not expected:
        raise HTTPException(status_code=403, detail="Debug router disabled")
    if x_perchpub_debug_key is None or not secrets.compare_digest(
        x_perchpub_debug_key, expected
    ):
        raise HTTPException(status_code=403, detail="Invalid debug key")


router = APIRouter(
    tags=["private"],
    prefix="/private",
    dependencies=[
        Depends(get_current_active_superuser),
        Depends(verify_debug_key),
    ],
)


class PrivateUserCreate(BaseModel):
    email: str
    password: str
    full_name: str
    is_verified: bool = False


@router.post("/users/", response_model=UserPublic)
def create_user(user_in: PrivateUserCreate, session: SessionDep) -> Any:
    """
    Create a new user.
    """

    user = User(
        email=user_in.email,
        full_name=user_in.full_name,
        hashed_password=get_password_hash(user_in.password),
    )

    session.add(user)
    session.commit()

    return user
