import io

from PIL import Image

from app.worker.tasks.image_filter import apply_filter
from app.worker.tasks.linear_system import solve


def test_solve_small_system():
    calls = []
    res = solve(60, calls.append, seed=1)
    assert res["n"] == 60
    assert res["max_error"] < 1e-8
    assert calls and max(calls) <= 100


def test_image_filters_return_png():
    img = Image.new("RGB", (40, 30), (200, 100, 50))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    for filt in ("blur", "sharpen", "edges"):
        out = apply_filter(buf.getvalue(), filt, 5, 2, lambda p: None)
        assert Image.open(io.BytesIO(out)).size == (40, 30)
