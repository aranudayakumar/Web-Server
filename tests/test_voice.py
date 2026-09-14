import unittest

import requests

from app.voice.stt import OpenAISpeechToText, inspect_wav_audio, validate_audio_payload
import io
import struct
import wave
from app.voice.tts import OpenAITextToSpeech
from app.voice.sunbird_stt import SunbirdSpeechToText
from app.voice.sunbird_tts import SunbirdTextToSpeech


class _FakeTranscription:
    def __init__(self, text):
        self.text = text


class _FakeTranscriptions:
    def __init__(self, text):
        self.text = text
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeTranscription(self.text)


class _FakeAudioSTT:
    def __init__(self, text):
        self.transcriptions = _FakeTranscriptions(text)


class _FakeSTTClient:
    def __init__(self, text="Plant maize after the rains begin."):
        self.audio = _FakeAudioSTT(text)


class _FakeSpeech:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self


class _FakeAudioTTS:
    def __init__(self, content):
        self.speech = _FakeSpeech(content)


class _FakeTTSClient:
    def __init__(self, content=b"fake-mp3-bytes"):
        self.audio = _FakeAudioTTS(content)


class SpeechToTextTests(unittest.TestCase):
    @staticmethod
    def wav_bytes(samples, rate=16000):
        output = io.BytesIO()
        with wave.open(output, "wb") as target:
            target.setnchannels(1)
            target.setsampwidth(2)
            target.setframerate(rate)
            target.writeframes(b"".join(struct.pack("<h", value) for value in samples))
        return output.getvalue()

    def test_transcribe_returns_stripped_text(self):
        client = _FakeSTTClient(text="  Plant maize after the rains begin.  ")
        service = OpenAISpeechToText(client=client, model="whisper-1")
        result = service.transcribe(b"fake-audio-bytes", filename="clip.wav")
        self.assertEqual(result, "Plant maize after the rains begin.")
        self.assertEqual(client.audio.transcriptions.calls[0]["model"], "whisper-1")
        self.assertEqual(client.audio.transcriptions.calls[0]["language"], "en")

    def test_transcribe_rejects_empty_audio(self):
        service = OpenAISpeechToText(client=_FakeSTTClient())
        with self.assertRaises(ValueError):
            service.transcribe(b"")

    def test_transcribe_rejects_blank_transcription(self):
        service = OpenAISpeechToText(client=_FakeSTTClient(text="   "))
        with self.assertRaises(ValueError):
            service.transcribe(b"fake-audio-bytes")

    def test_wav_diagnostics_measure_nonzero_pcm(self):
        audio = self.wav_bytes(([0, 1000, -1000, 2000, -2000] * 2000))
        diagnostics = inspect_wav_audio(audio)
        self.assertIsNotNone(diagnostics)
        self.assertGreater(diagnostics.rms, 0)
        self.assertEqual(diagnostics.peak, 2000)
        self.assertGreater(diagnostics.duration_seconds, 0.5)
        self.assertIsNotNone(validate_audio_payload(audio))

    def test_wav_validation_rejects_silence_and_short_audio(self):
        with self.assertRaisesRegex(ValueError, "silent"):
            validate_audio_payload(self.wav_bytes([0] * 16000))
        with self.assertRaisesRegex(ValueError, "too short"):
            validate_audio_payload(self.wav_bytes([1000] * 100))


class TextToSpeechTests(unittest.TestCase):
    def test_synthesize_returns_audio_bytes(self):
        client = _FakeTTSClient(content=b"mp3-bytes")
        service = OpenAITextToSpeech(client=client, model="gpt-4o-mini-tts", voice="alloy")
        audio = service.synthesize("Plant maize after the rains begin.")
        self.assertEqual(audio, b"mp3-bytes")
        call = client.audio.speech.calls[0]
        self.assertEqual(call["model"], "gpt-4o-mini-tts")
        self.assertEqual(call["voice"], "alloy")
        self.assertEqual(call["input"], "Plant maize after the rains begin.")

    def test_synthesize_rejects_empty_text(self):
        service = OpenAITextToSpeech(client=_FakeTTSClient())
        with self.assertRaises(ValueError):
            service.synthesize("   ")

    def test_synthesize_rejects_empty_audio_response(self):
        service = OpenAITextToSpeech(client=_FakeTTSClient(content=b""))
        with self.assertRaises(RuntimeError):
            service.synthesize("Plant maize.")


class _FakeSunbirdResponse:
    def __init__(self, status_code=200, json_data=None, content=b"", headers=None):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.content = content
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error", response=self)

    def json(self):
        return self._json_data


class _FakeSunbirdSession:
    def __init__(self, post_response=None, get_response=None):
        self.post_response = post_response or _FakeSunbirdResponse()
        self.get_response = get_response or _FakeSunbirdResponse()
        self.post_calls = []
        self.get_calls = []

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        return self.post_response

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        return self.get_response


