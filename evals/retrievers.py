import time
from typing import Protocol

from .dataset import normalize_filename


class Retriever(Protocol):
    name: str

    def search(self, query: str, k: int) -> list[tuple[str, int]]:
        """Return (filename, page) keys in rank order, best first."""
        ...


class DenseRetriever:

    """Vector search exactly as the application performs it."""
    def __init__(self, store, user, session):
        self._store = store
        self._user = user
        self._session = session
        self.name = f"dense/{store.embedder.name}"

    def search(self, query: str, k: int) -> list[tuple[str, int]]:
        hits = self._store.query_similar_context(query, self._user, self._session, top_k=k)

        seen: set[tuple[str, int]] = set()
        keys: list[tuple[str, int]] = []
        for hit in hits:
            key = (normalize_filename(hit["metadata"]["filename"]), hit["metadata"]["page"])
            if key not in seen:
                seen.add(key)
                keys.append(key)
        return keys


class TimedRetriever:
    """Wraps a retriever to record per-query latency."""

    def __init__(self, inner: Retriever):
        self._inner = inner
        self.name = inner.name
        self.last_latency_ms = 0.0

    def search(self, query: str, k: int) -> list[tuple[str, int]]:
        started = time.perf_counter()
        keys = self._inner.search(query, k)
        self.last_latency_ms = (time.perf_counter() - started) * 1000
        return keys


class HybridRetriever:
    """Full-text and vector search fused by reciprocal rank, then reranked.

    Not implemented yet - this is the next iteration
    """

    def __init__(self, *_args, **_kwargs):
        raise NotImplementedError(
            "HybridRetriever is not built yet. Run the dense baseline first - "
        )
