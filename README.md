<!-- Language Switcher -->
<p align="right">Language: English | <a href="./README_zh-TW.md">中文</a></p>

# Fortune-telling RAG LINE Bot

This project is a sophisticated, conversational AI chatbot designed for the LINE platform. It features a unique, humorous personality and provides insightful analysis based on user inputs. The system demonstrates how to build a modern, secure, and modular AI application by integrating Retrieval-Augmented Generation (RAG), secure session management, and independent background services.

## Core Features

- Engaging AI Personality: A meticulously crafted system prompt gives the AI a witty and entertaining personality, making user interactions enjoyable and memorable.

- RAG-Powered Knowledge Base: Leverages LangChain and ChromaDB to enable the AI to retrieve information from a private knowledge base hosted on Google Drive, ensuring responses are both contextual and accurate.

- Secure Session Management: Implements an Envelope Encryption pattern with Redis to securely manage user session data. This ensures that even if the database is compromised, sensitive information remains encrypted and inaccessible.

- Modular Architecture: Core functionalities like logging and session management are abstracted into a dedicated core module, promoting clean code and maintainability in the main application logic.

- LINE Bot Integration: A Flask-based webhook provides seamless integration with the LINE Messaging API for a fluid, real-time chat experience.

## Project Architecture

The project follows a modular design pattern, separating concerns into distinct packages and modules to enhance scalability and ease of maintenance.

```text
your-project/
├── core/
│   ├── __init__.py
│   ├── logger_config.py      # Shared logger configuration (outputs to the logs/ directory)
│   └── session_manager.py    # Handles session(personal information) encryption and Redis access
│
├── util/
│   ├── __init__.py
│   ├── rag.py       # Core RAG logic, including the model, retriever, and prompt templates
│   ├── embedding.py   # Standalone service for Google Drive sync and embedding
│   ├── name_fivegrid_wuxing.py # tool for numerology analysis
│   ├── bazi_true_solar.py      # tool for birth chart analysis
│   └── stroke_lookup.py   # tool for querying the stroke of name
│
├── app.py         # Main application: Flask + LINE Webhook endpoint
├── data/      #The government stroke data of comman words 
├── logs/                     # Log output directory
├── .env                      # Environment variable configuration
├── uv.lock                   # Python dependency management (uv)
└── pyproject.toml            # Python dependency management (uv)
```

## Getting Started

### 1. Prerequisites

Install [uv]: This project uses uv for high-performance Python package management.

```bash
pip install uv
```

Install Dependencies:

```bash
uv sync
```

Set up Google Service Account:

Navigate to the Google Cloud Console and create a new service account.

Enable the Google Drive API for your project.

Download the JSON key for the service account and save it as service_account.json in the project's root directory.

Share the Google Drive folder containing your knowledge base documents with the service account's email address.

### 2. Environment Configuration

Create a .env file in the root directory and populate it with the following variables:

```env
# --- LINE Bot Configuration ---
LINE_CHANNEL_ACCESS_TOKEN="Your Line Bot Access Token"
LINE_CHANNEL_SECRET="Your Line Channel Secret"

# --- Google & RAG Configuration ---
FOLDER_ID="Your Google Drive Folder ID"
GOOGLE_API_KEY="Your Google Maps API Key (for geolocation and timezone)"
EMBEDDING_MODEL="You can try your embedding model" # Recommended Chinese Embedding Model
MODEL_REPO_ID="You can try your model on Huggingface" # Selected Hugging Face Model

# --- Redis Configuration ---
REDIS_URL="redis://localhost:6379/0" # Redis connection URL (DB can be specified)

# --- Security Configuration ---
MASTER_ENCRYPTION_KEY="A Base64-encoded 32-byte key goes here"
```

How to generate a MASTER_ENCRYPTION_KEY?

Use one of the following commands to generate a secure, random key:

```powershell
# Windows (PowerShell)
[Convert]::ToBase64String((Get-Random -Count 32 -AsBytes))
```

```bash
# Linux / macOS
openssl rand -base64 32
```

### 3. Running the Services

You will need to run four separate services in four different terminal sessions.

Terminal 1: Start the LINE Bot Application

```bash
uv run app.py
```

Terminal 2: Start the Google Drive Sync & Embedding Service

```bash
uv run embedding.py
```

Terminal 3:Start the Redis service

```bash
redis-server.exe
```

Terminal 4:Start the ngrok domain service

```bash
ngrok http http://localhost:5000
```

and paste the endpoint url to your line account messageing API with /callback at the end.

## Usage

Once the services are running, you can interact with the bot directly through your LINE account.

Send Start to initiate the conversation flow.

Follow the message to provide the necessary information (e.g., name, birth date).

After the initial data collection, you can ask questions and leverage the RAG-powered knowledge base.

Send Cancel at any time to clear your session and end the conversation.

## 🙌 Contact & Support

For any questions or issues, please open an issue on the repository or contact the developers.

Sonny Huang
<partlysunny31@pm.me>

Zack Yang
<zackaryyang2001@gmail.com>
