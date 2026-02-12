import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query

from config import API_BASE_URL
from database.db import search_outfits

router = APIRouter()
logger = logging.getLogger(__name__)


def format_outfit(outfit_tuple: tuple) -> dict:
    """Format outfit response."""
    filename = Path(outfit_tuple[1]).name
    return {
        "id": outfit_tuple[0],
        "image_url": f"{API_BASE_URL}/uploads/{filename}",
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
    
    outfits = search_outfits(user_id, q)
    
    return {
        "success": True,
        "query": q,
        "count": len(outfits),
        "data": [format_outfit(outfit) for outfit in outfits],
    }
