"""
Health check route module.
Provides endpoints to verify that the backend server and the local Ollama LLM are operational.
"""
from fastapi import APIRouter
import httpx
from app.config import OLLAMA_BASE_URL, LLM_MODEL

# Initialize the router with a prefix of '/api'
router = APIRouter(prefix="/api", tags=["Health"])


@router.get("/health")
def get_health_status():
    """
    Backend service health check endpoint.
    Returns:
        dict: {"status": "ok"}
    """
    return {"status": "ok"}


@router.get("/health/llm")
def get_llm_health():
    """
    Ollama LLM health check endpoint.
    Pings Ollama and reports whether it is reachable and whether the configured model is available.
    """
    url = f"{OLLAMA_BASE_URL}/api/tags"

    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(url)

        if resp.status_code != 200:
            return {
                "status": "error",
                "reachable": True,
                "ollama_url": OLLAMA_BASE_URL,
                "model": LLM_MODEL,
                "model_available": False,
                "message": f"Ollama returned HTTP {resp.status_code}: {resp.text}",
            }

        data = resp.json()
        models = data.get("models", [])

        # Normalize names to check for model presence
        # e.g., 'qwen3:4b' or 'qwen3:4b:latest'
        model_names = set()
        for m in models:
            name = m.get("name", "")
            model_names.add(name)
            model_names.add(m.get("model", ""))
            if ":" in name:
                model_names.add(name.split(":")[0])

        target = LLM_MODEL
        target_base = target.split(":")[0] if ":" in target else target

        is_available = (
            target in model_names
            or f"{target}:latest" in model_names
            or target_base in model_names
        )

        if is_available:
            return {
                "status": "ok",
                "reachable": True,
                "ollama_url": OLLAMA_BASE_URL,
                "model": LLM_MODEL,
                "model_available": True,
                "message": f"Local AI model '{LLM_MODEL}' is ready and running.",
            }
        else:
            return {
                "status": "model_missing",
                "reachable": True,
                "ollama_url": OLLAMA_BASE_URL,
                "model": LLM_MODEL,
                "model_available": False,
                "message": f"Model '{LLM_MODEL}' is not available in Ollama. Run: `ollama pull {LLM_MODEL}` and try again.",
            }

    except (httpx.ConnectError, httpx.NetworkError):
        return {
            "status": "offline",
            "reachable": False,
            "ollama_url": OLLAMA_BASE_URL,
            "model": LLM_MODEL,
            "model_available": False,
            "message": "Local AI model is not running. Start Ollama and try again.",
        }
    except Exception as err:
        return {
            "status": "error",
            "reachable": False,
            "ollama_url": OLLAMA_BASE_URL,
            "model": LLM_MODEL,
            "model_available": False,
            "message": f"Could not verify Ollama status: {str(err)}",
        }
