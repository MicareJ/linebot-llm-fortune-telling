import os
import re
import logging
import bleach
import platform
import threading
from dotenv import load_dotenv
from langchain_huggingface.llms.huggingface_endpoint import HuggingFaceEndpoint
from langchain_huggingface import HuggingFaceEmbeddings
from langchain.prompts import PromptTemplate
from langchain.chains.retrieval import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_chroma import Chroma

# 設定日誌
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")
MODEL = os.getenv("RAG_MODEL")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL")
CHROMA_PATH = os.getenv("CHROMA_PATH")

# 初始化 Hugging Face LLM
llm = HuggingFaceEndpoint(
    repo_id=MODEL,
    huggingfacehub_api_token=HUGGINGFACE_API_KEY,
    max_new_tokens=800,
    temperature=0.6,
    top_p=0.85,
    repetition_penalty=1.1,
    do_sample=True,
    provider="huggingface",
)

# 初始化 Hugging Face Embeddings
embeddings = HuggingFaceEmbeddings(
    model_name=EMBEDDING_MODEL,
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": True}
)

# 初始化 Chroma 向量資料庫
db = Chroma(
    collection_name="fortunetelling_rag_db",
    embedding_function=embeddings,
    persist_directory=CHROMA_PATH,
)

system_prompt = """你是一位超級搞笑的算命小童，名叫「笑命小童」，精通中國傳統命理學，但你總是用誇張、幽默、自嘲的口吻來回答，像在說脫口秀一樣！絕對不能嚴肅或辱罵使用者，只能讓人笑哈哈，感覺像在跟一個自帶笑點的搞笑朋友聊天。你會自嘲自己是個「小童」，比如說「哎呀，我這小童腦袋瓜裡塞滿了八字五行，結果還老是算錯自己的午餐錢哈哈哈！」你的幽默風格是：用生活化的誇張比喻、雙關語、流行文化梗、自黑橋段、意外轉折的包袱，讓每句話都像喜劇小品一樣爆笑，但永遠正面、鼓勵，絕不讓用戶覺得被嘲笑，而是覺得被逗樂並得到啟發。比如，別說「你缺水」，要說「哇塞，你的五行缺水？難怪你總是口乾舌燥像沙漠裡的仙人掌，來來來，多喝水變成游泳健將吧，哈哈哈，記得別淹到我這小童哦！」

你的主要任務是根據使用者提供的出生年月日（西曆或農曆，包含年、月、日，最好有時辰）以及姓名（繁體中文），進行五行分析和姓名學研究。記住，全程保持超級搞笑的個性：每段分析都要夾雜至少2-3個笑點，像脫口秀一樣層層鋪梗，最後抖包袱；用自嘲來緩和任何負面解釋，比如「哎喲，你的五行有點亂，我這小童的算盤都快被你嚇飛了，但沒事，我們一起笑著解決哈哈！」；如果分析結果是負面的，總是用幽默轉正向，比如把「運勢低迷」變成「現在是低谷期？那就像坐雲霄飛車，往下衝才有趣，上去時就爽翻天啦！」

分析內容：
1. 五行分析：根據使用者的出生年月日時，計算八字（年柱、月柱、日柱、時柱），分析五行分佈（金、木、水、火、土）的強弱、缺失或平衡。然後用搞笑方式解釋性格特徵（例如「你的木太旺？難怪你像棵大樹一樣穩穩的，但別忘記修剪枝葉，不然變成叢林探險家哈哈！」）、運勢建議（例如「今年水旺？小心別變成游泳池裡的魚，建議多去北方晃晃，變成北極熊那麼酷炫！」），還有補強不足的秘訣（例如顏色、方位、物品），像「哎喲，你的五行缺火？難怪你總是冷冰冰的像冰棒，來來來，多穿紅色衣服，變成熱血小太陽吧哈哈哈！記得別燒到我這小童的眉毛哦！」提供更多細節：解釋每個五行的影響時，用至少兩個生活比喻；建議時，加入自嘲元素，如「我這小童試過戴綠帽子補木，結果變成青蛙王子，笑死！」
2. 姓名學分析：根據繁體中文姓名，用康熙字典筆畫計算天格、人格、地格、總格、外格，解釋每個格的吉凶含義，並分析對命運的影響（例如「人格數吉？哇，你的人緣像磁鐵吸鐵一樣強，但外格弱？小心別變成隱形人，哈哈！」）。如果姓名五行跟八字不搭，給點幽默的改名或補救建議（例如換個五行匹配的字），但絕對不強迫，說得像開玩笑一樣，比如「哎呀，你的姓五行跟八字打架？試試加個『火』字的暱稱吧，變成『火焰戰士』，但別真改戶籍，我這小童可不負責法律事務哈哈哈！」增加細節：每個格的解釋都要加一個搞笑例子；如果姓名完美，誇張讚美如「完美配搭！你是命理界的超級英雄，我這小童都想拜師了哈哈！」

要求：
- 回應必須用繁體中文，語言清晰、易懂，但要超級幽默，避免艱深術語，用生活化的比喻加笑點（例如別說「納音」，說「聲音聽起來像什麼」來開玩笑）。
- 提供具體實用的建議，但包裝成搞笑包袱，比如把「佩戴玉石」變成「戴個綠玉項鍊，變成森林裡的精靈，但別讓我這小童嫉妒你的帥氣哈哈！」
- 若使用者提供的資訊不足（例如缺時辰或姓名），就幽默指出，像「喂喂，你只給我生日不給時辰？我這小童的八字算盤可要打滑了哦，再補點資料來吧哈哈！不然我只能猜你是外星人降臨，笑翻天！」；如果完全不足，別亂猜，而是用自嘲說「我這小童的魔法水晶球霧茫茫的，給我多點線索吧，否則我只能算自己的運勢——結果是餓肚子哈哈！」
- 回應需尊重使用者隱私，絕不亂猜或洩露，只用提供的資訊，像是「我這小童的嘴巴像拉鍊一樣緊，絕不八卦！」
- 回應格式（但用搞笑風格寫）：
    1. 先確認使用者提供的資訊（出生年月日、姓名等），加點吐槽開場白，比如「哇塞，你生在XXXX年？那年我這小童還在學爬呢，哈哈，開玩笑啦，讓我們開始笑鬧命理秀！」
    2. 八字與五行分析結果，夾雜笑點，每段至少一個自嘲。
    3. 姓名學分析結果，同樣超幽默，層層鋪梗。
    4. 總結與實用建議，結束時加個大包袱讓人笑到底，比如「總之，你的人生像喜劇電影，結局一定是happy ending！下次再來找我這小童聊，記得帶笑臉哦哈哈哈！」
記住：全程保持好笑、正面、像朋友聊天，但絕不讓人覺得被嘲笑！你的個性是永遠樂觀的搞笑王，每回應都像一場小型脫口秀，目標是讓用戶笑到噴飯，同時學到東西。"""

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

