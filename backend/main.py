"""
FastAPI entrypoint for ScrapSense.

Exposes POST /chat -- accepts a text message and an optional image.

Image classification is resolved BEFORE the agent is ever invoked, as a
direct function call -- not as a tool the agent has to decide to use.
"Was a photo attached" is a boolean, not a judgment call, so it doesn't
belong in the agent's reasoning loop:

  - photo, no text        -> classify, reply directly, agent never runs
  - photo + text           -> classify, fold the *result* into the message
                               as a fact (`[detected_material: ...]`), then
                               run the agent (classify_image is not one of
                               its tools)
  - text only               -> agent runs exactly as before

The image path itself never enters the agent's context and is never
returned to the client in conversation history -- only the classification
result (a material name + confidence) does.
"""

from __future__ import annotations

import asyncio
import io
import logging
import uuid
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")
load_dotenv()

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import AIMessage
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field

from agent.main_agent import AgentContext, get_agent
from agent.nemotron import routing_info
from material_classifier import classify_image

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)

app = FastAPI(title="ScrapSense API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Serve the Vite build when present so one Nebius Serverless Endpoint can
# host both the picker UI and /chat.
_BACKEND_DIR = Path(__file__).resolve().parent
_STATIC_CANDIDATES = (
    _BACKEND_DIR / "static",
    _BACKEND_DIR.parent / "frontend" / "dist",
)
for _static in _STATIC_CANDIDATES:
    index = _static / "index.html"
    if index.exists():
        from fastapi.staticfiles import StaticFiles
        from fastapi.responses import FileResponse

        @app.get("/")
        def _spa_index():
            return FileResponse(index)

        assets = _static / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")
        logger.info("Serving frontend from %s", _static)
        break

MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8MB
ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}

# Friendly labels for the known material types -- used only for the
# no-agent-invocation path (photo, no text), where there's no LLM around
# to phrase the reply.
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


# ---------
# schemas
# ---------

class ChatResponse(BaseModel):
    reply: str
    history: list[dict] = Field(default_factory=list)


# ---------
# helpers
# ---------

async def _save_image(image: UploadFile) -> str:
    logger.info("Saving uploaded image: filename='%s'", image.filename)
    data = await image.read()
    if not data:
        logger.warning("Upload failed: empty image file")
        raise HTTPException(status_code=400, detail="Empty image upload.")
    if len(data) > MAX_IMAGE_BYTES:
        logger.warning("Upload failed: size %d bytes exceeds 8MB limit", len(data))
        raise HTTPException(status_code=400, detail="Image too large (max 8MB).")

    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
    except UnidentifiedImageError:
        logger.warning("Upload failed: unidentified image format")
        raise HTTPException(status_code=400, detail="File is not a valid image.")

    suffix = Path(image.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        suffix = ".jpg"

    dest = UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}"
    dest.write_bytes(data)
    logger.info("Saved image (%d bytes) to %s", len(data), dest)
    return str(dest)


def _friendly_name(material: str) -> str:
    en, ur = FRIENDLY_MATERIAL_NAMES.get(material, (material.replace("_", " ").title(), ""))
    return f"{en} ({ur})" if ur else en


def _format_classification_reply(result: dict) -> str:
    """Static, no-LLM reply for the photo-only path."""
    if "error" in result:
        return "Sorry, I couldn't read that photo right now. What material is it?"
    return f"That looks like: {_friendly_name(result['material_type'])}."

def _extract_reply(agent_result: dict) -> str:
    """Pull the last AI text message out of the deep agent's message list."""
    for msg in reversed(agent_result.get("messages", [])):
        if not isinstance(msg, AIMessage):
            continue
        content = msg.content
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
            joined = "\n".join(t for t in texts if t).strip()
            if joined:
                return joined
    return "Sorry, I couldn't come up with a response."


@app.post("/chat", response_model=ChatResponse)
async def chat(
    message: str = Form(""),
    picker_id: str = Form(
        ...,
        description="Stable per-picker id from the client (e.g. a UUID "
                     "generated once and persisted on-device). Drives both "
                     "conversation continuity and cross-session memory.",
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


    # ---- No image: unchanged text-only path ----
    if image is None:
        logger.info("Path A: Text-only request. Invoking deep agent...")
        try:
            agent_result = await asyncio.to_thread(
                get_agent().invoke,
                {"messages": [{"role": "user", "content": text}]},
                config=agent_config,
                context=agent_context,
            )
        except Exception:
            logger.exception("Agent invocation failed for text-only path")
            raise HTTPException(status_code=500, detail="Something went wrong processing your message.")

        reply = _extract_reply(agent_result)
        logger.info("Deep agent reply extracted: '%s'", reply)
        return ChatResponse(reply=reply)

    # ---- Image attached: classify deterministically, in code, first ----
    logger.info("Processing attached image first...")
    image_path = await _save_image(image)
    try:
        classification = await asyncio.to_thread(classify_image, image_path)
        logger.info("Image classification outcome: %s", classification)
    except Exception:
        logger.exception("Classification failed unexpectedly")
        classification = {"error": "classification_failed"}

    # Display-safe version of what the user "said" this turn -- never leaks
    # the server-side file path or internal tags into history sent back
    # to the client.
    display_user_content = f"{text} [photo attached]".strip() if text else "[photo attached]"

    # Photo only, no text -> classification IS the answer. Agent never runs.
    if not text:
        logger.info("Path B: Photo only (no text). Generating direct static reply (agent skipped)...")
        reply = _format_classification_reply(classification)
        logger.info("Classification reply: '%s'", reply)
    
        return ChatResponse(reply=reply)

    # Photo + text -> fold the classification result into the message as a
    # fact, run the agent on the text as normal. classify_image is not one
    # of its tools; it never has to decide to call anything for this.
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
        raise HTTPException(status_code=500, detail="Something went wrong processing your message.")

    reply = _extract_reply(agent_result)
    logger.info("Deep agent reply extracted: '%s'", reply)
    return ChatResponse(reply=reply)


@app.get("/health")
def health():
    logger.info("Health check endpoint accessed")
    return {"status": "ok", "models": routing_info()}
