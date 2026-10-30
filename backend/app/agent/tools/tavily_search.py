"""
External scrap-market search for the agent and estimator.

Uses Tavily when configured. Results are filtered in ``web_market``.
Neither source may invent a sale or replace ``estimate_price``.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any

from app.core.config import settings
from app.services.web_market import TAVILY_EXCLUDE_DOMAINS

logger = logging.getLogger(__name__)


def search_configured() -> bool:
    return bool(settings.TAVILY_API_KEY.strip())


def _search_tavily(query: str) -> dict[str, Any]:
    api_key = settings.TAVILY_API_KEY.strip()
    if not api_key:
        return {
            "query": query,
            "provider": "tavily",
            "results": [],
            "note": "Set TAVILY_API_KEY in .env for Tavily fallback.",
        }

    url = "https://api.tavily.com/search"
    payload = json.dumps({
        "api_key": api_key,
        "query": f"scrap recycling price rate per kg {query}",
        "search_depth": "basic",
        "include_answer": True,
        "max_results": 5,
        "exclude_domains": TAVILY_EXCLUDE_DOMAINS,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "Scrapwisest/1.0"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            return {
                "query": query,
                "provider": "tavily",
                "answer": res_data.get("answer"),
                "results": [
                    {
                        "title": r.get("title"),
                        "content": r.get("content"),
                        "url": r.get("url"),
                    }
                    for r in res_data.get("results", [])
                ],
            }
    except Exception as exc:
        logger.warning("Tavily search API call failed: %s", exc)
        return {"query": query, "provider": "tavily", "error": str(exc), "results": []}


def search_scrap_market_news(query: str, country: str = "") -> dict[str, Any]:
    """
    Look up public scrap-rate pages for supporting context.

    Use Tavily when ``TAVILY_API_KEY`` is set.
    Do not treat snippets as a confirmed picker price.
    """
    if settings.TAVILY_API_KEY.strip():
        return _search_tavily(query)
    return {
        "query": query,
        "provider": None,
        "results": [],
        "note": "Set TAVILY_API_KEY for live web market context.",
    }
