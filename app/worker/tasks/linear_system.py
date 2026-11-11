import random
import time


def solve(n: int, progress, seed: int | None = None) -> dict:
    t0 = time.perf_counter()
    rnd = random.Random(seed)

    a = [[rnd.random() for _ in range(n)] for _ in range(n)]
    for i in range(n):
        a[i][i] += n
    x_true = [rnd.random() for _ in range(n)]
    for i in range(n):
        a[i].append(sum(a[i][j] * x_true[j] for j in range(n)))

    for k in range(n):
        p = max(range(k, n), key=lambda i: abs(a[i][k]))
        if p != k:
            a[k], a[p] = a[p], a[k]
        row_k = a[k]
        pivot = row_k[k]
        if abs(pivot) < 1e-12:
            raise ValueError("Матриця вироджена")
        for i in range(k + 1, n):
            row_i = a[i]
            factor = row_i[k] / pivot
            for j in range(k, n + 1):
                row_i[j] -= factor * row_k[j]
        progress(90.0 * (k + 1) / n)

    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        row = a[i]
        s = row[n]
        for j in range(i + 1, n):
            s -= row[j] * x[j]
        x[i] = s / row[i]
        if i % 20 == 0:
            progress(90.0 + 10.0 * (n - i) / n)

    return {
        "n": n,
        "max_error": max(abs(x[i] - x_true[i]) for i in range(n)),
        "first_values": [round(v, 6) for v in x[:5]],
        "seconds": round(time.perf_counter() - t0, 2),
    }