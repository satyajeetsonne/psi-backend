import json
import logging
import re
import time
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import google.generativeai as genai

from database.db import get_user_context
from utils.season import current_season

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


# -------------------------
# Request / Response Models
# -------------------------
class WeeklyRequest(BaseModel):
    user_id: str
    season: Optional[str] = None


class SeasonalRequest(BaseModel):
    user_id: Optional[str] = None


class RecommendationResponse(BaseModel):
    season: str
    advice: str
    styling_tips: List[str]
    outfit_suggestions: List[dict]


# -------------------------
# Helpers
# -------------------------
def _clean_response_text(text: str) -> str:
    t = text.strip()
    if t.startswith("```json"):
        t = t[7:]
    if t.startswith("```"):
        t = t[3:]
    if t.endswith("```"):
        t = t[:-3]
    return t.strip()


def sanitize_json(raw: str) -> str:
    """Best-effort cleanup if LLM returns JSON-like text."""
    if not raw:
        return raw

    raw = re.sub(r"```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```", "", raw)

    raw = raw.strip()

    # normalize quotes
    raw = raw.replace('"', '"').replace('"', '"')

    # remove trailing commas
    raw = re.sub(r",\s*(?=[}\]])", "", raw)

    return raw

def _extract_json_from_text(text: str):
    """Extract and parse JSON from text, with fallback strategies."""
    start = text.find("[")
    end = text.rfind("]")
    
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON array found in response")
    
    json_str = text[start : end + 1]
    
    # Try to parse directly
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.warning(f"Direct JSON parse failed: {e}, trying cleanup...")
    
    # Fallback: try removing problematic characters
    try:
        # Remove trailing commas before ] or }
        json_str = re.sub(r",(\s*[}\]])", r"\1", json_str)
        # Remove single quotes and replace with double quotes in specific contexts
        # Try parsing again
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Unable to parse JSON after cleanup: {e}\nJSON text: {json_str[:200]}")

def build_weekly_prompt(user_context: dict, season: Optional[str] = None) -> str:
    outfits = user_context.get("outfits", [])
    favorites = user_context.get("favorites", [])
    inferred = user_context.get("inferred_preferences", {})

    brief_outfits = ""
    if outfits:
        brief_outfits = "\nUser outfits (most recent up to 8):\n"
        for o in outfits[:8]:
            name = o.get("name") or "Unnamed"
            tags = ", ".join(o.get("tags") or [])
            styles = ", ".join((o.get("analysis") or {}).get("styles") or [])
            brief_outfits += f"- {name}: tags({tags}) styles({styles})\n"

    season_str = f"Season: {season}." if season else ""

    prompt = f"""
You are an expert fashion stylist creating a personalized 7-day outfit plan for a user.

CURRENT CONTEXT
{season_str}
Generate recommendations for the upcoming week (Monday to Sunday), starting from the current date.

USER PROFILE
Favorite items: {', '.join(favorites) if favorites else 'No favorites yet'}
Style preferences: {', '.join(inferred.get('styles', [])) if inferred.get('styles') else 'Not specified'}
Color palette: {', '.join(inferred.get('colors', [])) if inferred.get('colors') else 'Not specified'}

AVAILABLE WARDROBE
{brief_outfits if brief_outfits else 'User has no items uploaded yet. Suggest common, everyday clothing pieces.'}

OBJECTIVE
Create a complete 7-day outfit plan that:
1. Uses items from the user's existing wardrobe whenever possible
2. Feels cohesive across the week while still offering variety
3. Gradually shifts from structured weekday looks to more relaxed weekend styling
4. Is optimized for calendar and card-based UI display (clear, concise, scannable)

IMPORTANT GUIDANCE
- If lifestyle, work, or event context is not explicitly provided, keep recommendations flexible and broadly applicable to everyday routines.
- Avoid strong assumptions about office environments or specific events unless implied by the wardrobe.

OUTPUT FORMAT
Return a JSON array containing EXACTLY 7 objects (one per day).

Each object must follow this structure:

{{
  "day_name": "Monday",
  "date": "2024-02-12",
  "occasion": "Work/Casual",
  "recommendation": "A clean, balanced look built around tailored pieces and neutral tones, offering structure while remaining comfortable for everyday wear.",
  "suggested_items": [
    "Black tailored trousers",
    "White cotton shirt",
    "Neutral lightweight jacket",
    "Leather loafers"
  ],
  "tags": ["minimal", "everyday", "structured"]
}}

CRITICAL CONSTRAINTS
- ALWAYS return exactly 7 days (Monday to Sunday)
- ALWAYS return valid JSON (no markdown, no comments, no extra text)
- Recommendation length: 18-30 words
- Use specific, realistic item names
- Prioritize wardrobe items
- Ensure variety across days
- Weekend outfits should feel more relaxed than weekdays

STYLE GUIDELINES
- Professional, editorial tone
- No emojis, no exclamation marks
- Neutral, adaptable language
- Avoid repetitive phrasing

NOW GENERATE THE COMPLETE 7-DAY PLAN.
Return ONLY the JSON array.
"""

    return prompt


