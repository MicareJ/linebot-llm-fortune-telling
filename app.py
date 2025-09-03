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
from cryptography.fernet import Fernet
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
cipher = Fernet(os.getenv("FERNET_KEY"))  # Fly.io Secrets 提供 key

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

def save_session(user_id: str, session: dict):
    """加密並儲存會話到 Redis，TTL 1小時"""
    encrypted = cipher.encrypt(json.dumps(session).encode()).decode()
    redis_client.setex(user_id, 3600, encrypted)

def load_session(user_id: str) -> dict:
    """從 Redis 讀取並解密會話"""
    encrypted = redis_client.get(user_id)
    if encrypted:
        return json.loads(cipher.decrypt(encrypted.encode()).decode())
    return {}

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

        # 重置命令
        if text == "重來一次":
            redis_client.delete(user_id)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[
                        TextMessage(
                            text="哈哈，小童把你的命盤清空啦！點「開始算命」重新來過吧！",
                            quick_reply=QuickReply(
                                items=[
                                    QuickReplyItem(action=MessageAction(label="開始算命", text="開始算命")),
                                    QuickReplyItem(action=MessageAction(label="取消", text="取消"))
                                ]
                            )
                        )
                    ]
                )
            )
            return

        # 取消命令
        if text == "取消":
            redis_client.delete(user_id)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[
                        TextMessage(
                            text="好吧，小童先下班啦！想算命再喊我哦！"
                        )
                    ]
                )
            )
            return

        # 開始算命入口
        if text in ["開始算命"]:
            session = {"step": 0}
            save_session(user_id, session)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[
                        TextMessage(text="小傑上線！你叫什麼名字：")
                    ]
                )
            )
            return

        # 新用戶或未啟動流程
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
            save_session(user_id, session)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[
                        TextMessage(text="OK！生日幾號（YYYY-MM-DD）：")
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
            save_session(user_id, session)
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
                            TextMessage(text="你要確欸？！")
                        ]
                    )
                )
                return
            session["birth_time"] = text
            session["step"] = 3
            save_session(user_id, session)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[
                        TextMessage(text="好咧！那你媽在哪把你生出來的")
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
                        TextMessage(text="好！說！你想問什麼")
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
                    TextMessage(text="都你啦 再不繳電話費阿！沒訊號了啦")
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