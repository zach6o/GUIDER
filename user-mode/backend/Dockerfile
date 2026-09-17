FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim@sha256:531f855bda2c73cd6ef67d56b733b357cea384185b3022bd09f05e002cd144ca AS runtime
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
RUN useradd --uid 10001 --create-home guider && mkdir -p /data/media && chown -R guider /data
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 GUIDE_STORAGE_PATH=/data/media
USER guider
EXPOSE 8000
CMD ["sh", "-c", "python -m alembic upgrade head && exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log"]

FROM runtime AS checks
USER root
RUN uv sync --locked
COPY tests ./tests
COPY scripts ./scripts
USER guider
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]

FROM runtime AS app
