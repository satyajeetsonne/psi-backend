import json
import base64
import logging
from pathlib import Path
from typing import List

import google.generativeai as genai

from database.db import update_analysis_status

logger = logging.getLogger(__name__)

# -------------------------------------------------
# Color name → hex mapping
# -------------------------------------------------
COLOR_NAME_MAP = {
    "red": "#EF4444",
    "crimson": "#DC143C",
    "dark red": "#8B0000",
    "pink": "#EC4899",
    "rose": "#F43F5E",
    "orange": "#F97316",
    "amber": "#FBBF24",
    "yellow": "#FBBF24",
    "lime": "#84CC16",
    "green": "#22C55E",
    "emerald": "#10B981",
    "teal": "#14B8A6",
    "cyan": "#06B6D4",
    "blue": "#3B82F6",
    "sky blue": "#0EA5E9",
    "indigo": "#4F46E5",
    "purple": "#A855F7",
    "violet": "#7C3AED",
    "magenta": "#D946EF",
    "white": "#FFFFFF",
    "gray": "#6B7280",
    "grey": "#6B7280",
    "dark gray": "#374151",
    "light gray": "#D1D5DB",
    "black": "#000000",
    "navy": "#000080",
    "brown": "#92400E",
    "gold": "#FFD700",
    "silver": "#C0C0C0",
    "beige": "#F5F5DC",
    "cream": "#FFFDD0",
    "olive": "#808000",
    "maroon": "#800000",
    "peach": "#FFDAB9",
    "lavender": "#E6E6FA",
    "charcoal": "#36454F",
}


def convert_color_names_to_hex(colors: List[str]) -> List[str]:
    """Convert color names from LLM output to hex codes."""
    result = []

    for color in colors or []:
        c = color.strip().lower()

        if c.startswith("#") and len(c) == 7:
            result.append(c)
        elif c in COLOR_NAME_MAP:
            result.append(COLOR_NAME_MAP[c])
        else:
            result.append("#9CA3AF")  # fallback gray

    return result


# -------------------------------------------------
# Main analysis function (background-safe)
# -------------------------------------------------
def analyze_outfit_image(image_path: str, outfit_id: str) -> None:
    """
    Analyze an outfit image using Gemini Vision API.
    This function MUST NEVER crash the app.
    """

    logger.info("Starting analysis for outfit %s", outfit_id)

    try:
        # Read image
        with open(image_path, "rb") as img:
            image_data = base64.b64encode(img.read()).decode("utf-8")

        ext = Path(image_path).suffix.lower()
        mime_type = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }.get(ext, "image/jpeg")

        model = genai.GenerativeModel("gemini-2.5-flash")

        prompt = """Analyze this outfit image and return ONLY a valid JSON object with this exact structure:
{
  "description": "2-3 sentences about the outfit style",
  "clothing_items": ["specific items visible"],
  "colors": ["hex or color names"],
  "patterns": ["solid", "striped"],
  "styles": ["casual", "formal", "streetwear"],
  "occasions": ["weekend", "work", "casual"],
  "fit_analysis": "description of how clothes fit",
  "color_theory": "explanation of color harmony",
  "recommendations": ["styling tip 1", "styling tip 2", "styling tip 3"]
}"""

        response = model.generate_content(
            [
                prompt,
                {"mime_type": mime_type, "data": image_data},
            ],
            generation_config=genai.types.GenerationConfig(
                temperature=0.3,
                max_output_tokens=2000,
            ),
        )

        raw_text = (response.text or "").strip()

        if not raw_text:
            raise ValueError("Empty response from Gemini")

        # Try to extract JSON object safely
        json_start = raw_text.find("{")
        json_end = raw_text.rfind("}")  
        if json_start == -1 or json_end == -1 or json_end <= json_start:
            logger.error(f"No JSON object found in response: {raw_text[:500]}")
            raise ValueError(f"No JSON object found in response: {raw_text[:200]}")
        json_str = raw_text[json_start: json_end + 1]
        analysis = json.loads(json_str)

        # Normalize colors
        if isinstance(analysis.get("colors"), list):
            analysis["colors"] = convert_color_names_to_hex(analysis["colors"])

        update_analysis_status(outfit_id, "completed", analysis)
        logger.info("Analysis completed for outfit %s", outfit_id)

    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing failed for outfit {outfit_id}: {str(e)}")
        logger.error(f"Raw response was: {raw_text[:500] if 'raw_text' in locals() else 'N/A'}")
        update_analysis_status(outfit_id, "failed")

    except ValueError as e:
        logger.error(f"Validation error for outfit {outfit_id}: {str(e)}")
        update_analysis_status(outfit_id, "failed")

    except Exception as e:
        logger.error(f"Unexpected error during analysis for outfit {outfit_id}: {str(e)}", exc_info=True)
        update_analysis_status(outfit_id, "failed")
