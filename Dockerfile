FROM python:3.11-slim

WORKDIR /app

# Install system dependencies needed for some Python wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install dependencies using pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files (ignoring based on .dockerignore)
COPY . .

# Runtime setup
RUN useradd -m -u 10001 appuser \
    && mkdir -p /app/data/uploads \
    && chown -R appuser:appuser /app

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Expose Uvicorn default port
EXPOSE 8000

USER appuser

# Start FastAPI application
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
