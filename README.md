Conversational RAG System for LINE BotThis project is a sophisticated, conversational AI chatbot designed for the LINE platform. It features a unique, humorous personality and provides insightful analysis based on user inputs. The system demonstrates how to build a modern, secure, and modular AI application by integrating Retrieval-Augmented Generation (RAG), secure session management, and independent background services.Core FeaturesEngaging AI Personality: A meticulously crafted system prompt gives the AI a witty and entertaining personality, making user interactions enjoyable and memorable.RAG-Powered Knowledge Base: Leverages LangChain and ChromaDB to enable the AI to retrieve information from a private knowledge base hosted on Google Drive, ensuring responses are both contextual and accurate.Asynchronous Document Embedding: A standalone service (embedding_refactored.py) runs in the background, periodically scanning a Google Drive folder to automatically update the vector database with new information.Secure Session Management: Implements an Envelope Encryption pattern with Redis to securely manage user session data. This ensures that even if the database is compromised, sensitive information remains encrypted and inaccessible.Modular Architecture: Core functionalities like logging and session management are abstracted into a dedicated core module, promoting clean code and maintainability in the main application logic.LINE Bot Integration: A Flask-based webhook provides seamless integration with the LINE Messaging API for a fluid, real-time chat experience.📁 Project ArchitectureThe project follows a modular design pattern, separating concerns into distinct packages and modules to enhance scalability and ease of maintenance.

your-project/
├── core/
│   ├── __init__.py
│   ├── logger_config.py      # Shared logger configuration (outputs to the logs/ directory)
│   └── session_manager.py    # Handles session encryption and Redis access
│
├── rag/
│   ├── __init__.py
│   ├── rag_refactored.py       # Core RAG logic, including the model, retriever, and prompt templates
│   ├── name_fivegrid_wuxing.py # (Your tool for numerology analysis)
│   └── bazi_true_solar.py      # (Your tool for birth chart analysis)
│
├── app_refactored.py         # Main application: Flask + LINE Webhook endpoint
├── embedding_refactored.py   # Standalone service for Google Drive sync and embedding
│
├── logs/                     # Log output directory (created automatically)
│   ├── app.log
│   └── embedding.log
│
├── service_account.json      # Google Service Account key (user-provided)
├── .env                      # Environment variable configuration
└── pyproject.toml            # Python dependency management (uv)
Getting Started1. PrerequisitesInstall [uv]: This project uses uv for high-performance Python package management.pip install uv
Install Dependencies:uv pip install -r requirements.txt
Set up Google Service Account:Navigate to the Google Cloud Console and create a new service account.Enable the Google Drive API for your project.Download the JSON key for the service account and save it as service_account.json in the project's root directory.Share the Google Drive folder containing your knowledge base documents with the service account's email address.2. Environment ConfigurationCreate a .env file in the root directory and populate it with the following variables:# --- LINE Bot Configuration ---
LINE_CHANNEL_ACCESS_TOKEN="Your Line Bot Access Token"
LINE_CHANNEL_SECRET="Your Line Channel Secret"

# --- Google & RAG Configuration ---
FOLDER_ID="Your Google Drive Folder ID"
GOOGLE_API_KEY="Your Google Maps API Key (for geolocation and timezone)"
EMBEDDING_MODEL="infgrad/stella-base-zh-v3-1792d" # Recommended Chinese Embedding Model
MODEL_REPO_ID="mistralai/Mixtral-8x7B-Instruct-v0.1" # Selected Hugging Face Model

# --- Redis Configuration ---
REDIS_URL="redis://localhost:6379/0" # Redis connection URL (DB can be specified)

# --- Security Configuration ---
MASTER_ENCRYPTION_KEY="A Base64-encoded 32-byte key goes here"
👉 How to generate a MASTER_ENCRYPTION_KEY?Use one of the following commands to generate a secure, random key:# Windows (PowerShell)
[Convert]::ToBase64String((Get-Random -Count 32 -AsBytes))

# Linux / macOS
openssl rand -base64 32
3. Running the ServicesYou will need to run two separate services in two different terminal sessions.Terminal 1: Start the LINE Bot Applicationpython app_refactored.py
Terminal 2: Start the Google Drive Sync & Embedding Servicepython embedding_refactored.py
Upon startup, the embedding service will perform an initial sync with Google Drive and then begin its scheduled polling.📄 UsageOnce the services are running, you can interact with the bot directly through your LINE account.Send Start to initiate the conversation flow.Follow the prompts to provide the necessary information (e.g., name, birth date).After the initial data collection, you can ask questions and leverage the RAG-powered knowledge base.Send Cancel at any time to clear your session and end the conversation.🙌 Contact & SupportFor any questions or issues, please open an issue on the repository or contact the developer.Sonny Huang
email: partlysunny31@pm.me
