import os
import logging
import time
import threading
import signal
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

from core.logger_config import setup_logger

logger = setup_logger('embedding')

load_dotenv()

# 從環境變數讀取設定
MODEL = os.getenv("RAG_MODEL")
CHROMA_PATH = os.getenv("CHROMA_PATH", "chroma_db")
SERVICE_ACCOUNT_PATH = os.getenv("SERVICE_ACCOUNT_PATH", "service_account.json")
FOLDER_ID = os.getenv("FOLDER_ID")
REDIS_URL = os.getenv("REDIS_URL")
# 24 hours
SYNC_INTERVAL_SECONDS =  86400

# --- Redis Key 常數 ---
EMBEDDED_KEY = "embedded_file_ids"
LAST_SYNC_KEY = "last_sync_time"
SYNC_STATUS_KEY = "sync_status"

# --- 全域客戶端初始化 ---
# 加上重試機制，增加連線穩定性
@retry(stop=stop_after_attempt(3), wait=wait_fixed(5))
def initialize_redis_client():
    logger.info("Initializing Redis client...")
    client = Redis.from_url(REDIS_URL, decode_responses=True)
    client.ping()
    logger.info("Redis client initialized successfully.")
    return client

redis_client = initialize_redis_client()
embeddings = OllamaEmbeddings(model=MODEL)
db = Chroma(
    collection_name="fortunetelling_rag_db",
    embedding_function=embeddings,
    persist_directory=CHROMA_PATH,
)

# --- 核心函式 ---
def load_embedded_ids_from_redis() -> set:
    """從 Redis 載入已嵌入檔案的 ID 集合"""
    return set(redis_client.smembers(EMBEDDED_KEY))

def add_embedded_ids_to_redis(new_ids: set):
    """將新嵌入的檔案 ID 新增到 Redis 集合中"""
    if new_ids:
        redis_client.sadd(EMBEDDED_KEY, *new_ids)
        logger.info(f"Successfully recorded {len(new_ids)} new file IDs to Redis.")

def clean_obsolete_embeddings(current_file_ids: set):
    """
    比對 Redis 中紀錄的 ID 與雲端硬碟當前的檔案 ID，
    刪除在雲端已被移除的檔案對應的向量。
    """
    embedded_ids = load_embedded_ids_from_redis()
    obsolete_ids = embedded_ids - current_file_ids
    
    if not obsolete_ids:
        return

    logger.info(f"Found {len(obsolete_ids)} obsolete files, preparing to remove from vector database...")
    # 注意：Chroma 的 delete 方法目前不支援基於 metadata 過濾
    # 我們需要先 get 再 delete，這在大量刪除時效率較低
    # 這是目前 Chroma API 的限制
    try:
        results = db.get(where={"source": {"$in": list(obsolete_ids)}})
        if results and results["ids"]:
            db.delete(ids=results["ids"])
            redis_client.srem(EMBEDDED_KEY, *obsolete_ids)
            logger.info(f"Successfully removed {len(results['ids'])} vector blocks related to obsolete files.")
    except Exception as e:
        logger.error(f"Error removing obsolete vectors from ChromaDB: {e}", exc_info=True)


