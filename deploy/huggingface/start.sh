#!/bin/sh
# Ollama first: the API embeds every question through it, so it must answer
# before the first request does.
ollama serve > /tmp/ollama.log 2>&1 &
for i in $(seq 1 60); do
    curl -sf http://127.0.0.1:11434/api/tags > /dev/null && break
    sleep 1
done

alembic upgrade head
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-7860}"
