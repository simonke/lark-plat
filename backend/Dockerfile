FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY docker-entrypoint.sh ./docker-entrypoint.sh
RUN chmod +x ./docker-entrypoint.sh

RUN pip install --upgrade pip && pip install .

EXPOSE 8000

# Single authoritative uvicorn startup (docker-entrypoint.sh); compose deploys
# reuse the same CMD instead of re-declaring the uvicorn command line.
CMD ["sh", "./docker-entrypoint.sh"]
