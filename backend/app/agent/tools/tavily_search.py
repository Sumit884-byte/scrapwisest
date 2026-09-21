"""
Tavily Search Tool integration for real-time scrap market rates and news lookup.
Qualifies Scrapwisest for the Best Use of Tavily prize at Nebius Global AI Hackathon.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from typing import Dict, Any

from app.core.config import settings

logger = logging.getLogger(__name__)


def search_scrap_market_news(query: str) -> Dict[str, Any]:
    """
    Search real-time scrap metal, plastic, paper, or glass market rates and news using Tavily Search API.
    Use this tool when local user reports are low or when looking up external market trends and commodity rates.
    """
    api_key = settings.TAVILY_API_KEY.strip()
    if not api_key:
        logger.info("TAVILY_API_KEY is not set; returning simulated offline web market context.")
        return {
            "query": query,
            "results": [
                {
                    "title": f"Regional Scrap Rates for '{query}'",
                    "content": f"Recent market updates indicate stable baseline rates for {query}. Scrap dealers in major urban hubs report steady demand.",
                    "url": "https://tavily.com/scrap-market-rates",
                }
            ],
            "note": "Set TAVILY_API_KEY in .env for live Tavily search results.",
        }

    url = "https://api.tavily.com/search"
    payload = json.dumps({
        "api_key": api_key,
        "query": f"scrap recycling price rate per kg {query}",
        "search_depth": "basic",
        "include_answer": True,
        "max_results": 3,
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
        return {"query": query, "error": f"Failed to execute Tavily search: {str(exc)}"}
