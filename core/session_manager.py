import os
import json
import base64
from redis import Redis
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core.logger_config import setup_logger

logger = setup_logger('session_manager')

class SessionManager:
    """
    一個專門處理使用者會話加密、儲存和讀取的類別。
    採用信封加密模式，確保儲存在 Redis 中的資料安全。
    """
    def __init__(self, redis_client: Redis, session_ttl_seconds: int = 3600):
        """
        初始化 SessionManager。

        Args:
            redis_client (Redis): 已初始化的 Redis 客戶端實例。
            session_ttl_seconds (int): Session 在 Redis 中的預設存活時間（秒）。
        """
        if not isinstance(redis_client, Redis):
            raise TypeError("redis_client must be an instance of Redis.")
        
        self.redis = redis_client
        self.ttl = session_ttl_seconds
        self._master_key = self._load_master_key()
        logger.info("SessionManager initialized successfully.")

    def _load_master_key(self) -> bytes:
        """從環境變數載入主加密金鑰 (KEK)。"""
        raw = os.getenv("MASTER_ENCRYPTION_KEY")
        if not raw:
            logger.critical("Environment variable MASTER_ENCRYPTION_KEY is not set!")
            raise RuntimeError("MASTER_ENCRYPTION_KEY isn't set yet")
        
        for decoder in (lambda x: base64.b64decode(x, validate=True), lambda x: bytes.fromhex(x), lambda x: x.encode("utf-8")):
            try:
                key = decoder(raw)
                if len(key) in (16, 24, 32): # AES 128, 192, 256
                    logger.info("Master Encryption Key (KEK) loaded successfully.")
                    return key
            except Exception:
                continue
        
        logger.critical("MASTER_ENCRYPTION_KEY format is invalid or has incorrect length.")
        raise RuntimeError("MASTER_ENCRYPTION_KEY format could not be parsed as 16/24/32 bytes")

    def _get_redis_key(self, user_id: str) -> str:
        """產生用於 Redis 的標準化 key 名稱。"""
        return f"session:{user_id}"

    def save(self, user_id: str, session_data: dict):
        """
        將使用者的 session 資料加密後存入 Redis。

        Args:
            user_id (str): 使用者的唯一識別碼。
            session_data (dict): 要儲存的 session 資料字典。
        """
        if not session_data:
            return

        try:
            plaintext = json.dumps(session_data, ensure_ascii=False).encode("utf-8")
            
            # 1. 產生一次性的資料加密金鑰 (DEK)
            dek = os.urandom(32)

            # 2. 使用 DEK 加密 session 資料
            session_aes = AESGCM(dek)
            session_nonce = os.urandom(12)
            session_ct_with_tag = session_aes.encrypt(session_nonce, plaintext, None)
            session_tag, session_ciphertext = session_ct_with_tag[-16:], session_ct_with_tag[:-16]

            # 3. 使用主金鑰 (KEK) 加密 DEK
            kek_aes = AESGCM(self._master_key)
            dek_nonce = os.urandom(12)
            dek_ct_with_tag = kek_aes.encrypt(dek_nonce, dek, None)
            dek_tag, encrypted_dek = dek_ct_with_tag[-16:], dek_ct_with_tag[:-16]

            # 4. 組合 payload
            payload = {
                "session_ciphertext": base64.b64encode(session_ciphertext).decode(),
                "session_nonce": base64.b64encode(session_nonce).decode(),
                "session_tag": base64.b64encode(session_tag).decode(),
                "encrypted_dek": base64.b64encode(encrypted_dek).decode(),
                "dek_nonce": base64.b64encode(dek_nonce).decode(),
                "dek_tag": base64.b64encode(dek_tag).decode(),
            }
            
            # 5. 寫入 Redis
            redis_key = self._get_redis_key(user_id)
            self.redis.setex(redis_key, self.ttl, json.dumps(payload, ensure_ascii=False))

        except Exception:
            logger.exception(f"Failed to save session for user {user_id}.")

    def load(self, user_id: str) -> dict:
        """
        從 Redis 讀取並解密使用者的 session 資料。

        Args:
            user_id (str): 使用者的唯一識別碼。

        Returns:
            dict: 解密後的 session 資料。如果找不到或解密失敗，則回傳空字典。
        """
        redis_key = self._get_redis_key(user_id)
        try:
            raw_payload = self.redis.get(redis_key)
            if not raw_payload:
                return {}

            payload = json.loads(raw_payload)
            
            # 驗證 payload 完整性
            required_keys = ["session_ciphertext", "session_nonce", "session_tag", "encrypted_dek", "dek_nonce", "dek_tag"]
            if not all(key in payload for key in required_keys):
                logger.warning(f"Session payload for user {user_id} is incomplete.")
                return {}

            # Base64 解碼
            session_ciphertext, session_nonce, session_tag, encrypted_dek, dek_nonce, dek_tag = \
                (base64.b64decode(payload[k]) for k in required_keys)
            
            # 1. 使用主金鑰 (KEK) 解密 DEK
            kek_aes = AESGCM(self._master_key)
            dek = kek_aes.decrypt(dek_nonce, encrypted_dek + dek_tag, None)
            
            # 2. 使用 DEK 解密 session 資料
            session_aes = AESGCM(dek)
            plaintext = session_aes.decrypt(session_nonce, session_ciphertext + session_tag, None)
            
            return json.loads(plaintext.decode("utf-8"))

        except json.JSONDecodeError:
            logger.warning(f"Failed to parse session payload (JSON) for user {user_id}.")
            return {}
        except Exception:
            logger.exception(f"Failed to load or decrypt session for user {user_id}.")
            return {}

    def clear(self, user_id: str):
        """
        從 Redis 中刪除指定使用者的 session 資料。

        Args:
            user_id (str): 使用者的唯一識別碼。
        """
        try:
            redis_key = self._get_redis_key(user_id)
            self.redis.delete(redis_key)
        except Exception:
            logger.exception(f"Failed to clear session for user {user_id}.")