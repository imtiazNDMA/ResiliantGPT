import whisper
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Singleton holder for the Whisper model – loaded once per process.
_whisper_model: Optional[Any] = None


def _get_whisper_model() -> Any:
    """
    Return a cached Whisper model, loading it on first use.

    Returns:
        Whisper model instance for transcription.
    """
    global _whisper_model
    if _whisper_model is None:
        logger.info("Loading Whisper model (base) for transcription")
        _whisper_model = whisper.load_model("base")
    return _whisper_model


def transcribe(path: str) -> str:
    """
    Transcribe an audio file at the given path and return the plain text.

    Args:
        path: File path to the audio file to transcribe.

    Returns:
        Transcribed text from the audio file.
    """
    model = _get_whisper_model()
    result = model.transcribe(path)
    return result["text"]
