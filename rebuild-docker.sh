#!/bin/bash

echo "=== Rebuilding Docker container with CUDA fix ==="

# Stop existing containers
echo "Stopping existing containers..."
docker-compose down

# Remove old image to force rebuild
echo "Removing old backend image..."
docker rmi $(docker images -q 'meeting-helper-backend*') 2>/dev/null || true

# Build the backend image
echo "Building new backend image..."
docker-compose build saywe_backend

# Start all services
echo "Starting services..."
docker-compose up -d

# Wait for services to start
echo "Waiting for services to start..."
sleep 10

# Check if backend is running
echo "Checking backend status..."
docker-compose ps saywe_backend

# Show logs
echo "Showing backend logs (last 50 lines)..."
docker-compose logs --tail=50 saywe_backend

# Test GPU access
echo ""
echo "=== Testing GPU access ==="
echo "Checking NVIDIA-SMI in container..."
docker exec saywe_backend nvidia-smi

echo ""
echo "Testing PyTorch CUDA availability..."
docker exec saywe_backend python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}'); print(f'CUDA device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else None}')"

echo ""
echo "=== Rebuild complete ==="
echo "To monitor logs: docker-compose logs -f saywe_backend"
echo "To test WhisperX: Upload an audio file through the API"