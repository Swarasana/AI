from datetime import datetime
from typing import Dict
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends
from fastapi import UploadFile, File, Form
from fastapi.responses import StreamingResponse

from app.services.supabase_client import (
    fetch_collection_meta,
    fetch_collection_context,
    fetch_latest_comment_ts,
    fetch_latest_comments,
    fetch_comment_count,
    fetch_new_comments_after_timestamp,
    update_collection_summary,
)
from app.services.ai_service import (
    generate_summary_async,
    generate_incremental_summary_async,
    AIServiceError,
)
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

    # Check if summary is empty (None or empty string)
    has_valid_summary = ai_summary_text and ai_summary_text.strip() != ""

    if not has_valid_summary:
        # Summary kosong: cek apakah sudah ada minimal 3 komentar
        comment_count = await fetch_comment_count(cid)
        if comment_count < 3:
            # Belum cukup komentar, return empty string
            return {"summary": ""}
        
        # Sudah ada minimal 3 komentar, generate summary dari semua komentar
        comments = await fetch_latest_comments(cid, limit=50)
        if len(comments) < 3:
            return {"summary": ""}
        
        # Fetch collection context untuk memberikan konteks kurator
        collection_context = await fetch_collection_context(cid)
        
        try:
            summary = await generate_summary_async(comments, collection_context)
        except AIServiceError as e:
            raise HTTPException(status_code=502, detail=str(e))

        # Update database with new summary
        try:
            await update_collection_summary(cid, summary)
        except Exception as e:
            import logging
            logging.error(f"Failed to update summary in database for {cid}: {str(e)}")
        
        return {"summary": summary}
    else:
        # Summary sudah ada: ambil summary lama + komentar baru setelah last_summary_generated_at
        if not last_summary_generated_at:
            # Jika tidak ada timestamp, return summary yang ada
            return {"summary": ai_summary_text}
        
        # Ambil komentar baru setelah summary terakhir digenerate
        new_comments = await fetch_new_comments_after_timestamp(
            cid, last_summary_generated_at, limit=50
        )
        
        if not new_comments:
            # Tidak ada komentar baru, return summary lama
            return {"summary": ai_summary_text}
        
        # Ada komentar baru, summarize ulang dengan menggabungkan summary lama + komentar baru
        # Fetch collection context untuk memberikan konteks kurator
        collection_context = await fetch_collection_context(cid)
        
        try:
            updated_summary = await generate_incremental_summary_async(
                ai_summary_text, new_comments, collection_context
            )
        except AIServiceError as e:
            raise HTTPException(status_code=502, detail=str(e))

        # Update database with updated summary
        try:
            await update_collection_summary(cid, updated_summary)
        except Exception as e:
            import logging
            logging.error(f"Failed to update summary in database for {cid}: {str(e)}")
        
        return {"summary": updated_summary}


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