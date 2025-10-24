# Coin Quant R11 - Dockerfile
# Multi-stage build for production deployment

# Build stage
FROM python:3.11-slim as builder

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY pyproject.toml .
COPY setup.py .

# Install package
RUN pip install -e .

# Production stage
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy installed packages from builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy source code
COPY src/ ./src/
COPY pyproject.toml .
COPY setup.py .
COPY launch.py .
COPY validate.py .

# Create data directory
RUN mkdir -p shared_data/health shared_data/memory shared_data/logs

# Set environment variables
ENV PYTHONPATH=/app/src
ENV COIN_QUANT_DATA_DIR=/app/shared_data

# Expose ports (if needed for web interface)
EXPOSE 8501

# Default command
CMD ["python", "validate.py"]
