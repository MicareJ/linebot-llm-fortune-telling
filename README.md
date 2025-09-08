# 🧠 Fortune Telling RAG System with LINE Bot

這是一個具備姓名學和八字五行分析能力的聊天機器人，結合：

- ✅ **LangChain + Huggingface**：處理五行與姓名學分析
- ✅ **Google Drive 文件嵌入**：建立私有知識庫（使用 Google Service Account）
- ✅ **Chroma 向量資料庫**：用於 RAG 檢索
- ✅ **LINE Bot 介接**：讓使用者從 LINE 傳送訊息互動

---

## 📁 專案結構

```
📦your-project/
├── embedding.py               # 建立與載入向量資料庫
├── rag.py                     # 使用 LLM 結合知識庫進行回答
├── app.py                     # Flask + LINE Webhook 接口
├── Dockerfile                 # Docker 建構設定
├── docker-compose.yml         # Compose 編排 (可選)
├── railway.json               # Railway 雲端部署設定
├── .env                       # 環境變數 (含 base64 service account)
├── pyproject.toml             # uv 套件管理設定
├── fortunetell_chroma__db/    # Chroma 向量資料庫 (可忽略追蹤)
```

---

## ⚙️ 安裝與啟動（使用 Docker）

### 1️⃣ 編輯 `.env`：

```env
FOLDER_ID=你的GoogleDrive資料夾ID
LINE_CHANNEL_ACCESS_TOKEN=你的Line Bot Access Token
LINE_CHANNEL_SECRET=你的Line Channel Secret
GDRIVE_SERVICE_ACCOUNT_B64=（將你的 service_account.json 轉 base64 放這）
```

👉 產生 base64：
```bash
base64 service_account.json > encoded.txt
```


### 2️⃣ 使用 Docker 啟動（本地）

```bash
docker-compose up --build
```

---

## 📄 使用說明

傳送訊息至你的 LINE Bot，例如：
```
1991年8月20日早上9點，姓名：陳美麗
```
即會收到完整的：
- 八字與五行分佈
- 姓名筆劃與吉凶分析
- 補五行、改名建議

---

## ☁️ Railway 部署（可選）

1. 推專案至 GitHub
2. Railway 新建專案 ➝ 選擇 GitHub Repo
3. 環境變數設定與 `.env` 相同
4. 自動部署完成

---

## 📦 使用的依賴（由 `uv` 管理）

見 `pyproject.toml`：
```toml
[project]
dependencies = [
  "flask",
  "line-bot-sdk",
  "langchain",
  "langchain_community",
  "langchain_ollama",
  "langchain_chroma",
  "python-dotenv"
]
```

---

## 🙌 聯絡與協助

有問題歡迎開 Issue 或聯絡開發者。

```
Sonny Huang
email: partlysunny31@pm.me
```