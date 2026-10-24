"""API-тести на Playwright (APIRequestContext).

Запуск:
    pip install playwright pytest
    python -m pytest e2e -v

Змінні середовища :
    BASE_URL=https://localhost   ADMIN_USERNAME=admin   ADMIN_PASSWORD=admin1234
    EXPECT_MIN_SERVERS=2
    HEAVY_N=1500
"""
import os
import time
import uuid

import pytest
from playwright.sync_api import sync_playwright

BASE_URL = os.getenv("BASE_URL", "https://localhost")
ADMIN_USER = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "admin1234")
EXPECT_MIN_SERVERS = int(os.getenv("EXPECT_MIN_SERVERS", "2"))
PASSWORD = "secret123"
HEAVY_N = int(os.getenv("HEAVY_N", "1500"))  # "важка" задача; не більше за ліміт сервера


@pytest.fixture(scope="session")
def pw():
    with sync_playwright() as p:
        yield p


@pytest.fixture
def new_client(pw):
    """Фабрика незалежних клієнтів (у кожного свої cookie)."""
    contexts = []

    def make():
        ctx = pw.request.new_context(base_url=BASE_URL, ignore_https_errors=True)
        contexts.append(ctx)
        return ctx

    yield make
    for c in contexts:
        c.dispose()


def unique_name():
    return "user_" + uuid.uuid4().hex[:10]


@pytest.fixture
def user(new_client):
    """Новий зареєстрований користувач."""
    c = new_client()
    name = unique_name()
    r = c.post("/api/register", data={"username": name, "password": PASSWORD})
    assert r.status == 200, r.text()
    return c, name


