"""app/config/ — static configuration: rubrics, weights, constants.

Re-exports all symbols from the original config.py so existing imports
like `from app.config import OLLAMA_BASE_URL` continue to work unchanged.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Search for .env in current directory or parent directory
_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_env_path = _BASE_DIR / ".env"
if _env_path.exists():
    load_dotenv(dotenv_path=_env_path)
else:
    load_dotenv()

OLLAMA_BASE_URL: str       = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
LLM_MODEL: str             = os.getenv("LLM_MODEL", "qwen3:4b")
MAX_INPUT_CHARS: int       = int(os.getenv("MAX_INPUT_CHARS", "40000"))
REQUEST_TIMEOUT_SECONDS: float = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "120.0"))