def fallback_response(season: str) -> dict:
    return {
        "season": season,
        "advice": f"Here's some {season.lower()} style inspiration for you.",
        "styling_tips": [
            "Layer outfits to adapt to changing temperatures.",
            "Stick to neutral tones with one seasonal accent color.",
            "Choose comfortable and breathable fabrics.",
        ],
        "outfit_suggestions": [
            {
                "title": f"Everyday {season} Look",
                "items": ["Light jacket", "T-shirt", "Jeans"],
                "explanation": "Simple and versatile for daily wear.",
            },
            {
                "title": f"Smart Casual {season}",
                "items": ["Blazer", "Chinos", "Loafers"],
                "explanation": "Works well for work and casual outings.",
            },
        ],
    }


# -------------------------
# Endpoints
# -------------------------
@router.post("/weekly")
async def weekly_recommendations(body: WeeklyRequest):
    if not body.user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    try:
        context = get_user_context(body.user_id)
        prompt = build_weekly_prompt(context, season=body.season)

        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)

        if not response or not getattr(response, "text", None):
            raise HTTPException(status_code=500, detail="LLM returned empty response")

        text = _clean_response_text(response.text)
        
        try:
            suggestions = _extract_json_from_text(text)
        except ValueError as ve:
            logger.error(f"JSON extraction failed: {ve}")
            raise HTTPException(status_code=500, detail=f"Failed to parse LLM response: {str(ve)}")

        today = datetime.utcnow().date()
        for i, item in enumerate(suggestions):
            if not item.get("date"):
                item["date"] = (today + timedelta(days=i)).isoformat()
            if not item.get("day_name"):
                item["day_name"] = datetime.fromisoformat(item["date"]).strftime("%A")

        return {"success": True, "data": suggestions}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to generate weekly recommendations: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/seasonal", response_model=RecommendationResponse)
async def seasonal_recommendations(req: SeasonalRequest):
    try:
        season = current_season()

        # Optional user context
        user_ctx = {}
        if req.user_id:
            user_ctx = get_user_context(req.user_id)

        # -------------------------
        # Prompt
        # -------------------------
        prompt = (
            f"You are a fashion stylist.\n"
            f"Current season: {season}\n\n"
            "Give seasonal fashion advice, styling tips, and outfit ideas.\n"
            "You may return plain text OR JSON.\n\n"
        )

        if user_ctx:
            prompt += "User wardrobe summary:\n"
            for outfit in user_ctx.get("outfits", [])[:5]:
                name = outfit.get("name", "Untitled")
                tags = ", ".join(outfit.get("tags", []))
                prompt += f"- {name}: {tags}\n"
            prompt += "\n"

        prompt += (
            "If you return JSON, use this format:\n"
            "{\n"
            '  "advice": "...",\n'
            '  "styling_tips": ["...", "..."],\n'
            '  "outfit_suggestions": [{"title": "...", "items": [], "explanation": "..."}]\n'
            "}\n"
        )

        # Try models with retries
        raw_text = None
        for model_name in ["gemini-2.5-flash"]:
            for attempt in range(1, 3):
                try:
                    logger.info("LLM model=%s attempt=%d", model_name, attempt)
                    model = genai.GenerativeModel(model_name)
                    response = model.generate_content(
                        [prompt],
                        generation_config=genai.types.GenerationConfig(
                            temperature=0.3,
                            max_output_tokens=1200,
                        ),
                    )
                    raw_text = (response.text or "").strip()
                    if raw_text:
                        logger.info("LLM success: %s", model_name)
                        break
                except Exception as e:
                    logger.warning("LLM failed model=%s attempt=%d: %s", model_name, attempt, str(e))
                    if attempt < 2:
                        time.sleep(2 ** (attempt - 1))
            if raw_text:
                break

        if not raw_text:
            logger.warning("All LLM attempts exhausted, returning fallback")
            return fallback_response(season)

        # Try JSON parsing
        try:
            # Remove code fences
            cleaned = raw_text.strip()
            if cleaned.startswith("`"):
                nl_pos = cleaned.find("\n")
                if nl_pos >= 0:
                    cleaned = cleaned[nl_pos + 1 :]
            if cleaned.endswith("`"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            # Find JSON object
            start_idx = cleaned.find("{")
            end_idx = cleaned.rfind("}")

            if start_idx < 0 or end_idx <= start_idx:
                logger.warning("No JSON object found in response")
                return fallback_response(season)

            json_str = cleaned[start_idx : end_idx + 1]
            json_str = sanitize_json(json_str)
            data = json.loads(json_str)

            return {
                "season": season,
                "advice": data.get("advice", ""),
                "styling_tips": data.get("styling_tips", []),
                "outfit_suggestions": data.get("outfit_suggestions", []),
            }

        except json.JSONDecodeError as e:
            logger.warning("JSON decode error: %s", str(e))
            return fallback_response(season)
        except Exception as e:
            logger.warning("JSON parsing error: %s", str(e))
            return fallback_response(season)

    except Exception as e:
        logger.exception("Seasonal recommendation failed: %s", str(e))
        raise HTTPException(
            status_code=500,
            detail="Failed to generate seasonal recommendations",
        )
