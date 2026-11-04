import heapq
from datetime import timedelta, timezone

from sqlalchemy import func, select, update

from ..db import SessionLocal
from ..models import Task, Worker, utcnow

ALIVE_SECONDS = 15
ORPHAN_SECONDS = 30
DEFAULT_K = 1.5e-9


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
    with SessionLocal() as db:
        row = db.execute(
            update(Task).where(Task.id == task_id).values(progress=round(progress, 1)).returning(Task.cancel_requested)
        ).first()
        db.commit()
        return bool(row and row[0])


def finish(task_id: int, status: str, result: dict | None = None, error: str | None = None) -> None:
    with SessionLocal() as db:
        t = db.get(Task, task_id)
        t.status = status
        t.finished_at = utcnow()
        if status == "done":
            t.progress = 100.0
        t.result = result
        t.error = error
        db.commit()


def requeue_orphans() -> None:
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


def _ts(dt) -> float:
    return (dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt).timestamp()


def compute_eta(db) -> dict:
    now = utcnow().timestamp()
    cutoff = utcnow() - timedelta(seconds=ALIVE_SECONDS)
    slots = max(1, db.scalar(select(func.count()).select_from(Worker).where(Worker.last_heartbeat > cutoff)) or 0)

    rows = db.execute(
        select(Task.params, Task.started_at, Task.finished_at)
        .where(Task.status == "done", Task.type == "linear", Task.started_at.is_not(None))
        .order_by(Task.id.desc()).limit(30)
    ).all()
    ks = sorted(
        (_ts(f) - _ts(s)) / int(p["n"]) ** 3
        for p, s, f in rows if p and p.get("n") and s and f and _ts(f) > _ts(s)
    )
    k = ks[len(ks) // 2] if ks else DEFAULT_K

    def est(t: Task) -> float:
        return k * int((t.params or {}).get("n", 1000)) ** 3

    remaining, free_at = {}, []
    for t in db.scalars(select(Task).where(Task.status == "running")):
        elapsed = now - _ts(t.started_at) if t.started_at else 0.0
        rem = max(est(t) - elapsed, 1.0)
        remaining[t.id] = round(rem, 1)
        free_at.append(rem)
    free_at += [0.0] * max(0, slots - len(free_at))
    heapq.heapify(free_at)

    wait = {}
    for t in db.scalars(select(Task).where(Task.status == "queued").order_by(Task.id)):
        start = heapq.heappop(free_at)
        wait[t.id] = round(start, 1)
        heapq.heappush(free_at, start + est(t))
    return {"wait": wait, "remaining": remaining}
