from openai import OpenAI

from app.core.config import settings


class OpenAITextToSpeech:
    def __init__(self, client=None, model: str | None = None, voice: str | None = None):
        if client is None and not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is required for text-to-speech")
        self.client = client or OpenAI(
            api_key=settings.OPENAI_API_KEY, timeout=settings.OPENAI_TIMEOUT_SECONDS, max_retries=1
        )
        self.model = model or settings.OPENAI_TTS_MODEL
        self.voice = voice or settings.OPENAI_TTS_VOICE
        self.audio_format = "mp3"

    def synthesize(self, text: str) -> bytes:
        if not text or not text.strip():
            raise ValueError("Text is required for speech synthesis")
        response = self.client.audio.speech.create(
            model=self.model, voice=self.voice, input=text, response_format="mp3"
        )
        content = response.content
        if not content:
            raise RuntimeError("Speech synthesis produced no audio")
        return content
