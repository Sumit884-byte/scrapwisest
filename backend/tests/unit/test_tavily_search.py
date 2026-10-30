from __future__ import annotations

import json

from app.agent.tools.tavily_search import search_scrap_market_news


def test_search_skips_without_key(monkeypatch):
    monkeypatch.setattr("app.agent.tools.tavily_search.settings.TAVILY_API_KEY", "")
    out = search_scrap_market_news("plastic_pet in Karachi, Pakistan, PKR")
    assert out["results"] == []
    assert out.get("provider") is None
    assert "stable baseline" not in json.dumps(out).lower()
