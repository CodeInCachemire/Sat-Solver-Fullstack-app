(function () {
    const API_BASE = '/api';
    const GRID_SIZE = 9;
    const BOX_SIZE = 3;
    const SAMPLE_PUZZLE = [
        [0, 9, 1, 0, 0, 0, 0, 7, 0],
        [3, 0, 0, 0, 0, 0, 0, 0, 6],
        [7, 0, 0, 0, 4, 0, 0, 0, 0],
        [0, 0, 0, 1, 0, 0, 0, 0, 5],
        [0, 6, 0, 0, 0, 8, 0, 3, 0],
        [5, 3, 0, 0, 0, 0, 2, 0, 9],
        [0, 0, 0, 0, 0, 7, 5, 0, 0],
        [0, 8, 0, 0, 0, 0, 0, 4, 2],
        [0, 0, 4, 6, 0, 0, 0, 0, 0]
    ]
    const SAMPLE_PUZZLE_UNSAT = [
        [0, 9, 1, 0, 0, 0, 0, 7, 0],
        [3, 0, 0, 0, 0, 0, 0, 0, 6],
        [7, 0, 9, 0, 4, 0, 0, 0, 0],

        [0, 0, 0, 1, 0, 0, 0, 0, 5],
        [0, 6, 0, 0, 0, 8, 0, 3, 0],
        [5, 3, 0, 0, 0, 0, 2, 0, 9],

        [0, 0, 0, 0, 0, 7, 5, 0, 0],
        [0, 8, 0, 0, 0, 0, 0, 4, 2],
        [0, 0, 4, 6, 0, 0, 0, 0, 0]
    ];
    const BOX_NAMES = [
        ["top-left", "top-middle", "top-right"],
        ["middle-left", "center", "middle-right"],
        ["bottom-left", "bottom-middle", "bottom-right"]
    ];

    const state = {
        userGrid: createEmptyGrid(),
        solutionGrid: null,
        givenMask: createBooleanGrid(false),
        conflicts: {
            cells: new Set(),
            messages: []
        },
        result: {
            status: "idle",
            message: "Submit a puzzle to see whether it is SOLVABLE or UNSOLVABLE.",
            solver: null,
            timeSeconds: null
        },
        isLoading: false,
        autoAdvance: true
    };

    const boardElement = document.getElementById("sudoku-board");
    const advisoryBanner = document.getElementById("advisory-banner");
    const advisoryList = document.getElementById("advisory-list");
    const resultBox = document.getElementById("result-box");
    const resultMeta = document.getElementById("result-meta");
    const solveButton = document.getElementById("solve-button");
    const clearButton = document.getElementById("clear-button");
    const sampleButton = document.getElementById("sample-button");
    const sampleButtonUNSAT = document.getElementById("sample-button-unsat");
    const uploadPuzzleButton = document.getElementById("upload-puzzle-button");
    const heroNote = document.querySelector(".hero-note");
    const nyEasy = document.getElementById("ny-easy")
    const nyMedium = document.getElementById("ny-medium")
    const nyHard = document.getElementById("ny-hard")
    const loadingModal = document.getElementById("loading-modal");
    const cellElements = [];

    // Create hidden file input for image upload
    const fileInput = document.createElement("input");
    fileInput.id = "sudoku-file-input";
    fileInput.type = "file";
    fileInput.accept = "image/*";
    fileInput.style.display = "none";
    document.body.appendChild(fileInput);

    fileInput.addEventListener("change", async (e) => {
        if (e.target.files && e.target.files[0]) {
            const file = e.target.files[0];
            console.log("File selected:", file.name, file.type, file.size);
            hideWelcomeModal();
            await handleImageUpload(file);
        }
    });

    init();

    function init() {
        buildBoard();
        attachActions();  // This already calls attachModalActions()
        recomputeValidation();
        render();
        // Note: Welcome modal is now managed by the mode-selection modal flow in HTML
        // showWelcomeModal() is called after user selects "Single Solver" mode
    }

    function buildBoard() {
        for (let row = 0; row < GRID_SIZE; row += 1) {
            const cellRow = [];
            for (let col = 0; col < GRID_SIZE; col += 1) {
                const input = document.createElement("input");
                input.className = "sudoku-cell";
                input.type = "text";
                input.inputMode = "numeric";
                input.autocomplete = "off";
                input.maxLength = 1;
                input.setAttribute("aria-label", `Row ${row + 1}, column ${col + 1}`);
                input.setAttribute("role", "gridcell");
                input.dataset.row = String(row);
                input.dataset.col = String(col);
                input.addEventListener("keydown", handleCellKeyDown);
                input.addEventListener("input", handleCellInput);
                input.addEventListener("paste", handleCellPaste);
                boardElement.appendChild(input);
                cellRow.push(input);
            }
            cellElements.push(cellRow);
        }
    }

    function attachActions() {
        solveButton.addEventListener("click", solveCurrentPuzzle);
        clearButton.addEventListener("click", clearBoard);
        sampleButton.addEventListener("click", loadSample);
        sampleButtonUNSAT.addEventListener("click", loadSampleUNSAT);
        uploadPuzzleButton.addEventListener("click", imageUpload);
        heroNote.addEventListener("click", navigateToAbout);
        nyEasy.addEventListener("click",() => loadPuzzleNy("easy"));
        nyMedium.addEventListener("click", () =>  loadPuzzleNy("medium"));
        nyHard.addEventListener("click", () => loadPuzzleNy("hard"));
        attachModalActions();
    }

    function handleCellKeyDown(event) {
        const { row, col } = getCellPosition(event.currentTarget);
        if (isNavigationKey(event.key)) {
            event.preventDefault();
            moveFocus(row, col, event.key);
            return;
        }
        if (event.key === "Backspace" || event.key === "Delete") {
            event.preventDefault();
            applyUserEdit(row, col, 0);
            return;
        }
        if (event.key === "0") {
            event.preventDefault();
            applyUserEdit(row, col, 0);
            if (state.autoAdvance) {
                moveFocus(row, col, "ArrowRight");
            }
            return;
        }
        if (/^[1-9]$/.test(event.key)) {
            event.preventDefault();
            applyUserEdit(row, col, Number(event.key));
            if (state.autoAdvance) {
                moveFocus(row, col, "ArrowRight");
            }
            return;
        }
        if (event.key === "Tab" || event.ctrlKey || event.metaKey || event.altKey) {
            return;
        }
        event.preventDefault();
    }

    function handleCellInput(event) {
        const { row, col } = getCellPosition(event.currentTarget);
        applyUserEdit(row, col, sanitizeCellValue(event.currentTarget.value), false);
    }

    function handleCellPaste(event) {
        event.preventDefault();
        const text = (event.clipboardData || window.clipboardData).getData("text");
        const { row, col } = getCellPosition(event.currentTarget);
        applyUserEdit(row, col, sanitizeCellValue(text));
    }

    function applyUserEdit(row, col, value, shouldRefocus = true) {
        if (state.solutionGrid) {
            state.solutionGrid = null;
            state.givenMask = createBooleanGrid(false);
        }
        state.userGrid[row][col] = value;
        clearStaleResultAfterEdit();
        recomputeValidation();
        render();
        if (shouldRefocus) {
            focusCell(row, col);
        }
    }

    function solveCurrentPuzzle() {
        const payload = createPayload();
        if (!payload.ok) {
            setResultState({
                status: "error",
                message: payload.message,
                solver: null,
                timeSeconds: null
            });
            render();
            return;
        }

        state.isLoading = true;
        setResultState({
            status: "loading",
            message: "Sending puzzle to the Sudoku solver...",
            solver: null,
            timeSeconds: null
        });
        render();

        fetch(`${API_BASE}/sudoku/solve`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ grid: payload.grid })
        })
            .then(async (response) => {
                const raw = await readJsonSafely(response);
                if (!response.ok) {
                    throw new Error(extractErrorMessage(raw, response.status));
                }
                return normalizeSolveResponse(raw);
            })
            .then((normalized) => {
                if (normalized.result === "SAT" && normalized.solutionGrid) {
                    state.solutionGrid = cloneGrid(normalized.solutionGrid);
                    state.givenMask = buildGivenMask(state.userGrid);
                    recomputeValidation(getDisplayedGrid());
                } else {
                    state.solutionGrid = null;
                    state.givenMask = createBooleanGrid(false);
                    recomputeValidation();
                }

                if (normalized.result === "SAT" && !normalized.solutionGrid) {
                    setResultState({
                        status: "error",
                        message: "The solver reported SAT but did not include a usable 9x9 solution grid.",
                        solver: normalized.solver,
                        timeSeconds: normalized.timeSeconds
                    });
                } else if (normalized.result === "UNSAT") {
                    setResultState({
                        status: "unsat",
                        message: normalized.message || "The puzzle is unsatisfiable. Contradictory clues may be the cause.",
                        solver: normalized.solver,
                        timeSeconds: normalized.timeSeconds
                    });
                } else if (normalized.result === "SAT") {
                    setResultState({
                        status: "sat",
                        message: normalized.message || "Solution found and merged into the board.",
                        solver: normalized.solver,
                        timeSeconds: normalized.timeSeconds
                    });
                } else {
                    setResultState({
                        status: "error",
                        message: normalized.message || "The solver returned an unexpected response.",
                        solver: normalized.solver,
                        timeSeconds: normalized.timeSeconds
                    });
                }
                render();
            })
            .catch((error) => {
                state.solutionGrid = null;
                state.givenMask = createBooleanGrid(false);
                recomputeValidation();
                setResultState({
                    status: "error",
                    message: error.message || "Something went wrong while contacting the solver.",
                    solver: null,
                    timeSeconds: null
                });
                render();
            })
            .finally(() => {
                state.isLoading = false;
                render();
            });
    }

    function clearBoard() {
        state.userGrid = createEmptyGrid();
        state.solutionGrid = null;
        state.givenMask = createBooleanGrid(false);
        state.isLoading = false;
        recomputeValidation();
        setResultState({
            status: "idle",
            message: "Submit a puzzle to see whether it is SOLVABLE or UNSOLVABLE.",
            solver: null,
            timeSeconds: null
        });
        render();
        focusCell(0, 0);
    }

    function loadSample() {
        state.userGrid = cloneGrid(SAMPLE_PUZZLE);
        state.solutionGrid = null;
        state.givenMask = createBooleanGrid(false);
        state.isLoading = false;
        recomputeValidation();
        setResultState({
            status: "idle",
            message: "Sample puzzle loaded. You can solve it as-is or edit any clues first.",
            solver: null,
            timeSeconds: null
        });
        render();
        focusCell(0, 0);
    }

    function loadSampleUNSAT() {
        state.userGrid = cloneGrid(SAMPLE_PUZZLE_UNSAT);
        state.solutionGrid = null;
        state.givenMask = createBooleanGrid(false);
        state.isLoading = false;
        recomputeValidation();
        setResultState({
            status: "idle",
            message: "Sample puzzle loaded. You can solve it as-is or edit any clues first.",
            solver: null,
            timeSeconds: null
        });
        render();
        focusCell(0, 0);
    }

    function navigateToAbout() {
        document.body.classList.add("page-flip-out");
        setTimeout(() => {
            window.location.href = "about.html";
        }, 300);
    }

    function createPayload() {
        if (!isValidGrid(state.userGrid)) {
            return {
                ok: false,
                message: "The board state is malformed. Only a 9x9 grid containing blank cells or digits 1-9 can be submitted."
            };
        }
        return {
            ok: true,
            grid: cloneGrid(state.userGrid)
        };
    }

    function recomputeValidation(grid = state.userGrid) {
        state.conflicts = validateGrid(grid);
    }

    function render() {
        renderBoard(getDisplayedGrid());
        renderAdvisory();
        renderResult();
        solveButton.disabled = state.isLoading;
        clearButton.disabled = state.isLoading;
        sampleButton.disabled = state.isLoading;
        uploadPuzzleButton.disabled = state.isLoading;
    }

    function renderBoard(displayedGrid) {
        for (let row = 0; row < GRID_SIZE; row += 1) {
            for (let col = 0; col < GRID_SIZE; col += 1) {
                const input = cellElements[row][col];
                const value = displayedGrid[row][col];
                const conflictKey = toCellKey(row, col);
                const isGiven = Boolean(state.solutionGrid && state.givenMask[row][col] && value !== 0);
                const isSolvedCell = Boolean(state.solutionGrid && !state.givenMask[row][col] && value !== 0);
                input.value = value === 0 ? "" : String(value);
                input.classList.toggle("is-given", isGiven);
                input.classList.toggle("is-solved", isSolvedCell);
                input.classList.toggle("is-conflict", state.conflicts.cells.has(conflictKey));
                input.classList.toggle("is-loading", state.isLoading);
                input.setAttribute("aria-invalid", state.conflicts.cells.has(conflictKey) ? "true" : "false");
            }
        }
    }

    function renderAdvisory() {
        const hasConflicts = state.conflicts.messages.length > 0;
        advisoryBanner.classList.toggle("status-ok", !hasConflicts);
        advisoryBanner.classList.toggle("status-warning", hasConflicts);
        advisoryBanner.textContent = hasConflicts
            ? "This board currently violates Sudoku rules. It may still be submitted, but the backend will return UNSOLVABLE(Unsatisfiable Constraint)."
            : "No duplicate conflicts detected.";

        advisoryList.innerHTML = "";
        state.conflicts.messages.forEach((message) => {
            const item = document.createElement("li");
            item.textContent = message;
            advisoryList.appendChild(item);
        });
    }

    function renderResult() {
        const current = state.result;
        resultBox.className = `result-box is-${current.status}`;
        resultBox.innerHTML = "";

        const stateLine = document.createElement("p");
        stateLine.className = "result-state";
        stateLine.textContent = resultStateLabel(current.status);
        resultBox.appendChild(stateLine);

        const messageLine = document.createElement("p");
        messageLine.className = "result-message";
        messageLine.textContent = current.message;
        resultBox.appendChild(messageLine);

        resultMeta.innerHTML = "";
        if (current.solver) {
            resultMeta.appendChild(buildMetaPill(`Solver: ${current.solver}`));
        }
        if (typeof current.timeSeconds === "number") {
            resultMeta.appendChild(buildMetaPill(`Runtime: ${current.timeSeconds.toFixed(6)}s`));
        }
        resultBox.appendChild(resultMeta);
    }

    function validateGrid(grid) {
        const cells = new Set();
        const messages = [];

        for (let row = 0; row < GRID_SIZE; row += 1) {
            collectDuplicates(
                grid[row].map((value, col) => ({ row, col, value })),
                `row ${row + 1}`,
                cells,
                messages
            );
        }
        for (let col = 0; col < GRID_SIZE; col += 1) {
            const columnEntries = [];
            for (let row = 0; row < GRID_SIZE; row += 1) {
                columnEntries.push({ row, col, value: grid[row][col] });
            }
            collectDuplicates(columnEntries, `column ${col + 1}`, cells, messages);
        }
        for (let boxRow = 0; boxRow < BOX_SIZE; boxRow += 1) {
            for (let boxCol = 0; boxCol < BOX_SIZE; boxCol += 1) {
                const boxEntries = [];
                for (let row = boxRow * BOX_SIZE; row < boxRow * BOX_SIZE + BOX_SIZE; row += 1) {
                    for (let col = boxCol * BOX_SIZE; col < boxCol * BOX_SIZE + BOX_SIZE; col += 1) {
                        boxEntries.push({ row, col, value: grid[row][col] });
                    }
                }
                collectDuplicates(boxEntries, `${BOX_NAMES[boxRow][boxCol]} 3x3 box`, cells, messages);
            }
        }
        return { cells, messages };
    }

    function collectDuplicates(entries, label, cells, messages) {
        const digitMap = new Map();
        entries.forEach((entry) => {
            if (entry.value === 0) {
                return;
            }
            if (!digitMap.has(entry.value)) {
                digitMap.set(entry.value, []);
            }
            digitMap.get(entry.value).push(entry);
        });

        digitMap.forEach((matches, digit) => {
            if (matches.length < 2) {
                return;
            }
            matches.forEach((match) => cells.add(toCellKey(match.row, match.col)));
            messages.push(`Duplicate ${digit} in ${label}.`);
        });
    }

    function normalizeSolveResponse(raw) {
        if (!raw || typeof raw !== "object") {
            return {
                result: "ERROR",
                solutionGrid: null,
                timeSeconds: null,
                solver: null,
                message: "The solver returned an unreadable response."
            };
        }
        if (raw.result === "SAT" || raw.result === "UNSAT" || raw.result === "ERROR") {
            return {
                result: raw.result,
                solutionGrid: parseSolutionGrid(raw.solution),
                timeSeconds: normalizeTime(raw.time_seconds),
                solver: normalizeOptionalString(raw.solver),
                message: normalizeOptionalString(raw.message) || normalizeOptionalString(raw.error) || defaultMessageFor(raw.result)
            };
        }
        if (typeof raw.solved === "boolean") {
            return {
                result: raw.solved ? "SAT" : "UNSAT",
                solutionGrid: parseSolutionGrid(raw.solution),
                timeSeconds: normalizeTime(raw.time_seconds),
                solver: normalizeOptionalString(raw.solver),
                message: normalizeOptionalString(raw.message) || normalizeOptionalString(raw.error) || defaultMessageFor(raw.solved ? "SAT" : "UNSAT")
            };
        }
        return {
            result: "ERROR",
            solutionGrid: null,
            timeSeconds: normalizeTime(raw.time_seconds),
            solver: normalizeOptionalString(raw.solver),
            message: normalizeOptionalString(raw.message) || normalizeOptionalString(raw.error) || "The solver response did not match any supported format."
        };
    }

    function parseSolutionGrid(solution) {
        if (!solution) {
            return null;
        }
        if (Array.isArray(solution) && solution.length === GRID_SIZE && solution.every(Array.isArray)) {
            const numericGrid = solution.map((row) => row.map((value) => Number(value)));
            return isValidGrid(numericGrid) ? numericGrid : null;
        }
        if (Array.isArray(solution) && solution.length === GRID_SIZE && solution.every((row) => typeof row === "string")) {
            const numericGrid = solution.map((row) => row.trim().split(/\s+/).map(Number));
            return isValidGrid(numericGrid) ? numericGrid : null;
        }
        if (solution.grid) {
            return parseSolutionGrid(solution.grid);
        }
        return null;
    }

    function readJsonSafely(response) {
        return response.text().then((text) => {
            if (!text) {
                return null;
            }
            try {
                return JSON.parse(text);
            } catch (error) {
                return { error: text };
            }
        });
    }

    function extractErrorMessage(raw, statusCode) {
        if (raw && typeof raw === "object") {
            if (typeof raw.detail === "string") {
                return raw.detail;
            }
            if (typeof raw.error === "string") {
                return raw.error;
            }
        }
        return `Request failed with status ${statusCode}.`;
    }

    function clearStaleResultAfterEdit() {
        if (state.result.status === "sat" || state.result.status === "unsat" || state.result.status === "error") {
            setResultState({
                status: "idle",
                message: "Board changed after the last backend result. Submit again to get a fresh answer.",
                solver: null,
                timeSeconds: null
            });
        }
    }

    function setResultState(next) {
        state.result = {
            status: next.status,
            message: next.message,
            solver: next.solver,
            timeSeconds: next.timeSeconds
        };
    }

    function getDisplayedGrid() {
        return state.solutionGrid ? state.solutionGrid : state.userGrid;
    }

    function buildGivenMask(grid) {
        return grid.map((row) => row.map((value) => value !== 0));
    }

    function isValidGrid(grid) {
        return Array.isArray(grid) &&
            grid.length === GRID_SIZE &&
            grid.every((row) =>
                Array.isArray(row) &&
                row.length === GRID_SIZE &&
                row.every((value) => Number.isInteger(value) && value >= 0 && value <= 9)
            );
    }

    function sanitizeCellValue(rawValue) {
        const text = String(rawValue || "").trim();
        if (text === "" || text === "0") {
            return 0;
        }
        const match = text.match(/[1-9]/);
        return match ? Number(match[0]) : 0;
    }

    function isNavigationKey(key) {
        return key === "ArrowUp" || key === "ArrowDown" || key === "ArrowLeft" || key === "ArrowRight";
    }

    function moveFocus(row, col, key) {
        const next = {
            ArrowUp: [Math.max(0, row - 1), col],
            ArrowDown: [Math.min(GRID_SIZE - 1, row + 1), col],
            ArrowLeft: [row, Math.max(0, col - 1)],
            ArrowRight: [row, Math.min(GRID_SIZE - 1, col + 1)]
        }[key];
        if (next) {
            focusCell(next[0], next[1]);
        }
    }

    function focusCell(row, col) {
        const cell = cellElements[row] && cellElements[row][col];
        if (cell) {
            cell.focus();
            cell.select();
        }
    }

    function getCellPosition(element) {
        return {
            row: Number(element.dataset.row),
            col: Number(element.dataset.col)
        };
    }

    function toCellKey(row, col) {
        return `${row}:${col}`;
    }

    function createEmptyGrid() {
        return Array.from({ length: GRID_SIZE }, () => Array(GRID_SIZE).fill(0));
    }

    function createBooleanGrid(fillValue) {
        return Array.from({ length: GRID_SIZE }, () => Array(GRID_SIZE).fill(fillValue));
    }

    function cloneGrid(grid) {
        return grid.map((row) => row.slice());
    }

    function normalizeOptionalString(value) {
        return typeof value === "string" && value.trim() ? value.trim() : null;
    }

    function normalizeTime(value) {
        if (typeof value === "number" && Number.isFinite(value)) {
            return value;
        }
        if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) {
            return Number(value);
        }
        return null;
    }

    function defaultMessageFor(result) {
        if (result === "SAT") {
            return "Solution found and merged into the board.";
        }
        if (result === "UNSAT") {
            return "The puzzle is unsatisfiable. Contradictory clues may be the cause.";
        }
        return "The solver returned an unexpected response.";
    }

    function resultStateLabel(status) {
        if (status === "loading") {
            return "Solving";
        }
        if (status === "sat") {
            return "SOLVABLE";
        }
        if (status === "unsat") {
            return "UNSOLVABLE";
        }
        if (status === "error") {
            return "Request Error";
        }
        return "Status";
    }

    function buildMetaPill(text) {
        const pill = document.createElement("span");
        pill.className = "meta-pill";
        pill.textContent = text;
        return pill;
    }

    function attachModalActions() {
        const uploadBtn = document.getElementById("modal-upload-btn");
        const manualBtn = document.getElementById("modal-manual-btn");
        const closeBtn = document.getElementById("modal-close-btn");

        uploadBtn.addEventListener("click", () => {
            // Trigger file input
            const fileInput = document.getElementById("sudoku-file-input");
            if (fileInput) {
                fileInput.click();
            }
        });

        manualBtn.addEventListener("click", () => {
            hideWelcomeModal();
        });

        closeBtn.addEventListener("click", () => {
            hideWelcomeModal();
        });
    }

    function showWelcomeModal() {
        const welcomeModal = document.getElementById("welcome-modal");
        welcomeModal.classList.remove("hidden");
    }

    function hideWelcomeModal() {
        const welcomeModal = document.getElementById("welcome-modal");
        welcomeModal.classList.add("hidden");
    }

    function showLoadingModal() {
        if (loadingModal) {
            loadingModal.classList.add("active");
        }
    }

    function hideLoadingModal() {
        if (loadingModal) {
            loadingModal.classList.remove("active");
        }
    }

    function imageUpload(){
        // Trigger file input
        const fileInput = document.getElementById("sudoku-file-input");
        if (fileInput) {
            fileInput.click();
        }
    }

    async function handleImageUpload(file) {
        /**
         * Handle image upload: validate file, send to backend, extract puzzle
         */
        
        // Validate file type
        const allowedTypes = ["image/jpeg", "image/png", "image/jpg"];
        if (!allowedTypes.includes(file.type)) {
            setResultState({
                status: "error",
                message: `Invalid file type: ${file.type}. Allowed: JPG, JPEG, PNG`,
                solver: null,
                timeSeconds: null
            });
            render();
            return;
        }
        
        // Validate file size (max 10MB)
        const maxSize = 10 * 1024 * 1024;
        if (file.size > maxSize) {
            setResultState({
                status: "error",
                message: `File too large: ${(file.size / (1024*1024)).toFixed(1)}MB. Maximum: 10MB`,
                solver: null,
                timeSeconds: null
            });
            render();
            return;
        }
        
        // Set loading state
        state.isLoading = true;
        showLoadingModal();
        setResultState({
            status: "loading",
            message: "Extracting puzzle from image using AI...",
            solver: null,
            timeSeconds: null
        });
        render();
        
        try {
            // Prepare form data
            const formData = new FormData();
            formData.append("file", file);
            
            // Send to backend
            console.log(`Uploading image: ${file.name} (${file.size} bytes)`);
            const response = await fetch(`${API_BASE}/sudoku/image-upload`, {
                method: "POST",
                body: formData
            });
            
            const raw = await readJsonSafely(response);
            
            if (!response.ok) {
                throw new Error(extractErrorMessage(raw, response.status));
            }
            
            // Validate extracted grid
            if (!raw.grid || !Array.isArray(raw.grid)) {
                throw new Error("No valid puzzle grid in response");
            }
            
            if (!isValidGrid(raw.grid)) {
                throw new Error("Extracted puzzle is not a valid 9x9 sudoku grid");
            }
            
            // Load extracted puzzle into board
            state.userGrid = cloneGrid(raw.grid);
            state.solutionGrid = null;
            state.givenMask = createBooleanGrid(false);
            recomputeValidation();
            
            setResultState({
                status: "idle",
                message: `Puzzle extracted from "${file.name}". Review and make any corrections, then click Solve! Remove all conflicts.`,
                solver: null,
                timeSeconds: null
            });
            
            console.log("Puzzle successfully extracted and loaded");
            
        } catch (error) {
            console.error("Image upload error:", error);
            setResultState({
                status: "error",
                message: error.message || "Failed to extract puzzle from image",
                solver: null,
                timeSeconds: null
            });
        } finally {
            state.isLoading = false;
            hideLoadingModal();
            render();
            
            // Reset file input so same file can be selected again
            const fileInput = document.getElementById("sudoku-file-input");
            if (fileInput) {
                fileInput.value = "";
            }
        }
    }

    async function loadPuzzleNy(difficulty){
        try {
            const response = await fetch(`${API_BASE}/sudoku/ny-puzzle/${difficulty.toLowerCase()}`, {
                method: 'GET',

            });

            if (!response.ok) {
                throw new Error(`Failed to fetch puzzle: ${response.status}`);
            }

            const data = await response.json();
            state.userGrid = data.grid;
            state.solutionGrid = null;
            state.givenMask = createBooleanGrid(false);
            recomputeValidation();
            setResultState({
                status: "idle",
                message: `NY Times ${difficulty} puzzle parsed and loaded. Click Solve to solve it!`,
                solver: null,
                timeSeconds: null
            });
            render();
        }catch(error) {
            setResultState({
            status: "error",
            message: error.message || "Failed to load NY puzzle",
            solver: null,
            timeSeconds: null
            });
            render();
        }
    }    
}());