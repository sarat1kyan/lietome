# Lightman CPU image with the web UI.
# Compose (recommended): docker compose up --build    -> project "lightman" in Docker Desktop
# Build:   docker build -t lightman:latest .
# Analyze: docker run --rm -v "$PWD:/work" lightman analyze /work/video.mp4 -o /work/output
# UI:      docker run --rm -p 127.0.0.1:8710:8710 -v lightman-output:/work/output lightman serve --host 0.0.0.0 --no-tls -o /work/output
FROM node:24-slim AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npx vite build --outDir /ui/out --emptyOutDir

FROM python:3.12-slim-bookworm AS base

LABEL org.opencontainers.image.title="lightman" \
      org.opencontainers.image.description="Lightman: local behavioral analysis workstation (face, voice, body against a personal baseline)" \
      org.opencontainers.image.source="https://github.com/sarat1kyan/lietome" \
      org.opencontainers.image.url="https://github.com/sarat1kyan/lietome" \
      org.opencontainers.image.licenses="Apache-2.0" \
      dev.lightman.project="lightman"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    LIGHTMAN_MODEL_DIR=/models

# libGL/glib are needed by opencv (pulled in by mediapipe); nothing else at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
COPY --from=ui /ui/out ./src/lightman/api/static
RUN uv sync --frozen --no-dev --no-editable

# Pre-fetch the face model so the image works offline. AU models (48-143 MB) are fetched on
# first use, or mount a populated cache at /models.
RUN /app/.venv/bin/lightman models download mediapipe/face_landmarker

RUN useradd --create-home --uid 1000 lightman && mkdir -p /work/output \
    && chown -R lightman /models /work
USER lightman
WORKDIR /work
EXPOSE 8710
ENTRYPOINT ["/app/.venv/bin/lightman"]
CMD ["--help"]
