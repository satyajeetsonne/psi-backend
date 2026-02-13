import uuid
import logging
import io
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks

from utils.llm import analyze_outfit_image
from utils.cloudinary_upload import upload_image_to_cloudinary
from database.postgres import execute_query

router = APIRouter()
logger = logging.getLogger(__name__)

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logger.warning("Pillow not installed - image compression disabled")

# Constants
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_IMAGE_DIMENSION = 2048  # Resize if larger


# =========================
# Helpers
# =========================
def compress_image(file_content: bytes, filename: str, max_size_kb: int = 500) -> bytes:
    """
    Compress image to optimize upload speed.
    Reduces file size while maintaining quality.
    """
    if not PIL_AVAILABLE:
        logger.warning("Pillow not available - skipping compression")
        return file_content
    
    try:
        # Check current size
        current_size_kb = len(file_content) / 1024
        if current_size_kb <= max_size_kb:
            logger.debug(f"Image already optimized: {current_size_kb:.1f}KB")
            return file_content
        
        logger.info(f"Compressing image from {current_size_kb:.1f}KB...")
        
        # Load image
        img = Image.open(io.BytesIO(file_content))
        
        # Convert RGBA to RGB if necessary (for JPEG compatibility)
        if img.mode in ("RGBA", "LA", "P"):
            rgb_img = Image.new("RGB", img.size, (255, 255, 255))
            rgb_img.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
            img = rgb_img
        
        # Resize if too large
        img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.Resampling.LANCZOS)
        
        # Compress and save to bytes
        output = io.BytesIO()
        quality = 85
        while quality > 40:
            output.seek(0)
            output.truncate(0)
            img.save(output, format="JPEG", quality=quality, optimize=True)
            if len(output.getvalue()) / 1024 <= max_size_kb:
                break
            quality -= 5
        
        compressed = output.getvalue()
        new_size_kb = len(compressed) / 1024
        logger.info(f"Image compressed: {current_size_kb:.1f}KB → {new_size_kb:.1f}KB ({(100 * (current_size_kb - new_size_kb) / current_size_kb):.0f}% reduction)")
        return compressed
        
    except Exception as e:
        logger.warning(f"Image compression failed: {e} - using original")
        return file_content


def validate_file(file, file_content):
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

    try:
        if not user_id.strip():
            raise HTTPException(status_code=400, detail="user_id is required")

        if not file.filename:
            raise HTTPException(status_code=400, detail="File is required")

        logger.info(f"Starting upload for user {user_id}, file: {file.filename}")

        file_content = await file.read()
        is_valid, error_msg = validate_file(file, file_content)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)
        
        # Compress image to optimize upload speed
        logger.info("Compressing image...")
        compressed_content = compress_image(file_content, file.filename)
        
        # Upload to Cloudinary with optimizations
        logger.info("Uploading to Cloudinary...")
        result = upload_image_to_cloudinary(compressed_content, file.filename)
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
            logger.info(f"Saving outfit {outfit_id} to database...")
            save_outfit_to_db(
                outfit_id=outfit_id,
                user_id=user_id,
                image_url=image_url,
                image_filename=cloudinary_public_id,
                name=name or file.filename,
                tags=tags,
                cloudinary_public_id=cloudinary_public_id,
            )
            logger.info(f"Outfit {outfit_id} saved to database")
        except Exception:
            logger.exception("Failed to save outfit %s to database", outfit_id)
            raise HTTPException(status_code=500, detail="Failed to save outfit metadata")

        # Run AI analysis in background (non-blocking)
        background_tasks.add_task(analyze_outfit_image, image_url, outfit_id)

        logger.info(f"Upload completed for outfit {outfit_id}")
        return {
            "success": True,
            "data": {
                "id": outfit_id,
                "image_url": image_url,
                "name": name or file.filename,
                "tags": [t.strip() for t in tags.split(",") if t.strip()],
                "analysis_status": "pending",
            },
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error in upload_outfit: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Server error uploading outfit: {str(e)}",
        )
