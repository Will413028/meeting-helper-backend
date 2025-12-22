FROM nvidia/cuda:12.8.1-cudnn-devel-ubuntu22.04

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
    wget \
    && rm -rf /var/lib/apt/lists/*

# Install cuDNN 8 libraries (required by pyannote/pytorch-lightning)
# The container has cuDNN 9 but pyannote needs cuDNN 8's libcudnn_ops_infer.so.8
RUN wget -q https://developer.download.nvidia.com/compute/cudnn/redist/cudnn/linux-x86_64/cudnn-linux-x86_64-8.9.7.29_cuda12-archive.tar.xz \
    && tar -xf cudnn-linux-x86_64-8.9.7.29_cuda12-archive.tar.xz \
    && cp cudnn-linux-x86_64-8.9.7.29_cuda12-archive/lib/*.so* /usr/lib/x86_64-linux-gnu/ \
    && ldconfig \
    && rm -rf cudnn-linux-x86_64-8.9.7.29_cuda12-archive* 

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy RTX 5090 specific pyproject.toml (uses PyTorch 2.7.1 + CUDA 12.8)
COPY pyproject.toml ./

# Copy project source files
COPY src/ ./src/
COPY alembic.ini ./
COPY alembic/ ./alembic/

# Install Python dependencies with uv (regenerate lock file for RTX 5090 deps)
RUN uv sync

# Copy patch script
COPY scripts/patch_pytorch_compat.py ./scripts/

# Patch WhisperX for PyTorch 2.x compatibility
# Fixes IndexError: tensors used as indices must be long, int, byte or bool tensors
RUN sed -i 's/tokens.clamp(min=0)/tokens.clamp(min=0).long()/g' .venv/lib/python3.12/site-packages/whisperx/alignment.py

# Patch for PyTorch 2.6+ weights_only compatibility
# PyTorch 2.6+ defaults to weights_only=True which breaks pyannote model loading
RUN .venv/bin/python scripts/patch_pytorch_compat.py

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