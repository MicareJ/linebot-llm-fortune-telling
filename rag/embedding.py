import os
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from dotenv import load_dotenv
from redis import Redis
from tenacity import retry, stop_after_attempt, wait_fixed
from langchain_google_community import GoogleDriveLoader
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain.text_splitter import RecursiveCharacterTextSplitter
import schedule

# 設定日誌
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

MODEL = os.getenv("RAG_MODEL", "cwchang/llama3-taide-lx-8b-chat-alpha1:q3_k_s")
CHROMA_PATH = os.getenv("CHROMA_PATH", "./fortunetell_chroma__db")
SERVICE_ACCOUNT_PATH = os.getenv("SERVICE_ACCOUNT_PATH", "service_account.json")
FOLDER_ID = os.getenv("FOLDER_ID")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
SYNC_INTERVAL_SECONDS = int(os.getenv("SYNC_INTERVAL_SECONDS", "86400")) 

# 初始化 Redis
redis_client = Redis.from_url(REDIS_URL, decode_responses=True)
EMBEDDED_KEY = "embedded_file_ids"
LAST_SYNC_KEY = "last_sync_time"
SYNC_STATUS_KEY = "sync_status"

# 全局 db
embeddings = OllamaEmbeddings(model=MODEL)
db = Chroma(
    collection_name="fortunetelling_rag_db",
    embedding_function=embeddings,
    persist_directory=CHROMA_PATH,
)

def load_embedded_record():
    """從 Redis 載入已嵌入 ID set"""
    return set(redis_client.smembers(EMBEDDED_KEY))

def save_embedded_record(new_ids: set):
    """新增 ID 到 Redis set"""
    if new_ids:
        redis_client.sadd(EMBEDDED_KEY, *new_ids)
        logger.info(f"Added {len(new_ids)} IDs to embedded record")

def clean_obsolete_embeddings(current_ids: set):
    """刪除已移除的文件嵌入"""
    embedded_ids = load_embedded_record()
    obsolete = embedded_ids - current_ids
    if obsolete:
        for file_id in obsolete:
            results = db.get(where={"id": file_id})
            if results:
                db.delete(results["ids"])
                redis_client.srem(EMBEDDED_KEY, file_id)
                logger.info(f"Removed obsolete embedding for ID: {file_id}")

@retry(stop=stop_after_attempt(3), wait=wait_fixed(300))  # 重試 3 次，間隔 5 分鐘
def sync_drive_embeddings():
    logger.info("🔄 開始同步 Google Drive 文件...")
    try:
        redis_client.set(LAST_SYNC_KEY, int(time.time()))  # 記錄開始時間
        redis_client.set(SYNC_STATUS_KEY, "running")

        embedded_ids = load_embedded_record()

        loader = GoogleDriveLoader.from_service_account_file(
            service_account_path=SERVICE_ACCOUNT_PATH,
            folder_id=FOLDER_ID,
            recursive=False,
        )
        docs = loader.load()

        current_ids = {doc.metadata.get("id") for doc in docs}
        clean_obsolete_embeddings(current_ids)

        new_docs = [doc for doc in docs if doc.metadata.get("id") not in embedded_ids]
        logger.info(f"✅ 新增文件數量：{len(new_docs)}")

        if not new_docs:
            logger.info("✅ 無需更新，所有文件已嵌入過。")
            redis_client.set(SYNC_STATUS_KEY, "success")
            return

        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        split_docs = splitter.split_documents(new_docs)

        def embed_chunk(chunk):
            uuids = [str(uuid4()) for _ in chunk]
            db.add_documents(chunk, ids=uuids)

        with ThreadPoolExecutor(max_workers=2) as executor:  # Fly.io 資源限制，降為 2 執行緒
            chunk_size = max(1, len(split_docs) // 2)
            chunks = [split_docs[i:i + chunk_size] for i in range(0, len(split_docs), chunk_size)]
            executor.map(embed_chunk, chunks)

        logger.info(f"✅ 已嵌入 {len(split_docs)} 區塊")

        new_ids = {doc.metadata.get("id") for doc in new_docs}
        save_embedded_record(new_ids)
        redis_client.set(SYNC_STATUS_KEY, "success")
        logger.info("✅ 嵌入紀錄已更新")
    except Exception as e:
        redis_client.set(SYNC_STATUS_KEY, f"failed: {str(e)}")
        logger.error(f"Sync error: {str(e)}")
        raise

def validate_texts(texts: list[str]) -> bool:
    """驗證手動輸入文本"""
    if not texts:
        logger.warning("Empty texts received")
        return False
    for text in texts:
        if len(text) > 10000:
            logger.warning("Text too long: %d", len(text))
            return False
    return True

def embedd_manual_from_text(texts: list[str], store: bool = True):
    if not validate_texts(texts):
        logger.error("Invalid texts, skipping embed")
        return None

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    split_docs = splitter.create_documents(texts)
    logger.info(f"✅ 手動傳入文字，共切分為 {len(split_docs)} 區塊")

    if store:
        def embed_chunk(chunk):
            uuids = [str(uuid4()) for _ in chunk]
            db.add_documents(chunk, ids=uuids)

        with ThreadPoolExecutor(max_workers=2) as executor:
            chunk_size = max(1, len(split_docs) // 2)
            chunks = [split_docs[i:i + chunk_size] for i in range(0, len(split_docs), chunk_size)]
            executor.map(embed_chunk, chunks)
        logger.info("✅ 手動嵌入資料已儲存")
    else:
        return db

def load_vector_db():
    """載入 db（已全局初始化）"""
    return db

def run_scheduler():
    """運行定時任務"""
    schedule.every(SYNC_INTERVAL_SECONDS).seconds.do(sync_drive_embeddings)
    logger.info(f"📅 定時任務已啟動，每 {SYNC_INTERVAL_SECONDS} 秒檢查一次 Google Drive")
    while True:
        schedule.run_pending()
        time.sleep(60)  # 每分鐘檢查，避免 CPU 過載

if __name__ == "__main__":
    import threading
    # 在後台執行緒運行定時任務
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    # 保持主執行緒存活
    try:
        while True:
            time.sleep(3600)  # 主執行緒休眠，任務由後台處理
    except KeyboardInterrupt:
        logger.info("🛑 停止定時任務")