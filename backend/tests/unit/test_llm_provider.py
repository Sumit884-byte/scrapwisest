from app.core.config import Settings
from app.core.config import settings as app_settings


def test_declared_xkiro_falls_back_to_nebius_when_only_nebius_key_exists():
    settings = Settings.model_construct(
        LLM_PROVIDER="xkiro",
        XKIRO_API_KEY="",
        NEBIUS_API_KEY="n" * 20,
    )
    assert settings.resolved_llm_provider() == "nebius"


def test_declared_nebius_falls_back_to_xkiro_when_only_xkiro_key_exists():
    settings = Settings.model_construct(
        LLM_PROVIDER="nebius",
        XKIRO_API_KEY="x" * 20,
        NEBIUS_API_KEY="",
    )
    assert settings.resolved_llm_provider() == "xkiro"


def test_declared_provider_kept_when_neither_key_exists():
    settings = Settings.model_construct(
        LLM_PROVIDER="xkiro",
        XKIRO_API_KEY="",
        NEBIUS_API_KEY="",
    )
    assert settings.resolved_llm_provider() == "xkiro"


def test_default_max_tokens_are_capped():
    assert 64 <= app_settings.LLM_NANO_MAX_TOKENS <= 512
    assert 128 <= app_settings.LLM_SUPER_MAX_TOKENS <= 1024
    assert app_settings.LLM_ULTRA_MAX_TOKENS <= 1024
    assert app_settings.LLM_MAX_TURNS_PER_DAY > 0
