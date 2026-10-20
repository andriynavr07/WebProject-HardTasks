from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Task


def check_active_limit(db: Session, user_id: int) -> None:
    active = db.scalar(
        select(func.count()).select_from(Task).where(Task.user_id == user_id, Task.status.in_(("queued", "running")))
    )
    if active >= settings.max_active_per_user:
        raise HTTPException(429, f"Ліміт активних задач: {settings.max_active_per_user}")


def check_linear(n: int) -> None:
    if not 2 <= n <= settings.max_linear_n:
        raise HTTPException(422, f"n має бути від 2 до {settings.max_linear_n}")
