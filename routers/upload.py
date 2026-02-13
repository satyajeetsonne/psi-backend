import uuid
import logging
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks

from utils.llm import analyze_outfit_image
from utils.cloudinary_upload import upload_image_to_cloudinary
from database.postgres import execute_query

router = APIRouter()
logger = logging.getLogger(__name__)

# Constants
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


# =========================
# Helpers
# =========================
def validate_file(file: UploadFile, file_content: bytes) -> tuple[bool, str]:
    """Validate uploaded file type and size."""
    file_ext = Path(file.filename).suffix.lower()

    if file_ext not in ALLOWED_EXTENSIONS:
        return False, f"Invalid file type. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"

    file_size = len(file_content)

    if file_size > MAX_FILE_SIZE:
        return False, "File size exceeds 10MB limit"

    if file_size < 1024:
        return False, "File size too small. Minimum size: 1KB"

    return True, ""


def save_outfit_to_db(
    outfit_id: str,
    user_id: str,
    image_url: str,
    image_filename: str,
    name: str,
    tags: str,
    cloudinary_public_id: str
) -> None:
    """Save outfit metadata to database."""
    execute_query(
        """
        INSERT INTO outfits (
            id,
            user_id,
            image_path,
            image_filename,
            name,
            tags,
            created_at,
            analysis_status
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            outfit_id,
            user_id,
            image_url,  # Store Cloudinary URL instead of file path
            cloudinary_public_id,  # Store public_id for deletion
            name,
            tags,
            datetime.utcnow(),
            "pending",
        ),
    )


# =========================
# API Endpoint
# =========================
@router.post("/api/outfits")
async def upload_outfit(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user_id: str = Form(...),
    name: str = Form(""),
    tags: str = Form(""),
):
    """Upload an outfit image and save metadata to database."""

    if not user_id.strip():
        raise HTTPException(status_code=400, detail="user_id is required")

    if not file.filename:
        raise HTTPException(status_code=400, detail="File is required")

    file_content = await file.read()
    is_valid, error_msg = validate_file(file, file_content)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)
    # Upload to Cloudinary
    result = upload_image_to_cloudinary(file_content, file.filename)
    if not result:
        raise HTTPException(status_code=500, detail="Failed to upload image to cloud storage")

    image_url = result.get("url")
    cloudinary_public_id = result.get("public_id")
    
    if not image_url or not cloudinary_public_id:
        raise HTTPException(status_code=500, detail="Invalid response from cloud storage")

    # Generate outfit ID
    outfit_id = str(uuid.uuid4())

    try:
        # Save to database (Cloudinary URL stored as image_path)
        save_outfit_to_db(
            outfit_id=outfit_id,
            user_id=user_id,
            image_url=image_url,
            image_filename=cloudinary_public_id,
            name=name or file.filename,
            tags=tags,
            cloudinary_public_id=cloudinary_public_id,
        )
    except Exception:
        logger.exception("Failed to save outfit %s to database", outfit_id)
        raise HTTPException(status_code=500, detail="Failed to save outfit metadata")

    # Run AI analysis in background
    background_tasks.add_task(analyze_outfit_image, image_url, outfit_id)

    return {
        "success": True,
        "data": {
            "id": outfit_id,
            "image_url": image_url,
            "name": name or file.filename,
            "tags": [t.strip() for t in tags.split(",") if t.strip()],
        },
    }
