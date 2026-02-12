from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent

DB_FILE = BASE_DIR / "outfits.db"
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

UPLOADS_DIR = BASE_DIR / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)
