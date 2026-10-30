"""Step 6 regression tests: seed/baseline data is explicitly market-scoped.

Fundamental rule: a seed price is valid only for the market it belongs to.

    500 PKR (Pakistan) != 500 INR (India) != 500 USD (USA)

No verified seed for a market -> unavailable. Never fabricate, never reuse
another country's seed, never convert currencies.
"""

from __future__ import annotations

from app.core.config import settings
from app.schemas.market import (
    UNKNOWN_CURRENCY,
    market_consistency_reason,
    market_key,
    normalize_currency,
)
from app.schemas.report import MaterialType
from app.services.location_resolver import validate_market_fields
from app.services.price_estimator import (
    SEED_PRICES,
    _band_for,
    _seed_for,
    estimate,
    seed_info_for,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pakistan_seed(material: MaterialType = MaterialType.METAL_ALUMINUM) -> float:
    return SEED_PRICES[material]


# ---------------------------------------------------------------------------
# Test A -- Pakistan seed (verified market, no history -> seed fallback)
# ---------------------------------------------------------------------------

def test_a_pakistan_seed_last_fallback():
    seed = _pakistan_seed()
    assert seed == 1050.0  # verified value preserved, not altered by refactor

    result = estimate(
        MaterialType.METAL_ALUMINUM,
        "Income Colony",
        [],
        currency="PKR",
        country="Pakistan",
        city="Multan",
        neighborhood="Income Colony",
    )
    assert result.tier_used == "seed"
    assert result.estimated_price_per_kg == seed
    assert result.currency == "PKR"
    assert result.confidence == 0.20


def test_a_pakistan_seed_case_insensitive_currency():
    # "pkr" normalizes to "PKR" via the canonical helper -- same market.
    lower = estimate(
        MaterialType.METAL_ALUMINUM,
        "Income Colony",
        [],
        currency="pkr",
        country="Pakistan",
        city="Multan",
        neighborhood="Income Colony",
    )
    assert lower.tier_used == "seed"
    assert lower.currency == "PKR"
    assert lower.estimated_price_per_kg == _pakistan_seed()


# ---------------------------------------------------------------------------
# Test B -- India isolation (no India seed -> unavailable, never PKR seed)
# ---------------------------------------------------------------------------

def test_b_india_isolation_no_pkr_leak():
    pkr_seed = _pakistan_seed()
    result = estimate(
        MaterialType.METAL_ALUMINUM,
        "Karol Bagh",
        [],
        currency="INR",
        country="India",
        city="Delhi",
        neighborhood="Karol Bagh",
    )
    assert result.tier_used == "unavailable"
    assert result.currency == "INR"
    assert result.estimated_price_per_kg == 0.0
    assert result.confidence == 0.0
    assert result.estimated_price_per_kg != pkr_seed


def test_b_seed_lookup_india_returns_none():
    assert _seed_for(MaterialType.METAL_ALUMINUM, "India", "INR") is None
    assert settings.seed_price_for("metal_aluminum", "India", "INR") is None


# ---------------------------------------------------------------------------
# Test C -- USA isolation (no USA seed -> unavailable, never PKR seed)
# ---------------------------------------------------------------------------

def test_c_usa_isolation_no_pkr_leak():
    pkr_seed = _pakistan_seed()
    result = estimate(
        MaterialType.METAL_ALUMINUM,
        "Pilsen",
        [],
        currency="USD",
        country="United States",
        city="Chicago",
        neighborhood="Pilsen",
    )
    assert result.tier_used == "unavailable"
    assert result.currency == "USD"
    assert result.estimated_price_per_kg == 0.0
    assert result.confidence == 0.0
    assert result.estimated_price_per_kg != pkr_seed


def test_c_seed_lookup_usa_returns_none():
    assert _seed_for(MaterialType.METAL_ALUMINUM, "United States", "USD") is None
    assert settings.seed_price_for("metal_aluminum", "United States", "USD") is None


# ---------------------------------------------------------------------------
# Test D -- Same material, different market
# ---------------------------------------------------------------------------

def test_d_same_material_different_market():
    pakistan = estimate(
        MaterialType.METAL_ALUMINUM,
        "Income Colony",
        [],
        currency="PKR",
        country="Pakistan",
        city="Multan",
        neighborhood="Income Colony",
    )
    india = estimate(
        MaterialType.METAL_ALUMINUM,
        "Karol Bagh",
        [],
        currency="INR",
        country="India",
        city="Delhi",
        neighborhood="Karol Bagh",
    )
    assert pakistan.tier_used == "seed"
    assert pakistan.currency == "PKR"
    assert india.tier_used == "unavailable"
    assert india.currency == "INR"
    # Same material, but the markets must never share the seed value.
    assert pakistan.estimated_price_per_kg == _pakistan_seed()
    assert india.estimated_price_per_kg != pakistan.estimated_price_per_kg


def test_d_seed_identity_is_material_plus_market():
    # (material, market) uniquely identifies a seed -- not material alone.
    assert _seed_for("metal_aluminum", "Pakistan", "PKR") == 1050.0
    assert _seed_for("metal_aluminum", "India", "INR") is None
    assert _seed_for("metal_aluminum", "United States", "USD") is None
    assert _seed_for("metal_aluminum", "France", "EUR") is None
    # Canonical helper: no duplicate market-key representations.
    assert market_key("Pakistan", "PKR") != market_key("India", "INR")
    assert market_key("Pakistan", "PKR") != market_key("United States", "USD")


# ---------------------------------------------------------------------------
# Test E -- No market context is unavailable (not a hidden PKR seed)
# ---------------------------------------------------------------------------

def test_e_blank_market_is_unavailable():
    blank = estimate(MaterialType.PLASTIC_PET, "income colony", [])
    assert blank.tier_used == "unavailable"
    assert blank.estimated_price_per_kg == 0.0
    assert blank.currency == UNKNOWN_CURRENCY
    assert _seed_for(MaterialType.PLASTIC_PET, None, UNKNOWN_CURRENCY) is None
    assert _seed_for(MaterialType.PLASTIC_PET, None, None) is None


def test_e_country_infers_currency_for_verified_seed():
    pakistan = estimate(
        MaterialType.PLASTIC_PET,
        "Karachi",
        [],
        country="Pakistan",
        city="Karachi",
    )
    assert pakistan.tier_used == "seed"
    assert pakistan.currency == "PKR"
    assert pakistan.estimated_price_per_kg == SEED_PRICES[MaterialType.PLASTIC_PET]


def test_e_blank_does_not_leak_into_explicit_markets():
    assert market_key(None, None) == ("unknown", "")
    assert market_key(None, UNKNOWN_CURRENCY) == ("unknown", "")
    assert market_key("India", "INR") != ("unknown", "")
    assert market_key("United States", "USD") != ("unknown", "")
    assert market_key("India", "PKR") != ("unknown", "")


# ---------------------------------------------------------------------------
# Test F -- Currency mismatch (India + PKR preserved, not reinterpreted)
# ---------------------------------------------------------------------------

def test_f_currency_mismatch_preserved_not_reinterpreted():
    reasons = validate_market_fields("PKR", "India", "Delhi", "Karol Bagh")
    assert any("mismatch" in r for r in reasons)
    assert market_consistency_reason("India", "PKR") is not None

    # The estimator must NOT silently reinterpret India/PKR as INR.
    result = estimate(
        MaterialType.METAL_ALUMINUM,
        "Karol Bagh",
        [],
        currency="PKR",
        country="India",
        city="Delhi",
        neighborhood="Karol Bagh",
    )
    assert result.currency == "PKR"  # preserved exactly, not rewritten to INR
    # (PKR, india) is a different market from (PKR, pakistan): no seed.
    assert result.tier_used == "unavailable"
    assert result.estimated_price_per_kg == 0.0


# ---------------------------------------------------------------------------
# Test G -- No fabricated values for unsupported markets
# ---------------------------------------------------------------------------

def test_g_no_fabricated_converted_or_guessed_values():
    pkr_seed = _pakistan_seed()
    for country, currency, city, neighborhood in [
        ("India", "INR", "Delhi", "Karol Bagh"),
        ("United States", "USD", "Chicago", "Pilsen"),
        ("France", "EUR", "Paris", "Le Marais"),
    ]:
        result = estimate(
            MaterialType.METAL_ALUMINUM,
            neighborhood,
            [],
            currency=currency,
            country=country,
            city=city,
            neighborhood=neighborhood,
        )
        assert result.tier_used == "unavailable", (country, currency)
        assert result.estimated_price_per_kg == 0.0
        assert result.confidence == 0.0
        # Not the Pakistan seed, not a conversion, not a guess.
        assert result.estimated_price_per_kg != pkr_seed
        assert _seed_for(MaterialType.METAL_ALUMINUM, country, currency) is None
        assert settings.seed_price_for("metal_aluminum", country, currency) is None
        assert seed_info_for(MaterialType.METAL_ALUMINUM, country, currency) is None


def test_g_all_materials_isolated_for_india_usa():
    # No material may leak a Pakistan seed into India/INR or USA/USD.
    for material in MaterialType:
        assert _seed_for(material, "India", "INR") is None
        assert _seed_for(material, "USA", "USD") is None
        pakistan_seed = _seed_for(material, "Pakistan", "PKR")
        assert pakistan_seed is not None
        assert pakistan_seed == SEED_PRICES[material]


# ---------------------------------------------------------------------------
# Currency normalization uses the existing canonical helper (no duplicates)
# ---------------------------------------------------------------------------

def test_currency_normalization_canonical():
    assert normalize_currency("pkr") == "PKR"
    assert normalize_currency(" pkr ") == "PKR"
    assert normalize_currency("inr") == "INR"
    assert normalize_currency("usd") == "USD"
    assert normalize_currency(None) == UNKNOWN_CURRENCY
    assert normalize_currency("") == UNKNOWN_CURRENCY
    # Canonical market identity derives from the same normalization.
    assert market_key("Pakistan", "pkr") == ("PKR", "pakistan")
    assert market_key("India", "inr") == ("INR", "india")
    assert market_key("United States", "usd") == ("USD", "united states")


# ---------------------------------------------------------------------------
# Price bands are market-scoped (Pakistan/PKR only, never converted)
# ---------------------------------------------------------------------------

def test_bands_scoped_to_verified_market():
    band = _band_for(MaterialType.METAL_ALUMINUM, "Pakistan", "PKR")
    assert band == (150.0, 1500.0)
    # Explicit foreign markets have no bands -- validators must skip.
    assert _band_for(MaterialType.METAL_ALUMINUM, "India", "INR") is None
    assert _band_for(MaterialType.METAL_ALUMINUM, "United States", "USD") is None
    assert _band_for(MaterialType.METAL_ALUMINUM, "India", "PKR") is None
    assert _band_for(MaterialType.METAL_ALUMINUM, None, UNKNOWN_CURRENCY) is None
    # Strict settings helper: only the exact verified market.
    assert settings.price_band_for("metal_aluminum", "Pakistan", "PKR") == (150.0, 1500.0)
    assert settings.price_band_for("metal_aluminum", "India", "INR") is None
    assert settings.price_band_for("metal_aluminum", "United States", "USD") is None
    # No conversion: bands are raw PKR ranges, never FX-adjusted.
    assert settings.price_band_for("metal_aluminum", "Pakistan", "PKR") == (150.0, 1500.0)


# ---------------------------------------------------------------------------
# Seed metadata is explicit but minimal (no management system)
# ---------------------------------------------------------------------------

def test_seed_metadata_explicit_minimal():
    info = seed_info_for(MaterialType.METAL_ALUMINUM, "Pakistan", "PKR")
    assert info is not None
    assert info["material"] == "metal_aluminum"
    assert info["country"] == "Pakistan"
    assert info["currency"] == "PKR"
    assert info["price_per_kg"] == 1050.0
    assert "source" in info and info["source"]

    assert seed_info_for(MaterialType.METAL_ALUMINUM, "India", "INR") is None
    assert seed_info_for(MaterialType.METAL_ALUMINUM, "United States", "USD") is None

    strict = settings.seed_info_for("metal_aluminum", "Pakistan", "PKR")
    assert strict is not None and strict["price_per_kg"] == 1050.0
    assert settings.seed_info_for("metal_aluminum", "India", "INR") is None


def test_verified_seed_values_preserved():
    # Step 6 must not alter verified numbers -- only market association.
    assert settings.SEED_PRICES["plastic_pet"] == 140.0
    assert settings.SEED_PRICES["plastic_hdpe"] == 85.0
    assert settings.SEED_PRICES["glass"] == 8.0
    assert settings.SEED_PRICES["metal_aluminum"] == 1050.0
    assert settings.SEED_PRICES["metal_steel"] == 195.0
    assert settings.SEED_PRICES["cardboard"] == 28.0
    assert settings.SEED_PRICES["mixed_paper"] == 42.0
    assert settings.SEED_PRICES["other"] == 50.0
    assert settings.verified_seed_market_key() == ("PKR", "pakistan")
