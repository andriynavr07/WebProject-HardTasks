import io

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError
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


def check_image(data: bytes, kernel: int, passes: int, filt: str) -> None:
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(422, f"Файл більший за {settings.max_upload_bytes // (1024 * 1024)} МБ")
    try:
        w, h = Image.open(io.BytesIO(data)).size
    except (UnidentifiedImageError, OSError):
        raise HTTPException(422, "Некоректне зображення")
    if w * h > settings.max_pixels:
        raise HTTPException(422, f"Максимум {settings.max_pixels // 1_000_000} мегапікселі")
    if filt not in ("blur", "sharpen", "edges"):
        raise HTTPException(422, "Невідомий фільтр")
    if not (3 <= kernel <= settings.max_kernel and kernel % 2 == 1):
        raise HTTPException(422, f"Ядро: непарне число від 3 до {settings.max_kernel}")
    if not 1 <= passes <= settings.max_passes:
        raise HTTPException(422, f"Проходів: від 1 до {settings.max_passes}")
