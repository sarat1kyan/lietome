# Lightman CPU image with the web UI.
# Build: docker build -t lightman .
# Analyze: docker run --rm -v "$PWD:/work" lightman analyze /work/video.mp4 -o /work/output
# UI:      docker run --rm -p 8710:8710 -v "$PWD/output:/work/output" lightman serve --host 0.0.0.0 -o /work/output
FROM node:24-slim AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npx vite build --outDir /ui/out --emptyOutDir

FROM python:3.12-slim-bookworm AS base

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

RUN useradd --create-home --uid 1000 lightman && chown -R lightman /models
USER lightman
WORKDIR /work
EXPOSE 8710
ENTRYPOINT ["/app/.venv/bin/lightman"]
CMD ["--help"]
