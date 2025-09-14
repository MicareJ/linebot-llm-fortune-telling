import os
import time
import threading
import signal
import requests
from typing import List

from dotenv import load_dotenv
from redis import Redis
from tenacity import retry, stop_after_attempt, wait_fixed
from langchain_google_community import GoogleDriveLoader
from langchain_chroma import Chroma
from langchain.text_splitter import RecursiveCharacterTextSplitter
import schedule

from core.logger_config import setup_logger

# --- 初始化設定 ---
logger = setup_logger('embedding_updater')
load_dotenv()

# 從環境變數讀取設定
CHROMA_PATH = os.getenv("CHROMA_PATH")
SERVICE_ACCOUNT_PATH = os.getenv("SERVICE_ACCOUNT_PATH")
FOLDER_ID = os.getenv("FOLDER_ID")
REDIS_URL = os.getenv("REDIS_URL")
EMBEDDING_SERVICE_URL = os.getenv("EMBEDDING_SERVICE_URL") # 讀取嵌入服務的 URL

if not all([CHROMA_PATH, SERVICE_ACCOUNT_PATH, FOLDER_ID, REDIS_URL, EMBEDDING_SERVICE_URL]):
    raise ValueError("One or more required environment variables are not set.")

# 24 hours
SYNC_INTERVAL_SECONDS = 86400

# --- Redis Key 常數 ---
EMBEDDED_KEY = "embedded_file_ids"
LAST_SYNC_KEY = "last_sync_time"
SYNC_STATUS_KEY = "sync_status"

# --- 全域客戶端初始化 ---
@retry(stop=stop_after_attempt(3), wait=wait_fixed(5))
def initialize_redis_client():
    logger.info("Initializing Redis client...")
    client = Redis.from_url(REDIS_URL, decode_responses=True)
    client.ping()
    logger.info("Redis client initialized successfully.")
    return client

redis_client = initialize_redis_client()

db = Chroma(
    collection_name="fortunetelling_rag_db",
    persist_directory=CHROMA_PATH,
)

# --- 核心函式 ---

# 呼叫外部嵌入服務的函式
@retry(stop=stop_after_attempt(3), wait=wait_fixed(5))
def get_embeddings_from_service(texts: List[str]) -> List[List[float]]:
    """向獨立的嵌入服務發送請求以獲取向量"""
    logger.info(f"Sending request to {EMBEDDING_SERVICE_URL} to process {len(texts)} texts...")
    try:
        response = requests.post(EMBEDDING_SERVICE_URL, json={"texts": texts})
        response.raise_for_status()  # 如果 HTTP 狀態碼是 4xx 或 5xx，則拋出異常
        data = response.json()
        return data["embeddings"]
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to call embedding service: {e}", exc_info=True)
        raise

def load_embedded_ids_from_redis() -> set:
    return set(redis_client.smembers(EMBEDDED_KEY))

def add_embedded_ids_to_redis(new_ids: set):
    if new_ids:
        redis_client.sadd(EMBEDDED_KEY, *new_ids)
        logger.info(f"Successfully recorded {len(new_ids)} new file IDs to Redis.")

def clean_obsolete_embeddings(current_file_ids: set):
    embedded_ids = load_embedded_ids_from_redis()
    obsolete_ids = embedded_ids - current_file_ids
    if not obsolete_ids:
        return
    logger.info(f"Found {len(obsolete_ids)} obsolete files, preparing to remove from vector database...")
    try:
        # 根據 metadata['source'] 來刪除是 ChromaDB 的標準做法
        db.delete(where={"source": {"$in": list(obsolete_ids)}})
        redis_client.srem(EMBEDDED_KEY, *obsolete_ids)
        logger.info(f"Successfully removed vectors related to obsolete files.")
    except Exception as e:
        logger.error(f"Error removing obsolete vectors from ChromaDB: {e}", exc_info=True)


