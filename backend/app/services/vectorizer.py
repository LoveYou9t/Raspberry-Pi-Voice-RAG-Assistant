# // AI辅助生成：ChatGPT-5.3 Codex, 2025-11-03
from __future__ import annotations

import re
import zlib

import numpy as np

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


def text_to_vector(text: str, dims: int) -> np.ndarray:
    """Build a stable hashed bag-of-words vector for lightweight retrieval."""
    vector = np.zeros(dims, dtype=np.float32)
    for token in TOKEN_PATTERN.findall(text.lower()):
        index = zlib.crc32(token.encode("utf-8")) % dims
        vector[index] += 1.0

    norm = np.linalg.norm(vector)
    if norm > 0:
        vector /= norm
    return vector
