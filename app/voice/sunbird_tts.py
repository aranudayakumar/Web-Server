import logging

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

_CONTENT_TYPE_TO_FORMAT = {
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/wave": "wav",
    "audio/ogg": "ogg",
}


class SunbirdTextToSpeech:
    """Text-to-speech via Sunbird AI's /tasks/audio/speech endpoint.

    Sunbird's TTS models (Spark-TTS-SALT, Orpheus) synthesize real Ugandan-language
    voices — Luganda, Acholi, Ateso, Lugbara, Runyankole, Swahili — rather than
    OpenAI's English-only voice catalog. Selected via VOICE_PROVIDER=sunbird; matches
    OpenAITextToSpeech's interface so the two are interchangeable from
    app/voice/router.py.

    The endpoint returns a JSON body with an `audio_url` rather than raw bytes, so
    `synthesize()` makes a second request to fetch the audio; the actual returned
    format is read from that response's Content-Type rather than assumed, and exposed
    afterward as `self.audio_format` for the caller to report accurately.

    See https://docs.sunbird.ai/languages and https://huggingface.co/Sunbird/spark-tts-salt.
    """

    def __init__(
        self,
        session: requests.Session | None = None,
        base_url: str | None = None,
        api_token: str | None = None,
        voice: str | None = None,
        language: str | None = None,
    ):
        self.api_token = api_token or settings.SUNBIRD_API_TOKEN
        if not self.api_token:
            raise RuntimeError("SUNBIRD_API_TOKEN is required for Sunbird text-to-speech")
        self.base_url = (base_url or settings.SUNBIRD_API_BASE_URL).rstrip("/")
        self.voice = voice if voice is not None else (settings.SUNBIRD_TTS_VOICE or None)
        self.language = language or settings.SUNBIRD_TTS_LANGUAGE
        self.session = session or requests.Session()
        self.audio_format = settings.SUNBIRD_TTS_AUDIO_FORMAT_FALLBACK

    def synthesize(self, text: str) -> bytes:
        if not text or not text.strip():
            raise ValueError("Text is required for speech synthesis")
        payload = {"text": text, "response_mode": "url", "language": self.language}
        if self.voice:
            payload["voice"] = self.voice
        try:
            response = self.session.post(
                f"{self.base_url}/tasks/audio/speech",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_token}"},
                timeout=settings.SUNBIRD_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            audio_url = response.json().get("audio_url")
            if not audio_url:
                raise RuntimeError("Sunbird TTS response did not include an audio_url")
            audio_response = self.session.get(audio_url, timeout=settings.SUNBIRD_TIMEOUT_SECONDS)
            audio_response.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Sunbird TTS request failed: %s", exc)
            raise RuntimeError("Sunbird speech synthesis request failed") from exc
        content_type = audio_response.headers.get("Content-Type", "").split(";")[0].strip().lower()
        self.audio_format = _CONTENT_TYPE_TO_FORMAT.get(content_type, self.audio_format)
        content = audio_response.content
        if not content:
            raise RuntimeError("Speech synthesis produced no audio")
        return content
