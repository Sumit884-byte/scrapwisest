"""Local NVIDIA Parakeet EN 0.6B speech-to-text.

On Apple Silicon this loads the official English TDT 0.6B weights through
``parakeet-mlx`` (``mlx-community/parakeet-tdt-0.6b-v2``). On CUDA it uses
NeMo ``nvidia/parakeet-tdt-0.6b-v2`` when that toolkit is installed.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

_NVIDIA_EN_06B = "nvidia/parakeet-tdt-0.6b-v2"
_MLX_EN_06B = "mlx-community/parakeet-tdt-0.6b-v2"

_lock = threading.Lock()
_model = None
_backend: Optional[str] = None
_loaded_id: Optional[str] = None
_load_error: Optional[str] = None


def _ffmpeg_bin() -> str:
    configured = (settings.PARAKEET_FFMPEG or "").strip()
    if configured:
        return configured
    return shutil.which("ffmpeg") or "ffmpeg"


def _mlx_model_id(requested: str) -> str:
    name = (requested or "").strip() or _NVIDIA_EN_06B
    aliases = {
        "nvidia/parakeet-tdt-0.6b-v2": _MLX_EN_06B,
        "parakeet-tdt-0.6b-v2": _MLX_EN_06B,
        "parakeet-en-0.6b": _MLX_EN_06B,
        "parakeet-en-0.6B": _MLX_EN_06B,
    }
    return aliases.get(name, name)


def parakeet_enabled() -> bool:
    return bool(settings.PARAKEET_ENABLED)


def parakeet_available() -> bool:
    """True when local Parakeet is turned on and a backend can be imported."""
    if not parakeet_enabled():
        return False
    if _model is not None:
        return True
    if _load_error:
        return False
    try:
        import parakeet_mlx  # noqa: F401

        return True
    except ImportError:
        pass
    try:
        import nemo.collections.asr  # noqa: F401

        return True
    except ImportError:
        return False


def parakeet_status() -> dict:
    return {
        "enabled": parakeet_enabled(),
        "available": parakeet_available(),
        "backend": _backend,
        "model": _loaded_id or settings.PARAKEET_MODEL,
        "error": _load_error,
    }


def _load_model():
    global _model, _backend, _loaded_id, _load_error
    if _model is not None:
        return _model
    with _lock:
        if _model is not None:
            return _model
        requested = (settings.PARAKEET_MODEL or "").strip() or _NVIDIA_EN_06B
        try:
            from parakeet_mlx import from_pretrained

            mlx_id = _mlx_model_id(requested)
            logger.info("Loading local Parakeet EN 0.6B via parakeet-mlx (%s)", mlx_id)
            _model = from_pretrained(mlx_id)
            _backend = "parakeet-mlx"
            _loaded_id = mlx_id
            _load_error = None
            return _model
        except ImportError:
            logger.info("parakeet-mlx not installed; trying NeMo")
        except Exception as exc:
            logger.exception("parakeet-mlx failed to load %s", requested)
            _load_error = str(exc)

        try:
            import nemo.collections.asr as nemo_asr

            logger.info("Loading local Parakeet EN 0.6B via NeMo (%s)", requested)
            _model = nemo_asr.models.ASRModel.from_pretrained(model_name=requested)
            _backend = "nemo"
            _loaded_id = requested
            _load_error = None
            return _model
        except ImportError:
            _load_error = _load_error or "Install parakeet-mlx (Apple Silicon) or nemo_toolkit[asr]"
        except Exception as exc:
            logger.exception("NeMo failed to load %s", requested)
            _load_error = str(exc)
        raise RuntimeError(_load_error or "Local Parakeet is not available")


def _write_16k_wav(audio_bytes: bytes, filename: str) -> Path:
    suffix = Path(filename or "audio.webm").suffix or ".webm"
    tmp_in = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp_out = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    tmp_out.close()
    try:
        tmp_in.write(audio_bytes)
        tmp_in.close()
        cmd = [
            _ffmpeg_bin(),
            "-y",
            "-i",
            tmp_in.name,
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            tmp_out.name,
        ]
        subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=30,
        )
        return Path(tmp_out.name)
    except Exception:
        try:
            os.unlink(tmp_out.name)
        except OSError:
            pass
        raise
    finally:
        try:
            os.unlink(tmp_in.name)
        except OSError:
            pass


def _extract_text(result) -> str:
    if result is None:
        return ""
    if isinstance(result, str):
        return result.strip()
    text = getattr(result, "text", None)
    if text:
        return str(text).strip()
    if isinstance(result, dict):
        return str(result.get("text") or "").strip()
    if isinstance(result, (list, tuple)) and result:
        return _extract_text(result[0])
    return str(result).strip()


def transcribe_parakeet(audio_bytes: bytes, filename: str) -> str:
    """Transcribe a clip with the local English Parakeet 0.6B model."""
    wav_path = _write_16k_wav(audio_bytes, filename)
    try:
        model = _load_model()
        if _backend == "nemo":
            raw = model.transcribe([str(wav_path)])
        else:
            raw = model.transcribe(str(wav_path))
        text = _extract_text(raw)
        logger.info("Parakeet (%s) text=%r", _backend, text[:80])
        return text
    finally:
        try:
            os.unlink(wav_path)
        except OSError:
            pass
