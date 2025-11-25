from datetime import datetime
from typing import Dict
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends
from fastapi import UploadFile, File, Form
from fastapi.responses import StreamingResponse

from app.services.supabase_client import (
    fetch_collection_meta,
    fetch_latest_comment_ts,
    fetch_latest_comments,
    update_collection_summary,
)
from app.services.ai_service import generate_summary_async, AIServiceError
from app.services.audio_ai_service import synthesize_speech, transcribe_audio, AudioAIError
from app.middleware.auth import verify_api_key


router = APIRouter(prefix="/api/v1")


@router.post("/summarize/{collection_id}")
async def summarize(
    collection_id: UUID,
    _: bool = Depends(verify_api_key)
) -> Dict[str, str]:
    cid = str(collection_id)
    ai_summary_text, last_summary_generated_at = await fetch_collection_meta(cid)
    if ai_summary_text is None and last_summary_generated_at is None:
        raise HTTPException(status_code=404, detail="Collection not found")

    max_comment_ts = await fetch_latest_comment_ts(cid)
    # Check if summary exists and is not empty, and is fresh
    has_valid_summary = ai_summary_text and ai_summary_text.strip() != ""
    if has_valid_summary and last_summary_generated_at and (
        max_comment_ts is None or last_summary_generated_at > max_comment_ts
    ):
        return {"summary": ai_summary_text}

    comments = await fetch_latest_comments(cid, limit=50)
    if len(comments) < 3:
        return {"summary": "Belum cukup data untuk merangkum."}

    try:
        summary = await generate_summary_async(comments)
    except AIServiceError as e:
        raise HTTPException(status_code=502, detail=str(e))

    # Update database with new summary
    try:
        await update_collection_summary(cid, summary)
    except Exception as e:
        # Log error but don't fail the request - summary is still returned
        import logging
        logging.error(f"Failed to update summary in database for {cid}: {str(e)}")
        # Continue - summary is still valid even if DB update fails
    
    return {"summary": summary}


@router.post("/tts")
async def tts_endpoint(
    text: str = Form(...),
    lang: str = Form("id-ID"),
    voice: str | None = Form(None),
    voice_type: str | None = Form(None),
    format_: str = Form("ogg"),
):
    """
    Text-to-Speech endpoint with voice type support:
    - voice_type: "male", "female", "child" (optional, defaults to "female")
    - voice: specific voice name (overrides voice_type if provided)
    """
    try:
        ogg = format_.lower() == "ogg"
        audio = await synthesize_speech(
            text=text, lang=lang, voice=voice, voice_type=voice_type, ogg=ogg
        )
        media = "audio/ogg" if ogg else "audio/mpeg"
        return StreamingResponse(iter([audio]), media_type=media)
    except AudioAIError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/stt")
async def stt_endpoint(
    file: UploadFile = File(...), 
    encoding: str | None = Form(None), 
    sample_rate: int | None = Form(None), 
    lang: str = Form("id-ID")
):
    try:
        data = await file.read()
        # Auto-detect format from filename
        file_ext = file.filename.split(".")[-1].lower() if file.filename else ""
        
        # Set default sample rate based on format
        if sample_rate is None:
            if file_ext in ["ogg", "opus"]:
                sample_rate = 48000  # OGG Opus typically 48kHz
            elif file_ext in ["mp3", "mpeg"]:
                sample_rate = 44100  # MP3 typically 44.1kHz
            else:
                sample_rate = 48000  # Default for auto-detect
        
        # Auto-detect encoding based on file extension if not provided
        encoding_param = None
        if encoding and encoding.strip() != "" and encoding != "AUTO":
            encoding_param = encoding
        else:
            # Auto-detect based on file extension for better compatibility
            if file_ext in ["mp3", "mpeg"]:
                encoding_param = "MP3"
            elif file_ext in ["ogg", "opus"]:
                # Use OGG_OPUS explicitly with sample_rate for better compatibility
                encoding_param = "OGG_OPUS"
                # Ensure sample_rate is set for OGG Opus (required by Google Cloud)
                if sample_rate is None:
                    sample_rate = 48000
            elif file_ext in ["wav"]:
                encoding_param = "LINEAR16"
            # else: encoding_param stays None for ENCODING_UNSPECIFIED
        
        text = await transcribe_audio(content=data, encoding=encoding_param, sample_rate=sample_rate, lang=lang)
        return {"text": text}
    except AudioAIError as e:
        raise HTTPException(status_code=502, detail=str(e))