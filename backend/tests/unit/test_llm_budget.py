from app.core.config import settings
from app.core.exceptions import QuotaExceededError
from app.core.llm_budget import clip_text, llm_budget


def setup_function() -> None:
    llm_budget.reset()


def test_clip_text_respects_limit():
    assert clip_text("  hello  ", 10) == "hello"
    assert len(clip_text("x" * 80, 40)) == 40


def test_chat_turn_reserves_estimated_super_tokens():
    used = llm_budget.reserve("chat", picker_id="picker-1")
    assert used == settings.LLM_SUPER_MAX_TOKENS * settings.LLM_CHAT_TURN_CALL_ESTIMATE
    snap = llm_budget.snapshot()
    assert snap["turns_last_minute"] == 1
    assert snap["output_tokens_today"] == used


def test_picker_minute_cap():
    original = settings.LLM_MAX_TURNS_PER_PICKER_PER_MINUTE
    settings.LLM_MAX_TURNS_PER_PICKER_PER_MINUTE = 2
    try:
        llm_budget.reserve("transcribe", picker_id="p")
        llm_budget.reserve("transcribe", picker_id="p")
        try:
            llm_budget.reserve("transcribe", picker_id="p")
            raise AssertionError("expected QuotaExceededError")
        except QuotaExceededError as exc:
            assert exc.status_code == 429
    finally:
        settings.LLM_MAX_TURNS_PER_PICKER_PER_MINUTE = original


def test_provider_quota_pauses_calls():
    llm_budget.trip_provider_quota(seconds=60)
    try:
        llm_budget.reserve("chat")
        raise AssertionError("expected QuotaExceededError")
    except QuotaExceededError as exc:
        assert "paused" in exc.message.lower()
