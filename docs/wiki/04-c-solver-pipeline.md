# C SAT Solver Pipeline

## Overview

The SAT solver is written from scratch in C. It supports two input modes with distinct pipelines and exposes a clean exit-code interface to the Python layer.

---

## Source Structure

```
src/
├── main.c          # CLI entry point, argument parsing, mode dispatch
├── lexer.c/h       # Tokenizer for propositional formula input
├── parser.c/h      # Recursive-descent parser → AST
├── propformula.c/h # AST node types and operations
├── tseitin.c/h     # Tseitin transformation: AST → CNF
├── cnf.c/h         # CNF data structures (clause list, variable table)
├── cnf_parser.c/h  # DIMACS CNF parser (direct CNF input mode)
├── dpll.c/h        # DPLL algorithm implementation
├── variables.c/h   # Variable table and assignment management
├── list.c/h        # Generic linked list (used for clause + assignment stack)
└── err.c/h         # Error handling utilities
```

---

## Input Mode 1: Propositional Formula (RPN)

Used by the SAT solver terminal frontend. Formula is submitted in Reverse Polish Notation.

```
Input: "a b || a ! &&"  (means: (a OR b) AND (NOT a))

Pipeline:
  1. Lexer     → tokenize input stream into token list
                 operators: && || ! => <=>
                 operands: alphanumeric variable names

  2. Parser    → recursive-descent construction of AST
                 each node is an operator or variable leaf

  3. Tseitin   → introduce auxiliary variable per AST node
                 emit CNF clauses preserving equisatisfiability
                 result: CNF in linear clause count relative to formula size

  4. DPLL      → solve the CNF

Output: stdout with variable assignments (for SAT), nothing additional for UNSAT
Exit:   10 (SAT) | 20 (UNSAT) | 30 (parse error)
```

**Why RPN?** RPN is unambiguous without parentheses or operator precedence rules. The lexer and parser are simpler because no precedence climbing or Pratt parsing is needed.

---

## Input Mode 2: Direct CNF (DIMACS)

Used for Sudoku solving where CNF is generated server-side by Python.

```
Input: DIMACS format
  p cnf <num_vars> <num_clauses>
  1 -2 3 0
  -1 2 0
  ...

Pipeline:
  1. CNF Parser → read header, parse clause lines
                  each integer is a literal (positive = true, negative = negated)
                  0 terminates each clause

  2. DPLL      → solve directly

Output: same as mode 1
```

This mode bypasses the lexer, parser, and Tseitin transformation entirely — CNF is fed directly to the solver. For Sudoku, the Python layer generates the DIMACS string and pipes it to the binary's stdin.

---

## DPLL Algorithm

DPLL is a recursive backtracking search over variable assignments. The implementation uses an explicit assignment stack (not recursion) to avoid stack overflow on large formulas.

### Core Data Structures

```c
typedef struct Assignment {
    VarIndex var;
    Reason reason;   // CHOSEN (guessed) or IMPLIED (forced by propagation)
} Assignment;

List* stack;  // assignment stack — push on assignment, pop on backtrack
```

### Algorithm Steps (one iteration)

```
1. Unit Propagation
   For each clause:
     If clause has exactly one unassigned literal → force it (IMPLIED)
     If clause is empty (all literals false) → CONFLICT
   Repeat until no unit clauses remain or conflict found.

2. Pure Literal Elimination
   For each unassigned variable:
     If it appears only positive across all remaining clauses → assign true
     If it appears only negative → assign false
   (Implied assignments, not chosen)

3. Branching
   If no unit clauses and no pure literals:
     Pick an unassigned variable (first unassigned in variable table)
     Push assignment as CHOSEN
     Recurse

4. Backtracking
   On CONFLICT:
     Pop stack until a CHOSEN assignment is found
     If no CHOSEN assignment remains → UNSAT (exhausted search space)
     Flip the CHOSEN assignment (try the other value)
     Continue from step 1
```

### Return Convention

Each iteration returns:
- `1` → solver should terminate with SAT
- `0` → solver should continue (not yet resolved)
- `-1` → solver should terminate with UNSAT

---

## Tseitin Transformation

Converts an arbitrary propositional formula (AST) to CNF with linear clause growth.

**Core idea:** For each sub-formula node `n` with sub-formulas `a` and `b`, introduce a fresh variable `z_n` and add clauses enforcing `z_n ↔ (a OP b)`. The top-level `z_root` is forced true.

**Why Tseitin over naive CNF conversion?** Naive conversion (distribute OR over AND) can produce an exponential number of clauses. Tseitin guarantees linear growth in the number of AST nodes, at the cost of introducing auxiliary variables. The equisatisfiability property is preserved — if the original formula is SAT, so is the Tseitin CNF (and vice versa), though the Tseitin CNF may have models the original doesn't (due to auxiliary variables).

---

## Python Integration

The Python solver wrappers (`backend/app/solvers/satsolver.py`, `sudoku_solver.py`) invoke the binary via `subprocess.run()`:

```python
process = subprocess.run(
    [SOLVER_PATH, "--cnf"],   # or no --cnf for RPN mode
    input=formula_string,
    capture_output=True,
    text=True,
    timeout=timeout_s,
)

# Decision: check exit code only — no stdout parsing needed for SAT/UNSAT
if process.returncode == SolverExitCodes.SAT:    # 10
    # parse stdout for variable assignments
elif process.returncode == SolverExitCodes.UNSAT: # 20
    # no solution
```

**Runtime measurement:** Wall-clock time is measured around the `subprocess.run()` call using `time.perf_counter()` — captures actual solver time including process startup.

---

## Build and CI

```makefile
# Makefile produces two binaries:
bin/satsolver_opt   # optimized build (-O2) used in production
bin/testrunner      # unit test runner
```

GitHub Actions runs `make` on every push to `main`, verifies both binaries are present and executable, then runs `python3 test/run_tests.py` which feeds known SAT/UNSAT formulas to the solver and checks exit codes and assignments.
