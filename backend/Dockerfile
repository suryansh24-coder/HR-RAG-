# syntax=docker/dockerfile:1
#
# HR Nexus API image.
#
# Two stages: the builder compiles the wheels, the runtime installs them into a
# slim image. PyMuPDF and sentence-transformers pull in compiled extensions, so
# building outside the final layer is what keeps the runtime image small.
#
# Note on the embedding model: the first request to load
# BAAI/bge-small-en-v1.5 (~130 MB) downloads it into HF_HOME. That path belongs to
# the unprivileged `nexus` user, not root, so mount a volume at
# /home/nexus/.cache/huggingface (see docker-compose.yml) and a restart does not
# pay the download again. For an air-gapped build, pre-download the model in the
# builder and copy it into the image instead.

FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /wheels
COPY requirements.txt .
RUN pip wheel --wheel-dir /wheels -r requirements.txt


FROM python:3.12-slim AS runtime

# Every path the app writes to is pinned inside the /app/data volume. They cannot
# be left to the code defaults: those are derived from the project root, which is
# "/" in this image, so the embedded Qdrant store would land in /data/qdrant —
# outside the mounted volume, and unwritable by the unprivileged `nexus` user.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/home/nexus/.cache/huggingface \
    DATA_DIR=/app/data/documents \
    QDRANT_PATH=/app/data/qdrant \
    DATABASE_URL=sqlite:////app/data/hr_nexus.db

# libgomp1 is required by the PyTorch wheels that sentence-transformers installs.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels requirements.txt

# Run unprivileged: the app only ever writes inside /app/data and its own cache.
RUN useradd --create-home --uid 10001 nexus \
    && mkdir -p /app/data/documents \
    && chown -R nexus:nexus /app
USER nexus

WORKDIR /app
COPY --chown=nexus:nexus app ./app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
