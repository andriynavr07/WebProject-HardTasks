import logging
import socket
import threading
import time

from ..config import settings
from ..services import queue
from .tasks.image_filter import apply_filter
from .tasks.linear_system import solve

log = logging.getLogger("worker")
HOST = socket.gethostname()


class Cancelled(Exception):
    pass


def execute(info: dict, worker_id: str) -> None:
    tid, params = info["id"], info["params"]
    last = [0.0]

    def progress(p: float) -> None:
        now = time.monotonic()
        if p < 100 and now - last[0] < 0.5:
            return
        last[0] = now
        queue.heartbeat(worker_id, HOST, tid)
        if queue.report_progress(tid, p):
            raise Cancelled()

    try:
        if info["type"] == "linear":
            queue.finish(tid, "done", result=solve(int(params["n"]), progress))
        elif info["type"] == "image":
            png = apply_filter(queue.load_input(tid), params["filter"], int(params["kernel"]),
                               int(params["passes"]), progress)
            queue.finish(tid, "done", result={"bytes": len(png)}, blob=png)
        else:
            raise ValueError(f"Невідомий тип задачі: {info['type']}")
    except Cancelled:
        queue.finish(tid, "cancelled")
    except Exception as e:  # noqa: BLE001
        log.exception("task %s failed", tid)
        queue.finish(tid, "failed", error=str(e)[:500])


def worker_loop(worker_id: str, stop: threading.Event) -> None:
    last_reap = 0.0
    while not stop.is_set():
        try:
            queue.heartbeat(worker_id, HOST, None)
            if time.monotonic() - last_reap > 10:
                queue.requeue_orphans()
                last_reap = time.monotonic()
            info = queue.claim_task(worker_id)
            if info is None:
                stop.wait(1.0)
                continue
            execute(info, worker_id)
        except Exception:  # noqa: BLE001
            log.exception("worker loop error")
            stop.wait(2.0)


def start_workers() -> threading.Event:
    stop = threading.Event()
    for i in range(settings.worker_threads):
        threading.Thread(target=worker_loop, args=(f"{HOST}-{i}", stop), daemon=True).start()
    return stop
