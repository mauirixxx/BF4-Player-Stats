FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml ./
COPY bf4ps ./bf4ps
RUN pip install --no-cache-dir .
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
COPY scripts/bf4ps_production_collector.py ./scripts/bf4ps_production_collector.py
USER 65532:65532
CMD ["python", "-m", "bf4ps.discovery_service"]
