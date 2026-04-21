import hashlib
from backend.app.core.constants import ALLOWED_OPERATORS, SolverMode
from fastapi import HTTPException
def normalize_and_hash(formula_raw: str, notation: str, mode: str) -> tuple[str, str]:
    #notation is not RPN
    validate_formula(formula_raw)
    if notation != "RPN":
        raise ValueError(f"RPN notations has not been used. Notation:{notation}")
    if mode == "RPN":
        normalized_rpn = normalize_rpn(formula_raw)
    elif mode == SolverMode.CNF_SUDOKU:
        normalized_rpn = formula_raw
    #so now we should have normalized rpn and we can hash it
    hash_input = f"{notation}:{normalized_rpn}"
    hashed_value = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
    
    return normalized_rpn, hashed_value
    
def normalize_rpn(formula_raw: str) -> str:
    # Collapse all whitespace to single spaces
    tokens = formula_raw.split()
    normalized_tokens = []
    for token in tokens:
        if token.isalnum() or token in ALLOWED_OPERATORS:
            normalized_tokens.append(token)
        else:
            raise ValueError(f"Unallowed symbols or operators.")
    return " ".join(normalized_tokens)

MAX_FORMULA_LENGTH = 300_000
MAX_TOKENS = 85_000

def validate_formula(v):
        """Validate formula size and content."""
        if not v or not v.strip():
            raise ValueError("Formula cannot be empty")
        
        if len(v) > MAX_FORMULA_LENGTH:
            raise ValueError(f"Formula exceeds {MAX_FORMULA_LENGTH} characters")
        
        if '\x00' in v:
            raise ValueError("Formula contains invalid characters")
        
        tokens = v.split()
        if len(tokens) > MAX_TOKENS:
            raise ValueError(f"Too many tokens (max {MAX_TOKENS})")
        return 