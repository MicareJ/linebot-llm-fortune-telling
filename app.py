from flask import Flask, request, abort
from linebot.v3.webhook import WebhookHandler
from linebot.v3.messaging import (
    MessagingApi, Configuration, ApiClient,
    TextMessage, QuickReply, QuickReplyItem, MessageAction,
    ApiException, ErrorResponse, ReplyMessageRequest
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.exceptions import InvalidSignatureError
import os
import json
import logging
import re
from datetime import datetime
from redis import Redis
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import base64
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import requests

from rag.name_fivegrid_wuxing import format_fivegrid_wuxing_prompt
from rag.bazi_true_solar import format_bazi_report
from rag.rag import run_rag_pipeline

# 設定日誌
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
REDIS_URL = os.getenv("REDIS_URL")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")  # Google Geocoding API key

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
api_client = ApiClient(configuration)
line_bot_api = MessagingApi(api_client)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
redis_client = Redis.from_url(REDIS_URL, decode_responses=True)

AES_KEY_TTL = 3600

def _redis_aeskey_name(user_id: str) -> str:
    return f"aeskey:{user_id}"

def _redis_session_name(user_id: str) -> str:
    return f"session:{user_id}"

def ensure_aes_key(user_id: str, ttl: int = AES_KEY_TTL) -> bytes:
    """
    產生或取得 AES-256 key（32 bytes），以 base64 存到 Redis，並設定 TTL。
    回傳原始 bytes。
    """
    key_name = _redis_aeskey_name(user_id)
    try:
        b64 = redis_client.get(key_name)
    except Exception:
        b64 = None
    if b64:
        try:
            return base64.b64decode(b64)
        except Exception:
            # 若 decode 失敗，重新產生
            pass
    # 產生新 key 並存 Redis（以 base64 儲存）
    key = os.urandom(32)
    try:
        redis_client.setex(key_name, ttl, base64.b64encode(key).decode())
    except Exception:
        # 若 Redis 寫入失敗，不要拋出明文 key；僅回傳 key（短期記憶）
        # 但若 Redis 無法使用，自動遺忘機制將無法保證
        pass
    return key

def encrypt_and_store_session(user_id: str, session: dict):
    """
    使用 AES-GCM 加密 session dict，並把 ciphertext / nonce / tag 以 base64 存回 Redis 的 session key。
    同時把 session key 設定與 AES key 相同的 TTL，確保金鑰過期時密文也會被刪除。
    """
    if session is None:
        return
    # 序列化
    plaintext = json.dumps(session, ensure_ascii=False).encode("utf-8")
    # 取得或產生金鑰
    key_name = _redis_aeskey_name(user_id)
    key = ensure_aes_key(user_id)

    aesgcm = AESGCM(key)
    nonce = os.urandom(12)  # 96-bit nonce 建議
    ct_with_tag = aesgcm.encrypt(nonce, plaintext, associated_data=None)  # returns ciphertext||tag
    # 分離 tag（最後 16 bytes）與 ciphertext
    tag = ct_with_tag[-16:]
    ciphertext = ct_with_tag[:-16]
    payload = {
        "ciphertext": base64.b64encode(ciphertext).decode(),
        "nonce": base64.b64encode(nonce).decode(),
        "tag": base64.b64encode(tag).decode(),
    }

    # 取得 AES key 在 Redis 上的剩餘 TTL（秒）
    try:
        ttl_remain = redis_client.ttl(key_name)
    except Exception:
        ttl_remain = -2  # error -> treat as no ttl

    # 決定要設定給 session key 的 TTL：
    # 如果 ttl_remain > 0 使用它；否則 fallback 到預設 AES_KEY_TTL
    if not (isinstance(ttl_remain, int) and ttl_remain > 0):
        logger.info("Skip storing session: AES key expired/missing (user=%s, ttl=%s)", user_id, ttl_remain)
        return

    session_ttl = ttl_remain  # 與金鑰完全同步 TTL

    # 存回 Redis 並設定相同 TTL（使用 setex 保證同時過期）
    try:
        redis_client.setex(_redis_session_name(user_id), session_ttl, json.dumps(payload, ensure_ascii=False))
    except Exception:
        logger.exception("Failed to store encrypted session for user %s", user_id)

def decrypt_session(user_id: str) -> dict | None:
    """
    嘗試從 Redis 取出 AES key（若 key TTL 尚在），並解密 session。
    若金鑰不存在或驗證失敗，回傳 None（表示無法還原明文）。
    """
    try:
        b64key = redis_client.get(_redis_aeskey_name(user_id))
    except Exception:
        b64key = None
    if not b64key:
        # 金鑰遺失（TTL 到期）或 Redis 不可用 -> 無法解密
        return None
    try:
        key = base64.b64decode(b64key)
    except Exception:
        return None
    # 取出 ciphertext payload
    try:
        payload_raw = redis_client.get(_redis_session_name(user_id))
    except Exception:
        payload_raw = None
    if not payload_raw:
        return None
    try:
        payload = json.loads(payload_raw)
        ciphertext = base64.b64decode(payload["ciphertext"])
        nonce = base64.b64decode(payload["nonce"])
        tag = base64.b64decode(payload["tag"])
        ct_with_tag = ciphertext + tag
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ct_with_tag, associated_data=None)
        return json.loads(plaintext.decode("utf-8"))
    except Exception:
        # 解密或解析失敗 -> 回傳 None
        logger.debug("Decrypt session failed or key invalid for user %s", user_id, exc_info=True)
        return None

