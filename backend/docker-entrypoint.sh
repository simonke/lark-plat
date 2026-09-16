#!/bin/sh
# lark-plat backend single entrypoint (dual-uvicorn convergence).
#
# Sole authoritative uvicorn startup definition - the Dockerfile CMD and the
# compose `backend` service command both delegate here, so there is exactly one
# `uvicorn app.main:app ...` invocation (no forklift copy to drift).
#
#   BACKEND_PORT    host/port to bind (default 8000)
#   UVICORN_WORKERS worker count (single instance, architecture §2/§4; default 2)
set -e

alembic upgrade head

exec uvicorn app.main:app --host 0.0.0.0 --port "${BACKEND_PORT:-8000}" --workers "${UVICORN_WORKERS:-2}"