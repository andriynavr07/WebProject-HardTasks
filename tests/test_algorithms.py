from app.worker.tasks.linear_system import solve


def test_solve_small_system():
    calls = []
    res = solve(60, calls.append, seed=1)
    assert res["n"] == 60
    assert res["max_error"] < 1e-8
    assert calls and max(calls) <= 100
