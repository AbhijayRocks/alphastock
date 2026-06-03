FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies (needed for compiling some C extensions, although slim might have most)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend codebase
COPY . .

# Expose port (Render sets this dynamically, default to 9000 as fallback)
EXPOSE 9000

# Start the FastAPI application
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-9000}"]
