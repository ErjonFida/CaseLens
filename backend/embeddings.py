import ollama
import logging
import os
from typing import Protocol

logger = logging.getLogger("embeddings")


class EmbeddingProvider(Protocol):

    name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        ...

    def embed_query(self, text: str) -> list[float]:
        ...


class OllamaEmbedder:

    def __init__(self, model: str = "nomic-embed-text", dimensions: int = 768, batch_size: int = 32):
        self.name = model
        self.dimensions = dimensions
        self.batch_size = batch_size

    def _embed(self, inputs: list[str]) -> list[list[float]]:
        

        all_vectors: list[list[float]] = []
        total_batches = (len(inputs) + self.batch_size - 1) // self.batch_size
        for i in range(0, len(inputs), self.batch_size):
            batch = inputs[i:i + self.batch_size]
            if total_batches > 1:
                logger.info(f"Embedding batch {i // self.batch_size + 1}/{total_batches} ({len(batch)} items)")
            try:
                response = ollama.embed(model=self.name, input=batch, dimensions=self.dimensions)
            except Exception as e:
                logger.error(f"Ollama embedding failed for model '{self.name}': {e}")
                raise
            all_vectors.extend(response.embeddings)

        if all_vectors and len(all_vectors[0]) != self.dimensions:
            raise ValueError(
                f"'{self.name}' returned {len(all_vectors[0])} dimensions, but the database "
                f"column expects {self.dimensions}. Update EMBEDDING_DIMENSIONS and migrate "
                f"the document_chunks.embedding column before indexing."
            )
        return all_vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed([f"search_document: {t}" for t in texts])

    def embed_query(self, text: str) -> list[float]:
        return self._embed([f"search_query: {text}"])[0]


class GeminiEmbedder:

    def __init__(self, model: str = "models/gemini-embedding-001", dimensions: int = 768, batch_size: int = 20):
        self.name = model.split("/")[-1]
        self.dimensions = dimensions
        self.batch_size = batch_size
        self._model = model

        import google.generativeai as genai

        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key:
            genai.configure(api_key=api_key)
        else:
            logger.warning("GEMINI_API_KEY is not set; Gemini embedding calls will fail")

    @staticmethod
    def _normalize(vector: list[float]) -> list[float]:
        norm = sum(x * x for x in vector) ** 0.5
        if norm == 0:
            return vector
        return [x / norm for x in vector]

    def _embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        import google.generativeai as genai

        all_vectors: list[list[float]] = []
        total_batches = (len(texts) + self.batch_size - 1) // self.batch_size
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            if total_batches > 1:
                logger.info(f"Embedding batch {i // self.batch_size + 1}/{total_batches} ({len(batch)} items)")
            try:
                response = genai.embed_content(
                    model=self._model,
                    content=batch,
                    task_type=task_type,
                    output_dimensionality=self.dimensions,
                )
            except Exception as e:
                logger.error(f"Gemini embedding failed: {e}")
                raise
            all_vectors.extend(response["embedding"])

        return [self._normalize(v) for v in all_vectors]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, task_type="retrieval_document")

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], task_type="retrieval_query")[0]


def get_embedder() -> EmbeddingProvider:
    from config import settings

    provider = settings.EMBEDDING_PROVIDER.lower()

    if provider == "ollama":
        embedder = OllamaEmbedder(
            model=settings.EMBEDDING_MODEL,
            dimensions=settings.EMBEDDING_DIMENSIONS,
        )
    elif provider == "gemini":
        embedder = GeminiEmbedder(dimensions=settings.EMBEDDING_DIMENSIONS)
    else:
        raise ValueError(
            f"Unknown EMBEDDING_PROVIDER '{settings.EMBEDDING_PROVIDER}'. Expected 'ollama' or 'gemini'."
        )

    logger.info(f"Embedding provider: {provider} / {embedder.name} ({embedder.dimensions} dims)")
    return embedder
