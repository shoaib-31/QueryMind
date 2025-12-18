"""
Utility functions for data processing and formatting.
"""

import math
import logging

logger = logging.getLogger(__name__)


def sanitize_for_json(obj):
    """
    Recursively sanitize data to be JSON-compliant.
    Replaces NaN, Infinity, and -Infinity with None.
    Converts numpy types to native Python types.
    
    Args:
        obj: Any Python object to sanitize
        
    Returns:
        JSON-serializable version of the object
    """
    # Handle numpy types
    if hasattr(obj, 'item'):  # numpy scalar
        obj = obj.item()
    
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(item) for item in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    elif isinstance(obj, (int, str, bool, type(None))):
        return obj
    else:
        # Try to convert to native Python type
        try:
            # For numpy types
            if hasattr(obj, 'tolist'):
                return obj.tolist()
            # Generic fallback
            return obj
        except:
            return str(obj)

