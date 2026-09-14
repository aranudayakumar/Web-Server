import os

from dotenv import load_dotenv


load_dotenv()


class Settings:
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./database.db")
    JWT_SECRET = os.getenv("JWT_SECRET")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL")
    OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    KNOWLEDGE_TOP_K = int(os.getenv("KNOWLEDGE_TOP_K", "3"))
    KNOWLEDGE_SIMILARITY_THRESHOLD = float(os.getenv("KNOWLEDGE_SIMILARITY_THRESHOLD", "0.25"))
    KNOWLEDGE_INGESTION_DIR = os.getenv("KNOWLEDGE_INGESTION_DIR", "./knowledge_sources")
    OPENAI_STT_MODEL = os.getenv("OPENAI_STT_MODEL", "whisper-1")
    OPENAI_TTS_MODEL = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
    OPENAI_TTS_VOICE = os.getenv("OPENAI_TTS_VOICE", "alloy")
    OPENAI_TIMEOUT_SECONDS = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "30"))
    JWT_TTL_MINUTES = int(os.getenv("JWT_TTL_MINUTES", "1440"))
    VOICE_MAX_UPLOAD_BYTES = int(os.getenv("VOICE_MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))

    # VOICE_PROVIDER selects which backend app/voice/router.py's get_speech_to_text() and
    # get_text_to_speech() build: "openai" (default, English-only) or "sunbird" (Sunbird AI,
    # covering Luganda/Acholi/Ateso/Lugbara/Runyankole/Swahili and more).
    VOICE_PROVIDER = os.getenv("VOICE_PROVIDER", "openai")
    SUNBIRD_API_BASE_URL = os.getenv("SUNBIRD_API_BASE_URL", "https://api.sunbird.ai")
    SUNBIRD_API_TOKEN = os.getenv("SUNBIRD_API_TOKEN")
    SUNBIRD_STT_LANGUAGE = os.getenv("SUNBIRD_STT_LANGUAGE", "lug")
    SUNBIRD_TTS_LANGUAGE = os.getenv("SUNBIRD_TTS_LANGUAGE", "lug")
    SUNBIRD_TTS_VOICE = os.getenv("SUNBIRD_TTS_VOICE", "")
    SUNBIRD_TTS_AUDIO_FORMAT_FALLBACK = os.getenv("SUNBIRD_TTS_AUDIO_FORMAT_FALLBACK", "wav")
    SUNBIRD_TIMEOUT_SECONDS = float(os.getenv("SUNBIRD_TIMEOUT_SECONDS", "30"))

    VERIFIED_USERS = {
        username.strip()
        for username in os.getenv("VERIFIED_USERS", "").split(",")
        if username.strip()
    }


settings = Settings()


def validate_startup_settings() -> None:
    errors = []
    if not settings.DATABASE_URL:
        errors.append("DATABASE_URL is required")
    if not settings.JWT_SECRET or len(settings.JWT_SECRET) < 32:
        errors.append("JWT_SECRET must contain at least 32 characters")
    if not settings.OPENAI_API_KEY:
        errors.append("OPENAI_API_KEY is required")
    if not settings.OPENAI_MODEL:
        errors.append("OPENAI_MODEL is required")
    if settings.OPENAI_TIMEOUT_SECONDS <= 0:
        errors.append("OPENAI_TIMEOUT_SECONDS must be positive")
    if settings.VOICE_PROVIDER not in ("openai", "sunbird"):
        errors.append("VOICE_PROVIDER must be 'openai' or 'sunbird'")
    if settings.VOICE_PROVIDER == "sunbird" and not settings.SUNBIRD_API_TOKEN:
        errors.append("SUNBIRD_API_TOKEN is required when VOICE_PROVIDER=sunbird")
    if errors:
        raise RuntimeError("Invalid configuration: " + "; ".join(errors))
