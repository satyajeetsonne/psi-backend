import sqlite3
import logging
from fastapi import APIRouter, HTTPException, Body

from config import DB_FILE
from database.db import get_outfit_tags, save_outfit_tags

router = APIRouter()
logger = logging.getLogger(__name__)

# Constants
MAX_TAG_LENGTH = 30
MAX_TAGS_PER_OUTFIT = 15


def validate_tag(tag: str) -> str:
    """Validate and normalize a tag."""
    if not isinstance(tag, str):
        raise HTTPException(status_code=400, detail="Tag must be a string")
    
    tag = tag.strip().lower()
    
    if not tag:
        raise HTTPException(status_code=400, detail="Tag cannot be empty")
    if len(tag) > MAX_TAG_LENGTH:
        raise HTTPException(status_code=400, detail=f"Tag must be {MAX_TAG_LENGTH} characters or less")
    
    # Only alphanumeric, spaces, and hyphens
    if not all(c.isalnum() or c in ' -' for c in tag):
        raise HTTPException(status_code=400, detail="Tag can only contain letters, numbers, spaces, and hyphens")
    
    return tag


def verify_outfit_ownership(outfit_id: str, user_id: str) -> bool:
    """Verify that a user owns an outfit."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM outfits WHERE id = ?", (outfit_id,))
            result = cursor.fetchone()
            if not result:
                return False
            return result[0] == user_id
    except Exception:
        logger.exception("Error verifying outfit ownership")
        return False


@router.get("/api/outfits/{outfit_id}/tags")
async def get_tags(outfit_id: str, user_id: str):
    """Get all tags for an outfit. Query param: user_id"""
    
    if not outfit_id.strip():
        raise HTTPException(status_code=400, detail="outfit_id is required")
    if not user_id.strip():
        raise HTTPException(status_code=400, detail="user_id is required")
    
    # Verify ownership
    if not verify_outfit_ownership(outfit_id, user_id):
        raise HTTPException(status_code=403, detail="You do not have permission to view this outfit")
    
    tags = get_outfit_tags(outfit_id)
    return {"success": True, "data": sorted(tags)}


@router.post("/api/outfits/{outfit_id}/tags")
async def add_tag(outfit_id: str, user_id: str, payload: dict = Body(...)):
    """Add a tag to an outfit. Query param: user_id. Body: {\"tag\": \"Casual\"}"""
    
    if not outfit_id.strip():
        raise HTTPException(status_code=400, detail="outfit_id is required")
    if not user_id.strip():
        raise HTTPException(status_code=400, detail="user_id is required")
    
    tag = payload.get("tag")
    if not tag:
        raise HTTPException(status_code=400, detail="tag is required")
    
    # Validate and normalize
    tag = validate_tag(tag)
    
    # Verify ownership
    if not verify_outfit_ownership(outfit_id, user_id):
        raise HTTPException(status_code=403, detail="You do not have permission to modify this outfit")
    
    # Get existing tags
    existing = get_outfit_tags(outfit_id)
    
    # Check for duplicate
    if tag in existing:
        raise HTTPException(status_code=409, detail="Tag already exists")
    
    # Check limit
    if len(existing) >= MAX_TAGS_PER_OUTFIT:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_TAGS_PER_OUTFIT} tags allowed per outfit"
        )
    
    # Add and save
    updated = existing + [tag]
    if not save_outfit_tags(outfit_id, updated):
        raise HTTPException(status_code=500, detail="Failed to save tag")
    
    return {"success": True, "data": sorted(updated)}


@router.delete("/api/outfits/{outfit_id}/tags/{tag}")
async def remove_tag(outfit_id: str, user_id: str, tag: str):
    """Remove a tag from an outfit. Query param: user_id. Path param: tag"""
    
    if not outfit_id.strip():
        raise HTTPException(status_code=400, detail="outfit_id is required")
    if not user_id.strip():
        raise HTTPException(status_code=400, detail="user_id is required")
    if not tag.strip():
        raise HTTPException(status_code=400, detail="tag is required")
    
    # Normalize the tag for comparison
    tag_normalized = tag.strip().lower()
    
    # Verify ownership
    if not verify_outfit_ownership(outfit_id, user_id):
        raise HTTPException(status_code=403, detail="You do not have permission to modify this outfit")
    
    # Get existing tags
    existing = get_outfit_tags(outfit_id)
    
    # Remove tag
    updated = [t for t in existing if t != tag_normalized]
    
    if len(updated) == len(existing):
        raise HTTPException(status_code=404, detail="Tag not found on this outfit")
    
    # Save
    if not save_outfit_tags(outfit_id, updated):
        raise HTTPException(status_code=500, detail="Failed to remove tag")
    
    return {"success": True, "data": sorted(updated)}

