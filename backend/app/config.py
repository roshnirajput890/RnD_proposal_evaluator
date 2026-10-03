"""
Configuration module.
Loads environment variables from .env using python-dotenv.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Search for .env in current directory or parent directory
BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

# Ollama local settings
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
LLM_MODEL: str = os.getenv("LLM_MODEL", "qwen3:4b")
MAX_INPUT_CHARS: int = int(os.getenv("MAX_INPUT_CHARS", "40000"))
REQUEST_TIMEOUT_SECONDS: float = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "120.0"))