@retry(stop=stop_after_attempt(3), wait=wait_fixed(300))
def sync_drive_embeddings():
    logger.info("Starting Google Drive synchronization...")
    redis_client.set(SYNC_STATUS_KEY, "running")
    
    try:
        # 載入雲端硬碟文件元資料
        loader = GoogleDriveLoader.from_service_account_file(
            service_account_path=SERVICE_ACCOUNT_PATH,
            folder_id=FOLDER_ID, recursive=False,
            file_loader_cls=lambda *args, **kwargs: None, load_auth=True
        )
        docs = loader.load()
        logger.info(f"Found {len(docs)} files from Google Drive.")

        # 清理過時的嵌入
        current_file_ids = {doc.metadata.get("source") for doc in docs}
        clean_obsolete_embeddings(current_file_ids)

        # 找出需要新增的文件
        embedded_ids = load_embedded_ids_from_redis()
        new_docs_meta = [doc for doc in docs if doc.metadata.get("source") not in embedded_ids]
        
        if not new_docs_meta:
            logger.info("No new files to embed.")
            redis_client.set(SYNC_STATUS_KEY, "success")
            redis_client.set(LAST_SYNC_KEY, int(time.time()))
            return

        logger.info(f"Found {len(new_docs_meta)} new files, starting processing...")
        
        # 讀取新文件內容並進行分割
        full_content_loader = GoogleDriveLoader.from_service_account_file(
            service_account_path=SERVICE_ACCOUNT_PATH,
            file_ids=[doc.metadata.get("source") for doc in new_docs_meta]
        )
        docs_with_content = full_content_loader.load()

        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        split_docs = splitter.split_documents(docs_with_content)
        
        if not split_docs:
            logger.warning("No embeddable chunks generated after document splitting.")
            redis_client.set(SYNC_STATUS_KEY, "success")
            return
            
        # 分批呼叫嵌入服務，並手動新增到 ChromaDB
        texts_to_embed = [doc.page_content for doc in split_docs]
        metadatas = [doc.metadata for doc in split_docs]
        
        # 呼叫我們的內部 API 服務來獲取向量
        vectors = get_embeddings_from_service(texts_to_embed)
        
        # 手動將文字、向量和元資料加入 ChromaDB
        db.add_texts(texts=texts_to_embed, embeddings=vectors, metadatas=metadatas)
        logger.info(f"Successfully embedded {len(split_docs)} document chunks.")

        # 更新 Redis 紀錄
        new_file_ids = {doc.metadata.get("source") for doc in new_docs_meta}
        add_embedded_ids_to_redis(new_file_ids)
        
        redis_client.set(SYNC_STATUS_KEY, "success")
        redis_client.set(LAST_SYNC_KEY, int(time.time()))
        logger.info("Google Drive synchronization completed successfully.")

    except Exception as e:
        redis_client.set(SYNC_STATUS_KEY, f"failed: {e}")
        logger.error(f"An error occurred during synchronization: {e}", exc_info=True)
        raise

# --- 定時任務管理  ---
def run_background_scheduler(stop_event: threading.Event):
    logger.info(f"Scheduler started. Syncing Google Drive every {SYNC_INTERVAL_SECONDS} seconds.")
    try:
        sync_drive_embeddings()
    except Exception:
        logger.error("Initial synchronization failed, the scheduler will retry after the specified interval.")
    
    schedule.every(SYNC_INTERVAL_SECONDS).seconds.do(sync_drive_embeddings)
    
    logger.info("Initial synchronization completed, entering scheduled wait mode...")
    while not stop_event.is_set():
        schedule.run_pending()
        stop_event.wait(60)
    logger.info("Received stop signal, scheduler thread has been safely shut down.")


# --- 主程式進入點  ---
if __name__ == "__main__":
    logger.info("Embedding updater service started...")
    shutdown_event = threading.Event()
    def signal_handler(signum, frame):
        logger.info("Detected shutdown signal (Ctrl+C), preparing to shut down service...")
        shutdown_event.set()
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    scheduler_thread = threading.Thread(
        target=run_background_scheduler,
        args=(shutdown_event,), name="SchedulerThread", daemon=True
    )
    scheduler_thread.start()
    logger.info("Main thread is waiting for shutdown signal...")
    scheduler_thread.join()
    logger.info("Embedding updater service has been fully shut down.")

