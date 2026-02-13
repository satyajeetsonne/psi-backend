import logging
from pathlib import Path
from typing import Optional, Tuple
from fastapi import APIRouter, HTTPException, Query

from database.postgres import execute_query_one, get_db_connection
from utils.cloudinary_upload import delete_image_from_cloudinary

router = APIRouter()
logger = logging.getLogger(__name__)


# =========================
# DB helper
# =========================
def delete_outfit_from_db(outfit_id: str, user_id: str) -> Optional[Tuple[str, str]]:
    """
    Delete an outfit after verifying ownership.
    Returns tuple of (image_path, cloudinary_public_id) if deleted.
    """
    try:
        logger.info(f"Attempting to delete outfit {outfit_id} for user {user_id}")
        
        outfit = execute_query_one(
            "SELECT id, user_id, image_path, image_filename FROM outfits WHERE id = %s",
            (outfit_id,),
        )

        if not outfit:
            logger.warning(f"Outfit {outfit_id} not found")
            raise HTTPException(status_code=404, detail="Outfit not found")

        if outfit[1] != user_id:
            logger.warning(f"User {user_id} does not own outfit {outfit_id}")
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to delete this outfit",
            )

        image_path = outfit[2]
        cloudinary_public_id = outfit[3]

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM outfits WHERE id = %s",
                (outfit_id,),
            )
            conn.commit()

        logger.info(f"Successfully deleted outfit {outfit_id} from database")
        return (image_path, cloudinary_public_id)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error deleting outfit {outfit_id}: {str(e)}")
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
    try:
        if not outfit_id or not outfit_id.strip():
            raise HTTPException(status_code=400, detail="outfit_id is required")

        if not user_id or not user_id.strip():
            raise HTTPException(status_code=400, detail="user_id is required")

        logger.info(f"DELETE request for outfit {outfit_id} by user {user_id}")
        result = delete_outfit_from_db(outfit_id, user_id)

        # Delete image from Cloudinary (non-fatal if fails)
        if result and result[1]:
            cloudinary_public_id = result[1]
            try:
                delete_image_from_cloudinary(cloudinary_public_id)
                logger.info("Deleted image from Cloudinary: %s", cloudinary_public_id)
            except Exception as e:
                logger.warning(f"Could not delete image from Cloudinary {cloudinary_public_id}: {str(e)}")

        logger.info(f"Successfully deleted outfit {outfit_id}")
        return {
            "success": True,
            "message": "Outfit deleted successfully",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error in delete_outfit: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Server error deleting outfit",
        )
