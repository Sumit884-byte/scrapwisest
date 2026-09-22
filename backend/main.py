"""
FastAPI entrypoint for ScrapSense.
Re-exports the modular app from app.main while maintaining full backwards compatibility.
"""

from __future__ import annotations

from app.main import app
from app.schemas.chat import ChatResponse
from app.agent.main_agent import AgentContext, get_agent
from app.agent.models import routing_info
from app.services.image_service import classify_image

# Export symbols for backward compatibility with legacy scripts and tests
__all__ = [
    "app",
    "ChatResponse",
    "AgentContext",
    "get_agent",
    "routing_info",
    "classify_image",
]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
