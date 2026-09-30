# The Hugging Face Space: frontend, API and embedding model in one container.
# Built from the repository deploy/huggingface/push.sh assembles, where backend/,
# frontend/ and this directory's files sit at the root.

# Node 24 ships npm 11, which reads the lock the way it was written.
FROM node:24-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OLLAMA_MODELS=/opt/ollama/models \
    OLLAMA_HOST=127.0.0.1:11434

RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-eng poppler-utils curl ca-certificates zstd \
    && rm -rf /var/lib/apt/lists/*

# Ollama embeds questions with nomic-embed-text, the model the retrieval numbers
# were measured with. Both are pinned, like the Python lock, so a rebuild cannot
# swap the embedder underneath the measurements. The Space has no GPU, so drop
# the GPU libraries Ollama ships.
RUN curl -fsSL https://ollama.com/install.sh | OLLAMA_VERSION=0.34.4 sh \
    && rm -rf /usr/local/lib/ollama/cuda_* /usr/local/lib/ollama/rocm*

# Pull the model at build time, so a cold start does not download it. v1.5 is
# the weights `latest` pointed at when measured (layer 970aa74c0a90); copied to
# the bare name, which is what the chunks in the database are tagged with.
RUN ollama serve > /dev/null 2>&1 & \
    for i in $(seq 1 30); do curl -sf http://127.0.0.1:11434/api/tags > /dev/null && break; sleep 1; done; \
    ollama pull nomic-embed-text:v1.5 && ollama cp nomic-embed-text:v1.5 nomic-embed-text

WORKDIR /app
COPY backend/requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

COPY backend/ .
COPY --from=frontend /frontend/dist /app/static
COPY start.sh /app/start.sh

# Spaces run the container as uid 1000.
RUN useradd -m -u 1000 user && mkdir -p /app/uploads /app/db && chown -R user /app /opt/ollama
USER user

ENV STATIC_DIR=/app/static \
    PORT=7860
EXPOSE 7860
CMD ["sh", "/app/start.sh"]
