import subprocess
import sys
import time
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

SIZE = 9
BLOCK = 3
DIGITS = list(range(1, 10))

def xvar(r: int, c: int, d: int) -> str:
    return f"x{r}{c}{d}"

class AuxGen:
    def __init__(self):
        self.k = 0

    def fresh(self) -> str:
        # name without '-' (negation handled by prefix)
        self.k += 1
        return f"t{self.k}"

# CNF helpers (<= 3 literals per clause line)

def neg(v: str) -> str:
    return v if v.startswith("-") else "-" + v

def strip_neg(v: str) -> str:
    return v[1:] if v.startswith("-") else v

def at_most_one_cnf(vars: List[str]) -> List[List[str]]:
    # pairwise: (¬a ∨ ¬b)
    clauses: List[List[str]] = []
    for i in range(len(vars)):
        for j in range(i + 1, len(vars)):
            clauses.append([neg(vars[i]), neg(vars[j])])
    return clauses

def at_least_one_to_3cnf(vars: List[str], gen: AuxGen) -> List[List[str]]:
    """
    Convert (v1 ∨ v2 ∨ ... ∨ vn) into CNF with clauses of size <= 3
    using auxiliary vars t1, t2, ...
    Works for n >= 1.

    If n <= 3: just one clause
    If n > 3: chain:
      (v1 ∨ v2 ∨ t1)
      (¬t1 ∨ v3 ∨ t2)
      ...
      (¬t{k} ∨ v{n-1} ∨ v{n})
    """
    n = len(vars)
    if n == 0:
        raise ValueError("at_least_one called with empty list")

    if n <= 3:
        return [vars[:]]

    clauses: List[List[str]] = []
    t_prev = gen.fresh()
    clauses.append([vars[0], vars[1], t_prev])

    # middle links
    # i runs over vars[2]..vars[n-3] (0-based)
    for idx in range(2, n - 2):
        t_next = gen.fresh()
        clauses.append([neg(t_prev), vars[idx], t_next])
        t_prev = t_next

    # last clause closes chain
    clauses.append([neg(t_prev), vars[n - 2], vars[n - 1]])
    return clauses

def exactly_one_cnf(vars: List[str], gen: AuxGen) -> List[List[str]]:
    # exactly one = at least one + at most one
    clauses = []
    clauses.extend(at_least_one_to_3cnf(vars, gen))
    clauses.extend(at_most_one_cnf(vars))
    return clauses

def encode_sudoku(puzzle: List[List[int]]) -> str:
    logger.debug("Starting Sudoku to CNF encoding")
    gen = AuxGen()
    cnf: List[List[str]] = []

    # (A) Each cell has exactly one digit
    logger.debug("Encoding constraint A: Each cell has exactly one digit")
    for r in range(1, SIZE + 1):
        for c in range(1, SIZE + 1):
            vars_rc = [xvar(r, c, d) for d in DIGITS]
            cnf.extend(exactly_one_cnf(vars_rc, gen))

    # (B) Rows: each digit appears exactly once
    logger.debug("Encoding constraint B: Each digit appears once per row")
    for r in range(1, SIZE + 1):
        for d in DIGITS:
            vars_row = [xvar(r, c, d) for c in range(1, SIZE + 1)]
            cnf.extend(exactly_one_cnf(vars_row, gen))

    # (C) Columns
    logger.debug("Encoding constraint C: Each digit appears once per column")
    for c in range(1, SIZE + 1):
        for d in DIGITS:
            vars_col = [xvar(r, c, d) for r in range(1, SIZE + 1)]
            cnf.extend(exactly_one_cnf(vars_col, gen))

    # (D) Blocks
    logger.debug("Encoding constraint D: Each digit appears once per 3x3 block")
    for br in range(0, SIZE, BLOCK):
        for bc in range(0, SIZE, BLOCK):
            for d in DIGITS:
                vars_blk = [
                    xvar(br + r, bc + c, d)
                    for r in range(1, BLOCK + 1)
                    for c in range(1, BLOCK + 1)
                ]
                cnf.extend(exactly_one_cnf(vars_blk, gen))

    # (E) Given clues (unit clauses)
    clue_count = 0
    logger.debug("Encoding constraint E: Given clues")
    for r in range(SIZE):
        for c in range(SIZE):
            d = puzzle[r][c]
            if d != 0:
                cnf.append([xvar(r + 1, c + 1, d)])
                clue_count += 1
    logger.debug(f"Encoded {clue_count} clues from puzzle")

    # Serialize: each clause is one line, 1..3 literals
    lines = [" ".join(cl) for cl in cnf]
    result = "\n".join(lines)
    logger.info(f"Sudoku encoding complete: {len(cnf)} total clauses, {gen.k} auxiliary variables")
    return result

def decode_solution(lines: List[str]) -> List[List[int]]:
    logger.debug(f"Decoding SAT solver output with {len(lines)} lines")
    grid = [[0] * SIZE for _ in range(SIZE)]
    decoded_count = 0

    for line in lines:
        line = line.strip()
        # only accept actual Sudoku vars xrcd
        if line.startswith("x") and "-> TRUE" in line:
            name = line.split()[0]  # xrcd
            if len(name) != 4:
                continue
            try:
                r = int(name[1])
                c = int(name[2])
                d = int(name[3])
                grid[r - 1][c - 1] = d
                decoded_count += 1
            except (ValueError, IndexError) as e:
                logger.warning(f"Failed to decode variable {name}: {e}")
                continue

    logger.debug(f"Decoded {decoded_count} variables from SAT output")
    return grid

    """
    Propagation for naked singles, if a row, col or 3x3 sub box has numbers 1-8, then put missing number.
    """
    
def block_cells(r, c):
    br = (r // BLOCK) * BLOCK
    bc = (c // BLOCK) * BLOCK
    return [(br + i, bc + j) for i in range(BLOCK) for j in range(BLOCK)]

def possible_digits(grid, r, c):
    used = set(grid[r])
    used |= {grid[i][c] for i in range(SIZE)}
    for rr, cc in block_cells(r, c):
        used.add(grid[rr][cc])
    return {d for d in DIGITS if d not in used}

def propagate(grid):
    """Constraint propagation via naked singles."""
    logger.debug("Starting constraint propagation")
    iteration = 0
    changed = True
    while changed:
        iteration += 1
        changed = False
        for r in range(SIZE):
            for c in range(SIZE):
                if grid[r][c] != 0:
                    continue
                candidates = possible_digits(grid, r, c)
                if len(candidates) == 0:
                    logger.warning(f"No candidates for cell ({r}, {c}) - puzzle is unsolvable")
                    return grid
                if len(candidates) == 1:
                    digit = candidates.pop()
                    grid[r][c] = digit
                    changed = True
                    logger.debug(f"Propagated digit {digit} to cell ({r}, {c})")
    logger.info(f"Constraint propagation complete after {iteration} iteration(s)")
    return grid