from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field, field_validator

Cell = Annotated[int, Field(ge=0, le=9)]
Mode = Annotated[str, Field(min_length=4, max_length=6)]

class SudokuGrid(BaseModel):
    grid: list[list[Cell]]
    
    @field_validator("grid")
    @classmethod
    def grid_validator(cls, grid: list[list[int]]) -> list[list[int]]:
        if len(grid) != 9:
            raise ValueError("Grid must contain exactly 9 rows.")
        for i, row in enumerate(grid):
            if len(row) != 9:
                raise ValueError(f"Row {i} must contain exactly 9 cells.")
        return grid
    

class NYMode(BaseModel):
    mode: Mode
    
    @field_validator("mode")
    @classmethod
    def mode_validator(cls, mode: str) -> str:
        valid_modes = {"EASY", "MEDIUM", "HARD"}
        if mode.upper() not in valid_modes:
            raise ValueError(f"NY puzzle mode must be one of: {', '.join(sorted(valid_modes))}")
        return mode.lower()
    
class NYDiffEnum(str, Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"