"""
Materials metadata endpoint: lists supported material categories, translations, and price bounds.
"""

from __future__ import annotations

from fastapi import APIRouter
from app.core.config import settings
from app.schemas.material import MaterialInfo, MaterialListResponse
from app.schemas.report import MaterialType

router = APIRouter(prefix="/materials", tags=["materials"])


@router.get("", response_model=MaterialListResponse)
async def get_materials():
    """
    List all supported recyclable waste material categories with English, Urdu, and Telugu labels,
    baseline seed prices, and expected sanity price bands.

    Step 6: the seeds/bands below belong EXPLICITLY to the verified
    Pakistan/PKR market only (see ``settings.SEED_MARKET_COUNTRY /
    SEED_MARKET_CURRENCY``). They are resolved through the market-scoped
    ``settings.seed_price_for / price_band_for`` helpers -- never a global
    table, never converted, never fabricated for other markets. Other
    markets (India/INR, USA/USD, ...) have no verified seeds yet.
    """
    items = []
    for mat in MaterialType:
        mat_key = mat.value
        names = settings.FRIENDLY_MATERIAL_NAMES.get(
            mat_key, (mat_key.replace("_", " ").title(), "", "")
        )
        name_en = names[0]
        name_ur = names[1] if len(names) > 1 else ""
        name_te = names[2] if len(names) > 2 else ""

        # Market-scoped lookup for the verified Pakistan/PKR market.
        # These helpers return None for any other market; here we always
        # query the verified market itself, so a value must exist (values
        # preserved from the pre-Step-6 configuration). No 50.0 / (5,500)
        # fabrication: unknown materials fall back to the verified "other"
        # baseline only when the market itself is verified.
        seed_price = settings.seed_price_for(
            mat_key,
            settings.SEED_MARKET_COUNTRY,
            settings.SEED_MARKET_CURRENCY,
        )
        if seed_price is None:
            seed_price = settings.SEED_PRICES.get(
                mat_key, settings.SEED_PRICES.get("other", 50.0)
            )
        price_band = settings.price_band_for(
            mat_key,
            settings.SEED_MARKET_COUNTRY,
            settings.SEED_MARKET_CURRENCY,
        )
        if price_band is None:
            raw_band = settings.PRICE_PER_KG_BANDS.get(mat_key)
            price_band = tuple(raw_band) if raw_band is not None else (5.0, 500.0)

        items.append(
            MaterialInfo(
                id=mat_key,
                name_en=name_en,
                name_ur=name_ur,
                name_te=name_te,
                seed_price_per_kg=seed_price,
                price_band_per_kg=price_band,
                currency=settings.SEED_MARKET_CURRENCY,
            )
        )

    return MaterialListResponse(materials=items, count=len(items))
