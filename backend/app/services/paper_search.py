"""
paper_search.py — Scholarly paper search via OpenAlex (free, no API key).

Public API:
    search_openalex(query: str, limit: int = 5) -> list[PaperResult]

DESIGN PRINCIPLES:
  - Never raises — returns [] on any failure (timeout, malformed, no results).
  - sync httpx to stay compatible with the existing sync call_llm_json pattern.
  - Deduplication is done by the merge helper, not here.
  - Abstracts are reconstructed from the inverted-index format OpenAlex provides.

OpenAlex endpoint docs: https://docs.openalex.org/api-entities/works/search-works
"""
import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────

OPENALEX_BASE   = "https://api.openalex.org"
REQUEST_TIMEOUT = 10.0   # seconds — fast fail so the pipeline isn't held up
# Polite-pool user-agent (OpenAlex asks for this)
_HEADERS = {
    "User-Agent": "RnD-Proposal-Evaluator/1.0 (mailto:research@example.org)",
    "Accept":     "application/json",
}

# Fields we actually need — keeping the request small
_SELECT_FIELDS = ",".join([
    "title",
    "publication_year",
    "cited_by_count",
    "primary_location",
    "abstract_inverted_index",
    "authorships",
    "doi",
])


# ── Result type (plain dict for easy JSON serialisation) ──────────────────────

def _make_paper(
    title:          str,
    authors:        List[str],
    year:           Optional[int],
    abstract:       Optional[str],
    url:            Optional[str],
    citation_count: int,
) -> Dict[str, Any]:
    return {
        "title":          title,
        "authors":        authors,
        "year":           year,
        "abstract":       abstract,
        "url":            url,
        "citation_count": citation_count,
    }


# ── Abstract reconstruction ────────────────────────────────────────────────────

def _reconstruct_abstract(inverted_index: Optional[Dict[str, List[int]]]) -> Optional[str]:
    """
    OpenAlex stores abstracts as an inverted index: {word: [position, ...], ...}
    This reconstructs the plain-text abstract.  Returns None if absent.
    """
    if not inverted_index:
        return None
    try:
        position_word: Dict[int, str] = {}
        for word, positions in inverted_index.items():
            for pos in positions:
                position_word[pos] = word
        return " ".join(position_word[i] for i in sorted(position_word))
    except Exception:
        return None


# ── Single-query search ────────────────────────────────────────────────────────

def search_openalex(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Search OpenAlex for papers matching `query`.

    Args:
        query:  Free-text search string.
        limit:  Max papers to return (default 5, capped at 25).

    Returns:
        List of PaperResult dicts, sorted by citation_count descending.
        Returns [] on any error — never raises.
    """
    if not query or not query.strip():
        return []

    limit = min(limit, 25)

    try:
        params = {
            "search":   query.strip(),
            "per-page": str(limit),
            "select":   _SELECT_FIELDS,
            "sort":     "cited_by_count:desc",
        }

        with httpx.Client(timeout=REQUEST_TIMEOUT, headers=_HEADERS) as client:
            resp = client.get(f"{OPENALEX_BASE}/works", params=params)

        if resp.status_code != 200:
            if resp.status_code == 429:
                logger.warning(
                    "OpenAlex rate-limited (HTTP 429) for query %r — "
                    "falling back to text-only novelty analysis", query
                )
            else:
                logger.warning(
                    "OpenAlex returned HTTP %s for query %r — "
                    "falling back to text-only novelty analysis",
                    resp.status_code, query,
                )
            return []

        data = resp.json()
        results: List[Dict[str, Any]] = []

        for work in data.get("results", []):
            title = work.get("title") or ""
            if not title:
                continue

            # Authors (up to 4 to keep the blob small)
            authorships = work.get("authorships") or []
            authors = [
                a.get("author", {}).get("display_name", "")
                for a in authorships[:4]
                if a.get("author", {}).get("display_name")
            ]

            year           = work.get("publication_year")
            citation_count = work.get("cited_by_count") or 0

            # URL: prefer doi, then landing_page_url
            doi        = work.get("doi")
            loc        = work.get("primary_location") or {}
            landing    = loc.get("landing_page_url")
            url        = doi or landing or None

            abstract = _reconstruct_abstract(work.get("abstract_inverted_index"))
            # Truncate long abstracts — the LLM only needs the gist (~150 words ≈ 500 chars)
            if abstract and len(abstract) > 500:
                abstract = abstract[:500] + "…"

            results.append(_make_paper(
                title          = title,
                authors        = authors,
                year           = year,
                abstract       = abstract,
                url            = url,
                citation_count = citation_count,
            ))

        logger.info(
            "OpenAlex: query=%r → %d results", query, len(results)
        )
        return results

    except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as net_err:
        logger.warning("OpenAlex unreachable for query %r: %s", query, net_err)
        return []
    except Exception as exc:
        logger.warning("OpenAlex unexpected error for query %r: %s", query, exc)
        return []


# ── Multi-query search with deduplication ────────────────────────────────────

def search_and_merge(
    queries:        List[str],
    per_query:      int = 5,
    final_limit:    int = 10,
) -> List[Dict[str, Any]]:
    """
    Run multiple queries sequentially, merge results, deduplicate by
    normalised title, and return the top `final_limit` by citation count.

    Args:
        queries:      List of search strings (typically 3).
        per_query:    Results requested per query.
        final_limit:  Max papers in the merged output.

    Returns:
        Deduplicated list sorted by citation_count descending.
        Returns [] if all queries fail.
    """
    seen_titles: set = set()
    merged:      List[Dict[str, Any]] = []

    for q in queries:
        papers = search_openalex(q, limit=per_query)
        for p in papers:
            # Normalise title for dedup: lowercase, strip punctuation
            norm = "".join(c for c in p["title"].lower() if c.isalnum() or c.isspace()).strip()
            if norm and norm not in seen_titles:
                seen_titles.add(norm)
                merged.append(p)

    # Sort by citation count descending, take top N
    merged.sort(key=lambda x: x.get("citation_count", 0) or 0, reverse=True)
    return merged[:final_limit]
