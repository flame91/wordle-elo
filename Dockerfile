FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY CHANGELOG.md ./
COPY src ./src

RUN pip install --no-cache-dir -e .

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

CMD ["python", "-m", "wordle_elo"]
