# syntax=docker/dockerfile:1
FROM python:3.11-slim-bookworm

# Set environment variables for production
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PORT=5000 \
    FLASK_ENV=production

# Install essential system build dependencies for dlib, OpenCV, and OpenBLAS
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    libopenblas-dev \
    liblapack-dev \
    libx11-dev \
    libgtk-3-dev \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Upgrade pip and install CPU-optimized PyTorch first (avoids multi-gigabyte CUDA bloat)
RUN pip install --no-cache-dir --upgrade pip setuptools<82 wheel && \
    pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir gunicorn

# Copy project files
COPY . .

# Create directory structure for uploads, instance, and posters
RUN mkdir -p instance/case_storage uploads static/generated_faces static/generated_posters static/generated_variations

EXPOSE 5000

# Initialize tables if database is reachable, then launch production WSGI server (optimized for 512MB RAM)
CMD ["sh", "-c", "flask init-db || true; exec gunicorn --bind 0.0.0.0:${PORT:-5000} --workers ${GUNICORN_WORKERS:-1} --threads ${GUNICORN_THREADS:-2} --timeout 120 app:app"]
