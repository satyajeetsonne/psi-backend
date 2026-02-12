import uuid
import sqlite3
import logging
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks

from utils.llm import analyze_outfit_image
from config import DB_FILE, API_BASE_URL, UPLOADS_DIR

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


def save_file_to_disk(file_content: bytes, file_ext: str) -> tuple[str, Path]:
    """Save file to disk and return outfit_id and file path."""
    outfit_id = str(uuid.uuid4())
    filename = f"{outfit_id}{file_ext}"
    file_path = UPLOADS_DIR / filename

    with open(file_path, "wb") as f:
        f.write(file_content)

    return outfit_id, file_path


def save_outfit_to_db(
    outfit_id: str,
    user_id: str,
    file_path: Path,
    name: str,
    tags: str
) -> None:
    """Save outfit metadata to database."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO outfits (
                id,
                user_id,
                image_path,
                name,
                tags,
                created_at,
                analysis_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                outfit_id,
                user_id,
                str(file_path),
                name,
                tags,
                datetime.utcnow(),
                "pending",
            ),
        )
        conn.commit()


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

    file_ext = Path(file.filename).suffix.lower()
    outfit_id, file_path = save_file_to_disk(file_content, file_ext)

    try:
        save_outfit_to_db(
            outfit_id=outfit_id,
            user_id=user_id,
            file_path=file_path,
            name=name or file.filename,
            tags=tags,
        )
    except Exception:
        logger.exception("Failed to save outfit %s to database", outfit_id)
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=500, detail="Failed to save outfit metadata")

    # Run AI analysis in background
    background_tasks.add_task(analyze_outfit_image, str(file_path), outfit_id)

    return {
        "success": True,
        "data": {
            "id": outfit_id,
            "image_url": f"{API_BASE_URL}/uploads/{file_path.name}",
            "name": name or file.filename,
            "tags": [t.strip() for t in tags.split(",") if t.strip()],
        },
    }
