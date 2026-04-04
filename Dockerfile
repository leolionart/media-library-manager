FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=9988 \
    STATE_FILE=/app/data/app-state.json

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends iproute2 net-tools smbclient \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md /app/
COPY src /app/src

RUN pip install --no-cache-dir .

EXPOSE 9988

CMD ["sh", "-c", "python -m media_library_manager.cli serve --host \"$HOST\" --port \"$PORT\" --state-file \"$STATE_FILE\""]
