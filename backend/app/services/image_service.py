import logging
import json
from typing import List, Any
from backend.app.core.config import settings
from backend.app.core.constants import GEMINI_EXTRACTION_PROMPT

logger = logging.getLogger(__name__)

class ImageExtractionError(Exception):
    """Custom exception for image extraction errors"""
    pass

try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

def validate_grid(grid: Any) -> List[List[int]]:
    """
    Validate and convert grid structure to proper format.
    
    Args:
        grid: The grid data to validate
        
    Returns:
        Validated 9x9 sudoku grid
        
    Raises:
        ImageExtractionError: If grid is invalid
    """
    if not isinstance(grid, list) or len(grid) != 9:
        raise ImageExtractionError(
            f"Invalid grid structure: expected 9 rows, got {len(grid) if isinstance(grid, list) else 'non-list'}"
        )
    
    for i, row in enumerate(grid):
        if not isinstance(row, list) or len(row) != 9:
            raise ImageExtractionError(f"Row {i} invalid: expected 9 cells, got {len(row) if isinstance(row, list) else 'non-list'}")
        
        for j, cell in enumerate(row):
            if not isinstance(cell, int) or cell < 0 or cell > 9:
                raise ImageExtractionError(f"Cell [{i}][{j}] must be an integer between 0 and 9, got {cell}")
    
    return grid


async def extract_sudoku_from_image(file_bytes: bytes, mime_type: str) -> List[List[int]]:
    """
    Extract sudoku puzzle from image using Gemini API.
    
    Args:
        file_bytes: Image file content as bytes
        mime_type: MIME type of the image (e.g., 'image/png')
        
    Returns:
        9x9 sudoku grid 
        
    Raises:
        ImageExtractionError: If API call fails or grid is invalid
    """
    if not GENAI_AVAILABLE:
        logger.error("Google-genai package not installed")
        raise ImageExtractionError("Google-genai package not installed")
    
    if not settings.GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY not configured")
        raise ImageExtractionError("GEMINI_API_KEY not configured")
    
    try:
        logger.info("Initializing Gemini client")
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        
        logger.info(f"Sending image to Gemini API (MIME: {mime_type}, size: {len(file_bytes)} bytes)")
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=[
                GEMINI_EXTRACTION_PROMPT,
                genai.types.Part.from_bytes(
                    data=file_bytes,
                    mime_type=mime_type,
                ),
            ],
        )
        
        logger.debug(f"Gemini response received: {response.text[:200]}...")
        
        # Parse JSON from response
        response_text = response.text.strip()
        
        # Try to extract JSON if response contains extra text
        if not response_text.startswith("{"):
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            if json_start != -1 and json_end > json_start:
                response_text = response_text[json_start:json_end]
                logger.debug("Extracted JSON from response text")
        
        try:
            response_data = json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini response as JSON: {response_text[:100]}")
            raise ImageExtractionError("Failed to parse puzzle from image - invalid response format")
        
        # Extract and validate grid
        if "grid" not in response_data:
            logger.error("No 'grid' field in Gemini response")
            raise ImageExtractionError("Failed to extract puzzle - no grid found in response")
        
        grid = response_data["grid"]
        validated_grid = validate_grid(grid)
        
        logger.info("Sudoku grid successfully extracted and validated from image")
        return validated_grid
        
    except ImageExtractionError:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error during image extraction: {type(e).__name__}: {str(e)}")
        raise ImageExtractionError(f"Failed to extract puzzle from image: {type(e).__name__}: {str(e)}")