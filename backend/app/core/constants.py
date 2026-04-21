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