from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..models import ScalerEvent, Task, User, utcnow
from ..schemas import LinearIn
from ..services import limits
from ..services.queue import compute_eta

router = APIRouter(prefix="/api/tasks")

SCALING_WINDOW = 60


def _iso(dt):
    return dt.isoformat() if dt else None


def is_scaling(db: Session) -> bool:
    since = utcnow() - timedelta(seconds=SCALING_WINDOW)
    return db.scalar(select(ScalerEvent.id).where(ScalerEvent.message.like("Scale UP%"),
                                                  ScalerEvent.ts > since).limit(1)) is not None


def serialize(t: Task, eta: dict, scaling: bool = False) -> dict:
    return {
        "id": t.id, "type": t.type, "status": t.status, "progress": t.progress, "params": t.params,
        "result": t.result, "error": t.error, "worker": t.worker_id,
        "created_at": _iso(t.created_at), "started_at": _iso(t.started_at), "finished_at": _iso(t.finished_at),
        "eta_seconds": eta["wait"].get(t.id),
        "remaining_seconds": eta["remaining"].get(t.id),
        "scaling": scaling and t.status == "queued",
    }


def _own_task(db: Session, task_id: int, user: User) -> Task:
    t = db.get(Task, task_id)
    if t is None or (t.user_id != user.id and not user.is_admin):
        raise HTTPException(404, "Задачу не знайдено")
    return t


@router.post("/linear")
def create_linear(body: LinearIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    limits.check_active_limit(db, user.id)
    limits.check_linear(body.n)
    t = Task(user_id=user.id, type="linear", params={"n": body.n})
    db.add(t)
    db.commit()
    return {"id": t.id}


@router.get("")
def list_tasks(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.scalars(select(Task).where(Task.user_id == user.id).order_by(Task.id.desc()).limit(50)).all()
    eta, scaling = compute_eta(db), is_scaling(db)
    return [serialize(t, eta, scaling) for t in rows]


@router.get("/{task_id}")
def get_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return serialize(_own_task(db, task_id, user), compute_eta(db), is_scaling(db))


@router.post("/{task_id}/cancel")
def cancel(task_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    t = _own_task(db, task_id, user)
    if t.status == "queued":
        t.status, t.finished_at = "cancelled", utcnow()
    elif t.status == "running":
        t.cancel_requested = True
    else:
        raise HTTPException(409, "Задача вже завершена")
    db.commit()
    return {"status": t.status, "cancel_requested": t.cancel_requested}


@router.get("/{task_id}/result")
def result(task_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    t = _own_task(db, task_id, user)
    if t.status != "done":
        raise HTTPException(409, "Результат ще не готовий")
    return t.result
