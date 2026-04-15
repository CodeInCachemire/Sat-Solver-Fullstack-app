from typing import Annotated

from pydantic import BaseModel, Field, field_validator

Cell = Annotated[int, Field(ge=0, le=9)]

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