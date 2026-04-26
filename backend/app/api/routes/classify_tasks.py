import uuid

from fastapi import APIRouter, HTTPException
from sqlmodel import func, select

from app.api.deps import SessionDep
from app.models.classify_task import (
    ClassifyTask,
    ClassifyTaskPublic,
    ClassifyTasksPublic,
    ClassifyTaskStatus,
)

router = APIRouter(prefix="/classify-task", tags=["classify-task"])


@router.get("/", response_model=ClassifyTasksPublic)
def read_classify_tasks(
    session: SessionDep,
    skip: int = 0,
    limit: int = 100,
    status: ClassifyTaskStatus | None = None,
    observation: uuid.UUID | None = None,
) -> ClassifyTasksPublic:
    """
    Retrieve a classify task.
    """

    count_statement = select(func.count()).select_from(ClassifyTask)
    if status is not None:
        count_statement = count_statement.where(ClassifyTask.status == status)
    if observation is not None:
        count_statement = count_statement.where(
            ClassifyTask.observation_id == observation
        )
    count = session.exec(count_statement).one()

    stmt = select(ClassifyTask)
    if status is not None:
        stmt = stmt.where(ClassifyTask.status == status)
    if observation is not None:
        stmt = stmt.where(ClassifyTask.observation_id == observation)
    stmt = stmt.offset(skip).limit(limit)
    classify_tasks = session.exec(stmt).all()

    return ClassifyTasksPublic(data=classify_tasks, count=count)


@router.get("/{id}", response_model=ClassifyTaskPublic)
def read_classify_task(session: SessionDep, id: uuid.UUID) -> ClassifyTask:
    """
    Get classify task by ID.
    """
    classify_task = session.get(ClassifyTask, id)
    if not classify_task:
        raise HTTPException(status_code=404, detail="Classify task not found")
    return classify_task
