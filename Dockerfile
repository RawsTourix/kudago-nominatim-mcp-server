# syntax=docker/dockerfile:1.7

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN addgroup --system app \
    && adduser --system --ingroup app --home /app app

# Install dependencies before copying the complete source tree so ordinary
# source changes can reuse this layer.
COPY pyproject.toml README.md ./
COPY app/__init__.py ./app/__init__.py
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install .

COPY --chown=app:app app ./app
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app alembic.ini mcp_server.py ./

USER app

EXPOSE 8011

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8011"]
