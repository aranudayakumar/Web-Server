import logging

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)


class SunbirdSpeechToText:
    """Speech-to-text via Sunbird AI's /tasks/audio/transcriptions endpoint.

    Sunbird's ASR models are fine-tuned specifically for Ugandan languages (Luganda,
    Acholi, Ateso, Lugbara, Runyankole, Swahili, and dozens more African languages) —
    languages OpenAI's Whisper does not natively recognize the way it does English.
    Selected via VOICE_PROVIDER=sunbird; matches OpenAISpeechToText's interface so the
    two are interchangeable from app/voice/router.py.

    See https://docs.sunbird.ai/languages for the full supported-language list and
    https://salt.sunbird.ai/tutorials/09-asr-models/ for model details.
    """

    def __init__(
        self,
        session: requests.Session | None = None,
        base_url: str | None = None,
        api_token: str | None = None,
        language: str | None = None,
    ):
        self.api_token = api_token or settings.SUNBIRD_API_TOKEN
        if not self.api_token:
            raise RuntimeError("SUNBIRD_API_TOKEN is required for Sunbird speech-to-text")
        self.base_url = (base_url or settings.SUNBIRD_API_BASE_URL).rstrip("/")
        self.language = language or settings.SUNBIRD_STT_LANGUAGE
        self.session = session or requests.Session()

    def transcribe(self, audio_bytes: bytes, filename: str = "audio.wav") -> str:
        if not audio_bytes:
            raise ValueError("Audio payload is empty")
        try:
            response = self.session.post(
                f"{self.base_url}/tasks/audio/transcriptions",
                files={"audio": (filename, audio_bytes, "audio/wav")},
                data={"language": self.language, "timestamps": "false"},
                headers={"Authorization": f"Bearer {self.api_token}"},
                timeout=settings.SUNBIRD_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Sunbird STT request failed: %s", exc)
            raise RuntimeError("Sunbird transcription request failed") from exc
        text = (response.json().get("audio_transcription") or "").strip()
        if not text:
            raise ValueError("Transcription produced no text")
        return text
