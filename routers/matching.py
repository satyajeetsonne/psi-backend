import json
import sqlite3
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
import google.generativeai as genai

from config import DB_FILE
from database.db import get_user_completed_outfits

router = APIRouter()
logger = logging.getLogger(__name__)


def get_outfit_from_db(outfit_id: str) -> Optional[tuple]:
    """Retrieve outfit from database."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, name, analysis_results, user_id
                FROM outfits
                WHERE id = ?
                """,
                (outfit_id,),
            )
            return cursor.fetchone()
    except Exception:
        logger.exception("Database error fetching outfit %s", outfit_id)
        return None


def generate_matching_suggestions(outfit_id: str, outfit_data: dict, user_id: str) -> Optional[dict]:
    """
    Generate matching suggestions for an outfit using Gemini Vision API.
    """
    try:
        # Get user's other completed outfits for context
        completed_outfits = get_user_completed_outfits(user_id)
        
        # Build context from user's outfits
        outfit_context = ""
        if completed_outfits:
            outfit_context = "\n\nUser's other outfits for reference:\n"
            for outfit in completed_outfits[:5]:  # Limit to 5 for token efficiency
                outfit_id_db, outfit_name, analysis_results = outfit
                if analysis_results:
                    try:
                        analysis = json.loads(analysis_results)
                        items = analysis.get("detected_items", [])
                        colors = analysis.get("colors", [])
                        outfit_context += f"- {outfit_name}: {', '.join(items[:3])} | Colors: {', '.join(colors[:2])}\n"
                    except (json.JSONDecodeError, TypeError):
                        pass

        # Prepare the prompt
        prompt = f"""
You are a professional fashion stylist and color theory expert. Analyze the following outfit and provide matching suggestions.

CURRENT OUTFIT:
Name: {outfit_data.get('name', 'Unnamed Outfit')}
Detected Items: {', '.join(outfit_data.get('detected_items', []))}
Colors: {', '.join(outfit_data.get('colors', []))}
Style Tags: {', '.join(outfit_data.get('style', []))}
Styling Tips: {outfit_data.get('styling_tips', '')}

{outfit_context}

Based on color theory, style compatibility, and fashion best practices, provide 3-4 matching suggestions.

For each suggestion, provide:
1. Item Category (e.g., "Footwear", "Outerwear", "Accessory", "Bottom", "Top")
2. Recommendation Title (e.g., "White Minimalist Sneakers")
3. Why it works (one concise sentence explaining color/style compatibility)
4. Styling tip (optional, one brief tip)

Format your response as a JSON array with this structure:
[
  {{
    "category": "Footwear",
    "title": "White Minimalist Sneakers",
    "why": "Complements the casual vibe and provides contrast with neutral tones",
    "tip": "Keep the style clean and understated"
  }}
]

Return ONLY the JSON array, no additional text.
"""

        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        
        if not response.text:
            logger.error("Empty response from Gemini API")
            return None

        # Parse the response
        suggestions_text = response.text.strip()
        
        # Remove markdown code blocks if present
        if suggestions_text.startswith("```json"):
            suggestions_text = suggestions_text[7:]
        if suggestions_text.startswith("```"):
            suggestions_text = suggestions_text[3:]
        if suggestions_text.endswith("```"):
            suggestions_text = suggestions_text[:-3]
        
        suggestions = json.loads(suggestions_text.strip())
        
        if not isinstance(suggestions, list):
            logger.error("Suggestions response is not a list")
            return None

        return {
            "suggestions": suggestions,
            "status": "completed"
        }

    except json.JSONDecodeError as e:
        logger.error("Failed to parse LLM response as JSON: %s", e)
        return None
    except Exception as e:
        logger.error("Error generating matching suggestions: %s", e)
        return None


@router.post("/api/outfits/{outfit_id}/matching")
async def get_matching_suggestions(outfit_id: str, user_id: str):
    """
    Generate and return matching suggestions for a specific outfit.
    
    Considers:
    - The outfit's detected items and colors
    - Color theory and complementary combinations
    - User's existing outfits for style consistency
    - Fashion best practices
    """
    
    if not outfit_id.strip():
        raise HTTPException(status_code=400, detail="outfit_id is required")

    if not user_id.strip():
        raise HTTPException(status_code=400, detail="user_id is required")

    # Get outfit from database
    outfit = get_outfit_from_db(outfit_id)
    if not outfit:
        raise HTTPException(status_code=404, detail="Outfit not found")

    outfit_id_db, outfit_name, analysis_results, outfit_user_id = outfit

    # Verify ownership
    if outfit_user_id != user_id:
        raise HTTPException(status_code=403, detail="You do not have permission to access this outfit")

    # Check if outfit analysis is completed
    if not analysis_results:
        raise HTTPException(status_code=400, detail="Outfit analysis must be completed before generating matching suggestions")

    try:
        outfit_data = json.loads(analysis_results)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=500, detail="Failed to parse outfit analysis data")

    # Generate suggestions
    result = generate_matching_suggestions(outfit_id_db, outfit_data, user_id)
    
    if not result:
        raise HTTPException(status_code=500, detail="Failed to generate matching suggestions")

    return {
        "success": True,
        "data": result
    }