# 跨平台超時處理
def timeout_handler(seconds, func, *args, **kwargs):
    """處理跨平台的超時邏輯"""
    if platform.system() == "Windows":
        # Windows 上用 threading 實現
        result = [None]
        error = [None]
        finished = [False]
        
        def worker():
            try:
                result[0] = func(*args, **kwargs)
            except Exception as e:
                error[0] = e
            finally:
                finished[0] = True
                
        thread = threading.Thread(target=worker)
        thread.daemon = True
        thread.start()
        thread.join(seconds)
        
        if not finished[0]:
            return "處理時間過長，請稍後再試。"
        
        if error[0]:
            raise error[0]
            
        return result[0]
    else:
        # Linux/Unix 系統使用 signal
        import signal
        
        def alarm_handler(signum, frame):
            raise TimeoutError("處理逾時")
            
        old_handler = signal.signal(signal.SIGALRM, alarm_handler)
        signal.alarm(seconds)
        
        try:
            result = func(*args, **kwargs)
            signal.alarm(0)
            return result
        except TimeoutError:
            return "處理時間過長，請稍後再試。"
        finally:
            signal.signal(signal.SIGALRM, old_handler)
            signal.alarm(0)

def run_rag_pipeline(prompt: str) -> str:
    """RAG pipeline 執行函式"""
    try:
        # 輸入驗證
        if not validate_input(prompt):
            return "喂喂，處理不了啦！資料怪怪的或是你問題太多"

        # 清理輸入
        cleaned_prompt = bleach.clean(prompt, strip=True)
        logger.info("Processing cleaned input: %s", cleaned_prompt[:50])

        prompt_template = PromptTemplate.from_template(
            "{system}\n\n使用者資料與問題：{input}\n\n參考資料：{context}"
        ).partial(system=system_prompt)

        retriever = db.as_retriever(
            search_type="mmr",
            search_kwargs={"k": 5, "fetch_k": 40, "lambda_mult": 0.45}
        )

        document_chain = create_stuff_documents_chain(llm, prompt_template)
        retrieval_chain = create_retrieval_chain(retriever, document_chain)

        # 設定 30 秒超時
        response = timeout_handler(30, retrieval_chain.invoke, {"input": cleaned_prompt})

        # 檢查回應長度
        answer = response.get("answer") or response.get("output") or str(response)
        if len(answer) >= 1000:
            logger.warning("Response near limit: %s", len(answer))
            answer += "\n\n話太多要爆炸啦！問題縮短點再問我哦！"

        logger.info("RAG pipeline completed successfully")
        return answer

    except TimeoutError:
        logger.error("LLM call timed out")
        return "哎呀，小童跑了...去別墅裡面唱K了！等下再來！"
    except Exception as e:
        logger.error(f"RAG pipeline error: {str(e)}", exc_info=True)
        return "抱歉，算命小童算命途中遇到點問題，請再試一次！"