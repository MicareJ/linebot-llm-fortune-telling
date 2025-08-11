from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from rag import rag
from rag.embedding import sync_drive_embeddings

import os
from dotenv import load_dotenv

# 載入 .env（本地開發會用，Railway 會直接使用環境變數）
load_dotenv()

# 初始化 Flask 應用
app = Flask(__name__)

# 讀取 LINE 憑證（來自 .env 或 Railway 環境變數）
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

# 初始化 LINE Bot API
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

@app.route("/callback", methods=["POST"])
def callback():
    # 驗證 X-Line-Signature
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"

# 接收文字訊息並回應
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_input = event.message.text
    try:
        rag_response = rag(user_input)
        reply_text = rag_response if isinstance(rag_response, str) else str(rag_response)
    except Exception as e:
        reply_text = f"發生錯誤，請稍後再試。\n{str(e)}"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

@app.route("/sync", methods=["POST"])
def sync_handler():
    try:
        sync_drive_embeddings()
        return {"status": "success"}, 200
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500
    
# 本地 or Railway 執行點
if __name__ == "__main__":
    # 若有 base64 格式的 GDRIVE_SERVICE_ACCOUNT_B64，寫出 json 憑證
    service_account_b64 = os.getenv("GDRIVE_SERVICE_ACCOUNT_B64")
    if service_account_b64:
        import base64
        with open("service_account.json", "wb") as f:
            f.write(base64.b64decode(service_account_b64))

    port = int(os.environ.get("PORT", 5000))  # Railway 會傳入 PORT，預設為 5000
    app.run(host="0.0.0.0", port=port)