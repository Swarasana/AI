import asyncio
from typing import Optional

from google.cloud import speech_v1 as speech
from google.cloud import texttospeech_v1 as tts


class AudioAIError(Exception):
    pass


async def synthesize_speech(text: str, lang: str = "id-ID", voice: Optional[str] = None, ogg: bool = True) -> bytes:
    try:
        def _run() -> bytes:
            client = tts.TextToSpeechClient()
            input_ = tts.SynthesisInput(text=text)
            voice_params = tts.VoiceSelectionParams(language_code=lang, name=voice) if voice else tts.VoiceSelectionParams(language_code=lang)
            audio_cfg = tts.AudioConfig(audio_encoding=tts.AudioEncoding.OGG_OPUS if ogg else tts.AudioEncoding.MP3)
            resp = client.synthesize_speech(input=input_, voice=voice_params, audio_config=audio_cfg)
            return resp.audio_content

        return await asyncio.to_thread(_run)
    except Exception as e:
        raise AudioAIError(str(e))


async def transcribe_audio(content: bytes, encoding: str = "LINEAR16", sample_rate: int = 16000, lang: str = "id-ID") -> str:
    try:
        def _run() -> str:
            client = speech.SpeechClient()
            cfg = speech.RecognitionConfig(
                encoding=getattr(speech.RecognitionConfig.AudioEncoding, encoding),
                sample_rate_hertz=sample_rate,
                language_code=lang,
                enable_automatic_punctuation=True,
            )
            audio = speech.RecognitionAudio(content=content)
            resp = client.recognize(config=cfg, audio=audio)
            parts = []
            for r in resp.results:
                if r.alternatives:
                    parts.append(r.alternatives[0].transcript)
            return " ".join(parts).strip()

        return await asyncio.to_thread(_run)
    except Exception as e:
        raise AudioAIError(str(e))