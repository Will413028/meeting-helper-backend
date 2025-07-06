FROM python:3.13-slim

# 設置工作目錄
WORKDIR /app

# 安裝系統依賴
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# 安裝 uv
RUN pip install uv

# 複製項目文件
COPY pyproject.toml uv.lock ./
COPY src/ ./src/
COPY alembic.ini ./
COPY alembic/ ./alembic/

# 安裝 Python 依賴
RUN uv sync --frozen

# 創建必要的目錄
RUN mkdir -p uploads

# 暴露端口
EXPOSE 8000

# 運行應用
CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]