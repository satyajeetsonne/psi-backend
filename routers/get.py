import json
import logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException

from database.postgres import execute_query, execute_query_one

router = APIRouter()
logger = logging.getLogger(__name__)


def is_outfit_favorited(outfit_id: str, user_id: str) -> bool:
    """Check if outfit is favorited by user."""
    try:
        result = execute_query_one(
            """
            SELECT 1 FROM favorites
            WHERE user_id = %s AND outfit_id = %s
            """,
            (user_id, outfit_id),
        )
        return result is not None
    except Exception:
        logger.exception("Database error checking favorite status")
        return False


def get_outfit_from_db(outfit_id: str) -> Optional[tuple]:
    """Retrieve outfit from database."""
    try:
        result = execute_query_one(
            """
            SELECT id, image_path, name, tags, created_at, user_id,
                   COALESCE(analysis_status, 'pending') AS analysis_status,
                   analysis_results
            FROM outfits
            WHERE id = %s
            """,
            (outfit_id,),
        )
        return result
    except Exception:
        logger.exception("Database error fetching outfit %s", outfit_id)
        return None


def format_outfit_detail(outfit_tuple: tuple, user_id: str) -> Optional[dict]:
    """Format detailed outfit response."""
    if not outfit_tuple:
        return None

    image_url = outfit_tuple[1]  # image_path from DB (Cloudinary URL)
    analysis_status = outfit_tuple[6] or "pending"
    analysis = None

    if outfit_tuple[7] and analysis_status == "completed":
        try:
            analysis = json.loads(outfit_tuple[7])
        except (json.JSONDecodeError, TypeError):
            analysis = None

    return {
        "id": outfit_tuple[0],
        "image_url": image_url,
        "name": outfit_tuple[2],
        "tags": [tag.strip() for tag in outfit_tuple[3].split(",")]
        if outfit_tuple[3]
        else [],
        "date": outfit_tuple[4],
        "analysis_status": analysis_status,
        "analysis": analysis,
        "is_favorite": is_outfit_favorited(outfit_tuple[0], user_id),
    }


@router.get("/api/outfits/{outfit_id}")
async def get_outfit_detail(outfit_id: str, user_id: str):
    """Get detailed information for a specific outfit with analysis."""

    if not outfit_id.strip():
        raise HTTPException(status_code=400, detail="outfit_id is required")

    if not user_id.strip():
        raise HTTPException(status_code=400, detail="user_id is required")

    outfit = get_outfit_from_db(outfit_id)
    if not outfit:
        raise HTTPException(status_code=404, detail="Outfit not found")

    if outfit[5] != user_id:
        raise HTTPException(status_code=403, detail="You do not have permission to view this outfit")

    return {
        "success": True,
        "data": format_outfit_detail(outfit, user_id),
    }