def clear_session(user_id: str):
    """刪除 session ciphertext 與 AES 金鑰（如果存在）"""
    try:
        redis_client.delete(_redis_session_name(user_id))
    except Exception:
        logger.debug("Failed to delete session ciphertext for %s", user_id, exc_info=True)
    try:
        redis_client.delete(_redis_aeskey_name(user_id))
    except Exception:
        logger.debug("Failed to delete aes key for %s", user_id, exc_info=True)

def save_session(user_id: str, session: dict):
    """使用 AES-GCM 加密並存儲 session。"""
    try:
        encrypt_and_store_session(user_id, session)
    except Exception:
        logger.exception("save_session failed for %s", user_id)

def load_session(user_id: str) -> dict:
    """嘗試解密 session；若解密失敗或金鑰過期，回傳空 dict。"""
    try:
        result = decrypt_session(user_id)
        return result or {}
    except Exception:
        logger.exception("load_session failed for %s", user_id)
        return {}

# 速率限制
limiter = Limiter(app=app,
                  key_func=get_remote_address,
                  default_limits=["10 per minute"],
                  storage_uri=REDIS_URL)

def validate_name(name: str) -> bool:
    """驗證姓名是否為繁體中文"""
    return bool(re.match(r"^[\u4e00-\u9fff]+$", name))

def validate_date(date: str) -> bool:
    """驗證日期格式 YYYY-MM-DD"""
    try:
        datetime.strptime(date, "%Y-%m-%d")
        return True
    except ValueError:
        return False

def validate_time(time: str) -> bool:
    """驗證時間格式 HH"""
    try:
        int(time)
        return 0 <= int(time) <= 23
    except ValueError:
        return False

def get_location_coordinates_and_timezone(location: str) -> tuple[float, str]:
    """用 Google Geocoding API 查詢經緯度，再用 Time Zone API 查詢時區"""
    try:
        # 1. 取得經緯度
        geo_url = f"https://maps.googleapis.com/maps/api/geocode/json?address={location}&key={GOOGLE_API_KEY}"
        geo_response = requests.get(geo_url).json()
        if geo_response['status'] == 'OK':
            result = geo_response['results'][0]
            lat = result['geometry']['location']['lat']
            lng = result['geometry']['location']['lng']
            # 2. 取得時區
            timestamp = int(datetime.now().timestamp())
            tz_url = f"https://maps.googleapis.com/maps/api/timezone/json?location={lat},{lng}&timestamp={timestamp}&key={GOOGLE_API_KEY}"
            tz_response = requests.get(tz_url).json()
            if tz_response['status'] == 'OK':
                tz_name = tz_response['timeZoneId']
                return lng, tz_name
            return lng, "Asia/Taipei"
        return 121.5654, "Asia/Taipei"
    except Exception as e:
        logger.error("Google Geocode/Timezone error: %s", str(e))
        return 121.5654, "Asia/Taipei"

