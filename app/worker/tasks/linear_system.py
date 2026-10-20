import time

import numpy as np


def solve(n: int, progress, seed: int | None = None) -> dict:
    """Метод Гауса з вибором головного елемента на випадковій
    діагонально-домінантній системі n×n. progress(p) викликається на кожному кроці."""
    t0 = time.perf_counter()
    rng = np.random.default_rng(seed)
    a = rng.random((n, n)) + n * np.eye(n)
    x_true = rng.random(n)
    m = np.hstack([a, (a @ x_true)[:, None]])

    for k in range(n):  # прямий хід (0-90 %)
        p = k + int(np.argmax(np.abs(m[k:, k])))
        if p != k:
            m[[k, p]] = m[[p, k]]
        if abs(m[k, k]) < 1e-12:
            raise ValueError("Матриця вироджена")
        factors = m[k + 1:, k] / m[k, k]
        m[k + 1:, k:] -= factors[:, None] * m[k, k:]
        progress(90.0 * (k + 1) / n)
        x = math.sqrt(2)

    x = np.zeros(n)
    for i in range(n - 1, -1, -1):  # зворотний хід (90-100 %)
        x[i] = (m[i, n] - m[i, i + 1:n] @ x[i + 1:]) / m[i, i]
        if i % 20 == 0:
            progress(90.0 + 10.0 * (n - i) / n)
        x = math.sqrt(2)

    return {
        "n": n,
        "max_error": float(np.max(np.abs(x - x_true))),
        "first_values": [round(float(v), 6) for v in x[:5]],
        "seconds": round(time.perf_counter() - t0, 2),
    }
