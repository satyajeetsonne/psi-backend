import sqlite3
import json
import logging
from pathlib import Path

from config import DB_FILE

logger = logging.getLogger(__name__)


def init_db():
    """Initialize the database with outfits and favorites tables."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()

        # Create outfits table if it doesn't exist
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS outfits (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                image_path TEXT NOT NULL,
                name TEXT,
                tags TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                analysis_status TEXT DEFAULT 'pending',
                analysis_results TEXT
            )
            """
        )

        # Check existing columns in outfits
        cursor.execute("PRAGMA table_info(outfits)")
        columns = {row[1] for row in cursor.fetchall()}

        if "analysis_status" not in columns:
            cursor.execute(
                "ALTER TABLE outfits ADD COLUMN analysis_status TEXT DEFAULT 'pending'"
            )

        if "analysis_results" not in columns:
            cursor.execute(
                "ALTER TABLE outfits ADD COLUMN analysis_results TEXT"
            )

        # Create favorites table if it doesn't exist
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                outfit_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (outfit_id) REFERENCES outfits(id),
                UNIQUE(user_id, outfit_id)
            )
            """
        )

        conn.commit()


def update_analysis_status(outfit_id: str, status: str, results: dict | None = None):
    """
    Update the analysis status and results in the database.
    """
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()

            analysis_json = json.dumps(results) if results else None

            cursor.execute(
                """
                UPDATE outfits
                SET analysis_status = ?, analysis_results = ?
                WHERE id = ?
                """,
                (status, analysis_json, outfit_id),
            )

            conn.commit()
    except Exception:
        logger.exception(
            "Error updating analysis status for outfit %s", outfit_id
        )


def get_user_completed_outfits(user_id: str) -> list:
    """
    Retrieve all completed outfits for a user with their analysis data.
    Used for matching suggestions context.
    """
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, name, analysis_results
                FROM outfits
                WHERE user_id = ? AND analysis_status = 'completed'
                ORDER BY created_at DESC
                """,
                (user_id,),
            )
            return cursor.fetchall() or []
    except Exception:
        logger.exception(
            "Error fetching completed outfits for user %s", user_id
        )
        return []


def get_outfit_tags(outfit_id: str) -> list[str]:
    """Get tags for an outfit as a list of strings."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT tags FROM outfits WHERE id = ?", (outfit_id,))
            result = cursor.fetchone()
            if not result or not result[0]:
                return []
            return [tag.strip() for tag in result[0].split(",") if tag.strip()]
    except Exception:
        logger.exception("Error fetching tags for outfit %s", outfit_id)
        return []


def save_outfit_tags(outfit_id: str, tags: list[str]) -> bool:
    """Save tags for an outfit as comma-separated string."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            tags_str = ",".join(tags) if tags else ""
            cursor.execute(
                "UPDATE outfits SET tags = ? WHERE id = ?",
                (tags_str, outfit_id),
            )
            conn.commit()
            return True
    except Exception:
        logger.exception("Error saving tags for outfit %s", outfit_id)
        return False


def get_user_context(user_id: str) -> dict:
    """
    Retrieve user context for recommendations.

    Returns a dict with:
      - outfits: list of {id, name, tags, analysis}
      - favorites: list of outfit_ids
      - inferred_preferences: dict (counts of styles/colors)
    """
    try:
        outfits = []
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, name, tags, analysis_results
                FROM outfits
                WHERE user_id = ? AND analysis_status = 'completed'
                ORDER BY created_at DESC
                """,
                (user_id,),
            )
            rows = cursor.fetchall() or []

            for r in rows:
                oid, name, tags_str, analysis_json = r
                try:
                    analysis = json.loads(analysis_json) if analysis_json else None
                except Exception:
                    analysis = None

                tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []

                outfits.append({
                    "id": oid,
                    "name": name,
                    "tags": tags,
                    "analysis": analysis,
                })

            # Favorites
            cursor.execute(
                "SELECT outfit_id FROM favorites WHERE user_id = ?",
                (user_id,),
            )
            fav_rows = cursor.fetchall() or []
            favorites = [r[0] for r in fav_rows]

        # Simple inferred preferences: tally styles and colors from analysis
        inferred = {"styles": {}, "colors": {}}
        for o in outfits:
            a = o.get("analysis") or {}
            for s in (a.get("styles") or []):
                inferred["styles"][s] = inferred["styles"].get(s, 0) + 1
            for c in (a.get("colors") or []):
                inferred["colors"][c] = inferred["colors"].get(c, 0) + 1

        return {"outfits": outfits, "favorites": favorites, "inferred_preferences": inferred}

    except Exception:
        logger.exception("Error building user context for %s", user_id)
        return {"outfits": [], "favorites": [], "inferred_preferences": {"styles": {}, "colors": {}}}


def search_outfits(user_id: str, query: str) -> list:
    """
    Search for outfits by query text across tags and analysis results.
    
    Args:
        user_id: The ID of the user
        query: The search query text
    
    Returns:
        List of matching outfits (id, image_path, name, tags, created_at, analysis_results)
    """
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            # Search through tags and analysis_results using LIKE for case-insensitive matching
            search_pattern = f"%{query}%"
            cursor.execute(
                """
                SELECT id, image_path, name, tags, created_at, analysis_results
                FROM outfits
                WHERE user_id = ? AND (
                    tags LIKE ? OR 
                    name LIKE ? OR 
                    analysis_results LIKE ?
                )
                ORDER BY created_at DESC
                """,
                (user_id, search_pattern, search_pattern, search_pattern),
            )
            return cursor.fetchall() or []
    except Exception:
        logger.exception("Error searching outfits for user %s with query %s", user_id, query)
        return []
