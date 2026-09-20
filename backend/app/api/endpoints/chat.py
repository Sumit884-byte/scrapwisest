"""
Chat endpoint: accepts text message and optional photo upload.
Processes photo classification ahead of the agent reasoning loop.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from langchain_core.messages import AIMessage

from app.agent.main_agent import AgentContext, get_agent
from app.schemas.chat import ChatResponse
from app.services.image_service import image_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


def _extract_reply(agent_result: dict) -> str:
    """Extract the last AI response text from the agent's message list."""
    for msg in reversed(agent_result.get("messages", [])):
        if not isinstance(msg, AIMessage):
            continue
        content = msg.content
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            texts = [
                b.get("text", "")
                for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            joined = "\n".join(t for t in texts if t).strip()
            if joined:
                return joined
    return "Sorry, I couldn't come up with a response."


@router.post("/chat", response_model=ChatResponse)
async def chat(
    message: str = Form(""),
    picker_id: str = Form(
        ...,
        description="Stable per-picker id from client device for continuity and memory.",
    ),
    image: Optional[UploadFile] = File(None),
):
    text = message.strip()
    logger.info(
        "=== POST /chat received: picker_id='%s' text='%s' image=%s",
        picker_id, text, image.filename if image else None,
    )

    if not text and image is None:
        logger.warning("Rejected /chat request: neither text nor image was provided.")
        raise HTTPException(status_code=400, detail="Provide a message, an image, or both.")

    agent_config = {"configurable": {"thread_id": picker_id}}
    agent_context = AgentContext(picker_id=picker_id)

    # Path A: Text-only request
    if image is None:
        logger.info("Path A: Text-only request. Invoking deep agent...")
        try:
            agent_result = await asyncio.to_thread(
                get_agent().invoke,
                {"messages": [{"role": "user", "content": text}]},
                config=agent_config,
                context=agent_context,
            )
        except Exception as exc:
            logger.exception("Agent invocation failed for text-only path")
            detail = (
                str(exc)
                if "NEBIUS_API_KEY" in str(exc)
                else "Something went wrong processing your message."
            )
            raise HTTPException(status_code=500, detail=detail) from exc

        reply = _extract_reply(agent_result)
        logger.info("Deep agent reply extracted: '%s'", reply)
        return ChatResponse(reply=reply)

    # Path B & C: Photo attached
    logger.info("Processing attached image first...")
    image_path = await image_service.save_image(image)
    try:
        classification = await asyncio.to_thread(image_service.classify_image, image_path)
        logger.info("Image classification outcome: %s", classification)
    except Exception:
        logger.exception("Classification failed unexpectedly")
        classification = {"error": "classification_failed"}

    # Photo only, no text -> classification IS the answer. Agent never runs.
    if not text:
        logger.info("Path B: Photo only (no text). Generating direct static reply...")
        reply = image_service.format_classification_reply(classification)
        logger.info("Classification reply: '%s'", reply)
        return ChatResponse(reply=reply)

    # Photo + text -> fold classification into message as fact
    logger.info("Path C: Photo + Text. Ingesting classification tag into message...")
    if "error" in classification:
        tag = "[image_analysis_failed]"
    else:
        tag = f"[detected_material: {classification['material_type']}, confidence: {classification['confidence']:.2f}]"

    augmented_content = f"{text}\n\n{tag}"
    logger.info("Invoking deep agent with augmented content: '%s'", augmented_content)

    try:
        agent_result = await asyncio.to_thread(
            get_agent().invoke,
            {"messages": [{"role": "user", "content": augmented_content}]},
            config=agent_config,
            context=agent_context,
        )
    except Exception:
        logger.exception("Agent invocation failed for photo+text path")
        raise HTTPException(
            status_code=500, detail="Something went wrong processing your message."
        )

    reply = _extract_reply(agent_result)
    logger.info("Deep agent reply extracted: '%s'", reply)
    return ChatResponse(reply=reply)
