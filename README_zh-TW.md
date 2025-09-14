<p align="right"><a href="./README.md">English</a> | 中文</p>

# 算命Line Bot

這是一個以LINE Bot為介面的RAG AI機器人。它具有獨特且幽默的個性，能根據使用者輸入提供有洞見的分析。系統整合檢索增強生成（RAG）、安全的會話管理與獨立背景服務，示範如何打造現代、安全且模組化的 AI 應用。

## 核心功能

- 有趣的 AI 個性：精心設計的系統提示讓 AI 具有風趣幽默的個性，提升互動體驗與記憶點。

- RAG 知識庫檢索：結合 LangChain 與 ChromaDB，從 Google Drive 私有知識庫擷取資訊，確保回應具脈絡且精準。

- 安全會話管理：採用 Envelope Encryption（信封加密）與 Redis 管理使用者會話，絕對保護使用者個人資料安全。縱使資料庫外洩，敏感資訊仍受保護且不可存取。

- 模組化架構：將日誌、會話管理等核心功能抽象為 core 模組，讓主程式更乾淨、可維護。

- LINE Bot 整合：以 Flask Webhook 無縫串接 LINE Messaging API，提供即時流暢的聊天體驗。

## 專案架構

採用模組化設計，將關注點分離到不同套件與模組，以提升延展性與維護性。

```text
your-project/
├── core/
│   ├── __init__.py
│   ├── logger_config.py      # 共用日誌設定（輸出至 logs/ 目錄）
│   └── session_manager.py    # 處理會話加密與 Redis 存取
│
├── util/
│   ├── __init__.py
│   ├── rag.py       # RAG 核心邏輯（模型、檢索器與提示模板）
│   ├── embedding.py   # Google Drive 同步與嵌入的獨立服務
│   ├── name_fivegrid_wuxing.py # 五格數理工具
│   ├── bazi_true_solar.py      # 八字命盤工具
│   └── stroke_lookup.py   # 姓名筆畫查詢工具
│
├── app.py         # 主應用：Flask + LINE Webhook 端點
├── data/      # 常用字政府筆畫資料
├── logs/                     # 日誌輸出目錄
├── .env                      # 環境變數設定
├── uv.lock                   # Python 相依管理（uv）
└── pyproject.toml            # Python 相依管理（uv）
```

## 若你也想照這個架構創建一個屬於自己的Bot，從這裡開始

### 1. 事先要求

安裝 [uv]：本專案使用 uv 作為 Python 套件管理工具。(也可以依照你的使用習慣管理套件，依賴請參考pyproject.toml)

```bash
pip install uv
```

安裝相依套件：

```bash
uv sync
```

設定 Google 服務帳號：

前往 Google Cloud Console 建立服務帳號。

為你的專案啟用 Google Drive API。

下載服務帳號的 JSON 金鑰並存為專案根目錄的 service_account.json。

將存放知識庫文件的 Google Drive 資料夾分享給該服務帳號的 Email。

### 2. 環境設定

在專案根目錄建立 .env 檔並填入以下變數：

```env
# --- LINE Bot Configuration ---
LINE_CHANNEL_ACCESS_TOKEN="Your Line Bot Access Token"
LINE_CHANNEL_SECRET="Your Line Channel Secret"

# --- Google & RAG Configuration ---
FOLDER_ID="Your Google Drive Folder ID"
GOOGLE_API_KEY="Your Google Maps API Key (for geolocation and timezone)"
EMBEDDING_MODEL="You can try your embedding model" # Recommended Chinese Embedding Model
MODEL_REPO_ID="You can try your model on Huggingface" # Selected Hugging Face Model

# --- Redis Configuration ---
REDIS_URL="redis://localhost:6379/0" # Redis connection URL (DB can be specified)

# --- Security Configuration ---
MASTER_ENCRYPTION_KEY="A Base64-encoded 32-byte key goes here"
```

如何產生 MASTER_ENCRYPTION_KEY？

使用以下指令生成隨機金鑰：

```powershell
# Windows (PowerShell)
[Convert]::ToBase64String((Get-Random -Count 32 -AsBytes))
```

```bash
# Linux / macOS
openssl rand -base64 32
```

### 3. 執行服務

你需要在四個不同的終端機視窗中啟動四個服務。

終端機 1：啟動 LINE Bot 應用

```bash
uv run app.py
```

終端機 2：啟動 Google Drive 同步與嵌入服務

```bash
uv run embedding.py
```

終端機 3：啟動 Redis 服務

```bash
redis-server.exe
```

終端機 4：啟動 ngrok 網域服務

```bash
ngrok http http://localhost:5000
```

並將該端點 URL 貼到你的 LINE 帳號 Messaging API，記得在最後加上 /callback。

## 使用說明

服務啟動後，你可以直接透過 LINE 與機器人互動。

傳送 Start 以開始對話流程。

依照訊息提示提供必要資訊（例如姓名、生日）。

完成資料蒐集後即可提問，並使用 RAG 知識庫。

隨時傳送 Cancel 以清除會話並結束對話。

## 🙌 聯絡與支援

若有任何問題，請在儲存庫開 issue 或聯絡開發者。

Sonny Huang
<partlysunny31@pm.me>

Zack Yang
<zackaryyang2001@gmail.com>