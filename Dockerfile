FROM python:3.12-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml uv.lock ./

ENV UV_PROJECT_ENVIRONMENT=/opt/venv
RUN pip install --upgrade pip \
    && pip install --no-cache-dir uv \
    && uv sync --frozen --no-install-project

FROM python:3.12-slim AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

COPY --from=builder /opt/venv /opt/venv
COPY app ./app
COPY pyproject.toml ./pyproject.toml

CMD ["python", "-m", "app.main"]
