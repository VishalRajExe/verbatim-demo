# syntax=docker/dockerfile:1
#
# Legal Contract Intelligence — backend image.
# Build context is the `backend/` directory:
#   docker build -f backend/Dockerfile backend -t lci-backend
# Run migrations happen automatically on startup (FastAPI lifespan), so no
# separate migrate step is required. The server binds to 0.0.0.0 and honours
# the platform-injected $PORT (Render/Fly/Railway) defaulting to 8000.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first so this layer is cached independently of code.
# All pinned packages (PyMuPDF, cryptography, lxml, SQLAlchemy/PyMySQL) ship
# prebuilt manylinux wheels, so no compiler toolchain is needed here.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Application code and migrations.
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app

# Writable location for uploads / generated redlines. For real deployments
# mount a persistent volume here (see DEPLOYMENT.md) or point STORAGE_DIR at it.
ENV STORAGE_DIR=/app/data \
    PORT=8000
RUN mkdir -p /app/data

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
