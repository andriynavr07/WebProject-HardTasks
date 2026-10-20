import io

import numpy as np
from PIL import Image

KERNELS = {
    "sharpen": np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32),
    "edges": np.array([[-1, -1, -1], [-1, 8, -1], [-1, -1, -1]], dtype=np.float32),
}


def apply_filter(data: bytes, filt: str, kernel_size: int, passes: int, progress) -> bytes:
    """Згортка зображення; кожен крок (зсув ядра) звітує про прогрес."""
    arr = np.asarray(Image.open(io.BytesIO(data)).convert("RGB"), dtype=np.float32)
    if filt == "blur":
        kernel = np.full((kernel_size, kernel_size), 1.0 / kernel_size ** 2, dtype=np.float32)
    else:
        kernel = KERNELS[filt]
    kh, kw = kernel.shape
    ph, pw = kh // 2, kw // 2
    h, w = arr.shape[:2]
    total, done = passes * kh * kw, 0

    for _ in range(passes):
        padded = np.pad(arr, ((ph, ph), (pw, pw), (0, 0)), mode="edge")
        out = np.zeros_like(arr)
        for dy in range(kh):
            for dx in range(kw):
                out += kernel[dy, dx] * padded[dy:dy + h, dx:dx + w]
                done += 1
                progress(100.0 * done / total)
        arr = np.clip(out, 0, 255)

    buf = io.BytesIO()
    Image.fromarray(arr.astype(np.uint8)).save(buf, "PNG")
    return buf.getvalue()
