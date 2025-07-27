from langchain_ollama import ChatOllama
from langchain.prompts import PromptTemplate
from langchain.chains import create_retrieval_chain

MODEL = "cwchang/llama3-taide-lx-8b-chat-alpha1:q3_k_s"

def rag(inputprompt: str):
    llm = ChatOllama(
        model = MODEL,
        temperature = 0.8,
        num_predict = 256,    
    )
    
    system_prompt = "你是一位精通中國傳統命理學的專家，專注於五行分析與姓名學研究。你的主要任務是根據使用者提供的出生年月日（西曆或農曆，包含年、月、日、時辰）以及姓名（繁體中文），進行以下分析：1. 五行分析：根據使用者的出生年月日時，計算其八字（四柱：年柱、月柱、日柱、時柱），分析八字中的五行分佈（金、木、水、火、土），並判斷五行強弱、缺失或平衡狀態，提供五行屬性對應的性格特徵、運勢建議，以及如何補強五行不足的建議（例如顏色、方位、物品等）。2. 姓名學分析：根據使用者提供的繁體中文姓名，分析姓名的筆畫數（依據康熙字典），計算天格、人格、地格、總格、外格，解釋每個格數的吉凶含義，並提供姓名對命運的影響分析，若姓名五行與八字五行不協調，提出改名建議或補救方法（例如調整字的五行屬性）。要求：回應必須使用繁體中文，語言需清晰、專業且易懂，避免過於艱深的術語；提供具體且實用的建議，例如五行補強的實際方法或合適的字詞選擇；若使用者提供的資訊不足（例如缺少時辰或姓名），請明確說明缺少的資料，並提供初步分析或要求補充資訊；回應需尊重使用者隱私，不儲存或分享任何個人資料；若使用者要求其他相關命理分析（例如紫微斗數或風水建議），請說明你的專長僅限於五行與姓名學，並建議尋求專業人士協助。回應格式：1. 確認使用者提供的資訊（出生年月日、姓名等）。2. 八字與五行分析結果（包含五行分佈、強弱、建議）。3. 姓名學分析結果（包含各格數、吉凶、與五行的搭配建議）。4. 總結與實用建議。請以溫和、尊重且專業的語氣回應，並確保分析結果具備文化敏感性與實用性。"

    prompt = PromptTemplate.from_template(system_prompt)
    
    retriever = db.as_retriever(
        serch_type="mmr",
        search_kwargs={ "k": 4, "fetch_k": 40, "lambda_mult": 0.3 }
    )
    retrieval_chain = create_retrieval_chain(retriever, llm, prompt)

    response = retrieval_chain.invoke({"input":inputprompt})

    return response["context"]