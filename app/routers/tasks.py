from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, undefer

from ..auth import current_user
from ..config import settings
from ..db import get_db
from ..models import Task, User, utcnow
from ..schemas import LinearIn
from ..services import limits
from ..services.queue import estimate_wait, eta_context

router = APIRouter(prefix="/api/tasks")


def _iso(dt):
    return dt.isoformat() if dt else None


def serialize(db: Session, t: Task, ctx: dict) -> dict:
    return {
        "id": t.id, "type": t.type, "status": t.status, "progress": t.progress, "params": t.params,
        "result": t.result, "error": t.error, "worker": t.worker_id,
        "created_at": _iso(t.created_at), "started_at": _iso(t.started_at), "finished_at": _iso(t.finished_at),
        "eta_seconds": estimate_wait(db, t, ctx),
    }


def _own_task(db: Session, task_id: int, user: User, with_result: bool = False) -> Task:
    opts = [undefer(Task.result_blob)] if with_result else []
    t = db.get(Task, task_id, options=opts)
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


@router.post("/image")
async def create_image(file: UploadFile = File(...), filter: str = Form("blur"), kernel: int = Form(5),
                       passes: int = Form(1), db: Session = Depends(get_db), user: User = Depends(current_user)):
    limits.check_active_limit(db, user.id)
    data = await file.read(settings.max_upload_bytes + 1)
    limits.check_image(data, kernel, passes, filter)
    t = Task(user_id=user.id, type="image", params={"filter": filter, "kernel": kernel, "passes": passes,
                                                    "filename": (file.filename or "image")[:80]},
             input_blob=data)
    db.add(t)
    db.commit()
    return {"id": t.id}


@router.get("")
def list_tasks(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.scalars(select(Task).where(Task.user_id == user.id).order_by(Task.id.desc()).limit(50)).all()
    ctx = eta_context(db)
    return [serialize(db, t, ctx) for t in rows]


@router.get("/{task_id}")
def get_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return serialize(db, _own_task(db, task_id, user), eta_context(db))


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
    t = _own_task(db, task_id, user, with_result=True)
    if t.status != "done":
        raise HTTPException(409, "Результат ще не готовий")
    if t.type == "image":
        return Response(t.result_blob, media_type="image/png",
                        headers={"Content-Disposition": f'inline; filename="result-{t.id}.png"'})
    return t.result
