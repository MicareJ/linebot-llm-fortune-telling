import logging
import os
from logging.handlers import RotatingFileHandler

LOG_DIR = "logs"

def setup_logger(name: str) -> logging.Logger:
    """
    設定並返回一個 logger，它會同時將日誌輸出到控制台和指定的日誌檔案。

    日誌檔案會存放在專案根目錄下的 'logs' 資料夾中，並具備自動輪替功能。

    Args:
        name (str): Logger 的名稱，也將用作日誌檔名 (例如 'app', 'embedding')。

    Returns:
        logging.Logger: 已設定好的 logger 物件。
    """
    # 確保日誌目錄存在
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

    # 根據傳入的名稱取得 logger，這可以確保在同一個程式中重複呼叫時，
    # 得到的是同一個 logger 實例。
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # 防止重複加入handler
    if logger.hasHandlers():
        return logger

    # 統一日誌格式
    log_format = logging.Formatter(
        "%(asctime)s - %(name)s - P%(process)d - %(threadName)s - %(levelname)s - %(message)s"
    )

    # --- 設定檔案 Handler (FileHandler) ---
    # 使用 RotatingFileHandler 來自動管理日誌檔案大小
    log_file = os.path.join(LOG_DIR, f"{name}.log")
    file_handler = RotatingFileHandler(
        filename=log_file,
        maxBytes=10 * 1024 * 1024,  # 每個檔案最大 10 MB
        backupCount=5,              # 保留最近的 5 個備份檔案
        encoding='utf-8'
    )
    file_handler.setFormatter(log_format)
    logger.addHandler(file_handler)

    # --- 設定控制台 Handler (StreamHandler) ---
    # 這樣在開發時仍然可以即時看到日誌輸出
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(log_format)
    logger.addHandler(stream_handler)

    return logger
