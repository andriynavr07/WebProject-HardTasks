import time

from fastapi.testclient import TestClient
from app.main import app


def wait_done(client, tid, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        t = client.get(f"/api/tasks/{tid}").json()
        if t["status"] in ("done", "failed", "cancelled"):
            return t
        time.sleep(0.3)
    raise AssertionError("timeout")


def test_full_flow():
    with TestClient(app) as c:
        assert c.get("/api/tasks").status_code == 401
        assert c.post("/api/register", json={"username": "student", "password": "secret1"}).status_code == 200

        r = c.post("/api/tasks/linear", json={"n": 40})
        t = wait_done(c, r.json()["id"])
        assert t["status"] == "done" and t["result"]["max_error"] < 1e-8

        assert c.post("/api/tasks/linear", json={"n": 999999}).status_code == 422

        assert t["status"] == "done"
        assert c.get(f"/api/tasks/{t['id']}/result").headers["content-type"] == "image/png"

        assert c.get("/api/admin/stats").status_code == 403


def test_cancel_running_task():
    with TestClient(app) as c:
        c.post("/api/login", json={"username": "student", "password": "secret1"})
        tid = c.post("/api/tasks/linear", json={"n": 1500}).json()["id"]
        time.sleep(2)
        c.post(f"/api/tasks/{tid}/cancel")
        assert wait_done(c, tid)["status"] == "cancelled"
