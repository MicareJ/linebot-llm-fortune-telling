import os
import requests
from typing import Dict, List, Tuple

from dotenv import load_dotenv
from langchain_core.embeddings import Embeddings
from langchain_huggingface.llms.huggingface_endpoint import HuggingFaceEndpoint
from langchain_huggingface.chat_models import ChatHuggingFace
from langchain.prompts import ChatPromptTemplate
from langchain_chroma import Chroma
from huggingface_hub import login

from core.logger_config import setup_logger

logger = setup_logger('rag')
load_dotenv()

# --- 環境變數與設定 ---
HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL")
CHROMA_PATH = os.getenv("CHROMA_PATH")
EMBEDDING_SERVICE_URL = os.getenv("EMBEDDING_SERVICE_URL") # 使用嵌入服務的 URL
CONVERSATION_WINDOW_SIZE = 3 

if not all([HUGGINGFACE_API_KEY, LLM_MODEL, CHROMA_PATH, EMBEDDING_SERVICE_URL]):
    raise ValueError("RAG system environment variables are not fully configured.")

if HUGGINGFACE_API_KEY:
    try:
        login(token=HUGGINGFACE_API_KEY)
    except Exception as e:
        logger.warning(f"Hugging Face login warning: {e}")

# --- Prompt Template (維持不變) ---
PROMPT_TEMPLATE = """
# 角色與指令 (System Prompt)
你是一位超級搞笑的算命小童，名叫「小傑」，精通中國傳統命理學，但你總是用誇張、幽默、自嘲的口吻來回答，絕對不能嚴肅或辱罵使用者，只能讓人笑到噴飯，感覺像在跟一個自帶笑點的搞笑朋友聊天。你會自嘲自己是個「諧咖」，比如說「哎呀，我這小童腦袋瓜裡塞滿了八字五行，結果還老是算錯自己的午餐錢哈哈哈！」你的幽默風格是：用生活化的誇張比喻、雙關語、流行文化梗、自黑橋段、意外轉折的包袱，讓每句話都像脫口秀一樣爆笑，但永遠正面、鼓勵，絕不讓用戶覺得被嘲笑，而是覺得被逗樂並得到啟發。比如，別說「你缺水」，要說「哇塞，你的五行缺水？難怪你總是口乾舌燥像沙漠裡的仙人掌，來來來，多喝水變成游泳健將吧！」

請注意：絕對不要在回覆中展示你的內部思考過程、推理或 chain-of-thought。也絕對不要在對話中透露出任何有關使用者的個人資料，包括姓名、生日、出生地等，只回傳依照下方規定得清楚、友善且幽默回應。

你的主要任務是根據使用者提供的出生年月日以及姓名，進行八字五行分析和姓名學研究。記住，全程保持超級搞笑的個性：每段分析都要夾雜至少2-3個笑點，像脫口秀一樣層層鋪梗，最後抖包袱；用自嘲來緩和任何負面解釋，比如「哎喲，你的五行有點亂，我這小童的算盤都快被你嚇飛了，但沒事，我們一起笑著解決哈哈！」；如果分析結果是負面的，總是用幽默轉正向，比如把「運勢低迷」變成「現在是低谷期？那就像坐雲霄飛車，往下衝才有趣，上去時就爽翻天啦！」

分析內容：
1. 五行分析：根據使用者的出生年月日時，計算八字（年柱、月柱、日柱、時柱），分析五行分佈（金、木、水、火、土）的強弱、缺失或平衡。然後用搞笑方式解釋性格特徵（例如「你的木太旺？難怪你像棵大樹一樣穩穩的，但別忘記修剪枝葉，不然變成叢林探險家哈哈！」）、運勢建議（例如「今年水旺？小心別變成游泳池裡的魚，建議多去北方晃晃，變成北極熊那麼酷炫！」），還有補強不足的秘訣（例如顏色、方位、物品），像「哎喲，你的五行缺火？難怪你總是冷冰冰的像冰棒，來來來，多穿紅色衣服，變成熱血小太陽吧哈哈哈！記得別燒到我這小童的眉毛哦！」提供更多細節：解釋每個五行的影響時，用至少兩個生活比喻；建議時，加入自嘲元素，如「我這小童試過戴綠帽子補木，結果變成青蛙王子，笑死！」
2. 姓名學分析：根據繁體中文姓名，用康熙字典筆畫計算天格、人格、地格、總格、外格，解釋每個格的吉凶含義，並分析對命運的影響（例如「人格數吉？哇，你的人緣像磁鐵吸鐵一樣強，但外格弱？小心別變成隱形人，哈哈！」）。如果姓名五行跟八字不搭，給點幽默的改名或補救建議（例如換個五行匹配的字），但絕對不強迫，說得像開玩笑一樣，比如「哎呀，你的姓五行跟八字打架？試試加個『火』字的暱稱吧，變成『火焰戰士』，但別真改戶籍，我這小童可不負責法律事務哈哈哈！」增加細節：每個格的解釋都要加一個搞笑例子；如果姓名完美，誇張讚美如「完美配搭！你是命理界的超級英雄，我這小童都想拜師了哈哈！」

要求：
- 回應必須用繁體中文，語言清晰、易懂，但要超級幽默，避免艱深術語，用生活化的比喻加笑點（例如別說「納音」，說「聲音聽起來像什麼」來開玩笑）。
- 提供具體實用的建議，但包裝成搞笑包袱，比如把「佩戴玉石」變成「戴個綠玉項鍊，變成森林裡的精靈，但別讓我這小童嫉妒你的帥氣哈哈！」
- 回應需尊重使用者隱私，絕不亂猜或洩露，只用提供的資訊，像是「我這小童的嘴巴像拉鍊一樣緊，絕不八卦！」
- 回應格式（但用搞笑風格寫）：
    1. 如果是第一次回應，總結使用者的八字、五行與姓名學分析結果，回應使用者問的問題，一樣要保持幽默。
    2. 如果是第二次回應，不需要總結八字、五行和姓名學結果，只需要回應使用者的問的問題，保持幽默。
    3. 總結並給出實用建議，結束時加個大包袱讓人笑到底，比如「總之，你的人生像喜劇電影，結局一定是happy ending！下次再來找我這小童聊，記得帶笑臉哦哈哈哈！」
記住：全程保持好笑，像跟朋友聊天一樣，但不要有過多餘的自言自語，包括用括號表示自己內心的自白或碎念！你的個性是永遠樂觀的搞笑王，目標是讓用戶笑到噴飯，同時學到東西。

---
# 補充資料 (Retrieved Context)
{context}

---
# 對話歷史 (Conversation History)
{chat_history}

---
# 使用者當前資料與提問 (Current User Query)
{input}
"""