class SunbirdSpeechToTextTests(unittest.TestCase):
    def test_transcribe_returns_stripped_text(self):
        session = _FakeSunbirdSession(
            post_response=_FakeSunbirdResponse(json_data={"audio_transcription": "  Sasa oli otya?  "})
        )
        service = SunbirdSpeechToText(
            session=session, api_token="test-token", base_url="https://api.sunbird.ai", language="lug"
        )
        result = service.transcribe(b"fake-audio-bytes", filename="clip.wav")
        self.assertEqual(result, "Sasa oli otya?")
        url, kwargs = session.post_calls[0]
        self.assertEqual(url, "https://api.sunbird.ai/tasks/audio/transcriptions")
        self.assertEqual(kwargs["data"]["language"], "lug")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-token")

    def test_transcribe_rejects_empty_audio(self):
        service = SunbirdSpeechToText(session=_FakeSunbirdSession(), api_token="test-token")
        with self.assertRaises(ValueError):
            service.transcribe(b"")

    def test_transcribe_rejects_blank_transcription(self):
        session = _FakeSunbirdSession(post_response=_FakeSunbirdResponse(json_data={"audio_transcription": "   "}))
        service = SunbirdSpeechToText(session=session, api_token="test-token")
        with self.assertRaises(ValueError):
            service.transcribe(b"fake-audio-bytes")

    def test_transcribe_wraps_http_errors(self):
        session = _FakeSunbirdSession(post_response=_FakeSunbirdResponse(status_code=401))
        service = SunbirdSpeechToText(session=session, api_token="test-token")
        with self.assertRaises(RuntimeError):
            service.transcribe(b"fake-audio-bytes")

    def test_requires_api_token(self):
        with self.assertRaises(RuntimeError):
            SunbirdSpeechToText(session=_FakeSunbirdSession(), api_token=None)


class SunbirdTextToSpeechTests(unittest.TestCase):
    def test_synthesize_returns_audio_bytes_and_detects_format(self):
        session = _FakeSunbirdSession(
            post_response=_FakeSunbirdResponse(json_data={"audio_url": "https://cdn.sunbird.ai/audio123.wav"}),
            get_response=_FakeSunbirdResponse(content=b"wav-bytes", headers={"Content-Type": "audio/wav"}),
        )
        service = SunbirdTextToSpeech(session=session, api_token="test-token", voice="salt_lug_0001", language="lug")
        audio = service.synthesize("Sasa oli otya?")
        self.assertEqual(audio, b"wav-bytes")
        self.assertEqual(service.audio_format, "wav")
        post_url, post_kwargs = session.post_calls[0]
        self.assertEqual(post_url, "https://api.sunbird.ai/tasks/audio/speech")
        self.assertEqual(post_kwargs["json"]["voice"], "salt_lug_0001")
        self.assertEqual(post_kwargs["json"]["language"], "lug")
        get_url, _ = session.get_calls[0]
        self.assertEqual(get_url, "https://cdn.sunbird.ai/audio123.wav")

    def test_synthesize_rejects_empty_text(self):
        service = SunbirdTextToSpeech(session=_FakeSunbirdSession(), api_token="test-token")
        with self.assertRaises(ValueError):
            service.synthesize("   ")

    def test_synthesize_raises_when_no_audio_url(self):
        session = _FakeSunbirdSession(post_response=_FakeSunbirdResponse(json_data={}))
        service = SunbirdTextToSpeech(session=session, api_token="test-token")
        with self.assertRaises(RuntimeError):
            service.synthesize("Sasa oli otya?")

    def test_synthesize_rejects_empty_audio_response(self):
        session = _FakeSunbirdSession(
            post_response=_FakeSunbirdResponse(json_data={"audio_url": "https://cdn.sunbird.ai/a.wav"}),
            get_response=_FakeSunbirdResponse(content=b"", headers={"Content-Type": "audio/wav"}),
        )
        service = SunbirdTextToSpeech(session=session, api_token="test-token")
        with self.assertRaises(RuntimeError):
            service.synthesize("Sasa oli otya?")

    def test_requires_api_token(self):
        with self.assertRaises(RuntimeError):
            SunbirdTextToSpeech(session=_FakeSunbirdSession(), api_token=None)


class VoiceProviderSelectionTests(unittest.TestCase):
    def test_selects_sunbird_when_configured(self):
        from app.core.config import settings
        from app.voice.router import get_speech_to_text, get_text_to_speech

        original_provider, original_token = settings.VOICE_PROVIDER, settings.SUNBIRD_API_TOKEN
        settings.VOICE_PROVIDER = "sunbird"
        settings.SUNBIRD_API_TOKEN = "test-token"
        try:
            self.assertIsInstance(get_speech_to_text(), SunbirdSpeechToText)
            self.assertIsInstance(get_text_to_speech(), SunbirdTextToSpeech)
        finally:
            settings.VOICE_PROVIDER = original_provider
            settings.SUNBIRD_API_TOKEN = original_token


if __name__ == "__main__":
    unittest.main()
