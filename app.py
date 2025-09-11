import os
import json
import base64
from datetime import datetime
import re
import requests
from flask import Flask, request, abort

from linebot.v3.webhook import WebhookHandler
from linebot.v3.messaging import (
    MessagingApi, Configuration, ApiClient,
    TextMessage, QuickReply, QuickReplyItem, MessageAction,
    ApiException, ErrorResponse, ReplyMessageRequest
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.exceptions import InvalidSignatureError
from redis import Redis
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from util.name_fivegrid_wuxing import format_fivegrid_wuxing_prompt
from util.bazi_true_solar import format_bazi_report
from util.rag import rag_system 

from core.logger_config import setup_logger

logger = setup_logger('app')

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
REDIS_URL = os.getenv("REDIS_URL")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
api_client = ApiClient(configuration)
line_bot_api = MessagingApi(api_client)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
redis_client = Redis.from_url(REDIS_URL, decode_responses=True)

# Session TTL (One hour)
SESSION_TTL = 3600

def _redis_session_name(user_id: str) -> str:
    return f"session:{user_id}"

# Master Key 
def _load_master_key() -> bytes:
    """
    從環境變數載入base64編碼主金鑰。
    """
    raw = os.getenv("MASTER_ENCRYPTION_KEY")
    if not raw:
        raise RuntimeError("MASTER_ENCRYPTION_KEY isn't set yet")
    # 嘗試 base64
    try:
        k = base64.b64decode(raw, validate=True)
    except Exception as e:
        raise RuntimeError("MASTER_ENCRYPTION_KEY cannot be decrypted from base64") from e
    
    if len(k) != 32:
        raise RuntimeError("MASTER_ENCRYPTION_KEY length is incorrect, must be 32 bytes")
    
    return k

MASTER_KEY = _load_master_key()

# 信封加密
def encrypt_and_store_session(user_id: str, session: dict):
    """
    1. 產生一次性 32 bytes DEK 
    2. 用 DEK (AES-GCM) 加密 session -> session_ciphertext / session_nonce / session_tag
    3. 用 Master Key (KEK, AES-GCM) 加密 DEK -> encrypted_dek / dek_nonce / dek_tag
    4. 將上述全部（base64後）寫入 Redis，設定 SESSION_TTL
    """
    if not session:
        return
    try:
        plaintext = json.dumps(session, ensure_ascii=False).encode("utf-8")
    except Exception:
        return

    # DEK
    dek = os.urandom(32)

    # 使用 DEK 加密 session
    session_aes = AESGCM(dek)
    session_nonce = os.urandom(12)
    session_ct_with_tag = session_aes.encrypt(session_nonce, plaintext, associated_data=None)
    session_tag = session_ct_with_tag[-16:]
    session_ciphertext = session_ct_with_tag[:-16]

    # 使用 Master Key 加密 DEK
    kek_aes = AESGCM(MASTER_KEY)
    dek_nonce = os.urandom(12)
    dek_ct_with_tag = kek_aes.encrypt(dek_nonce, dek, associated_data=None)
    dek_tag = dek_ct_with_tag[-16:]
    encrypted_dek = dek_ct_with_tag[:-16]

    payload = {
        "session_ciphertext": base64.b64encode(session_ciphertext).decode(),
        "session_nonce": base64.b64encode(session_nonce).decode(),
        "session_tag": base64.b64encode(session_tag).decode(),
        "encrypted_dek": base64.b64encode(encrypted_dek).decode(),
        "dek_nonce": base64.b64encode(dek_nonce).decode(),
        "dek_tag": base64.b64encode(dek_tag).decode(),
    }

    try:
        # 寫入 Redis
        redis_client.setex(_redis_session_name(user_id), SESSION_TTL, json.dumps(payload, ensure_ascii=False))
    except Exception:
        logger.exception("Store envelope session failed (user=%s)", user_id)

# 信封解密
def decrypt_and_load_session(user_id: str) -> dict:
    """
    1. 從 Redis 取 payload
    2. 用 Master Key 解開 encrypted_dek 得到 DEK
    3. 用 DEK 解開 session_ciphertext
    4. 回傳 dict；任何失敗回傳 {}
    """
    try:
        raw = redis_client.get(_redis_session_name(user_id))
    except Exception:
        raw = None
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
        required = [
            "session_ciphertext", "session_nonce", "session_tag",
            "encrypted_dek", "dek_nonce", "dek_tag"
        ]
        if any(k not in payload for k in required):
            return {}
        session_ciphertext = base64.b64decode(payload["session_ciphertext"])
        session_nonce = base64.b64decode(payload["session_nonce"])
        session_tag = base64.b64decode(payload["session_tag"])
        encrypted_dek = base64.b64decode(payload["encrypted_dek"])
        dek_nonce = base64.b64decode(payload["dek_nonce"])
        dek_tag = base64.b64decode(payload["dek_tag"])
    except Exception:
        return {}

    # 解出 DEK
    try:
        kek_aes = AESGCM(MASTER_KEY)
        dek_ct_with_tag = encrypted_dek + dek_tag
        dek = kek_aes.decrypt(dek_nonce, dek_ct_with_tag, associated_data=None)
    except Exception:
        return {}

    # 解出 session
    try:
        session_aes = AESGCM(dek)
        session_ct_with_tag = session_ciphertext + session_tag
        plaintext = session_aes.decrypt(session_nonce, session_ct_with_tag, associated_data=None)
        return json.loads(plaintext.decode("utf-8"))
    except Exception:
        return {}

def clear_session(user_id: str):
    try:
        redis_client.delete(_redis_session_name(user_id))
    except Exception:
        logger.debug("Clear session failed (user=%s)", user_id, exc_info=True)

def save_session(user_id: str, session: dict):
    try:
        encrypt_and_store_session(user_id, session)
    except Exception:
        logger.exception("save_session failed (user=%s)", user_id)

def load_session(user_id: str) -> dict:
    try:
        return decrypt_and_load_session(user_id)
    except Exception:
        logger.exception("load_session failed (user=%s)", user_id)
        return {}

# 速率限制
limiter = Limiter(app=app,
                  key_func=get_remote_address,
                  default_limits=["10 per minute"],
                  storage_uri=REDIS_URL)

def validate_name(name: str) -> bool:
    if len(name) < 2:
        raise ValueError("名字至少兩個字")
    return bool(re.match(r"^[\u4e00-\u9fff]+$", name))

def validate_date(date: str) -> bool:
    try:
        datetime.strptime(date, "%Y-%m-%d")
        return True
    except ValueError:
        return False

def validate_time(time: str) -> bool:
    try:
        v = int(time)
        return 0 <= v <= 23
    except ValueError:
        return False

def get_location_coordinates_and_timezone(location: str) -> tuple[float, str]:
    # 預設使用者為台灣人，使用台北經緯度與時區
    DEFAULT_LNG = 121.5654
    DEFAULT_TZ = "Asia/Taipei"

    try:
        geo_url = f"https://maps.googleapis.com/maps/api/geocode/json?address={location}&key={GOOGLE_API_KEY}"
        geo_response = requests.get(geo_url).json()
        
        if geo_response.get('status') == 'OK':
            result = geo_response['results'][0]
            lat = result['geometry']['location']['lat']
            lng = result['geometry']['location']['lng']
            timestamp = int(datetime.now().timestamp())
            tz_url = f"https://maps.googleapis.com/maps/api/timezone/json?location={lat},{lng}&timestamp={timestamp}&key={GOOGLE_API_KEY}"
            tz_response = requests.get(tz_url).json()
            if tz_response.get('status') == 'OK':
                return lng, tz_response['timeZoneId']
            else:
                logger.warning("Timezone API error: %s", tz_response.get('status'))
                return DEFAULT_LNG, DEFAULT_TZ
        else:
            logger.warning("Geocode API error: %s", geo_response.get('status'))
            return DEFAULT_LNG, DEFAULT_TZ
    
    except Exception as e:
        logger.error("Geocode/Timezone error: %s", e)
        return DEFAULT_LNG, DEFAULT_TZ

@app.route("/callback", methods=["POST"])
@limiter.limit("10 per minute")
def callback():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
        logger.info("Webhook processed")
    except InvalidSignatureError:
        logger.error("Invalid signature")
        abort(400)
    except Exception as e:
        logger.error("Webhook error: %s", e)
        abort(500)
    return "OK"

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text.strip()
    reply_token = event.reply_token
    try:
        session = load_session(user_id)

        if text == "差不多啦！":
            clear_session(user_id)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="Yes！下班！")]
                )
            )
            return

        if text == "開始！":
            session = {"step": 0}
            save_session(user_id, session)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="煩欸又要上班了！你叫什麼名字啦")]
                )
            )
            return

        if not session:
            quick_reply = QuickReply(
                items=[
                    QuickReplyItem(action=MessageAction(label="開始算命", text="開始算命")),
                    QuickReplyItem(action=MessageAction(label="取消", text="取消"))
                ]
            )
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="貨出的去，錢進得來，你會發大財！點下方按鈕開始吧", quick_reply=quick_reply)]
                )
            )
            return

        if session["step"] == 0:
            if not validate_name(text):
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=reply_token,
                        messages=[TextMessage(text="你的名字跟我家隔壁的柯基沒兩樣，重打一次！")]
                    )
                )
                return
            session["name"] = text
            session["step"] = 1
            save_session(user_id, session)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="生日幾號（YYYY-MM-DD）")]
                )
            )
            return

        elif session["step"] == 1:
            if not validate_date(text):
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=reply_token,
                        messages=[TextMessage(text="欸！再皮叫你自生自滅")]
                    )
                )
                return
            session["birth_date"] = text
            session["step"] = 2
            save_session(user_id, session)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="OK！你幾點出生的（0-23）")]
                )
            )
            return

        elif session["step"] == 2:
            if not validate_time(text):
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=reply_token,
                        messages=[TextMessage(text="你要確定欸？！")]
                    )
                )
                return
            session["birth_time"] = text
            session["step"] = 3
            save_session(user_id, session)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="那你媽在哪把你生出來的？")]
                )
            )
            return

        elif session["step"] == 3:
            session["location"] = text
            session["step"] = 4
            name_fivegrid = format_fivegrid_wuxing_prompt(session["name"])
            longitude, tz_name = get_location_coordinates_and_timezone(session["location"])
            year, month, day = map(int, session["birth_date"].split("-"))
            hour = int(session["birth_time"])
            bazi_result = format_bazi_report(year, month, day, hour, tz_name, longitude)
            session["background"] = f"{name_fivegrid}\n\n{bazi_result}"
            save_session(user_id, session)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="好啦說啦！你想問什麼")]
                )
            )
            return
        
        elif session["step"] == 4:
            user_question = text
            # 組合使用者背景資料和問題
            rag_input = f"{session.get('background', '')}\n\n使用者問題：{user_question}"
            
            # 呼叫新的 RAG 系統來生成回覆
            answer, updated_session = rag_system.generate_response(
                user_id=user_id,
                prompt=rag_input,
                session=session
            )
            
            # 將包含了新對話歷史的 session 存回 Redis
            save_session(user_id, updated_session)
            
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text=answer)]
                )
            )
            return
        
    except ApiException as e:
        logger.error("LineBotApi error: %s", e)
        try:
            if hasattr(e, "status"):
                logger.error("HTTP status: %s", e.status)
            if hasattr(e, "headers") and e.headers and "x-line-request-id" in e.headers:
                logger.error("x-line-request-id: %s", e.headers["x-line-request-id"])
            if hasattr(e, "body") and e.body:
                logger.error("response body: %s", ErrorResponse.from_json(e.body))
        except Exception:
            pass
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="都你啦再不繳電話費阿！沒訊號了啦")]
            )
        )

    except Exception as e:
        logger.error("Handle message error: %s", e)
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="靠！哪個工程師寫的爛軟體，出問題了啦")]
            )
        )

if __name__ == "__main__":
    app.run(port=5000, debug=True)