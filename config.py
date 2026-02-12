from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent


IS_VERCEL = os.environ.get("VERCEL") == "1"

# Use /tmp for writeable storage on Vercel
if IS_VERCEL:
    DB_FILE = Path("/tmp/outfits.db")
    UPLOADS_DIR = Path("/tmp/uploads")
else:
    DB_FILE = BASE_DIR / "outfits.db"
    UPLOADS_DIR = BASE_DIR / "uploads"

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

# Create uploads directory if it doesn't exist (safe in /tmp or local)
UPLOADS_DIR.mkdir(exist_ok=True, parents=True)
