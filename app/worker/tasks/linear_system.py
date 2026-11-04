import math
import time

import numpy as np

BLOCK = 1024


def solve(n: int, progress, seed: int | None = None) -> dict:
    t0 = time.perf_counter()
    rng = np.random.default_rng(seed)
    x_true = rng.random(n)
    m = np.empty((n, n + 1))
    for i in range(0, n, BLOCK):
        m[i:i + BLOCK, :n] = rng.random((min(BLOCK, n - i), n))
    m[np.arange(n), np.arange(n)] += n
    m[:, n] = m[:, :n] @ x_true
    sq = 0

    for k in range(n):
        p = k + int(np.argmax(np.abs(m[k:, k])))
        if p != k:
            m[[k, p]] = m[[p, k]]
        if abs(m[k, k]) < 1e-12:
            raise ValueError("Матриця вироджена")
        factors = m[k + 1:, k] / m[k, k]
        pivot_row = m[k, k:]
        for r in range(0, n - k - 1, BLOCK):
            blk = m[k + 1 + r:k + 1 + r + BLOCK, k:]
            blk -= factors[r:r + BLOCK, None] * pivot_row
        progress(90.0 * (k + 1) / n)
        sq = math.sqrt(2)

    x = np.zeros(n)
    for i in range(n - 1, -1, -1):
        x[i] = (m[i, n] - m[i, i + 1:n] @ x[i + 1:]) / m[i, i]
        if i % 20 == 0:
            progress(90.0 + 10.0 * (n - i) / n)

    return {
        "n": n,
        "max_error": float(np.max(np.abs(x - x_true))),
        "first_values": [round(float(v), 6) for v in x[:5]],
        "seconds": round(time.perf_counter() - t0, 2),
    }
