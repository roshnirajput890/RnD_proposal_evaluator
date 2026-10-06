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

OLLAMA_BASE_URL: str           = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
LLM_MODEL: str                 = os.getenv("LLM_MODEL", "gemma3:4b")
MAX_INPUT_CHARS: int           = int(os.getenv("MAX_INPUT_CHARS", "40000"))
REQUEST_TIMEOUT_SECONDS: float = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "900.0"))
PARALLEL_AGENTS: bool          = os.getenv("PARALLEL_AGENTS", "false").lower() in ("true", "1", "yes")

# Performance & Timeout Settings
AGENT_CONCURRENCY: int         = int(os.getenv("AGENT_CONCURRENCY", "1"))
AGENT_TIMEOUT_SECONDS: float   = float(os.getenv("AGENT_TIMEOUT_SECONDS", "180"))
NOVELTY_TIMEOUT_SECONDS: float = float(os.getenv("NOVELTY_TIMEOUT_SECONDS", "240"))
MAX_CHARS_PER_AGENT: int       = int(os.getenv("MAX_CHARS_PER_AGENT", "3000"))

# Ollama Performance Tuning
OLLAMA_NUM_CTX: int            = int(os.getenv("OLLAMA_NUM_CTX", "4096"))
OLLAMA_NUM_PREDICT: int        = int(os.getenv("OLLAMA_NUM_PREDICT", "500"))
OLLAMA_TEMPERATURE: float      = float(os.getenv("OLLAMA_TEMPERATURE", "0.2"))
OLLAMA_KEEP_ALIVE: str         = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
OLLAMA_FORMAT: str             = os.getenv("OLLAMA_FORMAT", "json")

# Coordinator-Specific Ollama Options (longer output, larger context)
COORDINATOR_NUM_CTX: int       = int(os.getenv("COORDINATOR_NUM_CTX", "8192"))
COORDINATOR_NUM_PREDICT: int   = int(os.getenv("COORDINATOR_NUM_PREDICT", "1200"))
COORDINATOR_TEMPERATURE: float = float(os.getenv("COORDINATOR_TEMPERATURE", "0.1"))
