"""Capture structured tool results for the /chat response.

Subagents run on worker threads, so thread-local storage cannot be used.
Active /chat calls push a slot; tools write into the matching picker slot.
"""

from __future__ import annotations

import threading
from typing import Any, Optional

_lock = threading.Lock()
_slots: list[dict[str, Any]] = []


def _runtime_picker_id() -> Optional[str]:
    try:
        from langgraph.runtime import get_runtime
        from app.agent.main_agent import AgentContext

        runtime = get_runtime(AgentContext)
        return getattr(runtime.context, "picker_id", None)
    except Exception:
        return None


def begin(
    picker_id: str,
    market: dict[str, Any] | None = None,
) -> None:
    """Push a slot for one /chat call, carrying its picker market context.

    ``market`` holds the canonical picker defaults
    (country/currency/city/neighborhood) so the report pipeline and the
    price-estimator tool can deterministically backfill them even when the
    LLM's rewritten subagent sentence drops the ``[picker_*]`` tags.
    """
    with _lock:
        _slots.append(
            {
                "picker_id": picker_id,
                "price": None,
                "report": None,
                "market": dict(market) if market else {},
            }
        )


def end(picker_id: str) -> tuple[Any, Any]:
    with _lock:
        for index in range(len(_slots) - 1, -1, -1):
            if _slots[index]["picker_id"] == picker_id:
                slot = _slots.pop(index)
                return slot.get("price"), slot.get("report")
    return None, None


def reset() -> None:
    with _lock:
        _slots.clear()


def _write(field: str, value: Any) -> None:
    picker_id = _runtime_picker_id()
    with _lock:
        if not _slots:
            return
        if picker_id:
            for slot in reversed(_slots):
                if slot["picker_id"] == picker_id:
                    slot[field] = value
                    return
        _slots[-1][field] = value


def record_price(value: Any) -> None:
    _write("price", value)


def record_report(value: Any) -> None:
    _write("report", value)


def take_price() -> Optional[Any]:
    with _lock:
        return _slots[-1].get("price") if _slots else None


def take_report() -> Optional[Any]:
    with _lock:
        return _slots[-1].get("report") if _slots else None


def get_market_context(picker_id: Optional[str] = None) -> dict[str, Any]:
    """Return the picker market defaults for the active /chat call.

    Prefers the slot matching ``picker_id`` (or the langgraph runtime
    picker when no id is given); falls back to the most recent slot so
    pipeline nodes running inside the agent invocation still resolve even
    when runtime propagation is unavailable. Returns {} when unknown.
    """
    if picker_id is None:
        picker_id = _runtime_picker_id()
    with _lock:
        if not _slots:
            return {}
        if picker_id:
            for slot in reversed(_slots):
                if slot.get("picker_id") == picker_id:
                    return dict(slot.get("market") or {})
        return dict(_slots[-1].get("market") or {})
