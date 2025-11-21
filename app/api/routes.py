from datetime import datetime
from typing import Dict
from uuid import UUID

from fastapi import APIRouter, HTTPException
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


router = APIRouter(prefix="/api/v1")


@router.post("/summarize/{collection_id}")
async def summarize(collection_id: UUID) -> Dict[str, str]:
    cid = str(collection_id)
    ai_summary_text, last_summary_generated_at = await fetch_collection_meta(cid)
    if ai_summary_text is None and last_summary_generated_at is None:
        raise HTTPException(status_code=404, detail="Collection not found")

    max_comment_ts = await fetch_latest_comment_ts(cid)
    if ai_summary_text and last_summary_generated_at and (
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

    await update_collection_summary(cid, summary)
    return {"summary": summary}


@router.post("/tts")
async def tts_endpoint(text: str = Form(...), lang: str = Form("id-ID"), voice: str | None = Form(None), format_: str = Form("ogg")):
    try:
        ogg = format_.lower() == "ogg"
        audio = await synthesize_speech(text=text, lang=lang, voice=voice, ogg=ogg)
        media = "audio/ogg" if ogg else "audio/mpeg"
        return StreamingResponse(iter([audio]), media_type=media)
    except AudioAIError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/stt")
async def stt_endpoint(file: UploadFile = File(...), encoding: str = Form("LINEAR16"), sample_rate: int = Form(16000), lang: str = Form("id-ID")):
    try:
        data = await file.read()
        text = await transcribe_audio(content=data, encoding=encoding, sample_rate=sample_rate, lang=lang)
        return {"text": text}
    except AudioAIError as e:
        raise HTTPException(status_code=502, detail=str(e))