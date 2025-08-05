# Multi-stage Dockerfile for Hydra production deployment
FROM python:3.11-alpine AS builder

RUN apk add --no-cache gcc musl-dev libffi-dev postgresql-dev

WORKDIR /build

COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.11-alpine AS runtime

RUN apk add --no-cache postgresql-libs && \
    addgroup -g 1001 hydra && \
    adduser -D -u 1001 -G hydra hydra

WORKDIR /app

COPY --from=builder /root/.local /home/hydra/.local
COPY --chown=hydra:hydra src/ ./src/
COPY --chown=hydra:hydra config/ ./config/
COPY --chown=hydra:hydra alembic.ini ./
COPY --chown=hydra:hydra migrations/ ./migrations/

USER hydra

ENV PATH=/home/hydra/.local/bin:$PATH
ENV PYTHONPATH=/app/src

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')"

CMD ["uvicorn", "hydra.api.service:app", "--host", "0.0.0.0", "--port", "8000"]