def wait_status(client, task_id, wanted=("done", "failed", "cancelled"), timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        t = client.get(f"/api/tasks/{task_id}").json()
        if t["status"] in wanted:
            return t
        time.sleep(0.5)
    raise AssertionError(f"Задача {task_id} не завершилась за {timeout} с")


def cancel_all(client):
    for t in client.get("/api/tasks").json():
        if t["status"] in ("queued", "running"):
            client.post(f"/api/tasks/{t['id']}/cancel")


# ---------- авторизація ----------

def test_health_has_served_by_header(new_client):
    r = new_client().get("/health")
    assert r.status == 200
    assert r.headers.get("x-served-by")


def test_tasks_require_auth(new_client):
    assert new_client().get("/api/tasks").status == 401
    assert new_client().post("/api/tasks/linear", data={"n": 10}).status == 401


@pytest.mark.parametrize("payload", [
    {"username": "ab", "password": "secret123"},         # занадто короткий логін
    {"username": "valid_name", "password": "123"},       # занадто короткий пароль
    {"username": "bad name!", "password": "secret123"},  # недопустимі символи
])
def test_register_validation(new_client, payload):
    assert new_client().post("/api/register", data=payload).status == 422


def test_duplicate_registration(user, new_client):
    _, name = user
    r = new_client().post("/api/register", data={"username": name, "password": PASSWORD})
    assert r.status == 409


def test_login_wrong_password(user, new_client):
    _, name = user
    r = new_client().post("/api/login", data={"username": name, "password": "wrong-pass"})
    assert r.status == 401


def test_login_and_me(user, new_client):
    _, name = user
    c = new_client()
    assert c.post("/api/login", data={"username": name, "password": PASSWORD}).status == 200
    me = c.get("/api/me").json()
    assert me == {"username": name, "is_admin": False}


def test_logout_clears_session(user):
    c, _ = user
    assert c.get("/api/me").status == 200
    assert c.post("/api/logout").status == 200
    assert c.get("/api/me").status == 401


# ---------- задачі ----------

def test_linear_task_full_cycle(user):
    c, _ = user
    r = c.post("/api/tasks/linear", data={"n": 60})
    assert r.status == 200
    task_id = r.json()["id"]

    t = wait_status(c, task_id)
    assert t["status"] == "done"
    assert t["progress"] == 100
    assert t["result"]["max_error"] < 1e-8
    assert t["worker"]

    result = c.get(f"/api/tasks/{task_id}/result").json()
    assert result["n"] == 60
    assert len(result["first_values"]) == 5


@pytest.mark.parametrize("n", [1, 0, -5, 10_000_000])
def test_linear_limits_rejected(user, n):
    c, _ = user
    assert c.post("/api/tasks/linear", data={"n": n}).status == 422


def test_linear_invalid_body(user):
    c, _ = user
    assert c.post("/api/tasks/linear", data={"n": "abc"}).status == 422


def test_history_lists_own_tasks_newest_first(user):
    c, _ = user
    ids = [c.post("/api/tasks/linear", data={"n": 30}).json()["id"] for _ in range(2)]
    for i in ids:
        wait_status(c, i)
    history = c.get("/api/tasks").json()
    assert [t["id"] for t in history[:2]] == sorted(ids, reverse=True)


def test_queued_task_has_eta_field(user):
    c, _ = user
    ids = [c.post("/api/tasks/linear", data={"n": HEAVY_N}).json()["id"] for _ in range(3)]
    try:
        for t in c.get("/api/tasks").json():
            assert "eta_seconds" in t
            if t["status"] != "queued":
                assert t["eta_seconds"] is None
            else:
                assert t["eta_seconds"] >= 0
    finally:
        cancel_all(c)
        for i in ids:
            wait_status(c, i)


def test_cancel_task(user):
    c, _ = user
    task_id = c.post("/api/tasks/linear", data={"n": HEAVY_N}).json()["id"]
    r = c.post(f"/api/tasks/{task_id}/cancel")
    assert r.status == 200
    assert wait_status(c, task_id)["status"] == "cancelled"
    # повторне скасування завершеної задачі
    assert c.post(f"/api/tasks/{task_id}/cancel").status == 409


def test_active_tasks_limit(user):
    c, _ = user
    ids = []
    try:
        for _ in range(3):
            r = c.post("/api/tasks/linear", data={"n": HEAVY_N})
            assert r.status == 200, r.text()
            ids.append(r.json()["id"])
        assert c.post("/api/tasks/linear", data={"n": HEAVY_N}).status == 429
    finally:
        cancel_all(c)
        for i in ids:
            wait_status(c, i)


def test_user_cannot_see_foreign_task(user, new_client):
    owner, _ = user
    task_id = owner.post("/api/tasks/linear", data={"n": 30}).json()["id"]
    wait_status(owner, task_id)

    other = new_client()
    other.post("/api/register", data={"username": unique_name(), "password": PASSWORD})
    assert other.get(f"/api/tasks/{task_id}").status == 404
    assert other.get(f"/api/tasks/{task_id}/result").status == 404
    assert other.post(f"/api/tasks/{task_id}/cancel").status == 404


def test_result_not_ready_returns_409(user):
    c, _ = user
    task_id = c.post("/api/tasks/linear", data={"n": HEAVY_N}).json()["id"]
    try:
        assert c.get(f"/api/tasks/{task_id}/result").status == 409
    finally:
        c.post(f"/api/tasks/{task_id}/cancel")
        wait_status(c, task_id)


# ---------- адмін-панель ----------

def test_admin_stats_forbidden_for_regular_user(user):
    c, _ = user
    assert c.get("/api/admin/stats").status == 403


def test_admin_stats_requires_auth(new_client):
    assert new_client().get("/api/admin/stats").status == 401


def test_admin_stats_ok(new_client):
    c = new_client()
    if c.post("/api/login", data={"username": ADMIN_USER, "password": ADMIN_PASS}).status != 200:
        pytest.skip("Невірні ADMIN_USERNAME/ADMIN_PASSWORD")
    r = c.get("/api/admin/stats")
    assert r.status == 200
    data = r.json()
    assert {"servers", "tasks", "queued", "running", "events"} <= data.keys()
    assert len(data["servers"]) >= 1


# ---------- балансування навантаження ----------

def test_load_balancer_uses_multiple_servers(new_client):
    c = new_client()
    servers = {c.get("/health").headers["x-served-by"] for _ in range(30)}
    assert len(servers) >= EXPECT_MIN_SERVERS, f"Відповіли сервери: {servers}"