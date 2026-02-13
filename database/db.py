import json
import logging
from pathlib import Path

from .postgres import execute_query, execute_query_one, get_db_connection

logger = logging.getLogger(__name__)


def init_db():
    """Initialize the database - handled by postgres.py"""
    # This is now handled in postgres.py
    pass


def update_analysis_status(outfit_id: str, status: str, results: dict | None = None):
    """
    Update the analysis status and results in the database.
    """
    try:
        analysis_json = json.dumps(results) if results else None
        execute_query(
            """
            UPDATE outfits
            SET analysis_status = %s, analysis_results = %s
            WHERE id = %s
            """,
            (status, analysis_json, outfit_id),
        )
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
        result = execute_query(
            """
            SELECT id, name, analysis_results
            FROM outfits
            WHERE user_id = %s AND analysis_status = 'completed'
            ORDER BY created_at DESC
            """,
            (user_id,),
            fetch=True
        )
        return result or []
    except Exception:
        logger.exception(
            "Error fetching completed outfits for user %s", user_id
        )
        return []


def get_outfit_tags(outfit_id: str) -> list[str]:
    """Get tags for an outfit as a list of strings."""
    try:
        result = execute_query_one(
            "SELECT tags FROM outfits WHERE id = %s",
            (outfit_id,)
        )
        if not result or not result[0]:
            return []
        return [tag.strip() for tag in result[0].split(",") if tag.strip()]
    except Exception:
        logger.exception("Error fetching tags for outfit %s", outfit_id)
        return []


def save_outfit_tags(outfit_id: str, tags: list[str]) -> bool:
    """Save tags for an outfit as comma-separated string."""
    try:
        tags_str = ",".join(tags) if tags else ""
        execute_query(
            "UPDATE outfits SET tags = %s WHERE id = %s",
            (tags_str, outfit_id),
        )
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
        outfits_result = execute_query(
            """
            SELECT id, name, tags, analysis_results
            FROM outfits
            WHERE user_id = %s AND analysis_status = 'completed'
            ORDER BY created_at DESC
            """,
            (user_id,),
            fetch=True
        )
        
        if outfits_result:
            for r in outfits_result:
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
        fav_result = execute_query(
            "SELECT outfit_id FROM favorites WHERE user_id = %s",
            (user_id,),
            fetch=True
        )
        favorites = [r[0] for r in fav_result] if fav_result else []

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
        List of matching outfits (id, image_filename, name, tags, created_at, analysis_results)
    """
    try:
        search_pattern = f"%{query}%"
        result = execute_query(
            """
            SELECT id, image_filename, name, tags, created_at, analysis_results
            FROM outfits
            WHERE user_id = %s AND (
                tags ILIKE %s OR 
                name ILIKE %s OR 
                analysis_results ILIKE %s
            )
            ORDER BY created_at DESC
            """,
            (user_id, search_pattern, search_pattern, search_pattern),
            fetch=True
        )
        return result or []
    except Exception:
        logger.exception("Error searching outfits for user %s with query %s", user_id, query)
        return []
