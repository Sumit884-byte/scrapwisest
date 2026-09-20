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
    CLASSIFIER_MODEL_PATH: Path = _BACKEND_DIR / "models" / "classifier" / "scrapsense_model.keras"
    CLASSIFIER_CONFIG_PATH: Path = _BACKEND_DIR / "models" / "classifier" / "config.json"

    # Nebius Token Factory / LLM Settings
    NEBIUS_API_KEY: str = ""
    NEMOTRON_NANO_MODEL: str = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
    NEMOTRON_SUPER_MODEL: str = "nvidia/nemotron-3-super-120b-a12b"
    NEMOTRON_ULTRA_MODEL: str = "nvidia/Nemotron-3-Ultra-550b-a55b"
    NEBIUS_NANO_BASE_URL: str = "https://api.tokenfactory.eu-north1.nebius.com/v1/"
    NEBIUS_REASONING_BASE_URL: str = "https://api.tokenfactory.us-central1.nebius.com/v1/"

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

    # Friendly material mappings (English, Urdu)
    FRIENDLY_MATERIAL_NAMES: dict[str, tuple[str, str]] = {
        "plastic_pet": ("PET plastic", "پلاسٹک (PET)"),
        "plastic_hdpe": ("HDPE plastic", "پلاسٹک (HDPE)"),
        "glass": ("Glass", "شیشہ"),
        "metal_aluminum": ("Aluminum", "ایلومینیم"),
        "metal_steel": ("Steel", "لوہا / سٹیل"),
        "cardboard": ("Cardboard", "گتہ"),
        "mixed_paper": ("Paper", "کاغذ"),
        "other": ("Mixed / other material", "دیگر مواد"),
    }

    # Baseline Seed Prices (PKR / kg)
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

    # Price per kg sanity check bands (min, max in PKR)
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


@lru_cache()
def get_settings() -> Settings:
    settings = Settings()
    # Ensure runtime directories exist
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    return settings


settings = get_settings()
