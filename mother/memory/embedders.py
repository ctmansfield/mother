from __future__ import annotations

import hashlib
import math
import os
from dataclasses import dataclass
from typing import List, Protocol


class Embedder(Protocol):
    def embed(self, text: str) -> List[float]: ...
    @property
    def dim(self) -> int: ...
    @property
    def name(self) -> str: ...


@dataclass
class HashEmbedder:
    """Dependency-free fallback embedder for smoke tests."""

    _dim: int = 1024
    _name: str = "hash-fallback-v1"

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def name(self) -> str:
        return self._name

    def embed(self, text: str) -> List[float]:
        h = hashlib.sha256(text.encode("utf-8")).digest()
        seed = int.from_bytes(h[:8], "big") or 1
        vals = [0.0] * self._dim
        x = seed
        for i in range(self._dim):
            x = (1103515245 * x + 12345) & ((1 << 63) - 1)
            vals[i] = ((x % 1000003) / 500001.5) - 1.0
        norm = math.sqrt(sum(v * v for v in vals)) or 1.0
        return [v / norm for v in vals]


def load_embedder():
    model_id = os.getenv("EMBEDDING_MODEL")
    dim_env = int(os.getenv("EMBEDDING_DIM", "1024"))
    if not model_id:
        return HashEmbedder(_dim=dim_env)
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore

        m = SentenceTransformer(model_id)

        class _ST:
            def __init__(self, m, name, dim):
                self._m = m
                self._name = name
                self._dim = dim

            @property
            def dim(self):
                return self._dim

            @property
            def name(self):
                return self._name

            def embed(self, text: str):
                v = self._m.encode(text, normalize_embeddings=True)
                return v.tolist() if hasattr(v, "tolist") else list(v)

        probe = _ST(m, model_id, dim_env)
        v = probe.embed("probe")
        probe._dim = len(v) or dim_env
        return probe
    except Exception:
        return HashEmbedder(_dim=dim_env)
