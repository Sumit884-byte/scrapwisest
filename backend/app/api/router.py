"""
Master API router aggregating all v1 domain endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.endpoints import auth, chat, health, materials, prices, reports, voice

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(chat.router)
api_router.include_router(prices.router)
api_router.include_router(reports.router)
api_router.include_router(materials.router)
api_router.include_router(voice.router)
