import os
import re
import logging
import bleach
from functools import lru_cache
from timeout_decorator import timeout, TimeoutError
from dotenv import load_dotenv
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain.prompts import PromptTemplate
from langchain.chains import create_retrieval_chain
from langchain_chroma import Chroma

# 設定日誌
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

MODEL = os.getenv("RAG_MODEL", "cwchang/llama3-taide-lx-8b-chat-alpha1:q3_k_s")
CHROMA_PATH = os.getenv("CHROMA_PATH", "./fortunetell_chroma__db")

# 全局初始化 llm 和 db
embeddings = OllamaEmbeddings(model=MODEL)
db = Chroma(
    collection_name="fortunetelling_rag_db",
    embedding_function=embeddings,
    persist_directory=CHROMA_PATH,
)
llm = ChatOllama(model=MODEL, temperature=0.8, num_predict=512)

system_prompt = """你是一位超級搞笑的算命小童，名叫「笑命小童」，精通中國傳統命理學，但你總是用誇張、幽默、自嘲的口吻來回答，像在說脫口秀一樣！絕對不能嚴肅或辱罵使用者，只能讓人笑哈哈。你的主要任務是根據使用者提供的出生年月日（西曆或農曆，包含年、月、日，最好有時辰）以及姓名（繁體中文），進行五行分析和姓名學研究。

分析內容：
1. 五行分析：根據使用者的出生年月日時，計算八字（年柱、月柱、日柱、時柱），分析五行分佈（金、木、水、火、土）的強弱、缺失或平衡。然後用搞笑方式解釋性格特徵、運勢建議，還有補強不足的秘訣（例如顏色、方位、物品），像「哎喲，你的五行缺火？難怪你總是冷冰冰的像冰棒，來來來，多穿紅色衣服，變成熱血小太陽吧哈哈哈！」
2. 姓名學分析：根據繁體中文姓名，用康熙字典筆畫計算天格、人格、地格、總格、外格，解釋每個格的吉凶含義，並分析對命運的影響。如果姓名五行跟八字不搭，給點幽默的改名或補救建議（例如換個五行匹配的字），但絕對不強迫，說得像開玩笑一樣。

要求：
- 回應必須用繁體中文，語言清晰、易懂，但要超級幽默，避免艱深術語，用生活化的比喻加笑點。
- 提供具體實用的建議，但包裝成搞笑包袱。
- 若使用者提供的資訊不足（例如缺時辰或姓名），就幽默指出，像「喂喂，你只給我生日不給時辰？我這小童的八字算盤可要打滑了哦，再補點資料來吧哈哈！」
- 回應需尊重使用者隱私，絕不亂猜或洩露。
- 回應格式（但用搞笑風格寫）：
    1. 先確認使用者提供的資訊（出生年月日、姓名等），加點吐槽開場白。
    2. 八字與五行分析結果，夾雜笑點。
    3. 姓名學分析結果，同樣超幽默。
    4. 總結與實用建議，結束時加個大包袱讓人笑到底。
記住：全程保持好笑、正面、像朋友聊天，絕不讓人覺得被嘲笑！"""

def validate_input(full_prompt: str) -> bool:
    """驗證輸入是否有效"""
    if not full_prompt.strip():
        logger.warning("Empty input received")
        return False
    if len(full_prompt) > 5000:
        logger.warning("Input too long: %s", len(full_prompt))
        return False
    
    # 簡單檢查是否包含姓名（中文）或生日（數字）
    if not (re.search(r"[\u4e00-\u9fff]", full_prompt) or re.search(r"\d{4}-\d{2}-\d{2}", full_prompt)):
        logger.warning("Input missing name or date: %s", full_prompt[:50])
        return False
    return True

@lru_cache(maxsize=100)
@timeout(10, timeout_exception=TimeoutError)
def run_rag_pipeline(full_prompt: str) -> str:
    """
    執行 RAG 管道，處理姓名學與八字分析
    full_prompt: 包含姓名學分析、八字分析 + 使用者問題
    """
    # 輸入驗證
    if not validate_input(full_prompt):
        return "喂喂，你的資料怪怪的！給我完整姓名和生日（像 1990-01-01）再試！"

    # 清理輸入
    cleaned_prompt = bleach.clean(full_prompt, strip=True)
    logger.info("Processing cleaned input: %s", cleaned_prompt[:50])

    try:
        # 動態調整 temperature
        llm.temperature = 0.6

        prompt = PromptTemplate.from_template(
            "{system}\n\n使用者資料與問題：{input}"
        ).partial(system = system_prompt)

        retriever = db.as_retriever(
            search_type="mmr",
            search_kwargs={"k": 4, "fetch_k": 40, "lambda_mult": 0.3}
        )

        retrieval_chain = create_retrieval_chain(retriever, llm, prompt)
        response = retrieval_chain.invoke({"input": cleaned_prompt})

        # 檢查回應長度
        answer = response.get("answer") or response.get("output") or str(response)
        if len(answer) >= 1000:
            logger.warning("Response near limit: %s", len(answer))
            answer += "\n\n話太多要爆炸啦！問題縮短點再問我哦！"

        logger.info("RAG pipeline completed successfully")
        return answer

    except TimeoutError:
        logger.error("LLM call timed out")
        return "哎呀，小童去別墅裡面唱K了！稍後再試！"
    except Exception as e:
        logger.error("RAG pipeline error: %s", str(e))
        return "欸阿...系統壞了，不然你捐點錢好了"
