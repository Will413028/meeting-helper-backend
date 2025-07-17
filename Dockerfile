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

# Install WhisperX and its dependencies separately
# Install torch with CUDA support first - using 2.2.0 for better compatibility
RUN uv pip install torch==2.2.0 torchvision==0.17.0 torchaudio==2.2.0 --index-url https://download.pytorch.org/whl/cu121

# Install transformers and other dependencies needed for WhisperX diarization
RUN uv pip install transformers==4.36.0 pyannote.audio==3.1.1

# Then install WhisperX
RUN uv pip install whisperx

# Create necessary directories
RUN mkdir -p uploads

# Expose port
EXPOSE 8000

# Run the application
CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]