# main_app.py

import os
import re
from datetime import datetime
import requests
from flask import Flask, request, abort
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from linebot.v3.webhook import WebhookHandler
from linebot.v3.messaging import (
    MessagingApi, Configuration, ApiClient,
    TextMessage, QuickReply, QuickReplyItem, MessageAction,
    ApiException, ErrorResponse, ReplyMessageRequest
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.exceptions import InvalidSignatureError

from core.logger_config import setup_logger
from core.session_manager import SessionManager
from core.rag import rag_system
from util.name_fivegrid_wuxing import format_fivegrid_wuxing_prompt
from util.bazi_true_solar import format_bazi_report

# --- 初始化 ---
logger = setup_logger('app')
app = Flask(__name__)

# --- 環境變數與設定 ---
class AppConfig:
    LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
    REDIS_URL = os.getenv("REDIS_URL")
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    REQUESTS_TIMEOUT = 10  # 統一外部 API 呼叫的超時時間

config = AppConfig()
limiter = Limiter(app=app, key_func=get_remote_address, default_limits=["10 per minute"], storage_uri=config.REDIS_URL)

# Line Bot API
line_config = Configuration(access_token=config.LINE_CHANNEL_ACCESS_TOKEN)
line_api_client = ApiClient(line_config)
line_bot_api = MessagingApi(line_api_client)
handler = WebhookHandler(config.LINE_CHANNEL_SECRET)

# Session Manager
session_manager = SessionManager()

# --- 輸入驗證函式 ---
def validate_name(name: str) -> bool:
    if len(name) < 2:
        return False
    return bool(re.match(r"^[\u4e00-\u9fff]+$", name))

def validate_date(date: str) -> bool:
    try:
        datetime.strptime(date, "%Y-%m-%d")
        return True
    except ValueError:
        return False

def validate_time(time: str) -> bool:
    try:
        return 0 <= int(time) <= 23
    except (ValueError, TypeError):
        return False

# --- 外部服務呼叫 ---
def get_location_coordinates_and_timezone(location: str) -> tuple[float, str]:
    DEFAULT_LNG = 121.5654
    DEFAULT_TZ = "Asia/Taipei"

    try:
        geo_url = f"https://maps.googleapis.com/maps/api/geocode/json?address={location}&key={config.GOOGLE_API_KEY}"
        geo_response = requests.get(geo_url, timeout=config.REQUESTS_TIMEOUT)
        geo_response.raise_for_status() # 檢查 HTTP 錯誤
        geo_data = geo_response.json()

        if geo_data.get('status') == 'OK':
            result = geo_data['results'][0]['geometry']['location']
            lat, lng = result['lat'], result['lng']
            
            timestamp = int(datetime.now().timestamp())
            tz_url = f"https://maps.googleapis.com/maps/api/timezone/json?location={lat},{lng}&timestamp={timestamp}&key={config.GOOGLE_API_KEY}"
            tz_response = requests.get(tz_url, timeout=config.REQUESTS_TIMEOUT)
            tz_response.raise_for_status()
            tz_data = tz_response.json()

            if tz_data.get('status') == 'OK':
                return lng, tz_data['timeZoneId']
    
    except requests.exceptions.RequestException as e:
        logger.error("Geocode/Timezone API request failed: %s", e)
    except Exception as e:
        logger.error("An unexpected error occurred in Geocode/Timezone lookup: %s", e)

    logger.warning("Falling back to default location for address: %s", location)
    return DEFAULT_LNG, DEFAULT_TZ


# ===== 狀態模式 (State Pattern) 來建構對話流程 =====
class StateHandler:
    """狀態處理器的基底類別"""
    def __init__(self, user_id, text, session, reply_token):
        self.user_id = user_id
        self.text = text
        self.session = session
        self.reply_token = reply_token

    def handle(self):
        raise NotImplementedError

    def _reply_text(self, message):
        line_bot_api.reply_message(
            ReplyMessageRequest(reply_token=self.reply_token, messages=[TextMessage(text=message)])
        )

    def _save_and_set_step(self, step):
        self.session["step"] = step
        session_manager.save(self.user_id, self.session) 

# 不同對話階段的處理機制。沒有問題step會繼續遞增，回應有問題會停在同一個step
class NameHandler(StateHandler):
    def handle(self):
        if not validate_name(self.text):
            self._reply_text("你的名字跟我家隔壁的柯基沒兩樣，重打一次！")
            return
        self.session["name"] = self.text
        self._save_and_set_step(1)
        self._reply_text("生日幾號（YYYY-MM-DD）")

class BirthDateHandler(StateHandler):
    def handle(self):
        if not validate_date(self.text):
            self._reply_text("欸！再皮叫你自生自滅")
            return
        self.session["birth_date"] = self.text
        self._save_and_set_step(2)
        self._reply_text("OK！你幾點出生的（0-23）")

class BirthTimeHandler(StateHandler):
    def handle(self):
        if not validate_time(self.text):
            self._reply_text("你要確定欸？！")
            return
        self.session["birth_time"] = self.text
        self._save_and_set_step(3)
        self._reply_text("那你媽在哪把你生出來的？")

class LocationHandler(StateHandler):
    def handle(self):
        self.session["location"] = self.text
        name_fivegrid = format_fivegrid_wuxing_prompt(self.session["name"])
        longitude, tz_name = get_location_coordinates_and_timezone(self.session["location"])
        year, month, day = map(int, self.session["birth_date"].split("-"))
        hour = int(self.session["birth_time"])
        bazi_result = format_bazi_report(year, month, day, hour, tz_name, longitude)
        self.session["background"] = f"{name_fivegrid}\n\n{bazi_result}"
        self._save_and_set_step(4)
        self._reply_text("好啦說啦！你想問什麼")

class QuestionHandler(StateHandler):
    def handle(self):
        rag_input = f"{self.session.get('background', '')}\n\n使用者問題：{self.text}"
        answer, updated_session = rag_system.generate_response(
            user_id=self.user_id, prompt=rag_input, session=self.session
        )
        session_manager.save(self.user_id, updated_session) # 使用 session_manager
        self._reply_text(answer)

# 狀態映射表
STATE_HANDLERS = {
    0: NameHandler, 1: BirthDateHandler, 2: BirthTimeHandler,
    3: LocationHandler, 4: QuestionHandler,
}


# --- Webhook 主處理邏輯 ---
@app.route("/callback", methods=["POST"])
@limiter.limit("10 per minute")
def callback():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.warning("Invalid signature. Check channel secret.")
        abort(400)
    except Exception as e:
        logger.error("Error occurred in webhook handler: %s", e)
        abort(500)
    return "OK"

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text.strip()
    reply_token = event.reply_token

    try:
        if text == "開始！":
            session = {"step": 0}
            session_manager.save(user_id, session) 
            line_bot_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text="煩欸又要上班了！你叫什麼名字啦")]))
            return
        
        if text == "差不多啦！":
            session_manager.clear(user_id) 
            line_bot_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text="Yes！下班！")]))
            return

        # 載入先前沒有結束的對話
        session = session_manager.load(user_id)

        if not session:
            quick_reply = QuickReply(items=[
                QuickReplyItem(action=MessageAction(label="開始算命", text="開始！")),
                QuickReplyItem(action=MessageAction(label="取消", text="取消"))
            ])
            line_bot_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text="貨出的去，錢進得來，你會發大財！點下方按鈕開始吧", quick_reply=quick_reply)]))
            return

        # 對話狀態處理機
        step = session.get("step")
        Handler = STATE_HANDLERS.get(step)

        if Handler:
            handler_instance = Handler(user_id, text, session, reply_token)
            handler_instance.handle()
        else:
            logger.warning("No handler found for step %s for user %s. Resetting session.", step, user_id)
            session_manager.clear(user_id) 
            line_bot_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text="哎呀，好像有點問題，我們重新開始吧！")]))
        
    except ApiException as e:
        logger.error("LINE Messaging API error: %s\nBody: %s", e, e.body)
        
    except Exception as e:
        logger.exception("An unhandled error occurred in handle_message for user %s", user_id)
        
        try:
            line_bot_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text="靠！哪個工程師寫的爛軟體，出問題了啦")]))
        except Exception as api_err:
            logger.error("Failed to even send error message to user %s: %s", user_id, api_err)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)