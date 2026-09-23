"""
Materials metadata endpoint: lists supported material categories, translations, and price bounds.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from app.core.config import settings
from app.schemas.market import resolve_currency
from app.schemas.material import MaterialInfo, MaterialListResponse
from app.schemas.report import MaterialType

router = APIRouter(prefix="/materials", tags=["materials"])


@router.get("", response_model=MaterialListResponse)
async def get_materials(
    currency: str = Query("PKR", description="ISO currency for seed prices and bands"),
):
    """
    List all supported recyclable waste material categories with English, Urdu, and Telugu labels,
    baseline seed prices, and expected sanity price bands.
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

        code = resolve_currency(currency, None, None)
        seeds = settings.SEED_PRICES_BY_CURRENCY.get(code, settings.SEED_PRICES)
        bands = settings.PRICE_BANDS_BY_CURRENCY.get(code, settings.PRICE_PER_KG_BANDS)
        seed_price = seeds.get(mat_key, 50.0)
        price_band = bands.get(mat_key, (5.0, 500.0))

        items.append(
            MaterialInfo(
                id=mat_key,
                name_en=name_en,
                name_ur=name_ur,
                name_te=name_te,
                seed_price_per_kg=seed_price,
                price_band_per_kg=price_band,
                currency=code if code != "unknown" else "PKR",
            )
        )

    return MaterialListResponse(materials=items, count=len(items))
