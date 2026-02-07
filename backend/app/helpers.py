# ABOUTME: Utility functions shared across Flask route handlers
# ABOUTME: Provides NaN cleaning for JSON and AI-powered conversation titling

import math
import logging
import numpy as np
from google import genai

logger = logging.getLogger(__name__)


def clean_nan_values(obj):
    """Recursively replace NaN values with None and convert numpy types for JSON serialization"""
    if isinstance(obj, dict):
        return {k: clean_nan_values(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_nan_values(item) for item in obj]
    elif isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    elif isinstance(obj, (np.integer, np.floating, np.bool_)):
        return obj.item()
    elif isinstance(obj, np.ndarray):
        return clean_nan_values(obj.tolist())
    return obj


def generate_conversation_title(message: str) -> str:
    """Generate a concise title for a conversation using Gemini Flash."""
    try:
        client = genai.Client()
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=f"""Generate a very concise title (3-4 words) for a conversation that starts with this message.
Return ONLY the title, no quotes, no explanation.

Message: {message[:500]}

Title:"""
        )
        title = response.text.strip()
        # Remove any quotes that might be in the response
        title = title.strip('"\'')
        # Limit to 60 chars max
        if len(title) > 60:
            title = title[:57] + "..."
        return title
    except Exception as e:
        logger.warning(f"Failed to generate title with LLM: {e}")
        # Fallback to truncation
        return message[:50] if len(message) <= 50 else message[:47] + "..."
