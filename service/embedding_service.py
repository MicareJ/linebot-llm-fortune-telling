import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
from dotenv import load_dotenv
from langchain_community.embeddings import HuggingFaceEmbeddings
from core.logger_config import setup_logger

# --------------------------------------------------------------------------
# 初始化設定
# --------------------------------------------------------------------------
logger = setup_logger('embedding_service')
load_dotenv()

# 從環境變數讀取模型名稱
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL")
if not EMBEDDING_MODEL:
    raise ValueError("EMBEDDING_MODEL environment variable not set.")

logger.info(f"Preparing to load local embedding model from Hugging Face: {EMBEDDING_MODEL}")

# --------------------------------------------------------------------------
# 核心：在服務啟動時，載入一次模型到記憶體中
# --------------------------------------------------------------------------
try:
    # 使用 HuggingFaceEmbeddings 在本地運行模型
    # 這是整個服務中最耗資源的部分，但只會執行一次。
    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        model_kwargs={"device": "cpu"},  # 強制使用 CPU
        encode_kwargs={
            "normalize_embeddings": True # 將向量正規化，這對相似度計算很重要
        }
    )
    logger.info("Embedding model loaded successfully into memory.")
except Exception as e:
    logger.error(f"Failed to load embedding model: {e}", exc_info=True)
    # 如果模型載入失敗，直接讓服務啟動失敗
    raise

# --------------------------------------------------------------------------
# FastAPI 應用程式設定
# --------------------------------------------------------------------------
app = FastAPI(
    title="Embedding Service API",
    description="一個將文字轉換為向量的內部微服務"
)

# 定義 API 請求的資料結構
class EmbeddingRequest(BaseModel):
    texts: List[str]

# --------------------------------------------------------------------------
# API 端點 (Endpoint)
# --------------------------------------------------------------------------
@app.post("/embed", summary="將一批文字轉換為嵌入向量")
def create_embeddings(request: EmbeddingRequest):
    """
    接收一個包含多個文字字串的列表，
    使用預先載入的模型將它們轉換為向量，然後回傳。
    """
    try:
        if not request.texts:
            raise HTTPException(status_code=400, detail="Input 'texts' list cannot be empty.")
        
        logger.info(f"Received request to embed {len(request.texts)} text segments...")
        
        # 使用模型的 embed_documents 方法進行批次處理
        vectors = embeddings.embed_documents(request.texts)
        
        logger.info(f"Successfully generated {len(vectors)} vectors.")
        return {"embeddings": vectors}

    except Exception as e:
        logger.error(f"An error occurred while processing embedding request: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

# --------------------------------------------------------------------------
# 健康檢查端點
# --------------------------------------------------------------------------
@app.get("/health", summary="服務健康狀態檢查")
def health_check():
    return {"status": "ok"}

