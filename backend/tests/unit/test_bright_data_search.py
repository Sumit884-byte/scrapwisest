from __future__ import annotations

import json

from app.agent.tools.tavily_search import search_scrap_market_news
from app.services import bright_data_search


def test_bright_data_skips_without_key(monkeypatch):
    monkeypatch.setattr(bright_data_search.settings, "BRIGHT_DATA_API_KEY", "")
    monkeypatch.setattr(bright_data_search.settings, "TAVILY_API_KEY", "")
    out = search_scrap_market_news("plastic_pet in Karachi, Pakistan, PKR", country="Pakistan")
    assert out["results"] == []
    assert out.get("provider") is None
    assert "stable baseline" not in json.dumps(out).lower()


def test_bright_data_parses_organic(monkeypatch):
    payload = {
        "organic": [
            {
                "title": "Karachi PET scrap rates",
                "link": "https://example.com/karachi-pet",
                "description": "Dealers quote PET in PKR per kg.",
            }
        ]
    }
    monkeypatch.setattr(bright_data_search.settings, "BRIGHT_DATA_API_KEY", "test-key")
    monkeypatch.setattr(
        bright_data_search,
        "_call_search_engine",
        lambda query, geo: json.dumps(payload),
    )
    out = bright_data_search.search_bright_data("plastic_pet in Karachi", country="Pakistan")
    assert out["provider"] == "bright_data"
    assert out["results"][0]["url"] == "https://example.com/karachi-pet"
    assert "PKR" in out["results"][0]["content"]


def test_bright_data_prefers_over_tavily(monkeypatch):
    monkeypatch.setattr(bright_data_search.settings, "BRIGHT_DATA_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.agent.tools.tavily_search.settings.BRIGHT_DATA_API_KEY",
        "test-key",
    )
    monkeypatch.setattr(
        "app.agent.tools.tavily_search.search_bright_data",
        lambda query, country=None: {"query": query, "provider": "bright_data", "results": []},
    )
    out = search_scrap_market_news("aluminum", country="India")
    assert out["provider"] == "bright_data"


def test_bright_data_error_is_empty(monkeypatch):
    def _boom(query, geo):
        raise RuntimeError("offline")

    monkeypatch.setattr(bright_data_search.settings, "BRIGHT_DATA_API_KEY", "test-key")
    monkeypatch.setattr(bright_data_search, "_call_search_engine", _boom)
    out = bright_data_search.search_bright_data("cardboard")
    assert out["results"] == []
    assert "error" in out