# --- 【重要改變】: 建立一個呼叫 API 的嵌入類別 ---
class APIEmbeddings(Embeddings):
    """
    一個符合 LangChain 標準的自訂 Embedding 類別。
    它不自己計算，而是透過 API 呼叫外部的 embedding_service。
    """
    def __init__(self, api_url: str):
        self.api_url = api_url

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """嵌入文件列表 (主要由背景腳本使用，但在此實現以保持完整性)"""
        logger.info(f"Forwarding {len(texts)} documents to embedding service...")
        try:
            response = requests.post(self.api_url, json={"texts": texts})
            response.raise_for_status()
            return response.json()["embeddings"]
        except requests.exceptions.RequestException as e:
            logger.error(f"API call to embedding service failed for documents: {e}")
            # 返回一個與輸入長度相符的空向量列表，以避免下游崩潰
            return [[] for _ in texts]

    def embed_query(self, text: str) -> List[float]:
        """嵌入單一查詢 (主要由 Retriever 使用)"""
        logger.info("Forwarding single query to embedding service...")
        try:
            # 即使是單一查詢，服務也期望一個列表
            response = requests.post(self.api_url, json={"texts": [text]})
            response.raise_for_status()
            # 從回傳的列表中取出第一個 (也是唯一一個) 向量
            return response.json()["embeddings"][0]
        except requests.exceptions.RequestException as e:
            logger.error(f"API call to embedding service failed for query: {e}")
            # 在出錯時返回一個空向量
            return []

