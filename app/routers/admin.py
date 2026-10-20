from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import admin_user
from ..db import get_db
from ..models import ScalerEvent, Task, Worker, utcnow
from ..services.queue import ALIVE_SECONDS

router = APIRouter(prefix="/api/admin")


@router.get("/stats")
def stats(db: Session = Depends(get_db), _=Depends(admin_user)):
    cutoff = utcnow() - timedelta(seconds=ALIVE_SECONDS)
    workers = db.scalars(select(Worker).where(Worker.last_heartbeat > cutoff).order_by(Worker.hostname, Worker.id)).all()
    servers: dict[str, dict] = {}
    for w in workers:
        s = servers.setdefault(w.hostname, {"hostname": w.hostname, "workers": 0, "busy": 0, "tasks": []})
        s["workers"] += 1
        if w.current_task_id:
            s["busy"] += 1
            s["tasks"].append(w.current_task_id)
    counts = {k: v for k, v in db.execute(select(Task.status, func.count()).group_by(Task.status)).all()}
    events = db.scalars(select(ScalerEvent).order_by(ScalerEvent.id.desc()).limit(20)).all()
    return {
        "servers": list(servers.values()),
        "tasks": counts,
        "queued": counts.get("queued", 0),
        "running": counts.get("running", 0),
        "events": [{"ts": e.ts.isoformat(), "message": e.message} for e in events],
    }
