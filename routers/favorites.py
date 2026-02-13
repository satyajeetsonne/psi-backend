import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException

from database.postgres import execute_query, execute_query_one, get_db_connection

router = APIRouter()
logger = logging.getLogger(__name__)


# =========================
# DB helpers
# =========================
def verify_outfit_ownership(outfit_id: str, user_id: str) -> bool:
    """Check if user owns the outfit."""
    try:
        result = execute_query_one(
            "SELECT user_id FROM outfits WHERE id = %s",
            (outfit_id,),
        )
        if not result:
            return False
        return result[0] == user_id
    except Exception:
        logger.exception("Database error verifying outfit ownership")
        return False


def add_favorite(outfit_id: str, user_id: str) -> bool:
    """Add outfit to user's favorites. Returns True if added, False if already favorited."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    INSERT INTO favorites (user_id, outfit_id)
                    VALUES (%s, %s)
                    """,
                    (user_id, outfit_id),
                )
                conn.commit()
                return True
            except Exception as e:
                # Check if it's a unique constraint violation
                if "unique" in str(e).lower():
                    return False
                raise
    except Exception:
        logger.exception("Database error adding favorite")
        raise HTTPException(
            status_code=500,
            detail="Database error while adding favorite",
        )


def remove_favorite(outfit_id: str, user_id: str) -> bool:
    """Remove outfit from user's favorites. Returns True if removed, False if not found."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM favorites
                WHERE user_id = %s AND outfit_id = %s
                """,
                (user_id, outfit_id),
            )
            conn.commit()
            return cursor.rowcount > 0
    except Exception:
        logger.exception("Database error removing favorite")
        raise HTTPException(
            status_code=500,
            detail="Database error while removing favorite",
        )
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


def get_user_favorites(user_id: str) -> list:
    """Retrieve all favorited outfits for a user with user's own outfits only."""
    try:
        result = execute_query(
            """
            SELECT o.id, o.image_path, o.name, o.tags, o.created_at
            FROM outfits o
            INNER JOIN favorites f ON o.id = f.outfit_id
            WHERE f.user_id = %s AND o.user_id = %s
            ORDER BY f.created_at DESC
            """,
            (user_id, user_id),
            fetch=True
        )
        return result or []
    except Exception:
        logger.exception("Database error fetching favorites for user %s", user_id)
        return []


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
    }


# =========================
# API endpoints
# =========================
@router.post("/api/outfits/{outfit_id}/favorite")
async def add_outfit_to_favorites(outfit_id: str, user_id: str):
    """Add outfit to user's favorites."""
    if not outfit_id.strip():
        raise HTTPException(status_code=400, detail="outfit_id is required")

    if not user_id.strip():
        raise HTTPException(status_code=400, detail="user_id is required")

    if not verify_outfit_ownership(outfit_id, user_id):
        raise HTTPException(
            status_code=403,
            detail="You can only favorite your own outfits",
        )

    result = add_favorite(outfit_id, user_id)

    return {
        "success": True,
        "message": "Outfit added to favorites" if result else "Outfit is already favorited",
        "is_favorite": True,
    }


@router.delete("/api/outfits/{outfit_id}/favorite")
async def remove_outfit_from_favorites(outfit_id: str, user_id: str):
    """Remove outfit from user's favorites."""
    if not outfit_id.strip():
        raise HTTPException(status_code=400, detail="outfit_id is required")

    if not user_id.strip():
        raise HTTPException(status_code=400, detail="user_id is required")

    result = remove_favorite(outfit_id, user_id)

    return {
        "success": True,
        "message": "Outfit removed from favorites" if result else "Outfit was not in favorites",
        "is_favorite": False,
    }


@router.get("/api/outfits/favorites")
async def get_favorites(user_id: str):
    """Get all outfits favorited by the authenticated user."""
    if not user_id.strip():
        raise HTTPException(status_code=400, detail="user_id is required")

    outfits = get_user_favorites(user_id)

    return {
        "success": True,
        "data": [format_outfit(outfit) for outfit in outfits],
    }
