FROM nvidia/cuda:12.1.0-cudnn8-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

# Set CUDA environment variables
ENV CUDA_HOME=/usr/local/cuda
ENV PATH=${CUDA_HOME}/bin:${PATH}
ENV LD_LIBRARY_PATH=${CUDA_HOME}/lib64:${LD_LIBRARY_PATH}

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    curl \
    build-essential \
    cmake \
    pkg-config \
    python3-pip \
    python3-venv \
    python3-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy project files
COPY pyproject.toml uv.lock ./
COPY src/ ./src/
COPY alembic.ini ./
COPY alembic/ ./alembic/

# Install Python dependencies with uv
RUN uv sync --frozen

# Patch WhisperX for PyTorch 2.x compatibility
# Fixes IndexError: tensors used as indices must be long, int, byte or bool tensors
RUN sed -i 's/tokens.clamp(min=0)/tokens.clamp(min=0).long()/g' .venv/lib/python3.12/site-packages/whisperx/alignment.py

# Create necessary directories
RUN mkdir -p uploads logs

# Expose port
EXPOSE 8000

# Make sure we use the virtualenv
ENV PATH="/app/.venv/bin:$PATH"

# Copy certificates
COPY certs/ ./certs/

# Run the application directly to avoid uv run resetting dependencies
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--ssl-keyfile", "certs/key.pem", "--ssl-certfile", "certs/cert.pem", "--no-access-log"]