@app.route("/callback", methods=["POST"])
@limiter.limit("10 per minute")
def callback():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
        logger.info("Webhook processed successfully")
    except InvalidSignatureError:
        logger.error("Invalid Line signature")
        abort(400)
    except Exception as e:
        logger.error("Webhook error: %s", str(e))
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
            redis_client.delete(user_id)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[
                        TextMessage(
                            text="Yes！下班！"
                        )
                    ]
                )
            )
            return

        # 開始算命
        if text == "開始！":
            session = {"step": 0}
            save_session(user_id, session)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[
                        TextMessage(text="煩欸又要上班了！你叫什麼名字啦")
                    ]
                )
            )
            return

        # 新使用者或session已過期
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
                    messages=[
                        TextMessage(
                            text="貨出的去，錢進得來，你會發大財！點下方按鈕開始吧",
                            quick_reply=quick_reply
                        )
                    ]
                )
            )
            return

        # 流程處理
        if session["step"] == 0:
            if not validate_name(text):
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=reply_token,
                        messages=[
                            TextMessage(text="你的名字跟我家隔壁的柯基沒兩樣，重打一次！")
                        ]
                    )
                )
                return
            session["name"] = text
            session["step"] = 1
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[
                        TextMessage(text="生日幾號（YYYY-MM-DD）")
                    ]
                )
            )
            return

        elif session["step"] == 1:
            if not validate_date(text):
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=reply_token,
                        messages=[
                            TextMessage(text="欸！再皮叫你自生自滅")
                        ]
                    )
                )
                return
            session["birth_date"] = text
            session["step"] = 2
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[
                        TextMessage(text="OK！你幾點出生的（0-23）")
                    ]
                )
            )
            return

        elif session["step"] == 2:
            if not validate_time(text):
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=reply_token,
                        messages=[
                            TextMessage(text="你要確定欸？！")
                        ]
                    )
                )
                return
            session["birth_time"] = text
            session["step"] = 3
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[
                        TextMessage(text="那你媽在哪把你生出來的？")
                    ]
                )
            )
            return

        elif session["step"] == 3:
            session["location"] = text
            session["step"] = 4

            # ==== 前處理 ====
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
                    messages=[
                        TextMessage(text="好啦說！你想問什麼")
                    ]
                )
            )
            return

        elif session["step"] == 4:
            user_question = text
            rag_input = f"{session['background']}\n\n使用者問題：{user_question}"
            answer = run_rag_pipeline(rag_input)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[
                        TextMessage(text=answer)
                    ]
                )
            )
            return

    except ApiException as e:
        logger.error("LineBotApi error: %s", str(e))
        if hasattr(e, "status"):
            logger.error("HTTP status: %s", str(e.status))
        if hasattr(e, "headers") and e.headers and "x-line-request-id" in e.headers:
            logger.error("x-line-request-id: %s", e.headers["x-line-request-id"])
        if hasattr(e, "body") and e.body:
            logger.error("response body: %s", ErrorResponse.from_json(e.body))
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[
                    TextMessage(text="都你啦再不繳電話費阿！沒訊號了啦")
                ]
            )
        )

    except Exception as e:
        logger.error("Handle message error: %s", str(e))
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[
                    TextMessage(text="靠！哪個工程師寫的爛軟體，出問題了啦")
                ]
            )
        )

if __name__ == "__main__":
    app.run(port=5000, debug=True)