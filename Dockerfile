FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLIGHTPULSE_DATA_DIR=/app/data

RUN apt-get update \
    && apt-get install -y --no-install-recommends openjdk-17-jre-headless \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt pyproject.toml ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/pip python -m pip install -r requirements.txt
COPY . .

ENTRYPOINT ["python", "-m", "flightpulse.cli"]
CMD ["--help"]
