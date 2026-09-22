"""Application package.

Keep the FastAPI application lazy-loaded so maintenance scripts can import
repositories and schemas without initializing every API integration and model
dependency.
"""

from __future__ import annotations

__all__ = ["app"]


def __getattr__(name: str):
    if name == "app":
        from app.main import app as fastapi_app

        return fastapi_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
