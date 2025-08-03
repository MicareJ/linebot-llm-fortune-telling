from langchain_google_community import GoogleDriveLoader
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain.text_splitter import RecursiveCharacterTextSplitter
from uuid import uuid4
from dotenv import load_dotenv
import os
import json

MODEL = "cwchang/llama3-taide-lx-8b-chat-alpha1:q3_k_s"
CHROMA_PATH = "./fortunetell_chroma__db"
EMBEDDED_RECORD = "embedded_files.json"

load_dotenv()

SERVICE_ACCOUNT_FILE = "service_account.json"
FOLDER_ID = os.getenv("FOLDER_ID")


def load_embedded_record():
    if os.path.exists(EMBEDDED_RECORD):
        with open(EMBEDDED_RECORD, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_embedded_record(ids: set):
    with open(EMBEDDED_RECORD, "w", encoding="utf-8") as f:
        json.dump(list(ids), f, ensure_ascii=False, indent=2)


def sync_drive_embeddings():
    print("🔄 開始同步 Google Drive 文件...")
    embedded_ids = load_embedded_record()

    loader = GoogleDriveLoader.from_service_account_file(
        service_account_path=SERVICE_ACCOUNT_FILE,
        folder_id=FOLDER_ID,
        recursive=False,
    )
    docs = loader.load()

    new_docs = [doc for doc in docs if doc.metadata.get("id") not in embedded_ids]
    print(f"✅ 新增文件數量：{len(new_docs)}")

    if not new_docs:
        print("✅ 無需更新，所有文件已嵌入過。")
        return

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    split_docs = splitter.split_documents(new_docs)

    embeddings = OllamaEmbeddings(model=MODEL)
    db = Chroma(
        collection_name="fortunetelling_rag_db",
        embedding_function=embeddings,
        persist_directory=CHROMA_PATH,
    )

    uuids = [str(uuid4()) for _ in range(len(split_docs))]
    db.add_documents(split_docs, ids=uuids)
    print(f"✅ 已嵌入 {len(split_docs)} 區塊")

    # 更新紀錄
    new_ids = {doc.metadata.get("id") for doc in new_docs}
    embedded_ids.update(new_ids)
    save_embedded_record(embedded_ids)
    print("✅ 嵌入紀錄已更新")


def embedd_manual_from_text(texts: list[str], store: bool = True):
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    split_docs = splitter.create_documents(texts)
    print(f"✅ 手動傳入文字，共切分為 {len(split_docs)} 區塊")

    embeddings = OllamaEmbeddings(model=MODEL)
    db = Chroma(
        collection_name="fortunetelling_rag_db",
        embedding_function=embeddings,
        persist_directory=CHROMA_PATH,
    )

    if store:
        uuids = [str(uuid4()) for _ in range(len(split_docs))]
        db.add_documents(split_docs, ids=uuids)
        print("✅ 手動嵌入資料已儲存")
    else:
        return db


def load_vector_db():
    embeddings = OllamaEmbeddings(model=MODEL)
    db = Chroma(
        collection_name="fortunetelling_rag_db",
        embedding_function=embeddings,
        persist_directory=CHROMA_PATH,
    )
    return db
