import logging
import socket
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import insert, select, text, update

from . import models
from .auth import hash_password, verify_password
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
    for attempt in range(40):
        try:
            with engine.begin() as conn:
                if engine.dialect.name == "postgresql":
                    conn.execute(text("SELECT pg_advisory_xact_lock(727272)"))
                Base.metadata.create_all(conn)
                row = conn.execute(select(User.id, User.password_hash).where(User.username == settings.admin_username)).first()
                if row is None:
                    conn.execute(insert(User).values(
                        username=settings.admin_username,
                        password_hash=hash_password(settings.admin_password),
                        is_admin=True,
                    ))
                elif not verify_password(settings.admin_password, row.password_hash):

                    conn.execute(update(User).where(User.id == row.id).values(
                        password_hash=hash_password(settings.admin_password), is_admin=True))
            return
        except Exception as e:
            logging.warning("DB not ready (%s): %s", attempt, e)
            time.sleep(1.5)
    raise RuntimeError("База даних недоступна")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    stop = start_workers()
    yield
    stop.set()


app = FastAPI(title="HardTasks", lifespan=lifespan)


@app.middleware("http")
async def served_by(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Served-By"] = HOST
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
