# 使用 Python 3.10 為基底映像
FROM python:3.12-slim

# 設定環境變數
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 安裝必要工具與 uv
RUN apt-get update && apt-get install -y git curl && rm -rf /var/lib/apt/lists/*
RUN pip install uv

# 建立工作目錄
WORKDIR /app

# 複製專案到容器
COPY . /app

# 安裝 Python 套件（使用 uv 的 pyproject.toml）
RUN uv pip install -r <(uv pip compile pyproject.toml)

# 暴露預設 Flask Port（Railway 用）
EXPOSE 5000

# 執行應用
CMD ["python", "app.py"]
