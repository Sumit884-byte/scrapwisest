"""
Application configuration management using Pydantic Settings.
Centralizes environment variables, model routing parameters, pricing bands, and file paths.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import List, Set

from pydantic_settings import BaseSettings, SettingsConfigDict

# Base directory references
_APP_DIR = Path(__file__).resolve().parent.parent
_BACKEND_DIR = _APP_DIR.parent
_REPO_ROOT = _BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_BACKEND_DIR / ".env", _REPO_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API & Project Metadata
    PROJECT_NAME: str = "Scrapwisest API"
    PROJECT_DESCRIPTION: str = "AI-powered waste classification and price intelligence platform"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = False
    DEMO_MODE: bool = False
    CORS_ORIGINS: List[str] = ["*"]

    # Filesystem Directories
    BACKEND_DIR: Path = _BACKEND_DIR
    UPLOAD_DIR: Path = _BACKEND_DIR / "data" / "uploads"
    DATA_DIR: Path = _BACKEND_DIR / "data"
    MODELS_DIR: Path = _BACKEND_DIR / "models"
    STATIC_DIR: Path = _BACKEND_DIR / "static"
    FRONTEND_DIST_DIR: Path = _REPO_ROOT / "frontend" / "dist"

    # Upload Rules
    MAX_IMAGE_BYTES: int = 8 * 1024 * 1024  # 8MB
    ALLOWED_IMAGE_SUFFIXES: Set[str] = {".jpg", ".jpeg", ".png", ".webp"}

    # Database Configuration
    DATABASE_URL: str = f"sqlite+aiosqlite:///{_BACKEND_DIR / 'reports.db'}"
    SYNC_DATABASE_URL: str = f"sqlite:///{_BACKEND_DIR / 'reports.db'}"

    # Agent Persistence
    CHECKPOINT_DB_PATH: Path = _BACKEND_DIR / "data" / "checkpoints.db"
    MEMORY_DB_PATH: Path = _BACKEND_DIR / "data" / "long_term_memory.db"

    # ML Classifier & Anomaly Model Paths
    ISOLATION_FOREST_PATH: Path = _BACKEND_DIR / "models" / "isolation_forest.pkl"
    CLASSIFIER_DIR: Path = _BACKEND_DIR / "models" / "classifier"
    CLASSIFIER_MODEL_PATH: Path = _BACKEND_DIR / "models" / "classifier" / "scrapwisest_model.keras"
    CLASSIFIER_CONFIG_PATH: Path = _BACKEND_DIR / "models" / "classifier" / "config.json"

    # LLM Provider Selection: "xkiro" (default, free Qwen models) or "nebius" (Nemotron models)
    LLM_PROVIDER: str = "xkiro"

    def resolved_llm_provider(self) -> str:
        """Use the declared provider when its key exists; otherwise the other key."""
        declared = (self.LLM_PROVIDER or "xkiro").strip().lower()
        has_nebius = bool(self.NEBIUS_API_KEY.strip())
        has_xkiro = bool(self.XKIRO_API_KEY.strip())
        wants_nebius = declared in {"nebius", "nemotron", "nebius-token-factory"}
        if wants_nebius:
            if has_nebius or not has_xkiro:
                return "nebius"
            return "xkiro"
        if has_xkiro or not has_nebius:
            return "xkiro"
        return "nebius"

    # xKiro API Gateway (Qwen models) — https://xkiro.com/dashboard/api-keys
    XKIRO_API_KEY: str = ""
    XKIRO_BASE_URL: str = "https://api.xkiro.com/v1"
    XKIRO_FAST_MODEL: str = "qwen/qwen3.8-omni-flash"
    XKIRO_EVERYDAY_MODEL: str = "qwen/qwen3.8-omni-flash:free"
    XKIRO_REASONING_MODEL: str = "qwen/qwen3.8-max:free"
    XKIRO_REQUEST_TIMEOUT: float = 20.0
    XKIRO_MAX_RETRIES: int = 2

    # Nebius Token Factory / LLM Settings (Nemotron models)
    NEBIUS_API_KEY: str = ""
    TAVILY_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    GROQ_WHISPER_MODEL: str = "whisper-large-v3"
    GROQ_STT_FIX_MODEL: str = "openai/gpt-oss-120b"
    GROQ_VISION_MODEL: str = "qwen/qwen3.8-27b"
    SARVAM_API_KEY: str = ""
    SARVAM_STT_MODEL: str = "saaras:v3"
    SARVAM_STT_MODE: str = "transcribe"
    SARVAM_TTS_MODEL: str = "bulbul:v3"
    SARVAM_TTS_SPEAKER: str = "priya"
    NEMOTRON_NANO_MODEL: str = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
    NEMOTRON_SUPER_MODEL: str = "nvidia/nemotron-3-super-120b-a12b"
    NEMOTRON_ULTRA_MODEL: str = "nvidia/Nemotron-3-Ultra-550b-a55b"
    NEBIUS_NANO_BASE_URL: str = "https://api.tokenfactory.eu-north1.nebius.com/v1/"
    NEBIUS_REASONING_BASE_URL: str = "https://api.tokenfactory.us-central1.nebius.com/v1/"
    TOKEN_FACTORY_DEFAULT_REGION: str = "us-central1"
    PIN_TOKEN_FACTORY_REGION: bool = False
    NEBIUS_REQUEST_TIMEOUT: float = 15.0
    NEBIUS_MAX_RETRIES: int = 2
    ENABLE_LLM_FALLBACKS: bool = True

    # Pricing & Anomaly Thresholds
    MIN_LOCAL_REPORTS: int = 5
    MIN_CITY_REPORTS: int = 10
    MIN_REPORTS_FOR_BASELINE: int = 3
    LOW_RATIO: float = 0.5
    HIGH_RATIO: float = 2.0
    MIN_REPORTS_TO_TRAIN_ML: int = 50
    CONTAMINATION_FACTOR: float = 0.05
    LOW_CONFIDENCE_THRESHOLD: float = 0.6
    USE_LLM_REASONING: bool = True
    USE_TAVILY_FALLBACK: bool = True

    # Friendly material mappings (English, Urdu, Telugu)
    FRIENDLY_MATERIAL_NAMES: dict[str, tuple[str, str, str]] = {
        "plastic_pet": ("PET plastic", "پلاسٹک (PET)", "PET ప్లాస్టిక్"),
        "plastic_hdpe": ("HDPE plastic", "پلاسٹک (HDPE)", "HDPE ప్లాస్టిక్"),
        "glass": ("Glass", "شیشہ", "గాజు"),
        "metal_aluminum": ("Aluminum", "ایلومینیم", "అల్యూమినియం"),
        "metal_steel": ("Steel", "لوہا / سٹیل", "ఇనుము / స్టీల్"),
        "cardboard": ("Cardboard", "گتہ", "అట్టపెట్టె (కార్డ్‌బోర్డ్)"),
        "mixed_paper": ("Paper", "کاغذ", "కాగితం"),
        "other": ("Mixed / other material", "دیگر مواد", "ఇతర రకం"),
    }

    # Baseline Seed Prices for the verified Pakistan / PKR market only.
    #
    # Step 6 invariant: a seed is valid ONLY for the market it belongs to,
    # i.e. (material, market) uniquely identifies a seed -- NEVER material
    # alone. ``SEED_PRICES`` below stores the raw verified numbers (material
    # value -> PKR/kg) for that single market; it is NOT a global table.
    # Other markets (e.g. India / INR, United States / USD) have NO verified
    # seeds yet -- look them up via ``seed_price_for()`` (which enforces the
    # canonical ``market_key`` identity) and treat a missing entry as
    # "no market seed" instead of reusing or inventing PKR numbers.
    # See ``app.services.price_estimator._seed_for()``.
    SEED_PRICES: dict[str, float] = {
        "plastic_pet": 140.0,
        "plastic_hdpe": 85.0,
        "glass": 8.0,
        "metal_aluminum": 1050.0,
        "metal_steel": 195.0,
        "cardboard": 28.0,
        "mixed_paper": 42.0,
        "other": 50.0,
    }

    # The single verified seed market. Derived via the canonical
    # ``market_key(country, currency)`` helper -- never duplicated as
    # "Pakistan/PKR", "pk", "pakistan_pkr", etc.
    SEED_MARKET_COUNTRY: str = "Pakistan"
    SEED_MARKET_CURRENCY: str = "PKR"
    # Human-readable provenance for the static baselines. No seed-management
    # system, no external APIs, no conversion -- just a label so callers can
    # surface source/status without inventing per-market numbers.
    SEED_SOURCE: str = "verified Pakistan/PKR baseline"

    # Price per kg sanity check bands for the verified Pakistan / PKR market
    # only (min, max in PKR). They are market-scoped exactly like seeds:
    # look them up via ``price_band_for()``. Other explicit markets skip the
    # band check until per-market bands exist -- never convert PKR bands.
    PRICE_PER_KG_BANDS: dict[str, tuple[float, float]] = {
        "plastic_pet": (20.0, 200.0),
        "plastic_hdpe": (15.0, 150.0),
        "glass": (2.0, 20.0),
        "metal_aluminum": (150.0, 1500.0),
        "metal_steel": (30.0, 200.0),
        "cardboard": (5.0, 40.0),
        "mixed_paper": (5.0, 30.0),
        "other": (5.0, 500.0),
    }

    def _material_key(self, material: object) -> str:
        """Normalize a material to its canonical ``MaterialType`` value."""
        value = getattr(material, "value", material)
        return str(value).strip().lower()

    def verified_seed_market_key(self) -> tuple[str, str]:
        """Canonical ``market_key`` for the single verified seed market."""
        from app.schemas.market import market_key

        return market_key(self.SEED_MARKET_COUNTRY, self.SEED_MARKET_CURRENCY)

    def seed_price_for(
        self,
        material: object,
        country: str | None,
        currency: str | None,
    ) -> float | None:
        """Verified seed for ``(material, market)``, else None.

        Uses the single canonical ``market_key(country, currency)`` identity
        -- the same helper as reports, the estimator, the anomaly detector,
        and picker context. Only the verified Pakistan/PKR market returns a
        value. Every other explicit market (India/INR, USA/USD, France/EUR,
        mismatched India/PKR, ...) returns None so callers emit
        ``unavailable`` instead of reusing PKR numbers, converting currency,
        or fabricating prices. No exchange rates, no guessing.
        """
        from app.schemas.market import market_key

        mat = self._material_key(material)
        if market_key(country, currency) != self.verified_seed_market_key():
            return None
        return self.SEED_PRICES.get(mat)

    def seed_info_for(
        self,
        material: object,
        country: str | None,
        currency: str | None,
    ) -> dict | None:
        """Seed metadata for ``(material, market)``: price/currency/source.

        Minimal provenance without a seed-management system -- just the
        material, its market, the verified price, and the source label.
        Returns None for markets without a verified seed.
        """
        price = self.seed_price_for(material, country, currency)
        if price is None:
            return None
        return {
            "material": self._material_key(material),
            "country": self.SEED_MARKET_COUNTRY,
            "currency": self.SEED_MARKET_CURRENCY,
            "price_per_kg": price,
            "source": self.SEED_SOURCE,
        }

    def price_band_for(
        self,
        material: object,
        country: str | None,
        currency: str | None,
    ) -> tuple[float, float] | None:
        """Sanity band for ``(material, market)``, else None.

        Only the verified Pakistan/PKR market has bands. All other explicit
        markets return None so validators skip the check instead of judging
        e.g. USD prices against PKR-denominated ranges. Legacy unknown
        markets (no currency/country) are handled by the callers'
        compatibility path, not here -- this helper is strict market-exact.
        """
        from app.schemas.market import market_key

        mat = self._material_key(material)
        if market_key(country, currency) != self.verified_seed_market_key():
            return None
        band = self.PRICE_PER_KG_BANDS.get(mat)
        return tuple(band) if band is not None else None


@lru_cache()
def get_settings() -> Settings:
    settings = Settings()
    # Ensure runtime directories exist
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    return settings


settings = get_settings()
