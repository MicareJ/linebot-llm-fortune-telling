from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage, QuickReply, QuickReplyButton, MessageAction
from linebot.exceptions import InvalidSignatureError
import os
import json
import logging
import re
from datetime import datetime
from redis import Redis
from cryptography.fernet import Fernet
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from linebot.exceptions import LineBotApiError
import requests  # 加 requests for Google API

from rag.name_fivegrid_wuxing import format_fivegrid_wuxing_prompt
from rag.bazi_true_solar import format_bazi_report
from rag.rag import run_rag_pipeline

# 設定日誌
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 環境變數
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")  # Google Geocoding API key

# 初始化 Line Bot 和 Redis
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
redis_client = Redis.from_url(REDIS_URL, decode_responses=True)
cipher = Fernet(os.getenv("FERNET_KEY", Fernet.generate_key()))  # Fly.io Secrets 提供 key

# 速率限制
limiter = Limiter(app=app, key_func=get_remote_address, default_limits=["10 per minute"])

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

@handler.add(MessageEvent, message=TextMessage)
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
                reply_token,
                TextSendMessage(text="哈哈，小童把你的命盤清空啦！點「開始算命」重新來過吧！", quick_reply=QuickReply(items=[
                    QuickReplyButton(action=MessageAction(label="開始算命", text="開始算命")),
                    QuickReplyButton(action=MessageAction(label="取消", text="取消"))
                ]))
            )
            return

        # 取消命令
        if text == "取消":
            redis_client.delete(user_id)
            line_bot_api.reply_message(reply_token, TextSendMessage(text="好吧，小童先下班啦！想算命再喊我哦！"))
            return

        # 開始算命入口
        if text in ["開始算命"]:
            session = {"step": 0}
            save_session(user_id, session)
            line_bot_api.reply_message(
                reply_token,
                TextSendMessage(text="嘿！笑命小童上線！請輸入您的姓名（純中文哦）：")
            )
            return

        # 新用戶或未啟動流程
        if not session:
            quick_reply = QuickReply(items=[
                QuickReplyButton(action=MessageAction(label="開始算命", text="開始算命")),
                QuickReplyButton(action=MessageAction(label="取消", text="取消"))
            ])
            line_bot_api.reply_message(
                reply_token,
                TextSendMessage(text="嘿！想讓笑命小童幫你算命嗎？點下方按鈕開始吧！", quick_reply=quick_reply)
            )
            return

        # 流程處理
        if session["step"] == 0:
            if not validate_name(text):
                line_bot_api.reply_message(reply_token, TextSendMessage(text="喂喂，姓名得是中文才行！別給我火星文，重新來！"))
                return
            session["name"] = text
            session["step"] = 1
            save_session(user_id, session)
            line_bot_api.reply_message(reply_token, TextSendMessage(text="姓名收到！請輸入您的出生日期（像 YYYY-MM-DD）："))
            return

        elif session["step"] == 1:
            if not validate_date(text):
                line_bot_api.reply_message(reply_token, TextSendMessage(text="哎喲，日期格式錯啦！請用 YYYY-MM-DD，比如 1990-01-01，再試哈哈！"))
                return
            session["birth_date"] = text
            session["step"] = 2
            save_session(user_id, session)
            line_bot_api.reply_message(reply_token, TextSendMessage(text="日期 OK！請輸入您的出生時間（HH，0-23）："))
            return

        elif session["step"] == 2:
            if not validate_time(text):
                line_bot_api.reply_message(reply_token, TextSendMessage(text="你確定你真的出生在這種時間？！"))
                return
            session["birth_time"] = text
            session["step"] = 3
            save_session(user_id, session)
            line_bot_api.reply_message(reply_token, TextSendMessage(text="時間收到！請輸入您的出生地（城市名）："))
            return

        elif session["step"] == 3:
            session["location"] = text
            session["step"] = 4

            # ==== 前處理 ====
            name_fivegrid = format_fivegrid_wuxing_prompt(session["name"])

            # 
            longitude, tz_name = get_location_coordinates_and_timezone(session["location"])

            year, month, day = map(int, session["birth_date"].split("-"))
            hour = int(session["birth_time"])

            bazi_result = format_bazi_report(year, month, day, hour, tz_name, longitude)

            session["background"] = f"{name_fivegrid}\n\n{bazi_result}"

            save_session(user_id, session)
            line_bot_api.reply_message(reply_token, TextSendMessage(text="資料已收集完成，請告訴我您想詢問的問題。"))
            return

        elif session["step"] == 4:
            user_question = text
            rag_input = f"{session['background']}\n\n使用者問題：{user_question}"
            answer = run_rag_pipeline(rag_input)
            line_bot_api.reply_message(reply_token, TextSendMessage(text=answer))
            return

    except LineBotApiError as e:
        logger.error("LineBotApi error: %s", str(e))
        line_bot_api.reply_message(reply_token, TextSendMessage(text="哎喲，小童的Line訊號被外星人搶走啦！稍後再試哈哈！"))
    except Exception as e:
        logger.error("Handle message error: %s", str(e))
        line_bot_api.reply_message(reply_token, TextSendMessage(text="哈哈，小童的算命攤出包啦！請再試一次！"))

if __name__ == "__main__":
    app.run(port=5000, debug=True)