import asyncio
from typing import List

import google.generativeai as genai


class AIServiceError(Exception):
    pass


_configured = False
_model = None


async def generate_summary_async(comments: List[str]) -> str:
    if not comments:
        raise AIServiceError("No comments provided")
    text = "\n".join(comments)
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

        resp = await asyncio.to_thread(_model.generate_content, text)
        if not hasattr(resp, "text") or not resp.text:
            raise AIServiceError("Empty AI response")
        return resp.text.strip()
    except Exception as e:
        raise AIServiceError(str(e))