@retry(stop=stop_after_attempt(3), wait=wait_fixed(300))
def sync_drive_embeddings():
    """
    與 Google Drive 同步，處理新增、刪除的檔案，並更新向量資料庫。
    """
    logger.info("Starting Google Drive synchronization...")
    redis_client.set(SYNC_STATUS_KEY, "running")
    
    try:
        # 1. 載入雲端硬碟文件
        loader = GoogleDriveLoader.from_service_account_file(
            service_account_path=SERVICE_ACCOUNT_PATH,
            folder_id=FOLDER_ID,
            recursive=False,
            # 優化：只載入 metadata，避免立即下載整個檔案內容
            file_loader_cls=lambda *args, **kwargs: None, 
            load_auth=True
        )
        docs = loader.load()
        logger.info(f"Found {len(docs)} files from Google Drive.")

        # 2. 清理過時的嵌入
        current_file_ids = {doc.metadata.get("source") for doc in docs}
        clean_obsolete_embeddings(current_file_ids)

        # 3. 找出需要新增的文件
        embedded_ids = load_embedded_ids_from_redis()
        new_docs = [doc for doc in docs if doc.metadata.get("source") not in embedded_ids]
        
        if not new_docs:
            logger.info("No new files to embed.")
            redis_client.set(SYNC_STATUS_KEY, "success")
            redis_client.set(LAST_SYNC_KEY, int(time.time()))
            return

        logger.info(f"Found {len(new_docs)} new files, starting embedding process...")
        
        # 4. 分割與嵌入文件
        # 注意：重新建立載入器以實際讀取文件內容
        full_content_loader = GoogleDriveLoader.from_service_account_file(
            service_account_path=SERVICE_ACCOUNT_PATH,
            file_ids=[doc.metadata.get("source") for doc in new_docs]
        )
        docs_with_content = full_content_loader.load()

        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        split_docs = splitter.split_documents(docs_with_content)
        
        if not split_docs:
            logger.warning("No embeddable chunks generated after document splitting.")
            redis_client.set(SYNC_STATUS_KEY, "success") # 仍視為成功，因為沒有新內容
            return

        db.add_documents(split_docs) # ChromaDB 會自動處理批次和 ID
        logger.info(f"Successfully embedded {len(split_docs)} document chunks.")

        # 5. 更新 Redis 紀錄
        new_file_ids = {doc.metadata.get("source") for doc in new_docs}
        add_embedded_ids_to_redis(new_file_ids)
        
        redis_client.set(SYNC_STATUS_KEY, "success")
        redis_client.set(LAST_SYNC_KEY, int(time.time()))
        logger.info("Google Drive synchronization completed successfully.")

    except Exception as e:
        # 發生任何錯誤時，標記為失敗並重新拋出，讓 tenacity 重試機制介入
        redis_client.set(SYNC_STATUS_KEY, f"failed: {e}")
        logger.error(f"Error occurred during synchronization: {e}", exc_info=True)
        raise

# --- 定時任務管理 ---
def run_background_scheduler(stop_event: threading.Event):
    """
    一個會在背景執行緒中運行的函式，負責管理定時任務。
    
    Args:
        stop_event: 一個 threading.Event 物件，用來通知此執行緒停止。
    """
    logger.info(f"Scheduler started. Syncing Google Drive every {SYNC_INTERVAL_SECONDS} seconds.")

    # 1. 立即執行一次首次同步 (滿足您的要求)
    try:
        sync_drive_embeddings()
    except Exception:
        logger.error("Initial synchronization failed, the scheduler will retry after the specified interval.")

    # 2. 設定週期性任務
    schedule.every(SYNC_INTERVAL_SECONDS).seconds.do(sync_drive_embeddings)

    # 3. 進入主迴圈，直到收到停止訊號
    logger.info("Initial synchronization completed, entering scheduled wait mode...")
    while not stop_event.is_set():
        schedule.run_pending()
        # 使用 stop_event.wait() 可以更優雅地等待，而不是固定 sleep
        # 這裡我們每 60 秒檢查一次，以確保能及時響應停止訊號
        stop_event.wait(60)

    logger.info("Received stop signal, scheduler thread has been safely shut down.")


# --- 主程式進入點 ---
if __name__ == "__main__":
    logger.info("Embedding service started...")

    # 建立一個事件(Event)物件，用於在主執行緒和背景執行緒之間通訊
    shutdown_event = threading.Event()

    # 設計一個訊號處理函式，當使用者按下 Ctrl+C 時，會設定上面的事件
    def signal_handler(signum, frame):
        logger.info("Detected shutdown signal (Ctrl+C), preparing to shut down service...")
        shutdown_event.set()

    # 註冊訊號處理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 啟動背景排程器執行緒
    scheduler_thread = threading.Thread(
        target=run_background_scheduler,
        args=(shutdown_event,),
        name="SchedulerThread",
        daemon=True
    )
    scheduler_thread.start()
    logger.info("Main thread is waiting for shutdown signal...")
    scheduler_thread.join()
    logger.info("Embedding service has been fully shut down.")
