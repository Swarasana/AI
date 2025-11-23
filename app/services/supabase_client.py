import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

from supabase import AsyncClient, acreate_client

from app.core.config import get_settings


_client: Optional[AsyncClient] = None
_lock = asyncio.Lock()


async def get_client() -> AsyncClient:
    global _client
    if _client is None:
        async with _lock:
            if _client is None:
                s = get_settings()
                _client = await acreate_client(s.SUPABASE_URL, s.SUPABASE_KEY)
    return _client


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    v = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(v)
    except ValueError:
        # Handle timestamp with variable microsecond precision
        # e.g., "2025-11-23T10:16:35.60425+00:00" -> normalize to 6 digits
        import re
        # Match pattern: YYYY-MM-DDTHH:MM:SS.microseconds+timezone
        match = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\.(\d+)([+-]\d{2}:\d{2})", v)
        if match:
            base, microsec, tz = match.groups()
            # Pad microseconds to 6 digits
            microsec = microsec.ljust(6, "0")[:6]
            v = f"{base}.{microsec}{tz}"
            try:
                return datetime.fromisoformat(v)
            except:
                pass
        # Fallback: try parsing without microseconds
        try:
            if "." in v:
                v_no_micro = v.split(".")[0]
                if "+" in v:
                    tz_part = v.split("+")[-1]
                    v_no_micro += f"+{tz_part}"
                elif v.count("-") > 2:  # timezone has -
                    parts = v.split("-")
                    v_no_micro = "-".join(parts[:-2]) + "-" + parts[-1]
                else:
                    v_no_micro += "+00:00"
                return datetime.fromisoformat(v_no_micro)
        except:
            pass
        return None


async def fetch_collection_meta(
    collection_id: str,
) -> tuple[Optional[str], Optional[datetime]]:
    client = await get_client()
    resp = await (
        client.table("collections")
        .select("ai_summary_text,last_summary_generated_at")
        .eq("id", collection_id)
        .maybe_single()
        .execute()
    )
    if not resp or not hasattr(resp, "data") or resp.data is None:
        return None, None
    data: Optional[dict[str, Any]] = resp.data if isinstance(resp.data, dict) else None
    if not data:
        return None, None
    return data.get("ai_summary_text"), _parse_ts(data.get("last_summary_generated_at"))


async def fetch_latest_comment_ts(collection_id: str) -> Optional[datetime]:
    client = await get_client()
    resp = await (
        client.table("comments")
        .select("created_at")
        .eq("collection_id", collection_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = resp.data if isinstance(resp.data, list) else []
    if not rows:
        return None
    return _parse_ts(rows[0].get("created_at"))


async def fetch_latest_comments(collection_id: str, limit: int = 50) -> list[str]:
    client = await get_client()
    resp = await (
        client.table("comments")
        .select("comment_text,created_at")
        .eq("collection_id", collection_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    rows = resp.data if isinstance(resp.data, list) else []
    return [r.get("comment_text", "") for r in rows if r.get("comment_text")]


async def update_collection_summary(collection_id: str, summary: str) -> None:
    client = await get_client()
    now = datetime.now(timezone.utc).isoformat()
    try:
        resp = await (
            client.table("collections")
            .update({"ai_summary_text": summary, "last_summary_generated_at": now})
            .eq("id", collection_id)
            .execute()
        )
        # Verify update was successful
        if resp.data is None:
            raise Exception(f"Update returned None for collection {collection_id}")
        if isinstance(resp.data, list) and len(resp.data) == 0:
            raise Exception(f"No rows updated for collection {collection_id}")
        # Log success
        import logging
        logging.info(f"Successfully updated summary for collection {collection_id}")
    except Exception as e:
        import logging
        logging.error(f"Error updating summary for {collection_id}: {str(e)}")
        raise
