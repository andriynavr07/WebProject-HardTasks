from datetime import timedelta

from sqlalchemy import func, select, update

from ..db import SessionLocal
from ..models import Task, Worker, utcnow

ALIVE_SECONDS = 15
ORPHAN_SECONDS = 30
DEFAULT_AVG = 15.0


def heartbeat(worker_id: str, hostname: str, task_id: int | None) -> None:
    with SessionLocal() as db:
        w = db.get(Worker, worker_id)
        if w is None:
            w = Worker(id=worker_id, hostname=hostname)
            db.add(w)
        w.last_heartbeat = utcnow()
        w.current_task_id = task_id
        db.commit()


def claim_task(worker_id: str) -> dict | None:
    """Атомарно бере першу задачу з черги. SKIP LOCKED гарантує, що
    два сервери не візьмуть одну й ту саму задачу."""
    with SessionLocal() as db:
        t = db.execute(
            select(Task).where(Task.status == "queued").order_by(Task.id).limit(1).with_for_update(skip_locked=True)
        ).scalar_one_or_none()
        if t is None:
            return None
        t.status = "running"
        t.worker_id = worker_id
        t.started_at = utcnow()
        t.progress = 0.0
        info = {"id": t.id, "type": t.type, "params": dict(t.params or {})}
        db.commit()
        return info


def report_progress(task_id: int, progress: float) -> bool:
    """Оновлює прогрес і повертає True, якщо користувач попросив скасувати."""
    with SessionLocal() as db:
        row = db.execute(
            update(Task).where(Task.id == task_id).values(progress=round(progress, 1)).returning(Task.cancel_requested)
        ).first()
        db.commit()
        return bool(row and row[0])


def load_input(task_id: int) -> bytes:
    with SessionLocal() as db:
        return db.execute(select(Task.input_blob).where(Task.id == task_id)).scalar_one()


def finish(task_id: int, status: str, result: dict | None = None, blob: bytes | None = None,
           error: str | None = None) -> None:
    with SessionLocal() as db:
        t = db.get(Task, task_id)
        t.status = status
        t.finished_at = utcnow()
        if status == "done":
            t.progress = 100.0
        t.result = result
        t.result_blob = blob
        t.error = error
        db.commit()


def requeue_orphans() -> None:
    """Задачі, чий воркер перестав слати heartbeat (контейнер зупинено/впав),
    повертаються в чергу."""
    cutoff = utcnow() - timedelta(seconds=ORPHAN_SECONDS)
    with SessionLocal() as db:
        alive = set(db.scalars(select(Worker.id).where(Worker.last_heartbeat > cutoff)))
        rows = db.scalars(select(Task).where(Task.status == "running").with_for_update(skip_locked=True)).all()
        for t in rows:
            if t.worker_id in alive:
                continue
            if t.cancel_requested:
                t.status, t.finished_at = "cancelled", utcnow()
            else:
                t.status, t.progress, t.worker_id, t.started_at = "queued", 0.0, None, None
        db.commit()


def eta_context(db) -> dict:
    cutoff = utcnow() - timedelta(seconds=ALIVE_SECONDS)
    slots = db.scalar(select(func.count()).select_from(Worker).where(Worker.last_heartbeat > cutoff)) or 0
    busy = db.scalar(select(func.count()).select_from(Task).where(Task.status == "running")) or 0
    rows = db.execute(
        select(Task.started_at, Task.finished_at).where(Task.status == "done", Task.started_at.is_not(None))
        .order_by(Task.id.desc()).limit(30)
    ).all()
    durs = [(f.replace(tzinfo=None) - s.replace(tzinfo=None)).total_seconds() for s, f in rows if s and f]
    avg = sum(durs) / len(durs) if durs else DEFAULT_AVG
    return {"slots": max(1, slots), "busy": busy, "avg": max(avg, 0.5)}


def estimate_wait(db, task: Task, ctx: dict) -> float | None:
    """Орієнтовний час до старту задачі (с). Задачі, що зараз виконуються,
    в середньому вже наполовину готові."""
    if task.status != "queued":
        return None
    ahead = db.scalar(select(func.count()).select_from(Task).where(Task.status == "queued", Task.id < task.id)) or 0
    free = max(0, ctx["slots"] - ctx["busy"])
    if ahead < free:
        return 0.0
    return round(ctx["avg"] * ((ahead - free) / ctx["slots"] + 0.5), 1)
