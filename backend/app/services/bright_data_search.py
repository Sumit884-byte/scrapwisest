"""Bright Data web lookup for external scrap-market context.

The Arka ``BRIGHTDATA_API_TOKEN`` is a user MCP token
(``https://mcp.brightdata.com/mcp``), not a SERP-zone key for
``api.brightdata.com/request``. Search uses the hosted MCP ``search_engine``
tool, same as Arka.

The quoted picker rate still comes from ``estimate_price``. These results
are supporting snippets only — never a sale, never FX conversion.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

_MCP_URL = "https://mcp.brightdata.com/mcp"
_MCP_PROTOCOL = "2024-11-05"
_SEARCH_TOOL = "search_engine"

_GL_BY_COUNTRY = {
    "pakistan": "pk",
    "india": "in",
    "bangladesh": "bd",
    "nepal": "np",
    "united states": "us",
    "usa": "us",
    "united kingdom": "uk",
    "sri lanka": "lk",
    "afghanistan": "af",
    "united arab emirates": "ae",
}


def bright_data_configured() -> bool:
    return bool(settings.BRIGHT_DATA_API_KEY.strip())


def _gl_for_country(country: str | None) -> str | None:
    if not country:
        return None
    return _GL_BY_COUNTRY.get(country.strip().lower())


def _parse_mcp_body(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    if text.startswith("{"):
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {"result": parsed}
    for line in text.splitlines():
        if line.startswith("data:"):
            payload = line[5:].strip()
            if payload:
                parsed = json.loads(payload)
                return parsed if isinstance(parsed, dict) else {"result": parsed}
    raise RuntimeError("unrecognized MCP response")


def _tool_result_text(result: Any) -> str:
    if not isinstance(result, dict):
        return str(result or "")
    chunks: list[str] = []
    for item in result.get("content") or []:
        if isinstance(item, dict) and item.get("type") == "text":
            chunks.append(str(item.get("text") or ""))
    if chunks:
        return "\n".join(chunks)
    structured = result.get("structuredContent")
    if structured is not None:
        return json.dumps(structured, ensure_ascii=False)
    return ""


def _organic_rows(payload: Any) -> list[dict[str, Any]]:
    rows: list[Any] = []
    if isinstance(payload, dict):
        for key in ("organic", "organic_results", "results", "items", "data"):
            extra = payload.get(key)
            if isinstance(extra, list):
                rows.extend(extra)
    elif isinstance(payload, list):
        rows.extend(payload)
    return [row for row in rows if isinstance(row, dict)]


def _snippet(row: dict[str, Any]) -> str:
    for key in ("description", "snippet", "content", "text"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _mcp_rpc(
    url: str,
    method: str,
    params: dict[str, Any] | None,
    *,
    request_id: int | None,
    session_id: str,
    timeout: float,
) -> tuple[Any, str]:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if request_id is not None:
        payload["id"] = request_id
    if params is not None:
        payload["params"] = params
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "User-Agent": "Scrapwisest/1.0",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        next_session = (
            response.headers.get("Mcp-Session-Id")
            or response.headers.get("mcp-session-id")
            or session_id
        )
        raw = response.read().decode("utf-8", errors="replace")
    if request_id is None:
        return None, next_session.strip()
    body = _parse_mcp_body(raw)
    if "error" in body:
        raise RuntimeError(str(body["error"].get("message", body["error"])))
    return body.get("result"), next_session.strip()


def _call_search_engine(query: str, geo: str | None) -> str:
    token = settings.BRIGHT_DATA_API_KEY.strip()
    url = f"{_MCP_URL}?token={token}"
    args: dict[str, Any] = {"query": query, "engine": "google"}
    if geo:
        args["geo_location"] = geo
    session = ""
    _, session = _mcp_rpc(
        url,
        "initialize",
        {
            "protocolVersion": _MCP_PROTOCOL,
            "capabilities": {},
            "clientInfo": {"name": "scrapwisest", "version": "0.1.0"},
        },
        request_id=1,
        session_id=session,
        timeout=20,
    )
    _mcp_rpc(
        url,
        "notifications/initialized",
        {},
        request_id=None,
        session_id=session,
        timeout=20,
    )
    result, _ = _mcp_rpc(
        url,
        "tools/call",
        {"name": _SEARCH_TOOL, "arguments": args},
        request_id=2,
        session_id=session,
        timeout=45,
    )
    return _tool_result_text(result)


def search_bright_data(
    query: str,
    *,
    country: str | None = None,
    max_results: int = 3,
) -> dict[str, Any]:
    """Search Google via Bright Data MCP ``search_engine``."""
    if not bright_data_configured():
        return {
            "query": query,
            "provider": "bright_data",
            "results": [],
            "note": "Set BRIGHT_DATA_API_KEY for live Bright Data search.",
        }

    q = f"scrap recycling price rate per kg {query}"
    geo = _gl_for_country(country)
    try:
        raw = _call_search_engine(q, geo)
        payload: Any
        try:
            payload = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            payload = {"results": [{"title": raw[:180], "content": raw[:400], "url": ""}]}
    except Exception as exc:
        logger.warning("Bright Data MCP search failed: %s", exc)
        return {"query": query, "provider": "bright_data", "error": str(exc), "results": []}

    results: list[dict[str, str]] = []
    for row in _organic_rows(payload)[:max_results]:
        title = str(row.get("title") or row.get("name") or "").strip()
        url = str(row.get("link") or row.get("url") or row.get("href") or "").strip()
        content = _snippet(row)
        if title or url or content:
            results.append({"title": title, "content": content, "url": url})

    answer = None
    if isinstance(payload, dict):
        box = payload.get("answer_box") or payload.get("knowledge")
        if isinstance(box, dict):
            answer = box.get("answer") or box.get("snippet") or box.get("description")
    if not answer and results:
        answer = results[0]["content"] or results[0]["title"]

    return {
        "query": query,
        "provider": "bright_data",
        "answer": answer,
        "results": results,
    }
