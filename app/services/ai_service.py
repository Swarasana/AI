import asyncio
from typing import List, Optional, Dict

import google.generativeai as genai


class AIServiceError(Exception):
    pass


_configured = False
_model = None


def _is_comments_too_short(comments: List[str]) -> bool:
    """Check if comments are too short or uninformative"""
    if not comments:
        return True
    # Check if average comment length is very short (< 10 chars) or mostly single words
    total_length = sum(len(c.strip()) for c in comments)
    avg_length = total_length / len(comments) if comments else 0
    # Also check if comments are mostly single words or very short phrases
    short_comments = sum(1 for c in comments if len(c.strip().split()) <= 2)
    return avg_length < 15 or short_comments >= len(comments) * 0.7


def _build_prompt_with_context(
    comments: List[str], collection_context: Optional[Dict[str, str]] = None
) -> str:
    """Build prompt with collection context if comments are too short"""
    comments_text = "\n".join(comments)
    
    # If comments are too short and we have context, include it subtly
    if _is_comments_too_short(comments) and collection_context:
        name = collection_context.get("name", "").strip()
        explanation = collection_context.get("artist_explanation", "").strip()
        
        if name or explanation:
            context_note = ""
            if name:
                context_note += f"\n\nKonteks: Karya ini berjudul \"{name}\""
            if explanation:
                # Truncate explanation if too long (max 200 chars)
                short_explanation = (
                    explanation[:200] + "..." if len(explanation) > 200 else explanation
                )
                context_note += f". {short_explanation}"
            context_note += (
                "\n\nGunakan konteks ini dengan bijak untuk memperkaya narasi "
                "ketika komentar pengunjung terlalu singkat, namun tetap fokus pada respons mereka."
            )
            return comments_text + context_note
    
    return comments_text


async def generate_summary_async(
    comments: List[str], collection_context: Optional[Dict[str, str]] = None
) -> str:
    if not comments:
        raise AIServiceError("No comments provided")
    
    prompt_text = _build_prompt_with_context(comments, collection_context)
    
    try:
        global _configured, _model
        if not _configured:
            from app.core.config import get_settings
            from app.core.prompts import SUMMARIZER_SYSTEM_PROMPT
            s = get_settings()
            genai.configure(api_key=s.GEMINI_API_KEY)
            _model = genai.GenerativeModel(
                model_name="gemini-2.5-flash",
                system_instruction=SUMMARIZER_SYSTEM_PROMPT,
            )
            _configured = True

        resp = await asyncio.to_thread(_model.generate_content, prompt_text)
        if not hasattr(resp, "text") or not resp.text:
            raise AIServiceError("Empty AI response")
        return resp.text.strip()
    except Exception as e:
        raise AIServiceError(str(e))


async def generate_incremental_summary_async(
    previous_summary: str,
    new_comments: List[str],
    collection_context: Optional[Dict[str, str]] = None,
) -> str:
    """Generate updated summary by combining previous summary with new comments"""
    if not new_comments:
        raise AIServiceError("No new comments provided")
    
    # Combine previous summary and new comments
    combined_text = (
        f"Ringkasan sebelumnya:\n{previous_summary}\n\nKomentar baru:\n"
        + "\n".join(new_comments)
    )
    
    # Add context if new comments are too short
    if _is_comments_too_short(new_comments) and collection_context:
        name = collection_context.get("name", "").strip()
        explanation = collection_context.get("artist_explanation", "").strip()
        if name or explanation:
            context_note = "\n\nKonteks: "
            if name:
                context_note += f"Karya ini berjudul \"{name}\""
            if explanation:
                short_explanation = (
                    explanation[:200] + "..." if len(explanation) > 200 else explanation
                )
                context_note += f". {short_explanation}"
            combined_text += context_note
    
    try:
        global _configured, _model
        if not _configured:
            from app.core.config import get_settings
            from app.core.prompts import SUMMARIZER_SYSTEM_PROMPT
            s = get_settings()
            genai.configure(api_key=s.GEMINI_API_KEY)
            _model = genai.GenerativeModel(
                model_name="gemini-2.5-flash",
                system_instruction=SUMMARIZER_SYSTEM_PROMPT,
            )
            _configured = True

        # Use a prompt that instructs to update the summary with new comments
        prompt = (
            f"{combined_text}\n\n"
            "Berdasarkan ringkasan sebelumnya dan komentar baru di atas, "
            "buatlah ringkasan yang diperbarui yang menggabungkan informasi lama dan baru. "
            "Ikuti ketentuan yang sama: naratif, maksimal 150 kata, hangat dan inklusif. "
            "Jika komentar baru terlalu singkat, gunakan konteks yang tersedia dengan bijak."
        )
        
        resp = await asyncio.to_thread(_model.generate_content, prompt)
        if not hasattr(resp, "text") or not resp.text:
            raise AIServiceError("Empty AI response")
        return resp.text.strip()
    except Exception as e:
        raise AIServiceError(str(e))