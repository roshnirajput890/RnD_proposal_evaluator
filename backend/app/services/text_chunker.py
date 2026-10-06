"""
Text chunking service for agent-specific keyword extraction.

Selects relevant text passages for each agent based on domain-specific keywords,
reducing the amount of text sent to the LLM while preserving relevant sections.
Falls back to first N characters if no keywords match.
"""
import logging
import re
from typing import Dict, Tuple

logger = logging.getLogger(__name__)


# Agent-specific keyword sets
AGENT_KEYWORDS = {
    "novelty": [
        "abstract", "introduction", "problem", "innovation", "related work",
        "prior art", "novelty", "contribution", "literature", "state of the art",
        "background", "research gap", "novel", "originality", "unique"
    ],
    "technical": [
        "methodology", "approach", "architecture", "requirements", "hardware",
        "software", "design", "implementation", "technology", "stack",
        "feasibility", "resources", "technical", "system", "platform",
        "tools", "framework", "algorithm", "method", "procedure"
    ],
    "financial": [
        "budget", "cost", "funding", "total", "Rs", "INR", "$", "price",
        "expense", "expenditure", "allocation", "financial", "economic",
        "investment", "grant", "salary", "equipment", "procurement",
        "breakdown", "estimate", "amount"
    ],
    "impact": [
        "objectives", "outcomes", "beneficiaries", "impact", "benefits",
        "results", "goals", "deliverables", "social", "economic impact",
        "sustainability", "stakeholders", "significance", "contribution",
        "value", "reach", "scalability", "adoption", "output"
    ],
}


def _split_into_paragraphs(text: str) -> list:
    """Split text into paragraphs, preserving structure."""
    # Split on double newlines or single newlines with clear breaks
    paragraphs = re.split(r'\n\s*\n|\n(?=[A-Z][a-z]+:|\d+\.)', text)
    return [p.strip() for p in paragraphs if p.strip()]


def _score_paragraph(paragraph: str, keywords: list) -> Tuple[int, int]:
    """
    Score a paragraph based on keyword matches.
    
    Returns:
        (keyword_count, char_count) tuple
    """
    lower_para = paragraph.lower()
    keyword_count = sum(1 for kw in keywords if kw.lower() in lower_para)
    return (keyword_count, len(paragraph))


def extract_relevant_text(
    full_text: str,
    agent_name: str,
    max_chars: int
) -> Dict[str, any]:
    """
    Extract relevant text for a specific agent based on keywords.
    
    Args:
        full_text: Full proposal text
        agent_name: Agent identifier (novelty, technical, financial, impact)
        max_chars: Maximum characters to return
    
    Returns:
        dict with:
            - text: Extracted text (up to max_chars)
            - truncated: bool indicating if text was truncated
            - method: "keyword" or "fallback"
            - chars_selected: actual character count
    """
    # Normalize agent name
    agent_key = agent_name.lower().replace("_agent", "").replace(" ", "")
    
    keywords = AGENT_KEYWORDS.get(agent_key, [])
    
    if not keywords or not full_text:
        # Fallback: return first max_chars
        selected = full_text[:max_chars]
        logger.info(
            "[text_chunker] %s: %d chars selected via fallback (no keywords defined)",
            agent_name, len(selected)
        )
        return {
            "text": selected,
            "truncated": len(full_text) > max_chars,
            "method": "fallback",
            "chars_selected": len(selected),
        }
    
    # Split into paragraphs
    paragraphs = _split_into_paragraphs(full_text)
    
    # Score each paragraph
    scored_paragraphs = [
        (para, *_score_paragraph(para, keywords))
        for para in paragraphs
    ]
    
    # Sort by keyword count (desc), then by paragraph length (desc)
    scored_paragraphs.sort(key=lambda x: (x[1], x[2]), reverse=True)
    
    # Check if any paragraphs have keyword matches
    has_matches = any(score > 0 for _, score, _ in scored_paragraphs)
    
    if not has_matches:
        # No keywords found, use fallback
        selected = full_text[:max_chars]
        logger.info(
            "[text_chunker] %s: %d chars selected via fallback (no keyword matches)",
            agent_name, len(selected)
        )
        return {
            "text": selected,
            "truncated": len(full_text) > max_chars,
            "method": "fallback",
            "chars_selected": len(selected),
        }
    
    # Collect paragraphs with keyword matches up to max_chars
    selected_paragraphs = []
    current_chars = 0
    
    for para, kw_count, char_count in scored_paragraphs:
        if kw_count == 0:
            # Stop once we hit paragraphs with no keywords
            break
        
        if current_chars + char_count <= max_chars:
            selected_paragraphs.append(para)
            current_chars += char_count
        elif current_chars < max_chars:
            # Include partial paragraph to reach max_chars
            remaining = max_chars - current_chars
            selected_paragraphs.append(para[:remaining])
            current_chars = max_chars
            break
        else:
            break
    
    # If we still haven't reached max_chars, add more paragraphs without keywords
    if current_chars < max_chars * 0.5 and len(selected_paragraphs) < len(paragraphs):
        for para, kw_count, char_count in scored_paragraphs:
            if kw_count > 0:
                continue  # Already included
            
            if current_chars + char_count <= max_chars:
                selected_paragraphs.append(para)
                current_chars += char_count
            else:
                break
    
    selected_text = "\n\n".join(selected_paragraphs)
    
    # Final truncation if needed
    if len(selected_text) > max_chars:
        selected_text = selected_text[:max_chars]
    
    truncated = len(full_text) > len(selected_text)
    
    logger.info(
        "[text_chunker] %s: %d chars selected via keyword (truncated=%s)",
        agent_name, len(selected_text), truncated
    )
    
    return {
        "text": selected_text,
        "truncated": truncated,
        "method": "keyword",
        "chars_selected": len(selected_text),
    }
