# API image: FastAPI + the pipeline + ffmpeg. Built from the repo root
# (docker-compose.yml sets `context: .`) because the dashboard's classifier
# table reads eval/results/*.json, which lives outside backend/ (D-73).
FROM python:3.12-slim

# ffmpeg: the assemble stage calls it for loudnorm and the MP3 encode.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "uv==0.8.17"

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app/backend

# Dependencies first, so a code change doesn't reinstall them.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ ./
RUN uv sync --frozen --no-dev
COPY eval/results/*.json /app/eval/results/

# Strip CRLF in case the checkout has Windows line endings: a "#!/bin/sh\r"
# shebang fails with "no such file or directory". No-op on an LF file.
RUN sed -i 's/\r$//' docker/entrypoint.sh && chmod +x docker/entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["docker/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
