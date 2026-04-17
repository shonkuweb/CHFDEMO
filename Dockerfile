# ── Build Stage ──────────────────────────────────────────────
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all site files
COPY . .

# Ensure the images directory exists for the logo
RUN mkdir -p assets/images

# Expose both ports
EXPOSE 8000
EXPOSE 8001

# Default: start the main site server
# (Use docker-compose to run both services simultaneously)
CMD ["python3", "server.py"]
