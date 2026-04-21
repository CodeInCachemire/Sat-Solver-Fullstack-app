from typing import Optional, Dict, List, Union

from pydantic import BaseModel, Field, field_validator

MAX_FORMULA_LENGTH = 300_000
MAX_TOKENS = 85_000

class SolveRequest(BaseModel):
    mode : str = Field(
        ...,
        description="Operation mode: CNF or RPN",
        json_schema_extra={"example": "SATSOLVER"},
        min_length=3,
        max_length=3,
    )
    notation : str = Field(
        ...,
        description="Notation in RPN(maybe add INFIX LATER)",
        json_schema_extra={"notation": "RPN"},
        min_length=3,
    )
    
    @field_validator('mode')
    @classmethod
    def validate_mode(cls,mode):
        if mode.upper() not in {"CNF","RPN"}:
            raise ValueError('Mode must be CNF or RPN')
        return mode.upper()
    @field_validator('notation')
    @classmethod
    def validate_notation(cls,notation):
        if notation != 'RPN':
            raise ValueError('Notation needs to be in RPN.')
        return notation
    
class SolveResponseCached(BaseModel): #sync
    msg: str
    formula: str
    result: str
    assignment : Optional[Dict[str,bool]]
    return_code: int
    cached: bool
    runtime: float

class SolveResponseFresh(BaseModel): #sync
    msg: str
    formula : str
    result : str
    assignment : Optional[Dict[str,bool]]
    return_code : int 
    runtime : float
    cached : bool

class HistoryEntry(BaseModel): #sync and async
    id: int
    formula: str
    formula_hash: str
    result: str
    return_code: int
    runtime: float

class HistoryResponse(BaseModel): #sync and #async
    entries: list[HistoryEntry]
    
class JobSubmitResponse(BaseModel):
    msg: str
    formula: str
    formula_id: int
    run_id : int
    status: str

class JobSubmitRequest(BaseModel):
    formula: str = Field(..., description="Formula in RPN notation or sudoku grid as JSON string", min_length=1)
    notation: str = Field(default="RPN", description="Notation format (RPN for formulas, ignored for sudoku)")
    mode: str = Field(default="RPN", description="Solver mode (RPN, CNF, or CNF_SUDOKU)")

class StatusSchema(BaseModel):
    msg: str
    run_id: int
    status: str

class SolverResult(BaseModel): 
    msg: str
    status: str
    run_id: int
    formula_id : int 
    formula : str
    result : str
    assignment : Optional[Union[Dict[str, bool], List[List[int]]]]
    runtime : float

    
    