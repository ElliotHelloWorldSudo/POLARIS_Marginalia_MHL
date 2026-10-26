import os

from dotenv import load_dotenv

load_dotenv()

MODEL_ID = os.getenv("GEMMA_MODEL", "gemma-4-26b-a4b-it")
MAX_NEW_TOKENS = int(os.getenv("MAX_NEW_TOKENS", "4096"))
CHUNK_CHARS = int(os.getenv("CHUNK_CHARS", "16000"))
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "40"))
CROSSREF_MAILTO = os.getenv("CROSSREF_MAILTO", "")
PORT = int(os.getenv("PORT", "8000"))
