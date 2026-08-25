FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app.py .
COPY scripts/ scripts/
COPY static/ static/
COPY config/ config/

# Expose server port
EXPOSE 8080

# Environment defaults
ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV DATA_DIR=/data

RUN mkdir -p /data

# Command to run FastAPI server
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
