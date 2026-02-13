import sqlite3
import logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException

from config import DB_FILE

router = APIRouter()
logger = logging.getLogger(__name__)


def get_user_outfits(user_id: str) -> Optional[list]:
    """Retrieve all outfits for a user."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, image_path, name, tags, created_at
                FROM outfits
                WHERE user_id = ?
                ORDER BY created_at DESC
                """,
                (user_id,),
            )
            return cursor.fetchall()
    except Exception:
        logger.exception("Database error fetching outfits for user %s", user_id)
        return None


def format_outfit(outfit_tuple: tuple) -> dict:
    """Format outfit response."""
    filename = Path(outfit_tuple[1]).name
    return {
        "id": outfit_tuple[0],
        "image_url": f"/uploads/{filename}",
        "name": outfit_tuple[2],
        "tags": [tag.strip() for tag in outfit_tuple[3].split(",")]
        if outfit_tuple[3]
        else [],
        "date": outfit_tuple[4],
    }


@router.get("/api/outfits")
async def get_all_outfits(user_id: str):
    """Get all outfits for a specific user."""

    if not user_id.strip():
        raise HTTPException(status_code=400, detail="user_id is required")

    outfits = get_user_outfits(user_id)
    if outfits is None:
        raise HTTPException(status_code=500, detail="Failed to fetch outfits")

    return {
        "success": True,
        "data": [format_outfit(outfit) for outfit in outfits],
    }
