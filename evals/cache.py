import hashlib
import logging
import sqlite3
import struct
from pathlib import Path

logger = logging.getLogger("evals.cache")


class EmbeddingCache:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path))
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vectors (
                key   TEXT PRIMARY KEY,
                dims  INTEGER NOT NULL,
                data  BLOB NOT NULL
            )
            """
        )
        self._conn.commit()
        self.hits = 0
        self.misses = 0

    @staticmethod
    def key(model: str, dimensions: int, text: str) -> str:
        digest = hashlib.sha256(f"{model}\x00{dimensions}\x00{text}".encode("utf-8"))
        return digest.hexdigest()

    def get(self, key: str) -> list[float] | None:
        row = self._conn.execute("SELECT dims, data FROM vectors WHERE key = ?", (key,)).fetchone()
        if row is None:
            self.misses += 1
            return None
        self.hits += 1
        dims, blob = row
        return list(struct.unpack(f"<{dims}f", blob))

    def put(self, key: str, vector: list[float]) -> None:
        blob = struct.pack(f"<{len(vector)}f", *vector)
        self._conn.execute(
            "INSERT OR REPLACE INTO vectors (key, dims, data) VALUES (?, ?, ?)",
            (key, len(vector), blob),
        )

    def commit(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        self._conn.commit()
        self._conn.close()

    @property
    def stats(self) -> dict:
        total = self.hits + self.misses
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hits / total, 4) if total else 0.0,
        }


class CachedEmbedder:

    def __init__(self, inner, cache: EmbeddingCache):
        self._inner = inner
        self._cache = cache
        self.name = inner.name
        self.dimensions = inner.dimensions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        keys = [EmbeddingCache.key(self.name, self.dimensions, t) for t in texts]
        results: list[list[float] | None] = [self._cache.get(k) for k in keys]

        pending = [i for i, v in enumerate(results) if v is None]
        if pending:
            logger.info(f"Embedding {len(pending)} new chunks ({len(texts) - len(pending)} cached)")
            fresh = self._inner.embed_documents([texts[i] for i in pending])
            for i, vector in zip(pending, fresh):
                results[i] = vector
                self._cache.put(keys[i], vector)
            self._cache.commit()

        return [v for v in results if v is not None]

    def embed_query(self, text: str) -> list[float]:
        return self._inner.embed_query(text)