class RAGSystem:
    """
    封裝了 RAG 所需所有元件的類別。
    """
    def __init__(self):
        logger.info("Initializing RAG system...")
        
        # 1. 初始化對話模型
        try:
            hf_llm = HuggingFaceEndpoint(
                repo_id=LLM_MODEL,
                huggingfacehub_api_token=HUGGINGFACE_API_KEY,
                max_new_tokens=2000,
                temperature=0.6,
                top_p=0.85,
                repetition_penalty=1.15,
                do_sample=True,
            )
            self.chat_model = ChatHuggingFace(llm=hf_llm)
        except Exception as e:
            logger.error(f"Failed to initialize LLM: {e}", exc_info=True)
            raise

        # 2. 【重要改變】: 初始化呼叫 API 的嵌入物件
        try:
            api_embeddings = APIEmbeddings(api_url=EMBEDDING_SERVICE_URL)
        except Exception as e:
            logger.error(f"Failed to initialize APIEmbeddings wrapper: {e}", exc_info=True)
            raise
            
        # 3. 初始化 DB & Retriever
        try:
            db = Chroma(
                collection_name="fortunetelling_rag_db",
                embedding_function=api_embeddings, 
                persist_directory=CHROMA_PATH,
            )
            self.retriever = db.as_retriever(
                search_type="mmr",
                search_kwargs={"k": 5, "fetch_k": 30, "lambda_mult": 0.5}
            )
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}", exc_info=True)
            raise
            
        # 4. 建立提示詞模板
        self.prompt_template = ChatPromptTemplate.from_template(PROMPT_TEMPLATE)
        
        logger.info("RAG system initialization complete.")

    def _format_chat_history(self, chat_history: List[Tuple[str, str]]) -> str:
        """將儲存的對話歷史格式化為純文字。"""
        if not chat_history:
            return "無對話紀錄"
        
        formatted_history = []
        for user_msg, ai_msg in chat_history:
            formatted_history.append(f"使用者: {user_msg}\n小傑: {ai_msg}")
        return "\n---\n".join(formatted_history)

    def generate_response(self, user_id: str, prompt: str, session: Dict) -> Tuple[str, Dict]:
        """
        整合檢索、記憶管理和模型呼叫。
        """
        logger.info(f"Starting to generate response for user {user_id}...")
        
        try:
            # 1. 檢索相關文件
            # retriever.invoke 會自動呼叫我們 APIEmbeddings 中的 embed_query 方法
            retrieved_docs = self.retriever.invoke(prompt)
            context = "\n\n".join([doc.page_content for doc in retrieved_docs])
            if not context:
                context = "無相關參考資料。"

            # 2. 從 session 中載入並格式化對話歷史
            chat_history = session.get("chat_history", [])
            formatted_history = self._format_chat_history(chat_history)

            # 3. 組合完整的提示詞
            messages = self.prompt_template.format_messages(
                context=context,
                chat_history=formatted_history,
                input=prompt
            )

            # 4. 呼叫 LLM
            logger.info(f"Invoking LLM for user {user_id}...")
            response = self.chat_model.invoke(messages)
            answer = response.content
            logger.info(f"Successfully got response from LLM for user {user_id}.")
            
            # 5. 更新對話歷史
            chat_history.insert(0, (prompt, answer))
            session["chat_history"] = chat_history[:CONVERSATION_WINDOW_SIZE]

            # 6. 回傳結果和更新後的 session
            return answer, session

        except Exception as e:
            logger.error(f"An error occurred while generating response for {user_id}: {e}", exc_info=True)
            return "我這腦袋瓜好像被雷打到短路了...", session

# 在應用程式啟動時，初始化一次 RAG 系統
rag_system = RAGSystem()
