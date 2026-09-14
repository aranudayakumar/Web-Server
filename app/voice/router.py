import base64
import json
import logging
import hashlib
import time

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.chat import create_chat_response
from app.core.config import settings
from app.db.session import get_db
from app.models import User
from app.voice.stt import OpenAISpeechToText, validate_audio_payload
from app.voice.tts import OpenAITextToSpeech
from app.voice.sunbird_stt import SunbirdSpeechToText
from app.voice.sunbird_tts import SunbirdTextToSpeech

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])

SpeechToTextProvider = OpenAISpeechToText | SunbirdSpeechToText
TextToSpeechProvider = OpenAITextToSpeech | SunbirdTextToSpeech


class VoiceChatResponse(BaseModel):
    transcript: str
    content: str
    citations: list[dict]
    audio_base64: str
    audio_format: str = "mp3"
    timings: dict[str, int | None]


def get_speech_to_text() -> SpeechToTextProvider:
    if settings.VOICE_PROVIDER == "sunbird":
        return SunbirdSpeechToText()
    return OpenAISpeechToText()


def get_text_to_speech() -> TextToSpeechProvider:
    if settings.VOICE_PROVIDER == "sunbird":
        return SunbirdTextToSpeech()
    return OpenAITextToSpeech()


@router.post("/chat", response_model=VoiceChatResponse)
async def voice_chat(
    audio: UploadFile = File(...),
    conversation_id: int | None = Form(None),
    voice_session_id: int | None = Form(None),
    include_audio: bool = Form(True),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    stt: SpeechToTextProvider = Depends(get_speech_to_text),
    tts: TextToSpeechProvider = Depends(get_text_to_speech),
):
    """Speech in, speech out: transcribes the upload, runs it through the normal RAG
    chat pipeline, then synthesizes the reply as audio."""
    backend_received_at = time.perf_counter_ns()
    if not audio.content_type or not audio.content_type.startswith("audio/"):
        raise HTTPException(415, "An audio content type is required")
    audio_bytes = await audio.read(settings.VOICE_MAX_UPLOAD_BYTES + 1)
    if not audio_bytes:
        raise HTTPException(422, "Audio payload is empty")
    if len(audio_bytes) > settings.VOICE_MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Audio payload is too large")
    audio_hash = hashlib.sha256(audio_bytes).hexdigest()
    logger.warning(
        "VOICE session=%s HTTP_AUDIO file=%s content_type=%s bytes=%d sha256=%s",
        voice_session_id, audio.filename, audio.content_type, len(audio_bytes), audio_hash,
    )
    try:
        diagnostics = validate_audio_payload(audio_bytes)
    except ValueError as exc:
        logger.warning("VOICE session=%s CAPTURE_REJECTED sha256=%s reason=%s", voice_session_id, audio_hash, exc)
        raise HTTPException(422, str(exc)) from exc
    if diagnostics is not None:
        logger.warning(
            "VOICE session=%s PCM sha256=%s duration=%.3fs rate=%d frames=%d rms=%d peak=%d",
            voice_session_id, audio_hash, diagnostics.duration_seconds, diagnostics.sample_rate,
            diagnostics.frames, diagnostics.rms, diagnostics.peak,
        )
    stt_started_at = time.perf_counter_ns()
    try:
        transcript = stt.transcribe(audio_bytes, filename=audio.filename or "audio.wav")
    except ValueError as exc:
        raise HTTPException(422, "Audio could not be transcribed") from exc
    except Exception as exc:
        logger.error("Speech transcription failed: %s", type(exc).__name__)
        raise HTTPException(502, "Speech transcription unavailable") from exc

    stt_completed_at = time.perf_counter_ns()
    logger.warning("VOICE session=%s STT_FINAL sha256=%s transcript=%r", voice_session_id, audio_hash, transcript[:500])

    content = ""
    citations: list[dict] = []
    chat_timing: dict[str, int] = {}
    for event in create_chat_response(
        db, user, transcript, conversation_id=conversation_id, timing=chat_timing
    ):
        payload = json.loads(event.removeprefix("data: ").strip())
        if "error" in payload:
            raise HTTPException(502, payload["error"])
        if "content" in payload:
            content = payload["content"]
        if "citations" in payload:
            citations = payload["citations"]

    if not content:
        raise HTTPException(502, "Chat service produced no response")

    tts_started_at = time.perf_counter_ns()
    reply_audio = b""
    if include_audio:
        try:
            reply_audio = tts.synthesize(content)
        except Exception as exc:
            logger.error("Speech synthesis failed: %s", type(exc).__name__)
            raise HTTPException(502, "Speech synthesis unavailable") from exc
        if not reply_audio:
            raise HTTPException(502, "Speech synthesis produced no audio")
    tts_completed_at = time.perf_counter_ns()
    tts_elapsed_ms = (tts_completed_at - tts_started_at) // 1_000_000

    timings = {
        "backend_received_to_stt_start_ms": (stt_started_at - backend_received_at) // 1_000_000,
        "stt_ms": (stt_completed_at - stt_started_at) // 1_000_000,
        "llm_first_token_ms": None,
        "llm_completion_ms": chat_timing.get("llm_completion_ms", 0),
        "tts_first_audio_ms": tts_elapsed_ms if include_audio else None,
        "tts_completion_ms": tts_elapsed_ms,
        "backend_total_ms": (tts_completed_at - backend_received_at) // 1_000_000,
    }
    logger.warning("VOICE session=%s TIMING %s", voice_session_id, timings)

    return VoiceChatResponse(
        transcript=transcript,
        content=content,
        citations=citations,
        audio_base64=base64.b64encode(reply_audio).decode("ascii"),
        audio_format=getattr(tts, "audio_format", "mp3") if include_audio else "mp3",
        timings=timings,
    )
