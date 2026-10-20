"""Автоскейлер: стежить за довжиною черги й додає/прибирає контейнери app.

Нові контейнери створюються з того ж образу й середовища, що й сервіс app,
підключаються до тієї ж мережі з alias "app" - тому nginx підхоплює їх
автоматично через Docker DNS.
"""
import os
import time
from datetime import datetime, timezone

import docker
from sqlalchemy import create_engine, text

MIN_APPS = int(os.getenv("MIN_APPS", "2"))
MAX_APPS = int(os.getenv("MAX_APPS", "5"))
SCALE_UP_QUEUE = int(os.getenv("SCALE_UP_QUEUE", "3"))    # задач у черзі на один сервер
SCALE_DOWN_IDLE = int(os.getenv("SCALE_DOWN_IDLE", "60"))  # с простою перед зменшенням
INTERVAL = 10
COOLDOWN = 25
EXTRA_LABEL = "hardtasks.autoscaled"

client = docker.from_env()
engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)


def log_event(msg: str) -> None:
    print(msg, flush=True)
    try:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO scaler_events (ts, message) VALUES (:ts, :m)"),
                         {"ts": datetime.now(timezone.utc), "m": msg})
    except Exception as e:  # noqa: BLE001
        print("event log failed:", e, flush=True)


def containers():
    base = client.containers.list(filters={"label": "com.docker.compose.service=app", "status": "running"})
    extra = client.containers.list(filters={"label": f"{EXTRA_LABEL}=1", "status": "running"})
    return base, extra


def scale_up(template) -> None:
    cfg = template.attrs["Config"]
    net_name = next(iter(template.attrs["NetworkSettings"]["Networks"]))
    c = client.containers.create(
        image=cfg["Image"], command=cfg.get("Cmd"), environment=cfg.get("Env"),
        labels={EXTRA_LABEL: "1"}, network=net_name, name=f"hardtasks-app-auto-{int(time.time())}",
    )
    net = client.networks.get(net_name)
    net.disconnect(c)
    net.connect(c, aliases=["app"])
    c.start()


def main() -> None:
    idle_since = None
    print(f"autoscaler: min={MIN_APPS} max={MAX_APPS} up_queue={SCALE_UP_QUEUE} idle={SCALE_DOWN_IDLE}s", flush=True)
    while True:
        time.sleep(INTERVAL)
        try:
            with engine.connect() as conn:
                queued = conn.execute(text("SELECT count(*) FROM tasks WHERE status='queued'")).scalar()
                running = conn.execute(text("SELECT count(*) FROM tasks WHERE status='running'")).scalar()
            base, extra = containers()
            total = len(base) + len(extra)

            if queued > SCALE_UP_QUEUE * total and total < MAX_APPS and base:
                scale_up(base[0])
                log_event(f"Scale UP: {total} -> {total + 1} серверів (у черзі {queued})")
                idle_since = None
                time.sleep(COOLDOWN)
            elif queued == 0 and running == 0:
                idle_since = idle_since or time.monotonic()
                if extra and total > MIN_APPS and time.monotonic() - idle_since >= SCALE_DOWN_IDLE:
                    victim = extra[-1]
                    victim.stop(timeout=10)
                    victim.remove()
                    log_event(f"Scale DOWN: {total} -> {total - 1} серверів (простій)")
                    idle_since = time.monotonic()
            else:
                idle_since = None
        except Exception as e:  # noqa: BLE001
            print("autoscaler error:", e, flush=True)


if __name__ == "__main__":
    main()
