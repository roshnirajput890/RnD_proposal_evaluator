"""
Local Ollama LLM Client Service.

Provides robust interaction with a local Ollama instance (default: http://localhost:11434).
Uses POST /api/generate with stream=false, request timeout >= 120s, and resilient JSON extraction
with automatic retry and sanitized error handling for offline servers, missing models, and parsing issues.
"""
import json
import re
from typing import Any, Dict, Optional
import httpx

from app.config import OLLAMA_BASE_URL, LLM_MODEL, REQUEST_TIMEOUT_SECONDS


class LLMClientError(Exception):
    """Custom exception for Ollama LLM client errors."""

    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _clean_json_text(text: str) -> str:
    """
    Cleans LLM response text for JSON parsing:
    - Strips <think>...</think> reasoning blocks if present
    - Strips markdown code blocks (```json ... ``` or ``` ... ```)
    - Extracts outermost JSON object if surrounding commentary exists
    """
    if not text:
        return ""

    cleaned = text.strip()

    # 1. Remove <think>...</think> blocks if present
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()

    # 2. Remove markdown code fences if present
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    # 3. If not cleanly starting with '{' or '[', find outermost braces
    if not (cleaned.startswith("{") or cleaned.startswith("[")):
        start_brace = cleaned.find("{")
        end_brace = cleaned.rfind("}")
        if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
            cleaned = cleaned[start_brace : end_brace + 1].strip()

    return cleaned


def call_llm(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
    timeout: Optional[float] = None,
    format_json: bool = False,
) -> str:
    """
    Calls the local Ollama model via POST /api/generate with stream=false.

    Args:
        system_prompt: System directive for the LLM.
        user_prompt: User prompt content.
        model: Optional model override (defaults to config.LLM_MODEL).
        timeout: Optional timeout override in seconds (defaults to at least 120s).
        format_json: If True, requests Ollama's structured JSON format mode.

    Returns:
        str: Raw text response from the model.

    Raises:
        LLMClientError: With user-friendly messages for connection errors,
                        missing models, timeouts, or empty responses.
    """
    target_model = model or LLM_MODEL
    req_timeout = timeout or max(REQUEST_TIMEOUT_SECONDS, 120.0)
    url = f"{OLLAMA_BASE_URL}/api/generate"

    payload: Dict[str, Any] = {
        "model": target_model,
        "prompt": user_prompt,
        "system": system_prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
        },
    }
    if format_json:
        payload["format"] = "json"

    try:
        with httpx.Client(timeout=req_timeout) as client:
            response = client.post(url, json=payload)

    except (httpx.ConnectError, httpx.NetworkError):
        raise LLMClientError(
            "Local AI model is not running. Start Ollama and try again.",
            status_code=503,
        )
    except (httpx.TimeoutException, httpx.ReadTimeout):
        raise LLMClientError(
            f"Local AI model request timed out after {int(req_timeout)} seconds. "
            "Local models are slower than cloud APIs; verify system resources and model size.",
            status_code=504,
        )
    except Exception as err:
        raise LLMClientError(
            f"Unexpected communication error with local AI server: {str(err)}",
            status_code=500,
        )

    # Handle Ollama HTTP error responses
    if response.status_code == 404 or "not found" in response.text.lower():
        raise LLMClientError(
            f"Model '{target_model}' is not pulled in Ollama. "
            f"Run: `ollama pull {target_model}` and try again.",
            status_code=404,
        )

    if response.status_code != 200:
        raise LLMClientError(
            f"Ollama server returned error ({response.status_code}): {response.text}",
            status_code=response.status_code,
        )

    try:
        data = response.json()
        raw_content = data.get("response", "")
        if not raw_content and "message" in data:
            raw_content = data["message"].get("content", "")
    except Exception as parse_err:
        raise LLMClientError(
            f"Failed to decode response from Ollama: {str(parse_err)}",
            status_code=502,
        )

    if not raw_content or not raw_content.strip():
        raise LLMClientError(
            "Local AI model returned an empty response. Please try again.",
            status_code=502,
        )

    return raw_content.strip()


def call_llm_json(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Calls the local Ollama model and enforces valid JSON output.
    Applies explicit formatting instructions, strips code fences and think tags,
    and automatically retries once if initial JSON decoding fails.

    Returns:
        dict: Parsed JSON object, or a structured error dict if both attempts fail.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    json_directive = (
        "Respond with ONLY valid JSON. No explanation, no markdown code fences, "
        "no extra text before or after."
    )

    combined_system_prompt = f"{system_prompt}\n\nIMPORTANT: {json_directive}"

    # First Attempt
    first_response = call_llm(
        system_prompt=combined_system_prompt,
        user_prompt=user_prompt,
        model=model,
        timeout=timeout,
        format_json=True,
    )

    cleaned_first = _clean_json_text(first_response)
    try:
        parsed_json = json.loads(cleaned_first)
        if isinstance(parsed_json, dict):
            return parsed_json
        return {"result": parsed_json}
    except json.JSONDecodeError as first_err:
        # Log the raw text that failed to parse
        logger.warning(
            "First JSON parse attempt failed for this request. Raw response (first 800 chars):\n%s\n\nCleaned text (first 800 chars):\n%s\n\nError: %s",
            first_response[:800],
            cleaned_first[:800],
            str(first_err)
        )

    # Second Attempt (Retry with explicit correction instruction)
    retry_prompt = (
        f"{user_prompt}\n\n"
        "Your last response was not valid JSON. Return ONLY the JSON object. "
        "Do not include any thought process, markdown fences, or text outside the JSON."
    )

    try:
        second_response = call_llm(
            system_prompt=combined_system_prompt,
            user_prompt=retry_prompt,
            model=model,
            timeout=timeout,
            format_json=True,
        )
        cleaned_second = _clean_json_text(second_response)
        parsed_json = json.loads(cleaned_second)
        if isinstance(parsed_json, dict):
            return parsed_json
        return {"result": parsed_json}
    except (json.JSONDecodeError, Exception) as second_err:
        # Structured error return instead of crashing
        logger.error(
            "Second JSON parse attempt also failed. Second raw response (first 800 chars):\n%s\n\nError: %s",
            second_response[:800] if "second_response" in locals() else "N/A",
            str(second_err)
        )
        return {
            "error": "Failed to parse JSON response from local AI model after retry.",
            "details": str(second_err),
            "raw_response": second_response if "second_response" in locals() else first_response,
        }
