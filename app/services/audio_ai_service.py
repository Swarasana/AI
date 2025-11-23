import asyncio
from typing import Optional

from google.cloud import speech_v1 as speech
from google.cloud import texttospeech_v1 as tts


class AudioAIError(Exception):
    pass


async def synthesize_speech(
    text: str, lang: str = "id-ID", voice: Optional[str] = None, ogg: bool = True
) -> bytes:
    try:

        def _run() -> bytes:
            import os
            from pathlib import Path

            # Set Google Cloud credentials path
            creds_path = (
                Path(__file__).resolve().parents[2]
                / "hms-fund-438007-ec9106f14570.json"
            )
            if creds_path.exists():
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(creds_path)

            client = tts.TextToSpeechClient()

            # Use SSML for more natural speech with better prosody
            # Rate: slightly faster (1.1x), pitch: more expressive, volume: normal
            ssml_text = f"""<speak>
                <prosody rate="1.1" pitch="+2st" volume="+0dB">
                    {text}
                </prosody>
            </speak>"""

            input_ = tts.SynthesisInput(ssml=ssml_text)

            # Use Wavenet voice for better quality (more natural)
            # Handle voice selection - use local variable to avoid scope issues
            selected_voice = voice
            if not selected_voice:
                # Default to Wavenet-A for Indonesian (female, natural)
                if lang.startswith("id"):
                    selected_voice = "id-ID-Wavenet-A"
                else:
                    selected_voice = None

            voice_params = (
                tts.VoiceSelectionParams(language_code=lang, name=selected_voice)
                if selected_voice
                else tts.VoiceSelectionParams(language_code=lang)
            )

            audio_cfg = tts.AudioConfig(
                audio_encoding=(
                    tts.AudioEncoding.OGG_OPUS if ogg else tts.AudioEncoding.MP3
                ),
                speaking_rate=1.0,  # Base rate (SSML prosody will override)
                pitch=0.0,  # Base pitch (SSML prosody will override)
            )

            resp = client.synthesize_speech(
                input=input_, voice=voice_params, audio_config=audio_cfg
            )
            return resp.audio_content

        return await asyncio.to_thread(_run)
    except Exception as e:
        raise AudioAIError(str(e))


async def transcribe_audio(
    content: bytes,
    encoding: Optional[str] = None,
    sample_rate: Optional[int] = None,
    lang: str = "id-ID",
) -> str:
    try:

        def _run() -> str:
            import os
            from pathlib import Path

            # Set Google Cloud credentials path
            creds_path = (
                Path(__file__).resolve().parents[2]
                / "hms-fund-438007-ec9106f14570.json"
            )
            if creds_path.exists():
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(creds_path)

            client = speech.SpeechClient()

            # Handle encoding - use explicit encoding if provided, otherwise auto-detect
            if encoding is None or encoding == "" or encoding == "AUTO":
                # Use ENCODING_UNSPECIFIED for auto-detection
                # Use enhanced model for better accuracy, especially for Indonesian
                cfg = speech.RecognitionConfig(
                    encoding=speech.RecognitionConfig.AudioEncoding.ENCODING_UNSPECIFIED,
                    language_code=lang,
                    enable_automatic_punctuation=True,
                    model="latest_long",
                    use_enhanced=True,
                )
            else:
                # Use specified encoding
                try:
                    encoding_enum = getattr(
                        speech.RecognitionConfig.AudioEncoding, encoding
                    )
                except AttributeError:
                    # Fallback to auto-detect if encoding not recognized
                    encoding_enum = (
                        speech.RecognitionConfig.AudioEncoding.ENCODING_UNSPECIFIED
                    )

                # Build config based on encoding type
                if (
                    encoding_enum
                    == speech.RecognitionConfig.AudioEncoding.ENCODING_UNSPECIFIED
                ):
                    # Auto-detect: minimal config
                    cfg = speech.RecognitionConfig(
                        encoding=encoding_enum,
                        language_code=lang,
                        enable_automatic_punctuation=True,
                    )
                elif encoding_enum == speech.RecognitionConfig.AudioEncoding.OGG_OPUS:
                    # OGG Opus: must specify sample_rate_hertz (48000 is typical)
                    # Use enhanced model for better accuracy, especially for Indonesian
                    cfg = speech.RecognitionConfig(
                        encoding=encoding_enum,
                        sample_rate_hertz=sample_rate or 48000,
                        language_code=lang,
                        enable_automatic_punctuation=True,
                        model="latest_long",
                        use_enhanced=True,
                    )
                elif encoding_enum == speech.RecognitionConfig.AudioEncoding.MP3:
                    # MP3: don't specify sample_rate_hertz (auto-detect)
                    cfg = speech.RecognitionConfig(
                        encoding=encoding_enum,
                        language_code=lang,
                        enable_automatic_punctuation=True,
                    )
                else:
                    # Uncompressed formats: specify sample_rate_hertz
                    cfg = speech.RecognitionConfig(
                        encoding=encoding_enum,
                        sample_rate_hertz=sample_rate or 16000,
                        language_code=lang,
                        enable_automatic_punctuation=True,
                    )

            # Use recognize for short audio (< 1 minute), streaming_recognize for longer
            # Check audio length - if > 60 seconds, use streaming
            audio = speech.RecognitionAudio(content=content)

            # Try recognize first (simpler, works for most cases)
            resp = client.recognize(config=cfg, audio=audio)

            parts = []
            for r in resp.results:
                if r.alternatives:
                    transcript = r.alternatives[0].transcript
                    confidence = (
                        r.alternatives[0].confidence
                        if hasattr(r.alternatives[0], "confidence")
                        else None
                    )
                    parts.append(transcript)

            result = " ".join(parts).strip()

            # If no results and audio might be long, try streaming_recognize
            if not result and len(content) > 100000:  # > 100KB might need streaming
                # Use streaming for longer audio
                import io

                stream = [content]
                requests = (
                    speech.StreamingRecognizeRequest(audio_content=chunk)
                    for chunk in stream
                )
                config_request = speech.StreamingRecognizeRequest(
                    streaming_config=speech.StreamingRecognitionConfig(config=cfg)
                )

                streaming_config = speech.StreamingRecognitionConfig(config=cfg)
                streaming_requests = [
                    speech.StreamingRecognizeRequest(streaming_config=streaming_config)
                ]
                streaming_requests.extend(
                    speech.StreamingRecognizeRequest(audio_content=chunk)
                    for chunk in [content]
                )

                stream_resp = client.streaming_recognize(streaming_requests)
                for response in stream_resp:
                    for result in response.results:
                        if result.alternatives:
                            parts.append(result.alternatives[0].transcript)
                result = " ".join(parts).strip()

            # Return result (empty string if no transcription)
            return result if result else ""

        return await asyncio.to_thread(_run)
    except Exception as e:
        raise AudioAIError(str(e))
