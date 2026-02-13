import logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from database.postgres import execute_query_one, get_db_connection

router = APIRouter()
logger = logging.getLogger(__name__)


# =========================
# DB helper
# =========================
def delete_outfit_from_db(outfit_id: str, user_id: str) -> Optional[str]:
    """
    Delete an outfit after verifying ownership.
    Returns image_path if deleted.
    """
    try:
        outfit = execute_query_one(
            "SELECT id, user_id, image_path FROM outfits WHERE id = %s",
            (outfit_id,),
        )

        if not outfit:
            raise HTTPException(status_code=404, detail="Outfit not found")

        if outfit[1] != user_id:
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to delete this outfit",
            )

        image_path = outfit[2]

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM outfits WHERE id = %s",
                (outfit_id,),
            )
            conn.commit()

        return image_path

    except HTTPException:
        raise
    except Exception:
        logger.exception("Database error while deleting outfit")
        raise HTTPException(
            status_code=500,
            detail="Database error while deleting outfit",
        )


# =========================
# API endpoint
# =========================
@router.delete("/api/outfits/{outfit_id}")
async def delete_outfit(
    outfit_id: str,
    user_id: str = Query(..., description="User ID of the outfit owner"),
):
    if not outfit_id.strip():
        raise HTTPException(status_code=400, detail="outfit_id is required")

    if not user_id.strip():
        raise HTTPException(status_code=400, detail="user_id is required")

    image_path = delete_outfit_from_db(outfit_id, user_id)

    # Delete image file (non-fatal if fails)
    if image_path:
        try:
            image_file = Path(image_path)
            if image_file.exists():
                image_file.unlink()
                logger.info("Deleted image file: %s", image_path)
        except Exception:
            logger.warning("Could not delete image file: %s", image_path)

    return {
        "success": True,
        "message": "Outfit deleted successfully",
    }
