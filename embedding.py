from langchain_google_community import GoogleDriveLoader
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain.text_splitter import RecursiveCharacterTextSplitter
from uuid import uuid4
from dotenv import load_dotenv
import os

MODEL = "cwchang/llama3-taide-lx-8b-chat-alpha1:q3_k_s"
TOKEN_PATH = ".credentials\token.json"


def embeddinng(store: bool):
    # Load environment variables from .env file
    load_dotenv()

    loader = GoogleDriveLoader(
        folder_id = os.getenv("FOLDER_ID"),
        token_path = TOKEN_PATH,
        recursive=False,
    )
    docs = loader.load()
    print(f"Loaded {len(docs)} PDF files from Google Drive.")

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    split_docs = splitter.split_documents(docs)

    print(f"Loaded and split {len(split_docs)} documents from the PDF.")
    
    embeddings = OllamaEmbeddings(model=MODEL)
    
    db = Chroma(
        collection_name="fortunetelling_rag_db",
        embedding_function=embeddings,
        persist_directory="./fortunetell_chroma__db",
    )
    
    if store:
        uuids = [str(uuid4()) for _ in range(len(split_docs))]
        db.add_documents(split_docs, ids = uuids)

    else: 
        return db
