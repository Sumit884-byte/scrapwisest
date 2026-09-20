"""
Pydantic schemas for the chat endpoint.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(default="", description="Text message from waste picker")
    picker_id: str = Field(..., description="Unique picker identifier")


class ChatResponse(BaseModel):
    reply: str
    history: List[Dict[str, Any]] = Field(default_factory=list)
