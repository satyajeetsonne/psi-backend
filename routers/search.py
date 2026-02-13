import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query

from database.postgres import execute_query

router = APIRouter()
logger = logging.getLogger(__name__)


def format_outfit(outfit_tuple: tuple) -> dict:
    """Format outfit response."""
    image_url = outfit_tuple[1]  # image_path from DB (Cloudinary URL)
    return {
        "id": outfit_tuple[0],
        "image_url": image_url,
        "name": outfit_tuple[2],
        "tags": [tag.strip() for tag in outfit_tuple[3].split(",")]
        if outfit_tuple[3]
        else [],
        "date": outfit_tuple[4],
        "analysis_results": outfit_tuple[5],
    }


@router.get("/api/search")
async def search_outfits_endpoint(user_id: str = Query(...), q: str = Query(...)):
    """
    Search for outfits by query text.
    
    Query Parameters:
    - user_id: The ID of the user (required)
    - q: The search query text (required)
    
    Returns:
    - Matching outfits with metadata
    """
    if not user_id.strip():
        raise HTTPException(status_code=400, detail="user_id is required")
    
    if not q.strip():
        raise HTTPException(status_code=400, detail="q (search query) is required")
    
    # Search in name and tags
    search_pattern = f"%{q}%"
    outfits = execute_query(
        """
        SELECT id, image_path, name, tags, created_at, analysis_results
        FROM outfits
        WHERE user_id = %s AND (name ILIKE %s OR tags ILIKE %s)
        ORDER BY created_at DESC
        """,
        (user_id, search_pattern, search_pattern),
        fetch=True
    )
    
    return {
        "success": True,
        "query": q,
        "count": len(outfits) if outfits else 0,
        "data": [format_outfit(outfit) for outfit in outfits] if outfits else [],
    }
