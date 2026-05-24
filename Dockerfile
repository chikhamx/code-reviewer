FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"

COPY src/ src/
COPY config/ config/

RUN mkdir -p /app/data

ENV PYTHONUNBUFFERED=1
ENV CR_REDIS_URL=redis://redis:6379/0
ENV CR_DATABASE_URL=sqlite+aiosqlite:///app/data/cr_agent.db

EXPOSE 8000

CMD ["uvicorn", "code_review_agent.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
