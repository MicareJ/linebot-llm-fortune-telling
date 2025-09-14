# --- 第一階段：建置環境 (Builder Stage) ---
# 使用一個包含完整編譯工具的基礎鏡像來安裝依賴
# 明確指定 Debian 版本 (bookworm)，增加可預測性
FROM python:3.11-slim-bookworm as builder

# 設定環境變數
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    POETRY_NO_INTERACTION=1

# 安裝 uv，一個極速的 Python 套件安裝器
RUN pip install uv

# 將依賴定義檔複製到建置環境中
WORKDIR /app
COPY pyproject.toml uv.lock ./

# 使用 uv 安裝所有依賴到一個獨立的虛擬環境中
RUN uv venv /opt/venv && \
    . /opt/venv/bin/activate && \
    uv pip install --no-cache-dir -r requirements.txt


# --- 第二階段：正式環境 (Final Stage) ---
# 使用同一個輕量級的基礎鏡像來運行應用
FROM python:3.11-slim-bookworm

# 【安全強化】: 更新作業系統套件並安裝 supervisor
# 這一步是修復漏洞的關鍵
RUN apt-get update && \
    apt-get install -y --no-install-recommends supervisor && \
    apt-get upgrade -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 設定非 root 使用者，增加安全性
# 將工作目錄的擁有者也指定給 appuser
WORKDIR /home/appuser/app
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /home/appuser

# 切換到非 root 使用者
USER appuser

# 從建置環境中，只複製包含已安裝套件的虛擬環境
COPY --chown=appuser:appuser --from=builder /opt/venv /opt/venv

# 將應用程式碼複製到正式環境中
COPY --chown=appuser:appuser . .

# 複製 supervisor 設定檔和啟動腳本
COPY --chown=appuser:appuser supervisord.conf start.sh ./
RUN chmod +x ./start.sh

# 設定 PATH，讓 shell 可以直接找到虛擬環境中的執行檔
ENV PATH="/opt/venv/bin:$PATH"

# 開放 LINE Bot 服務的端口
EXPOSE 8080

# 設定容器的進入點
ENTRYPOINT ["./start.sh"]

