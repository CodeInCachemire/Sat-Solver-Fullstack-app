class JobStatus:
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED" 
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    RETRYING = "RETRYING"

class SolverMode:
    CNF_SUDOKU: str = "CNF_SUDOKU"
    
class SolverExitCodes:
    SAT = 10
    UNSAT = 20
    PARSE_ERROR = 30

ALLOWED_OPERATORS = { '&&', "||", "<=>", "=>", "!"}
    
MAX_RETRIES = 3 
TIMEOUT_S_SUDOKU = 250
TIMEOUT_S_SAT = 10
NYT_SUDOKU_URL_BASE = "https://www.nytimes.com/puzzles/sudoku/"

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/jpg"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
GEMINI_EXTRACTION_PROMPT = """
Extract the Sudoku puzzle from this image.

Return ONLY valid JSON in this exact format:
{
  "grid": [
    [0,0,0,0,0,0,0,0,0],
    [0,0,0,0,0,0,0,0,0],
    [0,0,0,0,0,0,0,0,0],
    [0,0,0,0,0,0,0,0,0],
    [0,0,0,0,0,0,0,0,0],
    [0,0,0,0,0,0,0,0,0],
    [0,0,0,0,0,0,0,0,0],
    [0,0,0,0,0,0,0,0,0],
    [0,0,0,0,0,0,0,0,0]
  ]
}

Rules:
- Exactly 9 rows and 9 columns
- Each value must be an integer between 0 and 9
- Use digits 1-9 for filled cells
- Use 0 for empty or unclear cells
""".strip()