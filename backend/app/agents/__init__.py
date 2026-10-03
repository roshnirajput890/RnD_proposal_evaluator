"""
agents/ — LLM agent implementations.

Each agent is a focused callable that receives structured input (never raw
proposal text) and returns a structured dict. Agents share the same
call_llm_json / LLMClientError infrastructure from services/llm_client.py.
"""
