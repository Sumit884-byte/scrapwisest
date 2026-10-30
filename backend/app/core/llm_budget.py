"""
In-process guards so paid LLM / STT / vision calls cannot run away.

Caps are conservative: short completions plus a
daily turn and output-token budget. State is process-local and resets
when the backend restarts.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Optional

from app.core.config import settings
from app.core.exceptions import QuotaExceededError

_MINUTE = 60.0
_HOUR = 3600.0
_DAY = 86400.0

_ROLE_TOKENS = {
    "nano": "LLM_NANO_MAX_TOKENS",
    "super": "LLM_SUPER_MAX_TOKENS",
    "ultra": "LLM_ULTRA_MAX_TOKENS",
    "chat": "LLM_SUPER_MAX_TOKENS",
    "vision": "GROQ_VISION_MAX_TOKENS",
    "stt_fix": "GROQ_STT_FIX_MAX_TOKENS",
    "transcribe": None,
    "tts": None,
}


class LlmBudget:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._turns: Deque[float] = deque()
        self._picker_turns: dict[str, Deque[float]] = defaultdict(deque)
        self._token_events: Deque[tuple[float, int]] = deque()
        self._blocked_until: float = 0.0

    def reset(self) -> None:
        with self._lock:
            self._turns.clear()
            self._picker_turns.clear()
            self._token_events.clear()
            self._blocked_until = 0.0

    def trip_provider_quota(self, seconds: float = 300.0) -> None:
        """Stop further paid calls after the provider returns 429 / quota."""
        with self._lock:
            self._blocked_until = max(self._blocked_until, time.monotonic() + seconds)

    def estimated_tokens(self, role: str) -> int:
        attr = _ROLE_TOKENS.get(role)
        if attr is None:
            return 0
        base = int(getattr(settings, attr))
        if role == "chat":
            return base * max(1, int(settings.LLM_CHAT_TURN_CALL_ESTIMATE))
        return base

    def snapshot(self) -> dict:
        now = time.monotonic()
        with self._lock:
            self._prune(now)
            return {
                "turns_last_minute": sum(1 for t in self._turns if now - t < _MINUTE),
                "turns_last_hour": sum(1 for t in self._turns if now - t < _HOUR),
                "turns_last_day": len(self._turns),
                "max_turns_per_minute": settings.LLM_MAX_TURNS_PER_MINUTE,
                "max_turns_per_hour": settings.LLM_MAX_TURNS_PER_HOUR,
                "max_turns_per_day": settings.LLM_MAX_TURNS_PER_DAY,
                "output_tokens_today": sum(n for _, n in self._token_events),
                "max_output_tokens_per_day": settings.LLM_MAX_OUTPUT_TOKENS_PER_DAY,
                "paused": now < self._blocked_until,
            }

    def reserve(self, role: str, picker_id: str | None = None) -> int:
        """Record one paid call. Raises QuotaExceededError when a cap is hit."""
        now = time.monotonic()
        tokens = self.estimated_tokens(role)
        with self._lock:
            if now < self._blocked_until:
                raise QuotaExceededError(
                    "The language API is paused after a quota error. Try again in a few minutes.",
                    details={"role": role},
                )
            self._prune(now)
            minute = sum(1 for t in self._turns if now - t < _MINUTE)
            hour = sum(1 for t in self._turns if now - t < _HOUR)
            day = len(self._turns)
            if minute >= settings.LLM_MAX_TURNS_PER_MINUTE:
                raise QuotaExceededError(
                    "Too many AI requests right now. Wait a minute and try again.",
                    details={"limit": "per_minute", "role": role},
                )
            if hour >= settings.LLM_MAX_TURNS_PER_HOUR:
                raise QuotaExceededError(
                    "Hourly AI budget is used up. Price checks still work from local data.",
                    details={"limit": "per_hour", "role": role},
                )
            if day >= settings.LLM_MAX_TURNS_PER_DAY:
                raise QuotaExceededError(
                    "Daily AI budget is used up. Come back tomorrow or use a local price check.",
                    details={"limit": "per_day", "role": role},
                )
            if picker_id:
                bucket = self._picker_turns[picker_id]
                while bucket and now - bucket[0] >= _MINUTE:
                    bucket.popleft()
                if len(bucket) >= settings.LLM_MAX_TURNS_PER_PICKER_PER_MINUTE:
                    raise QuotaExceededError(
                        "Too many requests from this device. Wait a moment.",
                        details={"limit": "per_picker", "role": role},
                    )
            used_tokens = sum(n for _, n in self._token_events)
            if tokens and used_tokens + tokens > settings.LLM_MAX_OUTPUT_TOKENS_PER_DAY:
                raise QuotaExceededError(
                    "Daily token budget is used up. Local estimates still work.",
                    details={"limit": "tokens_per_day", "role": role},
                )
            self._turns.append(now)
            if picker_id:
                self._picker_turns[picker_id].append(now)
            if tokens:
                self._token_events.append((now, tokens))
        return tokens

    def _prune(self, now: float) -> None:
        while self._turns and now - self._turns[0] >= _DAY:
            self._turns.popleft()
        while self._token_events and now - self._token_events[0][0] >= _DAY:
            self._token_events.popleft()
        stale = [key for key, bucket in self._picker_turns.items() if not bucket or now - bucket[-1] >= _HOUR]
        for key in stale:
            self._picker_turns.pop(key, None)


llm_budget = LlmBudget()


def clip_text(text: str, limit: Optional[int] = None) -> str:
    cap = int(limit if limit is not None else settings.LLM_MAX_INPUT_CHARS)
    cleaned = (text or "").strip()
    if cap <= 0 or len(cleaned) <= cap:
        return cleaned
    return cleaned[:cap].rstrip()


def reserve_llm(role: str, picker_id: str | None = None) -> int:
    return llm_budget.reserve(role, picker_id)
