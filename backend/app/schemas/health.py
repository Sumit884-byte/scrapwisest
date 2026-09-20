"""
Pydantic schemas for service health status.
"""

from __future__ import annotations

from typing import Any, Dict
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    models: Dict[str, Any]
    version: str = "0.1.0"
