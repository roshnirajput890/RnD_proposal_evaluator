"""
Config route module.

Provides GET /api/config and POST /api/config for reading and updating
session-level LLM configuration (model, temperature, timeout, base URL).

Changes are held in-memory for the current server session only.
They are clearly labelled "active for this session" in all responses.
To make changes permanent, update backend/.env and restart the server.
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import os
from app.config import OLLAMA_BASE_URL, LLM_MODEL, MAX_INPUT_CHARS, REQUEST_TIMEOUT_SECONDS

router = APIRouter(prefix="/api", tags=["Config"])

# ── In-memory session config (initialised from .env values at startup) ─────────
_session_config: dict = {
    "ollama_base_url":       OLLAMA_BASE_URL,
    "model":                 LLM_MODEL,
    "temperature":           0.1,
    "request_timeout":       REQUEST_TIMEOUT_SECONDS,
    "max_input_chars":       MAX_INPUT_CHARS,
    "session_only":          True,   # always true — not written to disk
}


class ConfigUpdate(BaseModel):
    ollama_base_url:   Optional[str]   = None
    model:             Optional[str]   = None
    temperature:       Optional[float] = None
    request_timeout:   Optional[float] = None
    max_input_chars:   Optional[int]   = None


@router.get(
    "/config",
    summary="Get current session LLM configuration",
    description="Returns the active in-session configuration. Reflects .env defaults at startup; "
                "any POST /api/config changes are active for this server session only.",
)
def get_config():
    return {
        **_session_config,
        "note": "Active for this session only. Restart the server or update backend/.env to persist changes.",
    }


@router.post(
    "/config",
    summary="Update session LLM configuration",
    description="Updates one or more LLM config values for the current server session. "
                "Does not write to .env. Changes are lost on server restart.",
)
def update_config(body: ConfigUpdate):
    changed = {}

    if body.ollama_base_url is not None:
        _session_config["ollama_base_url"] = body.ollama_base_url.rstrip("/")
        changed["ollama_base_url"] = _session_config["ollama_base_url"]

    if body.model is not None:
        _session_config["model"] = body.model
        changed["model"] = body.model

    if body.temperature is not None:
        temp = max(0.0, min(1.0, body.temperature))   # clamp 0–1
        _session_config["temperature"] = temp
        changed["temperature"] = temp

    if body.request_timeout is not None:
        timeout = max(30.0, body.request_timeout)     # minimum 30 s
        _session_config["request_timeout"] = timeout
        changed["request_timeout"] = timeout

    if body.max_input_chars is not None:
        chars = max(1000, body.max_input_chars)        # sanity floor
        _session_config["max_input_chars"] = chars
        changed["max_input_chars"] = chars

    return {
        "status": "updated",
        "changed": changed,
        "active_config": _session_config,
        "note": "Active for this session only. Restart the server or update backend/.env to persist changes.",
    }
