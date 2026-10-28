FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src/ src/
RUN pip install --no-cache-dir ".[hosted]"

VOLUME /data
EXPOSE 8000
CMD ["swapgate", "serve", "--port", "8000", "--history", "/data/runs.db"]
