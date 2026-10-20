import logging
import socket
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import insert, select, text

from . import models  # noqa: F401  (реєстрація моделей)
from .auth import hash_password
from .config import settings
from .db import Base, engine
from .models import User
from .routers import admin as admin_router
from .routers import auth as auth_router
from .routers import tasks as tasks_router
from .worker.runner import start_workers

logging.basicConfig(level=logging.INFO)
STATIC = Path(__file__).parent / "static"
HOST = socket.gethostname()


def init_db() -> None:
    """Створює таблиці й адміна. Advisory lock захищає від гонки,
    коли кілька контейнерів стартують одночасно."""
    for attempt in range(40):
        try:
            with engine.begin() as conn:
                if engine.dialect.name == "postgresql":
                    conn.execute(text("SELECT pg_advisory_xact_lock(727272)"))
                Base.metadata.create_all(conn)
                exists = conn.execute(select(User.id).where(User.username == settings.admin_username)).first()
                if exists is None:
                    conn.execute(insert(User).values(
                        username=settings.admin_username,
                        password_hash=hash_password(settings.admin_password),
                        is_admin=True,
                    ))
            return
        except Exception as e:  # noqa: BLE001
            logging.warning("DB not ready (%s): %s", attempt, e)
            time.sleep(1.5)
    raise RuntimeError("База даних недоступна")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    stop = start_workers()
    yield
    stop.set()


app = FastAPI(title="Compute Hub", lifespan=lifespan)


@app.middleware("http")
async def served_by(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Served-By"] = HOST  # видно, який сервер відповів
    return response


app.include_router(auth_router.router)
app.include_router(tasks_router.router)
app.include_router(admin_router.router)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/admin")
def admin_page():
    return FileResponse(STATIC / "admin.html")


@app.get("/health")
def health():
    return {"status": "ok", "server": HOST}
