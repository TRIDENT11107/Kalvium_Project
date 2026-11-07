import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")
APP_TITLE = "AI Lesson Studio"
DATABASE_URL = os.getenv("DATABASE_PATH", "database/lessons.db")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_TIMEOUT = int(os.getenv("GROQ_TIMEOUT", "120"))
GROQ_MAX_RETRIES = int(os.getenv("GROQ_MAX_RETRIES", "2"))
GROQ_MAX_COMPLETION_TOKENS = int(os.getenv("GROQ_MAX_COMPLETION_TOKENS", "2500"))
GROQ_QC_MAX_COMPLETION_TOKENS = int(os.getenv("GROQ_QC_MAX_COMPLETION_TOKENS", "1400"))
GROQ_TPM_BUDGET = int(os.getenv("GROQ_TPM_BUDGET", "8000"))
GROQ_BACKOFF_MAX_SECONDS = float(os.getenv("GROQ_BACKOFF_MAX_SECONDS", "60"))
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
GOOGLE_BOOKS_API_KEY = os.getenv("GOOGLE_BOOKS_API_KEY", "")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
OPENALEX_MAILTO = os.getenv("OPENALEX_MAILTO", "")
CROSSREF_MAILTO = os.getenv("CROSSREF_MAILTO", "")
WEB_LIMIT = int(os.getenv("WEB_LIMIT", "5"))
BOOK_LIMIT = int(os.getenv("BOOK_LIMIT", "4"))
YOUTUBE_LIMIT = int(os.getenv("YOUTUBE_LIMIT", "4"))
