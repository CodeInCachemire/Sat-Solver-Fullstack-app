// Real backend job queue integration for async Sudoku solving
        
        const API_BASE = '/api';
        const POLL_INTERVAL_MS = 500;  // Poll status every 500ms
        
        const SAMPLE_PUZZLES = [
            [
                [0, 9, 1, 0, 0, 0, 0, 7, 0],
                [3, 0, 0, 0, 0, 0, 0, 0, 6],
                [7, 0, 0, 0, 4, 0, 0, 0, 0],
                [0, 0, 0, 1, 0, 0, 0, 0, 5],
                [0, 6, 0, 0, 0, 8, 0, 3, 0],
                [5, 3, 0, 0, 0, 0, 2, 0, 9],
                [0, 0, 0, 0, 0, 7, 5, 0, 0],
                [0, 8, 0, 0, 0, 0, 0, 4, 2],
                [0, 0, 4, 6, 0, 0, 0, 0, 0]
            ],
            [
                [5, 3, 0, 0, 7, 0, 0, 0, 0],
                [6, 0, 0, 1, 9, 5, 0, 0, 0],
                [0, 9, 0, 0, 0, 0, 0, 6, 0],
                [8, 0, 0, 0, 6, 0, 0, 0, 3],
                [4, 0, 0, 8, 0, 3, 0, 0, 1],
                [7, 0, 0, 0, 2, 0, 0, 0, 6],
                [0, 6, 0, 0, 0, 0, 2, 8, 0],
                [0, 0, 0, 4, 1, 9, 0, 0, 5],
                [0, 0, 0, 0, 8, 0, 0, 7, 9]
            ],
            [
                [0, 0, 0, 2, 6, 0, 7, 0, 1],
                [6, 0, 0, 0, 7, 5, 0, 0, 9],
                [0, 9, 0, 0, 0, 0, 6, 0, 0],
                [3, 0, 0, 0, 0, 1, 0, 0, 4],
                [0, 8, 0, 4, 0, 7, 0, 5, 0],
                [5, 0, 0, 6, 0, 0, 0, 0, 8],
                [0, 0, 4, 0, 0, 0, 0, 6, 0],
                [1, 0, 0, 8, 3, 0, 0, 0, 5],
                [7, 0, 5, 0, 4, 9, 0, 0, 0]
            ],
            [
                [0, 2, 0, 0, 1, 0, 0, 3, 0],
                [0, 0, 5, 3, 0, 7, 8, 0, 0],
                [8, 0, 0, 0, 0, 0, 0, 0, 1],
                [0, 7, 0, 0, 3, 0, 0, 6, 0],
                [3, 0, 1, 7, 0, 5, 9, 0, 8],
                [0, 8, 0, 0, 6, 0, 0, 4, 0],
                [2, 0, 0, 0, 0, 0, 0, 0, 9],
                [0, 0, 3, 1, 0, 2, 7, 0, 0],
                [0, 9, 0, 0, 5, 0, 0, 8, 0]
            ],
            [
                [1, 0, 0, 0, 0, 6, 0, 3, 0],
                [0, 5, 0, 0, 3, 0, 0, 0, 4],
                [0, 0, 9, 0, 0, 0, 8, 0, 0],
                [0, 0, 0, 0, 9, 0, 0, 0, 1],
                [2, 0, 0, 5, 0, 7, 0, 0, 3],
                [7, 0, 0, 0, 2, 0, 0, 0, 0],
                [0, 0, 3, 0, 0, 0, 1, 0, 0],
                [5, 0, 0, 0, 7, 0, 0, 9, 0],
                [0, 8, 0, 4, 0, 0, 0, 0, 7]
            ],
            [
                [0, 0, 7, 0, 4, 0, 5, 0, 0],
                [2, 0, 0, 0, 0, 1, 0, 0, 8],
                [0, 0, 5, 0, 0, 0, 7, 0, 0],
                [0, 1, 0, 6, 0, 2, 0, 7, 0],
                [0, 0, 0, 0, 0, 0, 0, 0, 0],
                [0, 2, 0, 9, 0, 3, 0, 6, 0],
                [0, 0, 3, 0, 0, 0, 8, 0, 0],
                [4, 0, 0, 2, 0, 0, 0, 0, 6],
                [0, 0, 6, 0, 7, 0, 3, 0, 0]
            ],
            [
                [0, 3, 0, 1, 0, 0, 0, 0, 0],
                [0, 0, 0, 0, 2, 0, 9, 0, 0],
                [7, 0, 4, 0, 0, 0, 0, 0, 0],
                [0, 0, 0, 0, 0, 3, 0, 0, 7],
                [0, 0, 8, 0, 0, 0, 5, 0, 0],
                [6, 0, 0, 4, 0, 0, 0, 0, 0],
                [0, 0, 0, 0, 0, 0, 6, 0, 2],
                [0, 0, 9, 0, 4, 0, 0, 0, 0],
                [0, 0, 0, 0, 0, 1, 0, 8, 0]
            ],
            puzzle = [
    [0, 9, 2, 3, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 8, 0, 1, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],

    [1, 0, 7, 0, 4, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 6, 5],
    [8, 0, 0, 0, 0, 0, 0, 0, 0],

    [0, 6, 0, 5, 0, 2, 0, 0, 0],
    [4, 0, 0, 0, 0, 0, 7, 0, 0],
    [0, 0, 0, 9, 0, 0, 0, 0, 0]
],
        ];

        const WORKER_COUNT = 4;

        // State management
        const state = {
            puzzles: [],
            pollIntervals: {},  // Store poll interval IDs: { puzzleId: intervalId }
            activities: [],
            isRunning: false,
            cellInputs: {}  // Store input element references: { "puzzle-row-col": input }
        };

        // Initialize
        init();

        function init() {
            createPuzzles();
            initPuzzleWall();  // Create DOM once
            attachEventListeners();
            state.activities = [{ time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }), message: 'System ready' }];
            renderActivityLog();
        }

        function createPuzzles(puzzlesData = null) {
            const data = puzzlesData || Array(8).fill(null).map(() => 
                Array(9).fill(null).map(() => Array(9).fill(0))
            );
            
            state.puzzles = data.map((puzzle, idx) => ({
                id: idx + 1,
                grid: puzzle.map(row => [...row]),  // Mutable copy (user edits before run)
                original: puzzle.map(row => [...row]),  // Immutable for reset
                // Backend state
                status: 'idle',  // idle, queued, running, finished (success), failed (failure)
                runId: null,
                backendStatus: null,  // QUEUED, PROCESSING, COMPLETED, FAILED, TIMEOUT
                submittedGrid: null,  // Frozen copy of grid at submission
                solutionGrid: null,   // Solved grid from backend
                result: null,
                errorMessage: null,
                pollStartedAt: null,
                submittedAt: null,
                runtime: null  // Execution time in seconds from backend
            }));
        }

        function attachEventListeners() {
            document.getElementById('demo-run-btn').addEventListener('click', runDemo);
            document.getElementById('demo-reset-btn').addEventListener('click', resetDemo);
            document.getElementById('load-default-btn').addEventListener('click', loadDefaultPuzzles);
        }

        function loadDefaultPuzzles() {
            // Cancel any active polling
            cancelAllPolling();
            
            state.isRunning = false;
            state.activities = [{ time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }), message: 'Default puzzles loaded' }];
            
            createPuzzles(SAMPLE_PUZZLES);
            
            document.getElementById('demo-run-btn').disabled = false;
            
            // Unlock and re-populate all puzzle inputs
            state.puzzles.forEach(puzzle => {
                for (let r = 0; r < 9; r++) {
                    for (let c = 0; c < 9; c++) {
                        const key = `puzzle-${puzzle.id}-${r}-${c}`;
                        const input = state.cellInputs[key];
                        if (input) {
                            input.disabled = false;
                            input.value = puzzle.grid[r][c] === 0 ? '' : puzzle.grid[r][c];
                            // Update given cell styling
                            if (puzzle.grid[r][c] !== 0) {
                                input.classList.add('given');
                            } else {
                                input.classList.remove('given');
                            }
                        }
                    }
                }
            });
            
            renderPuzzleWall();
            updateStats();
            renderActivityLog();
        }

        function runDemo() {
            if (state.isRunning) return;
            state.isRunning = true;
            document.getElementById('demo-run-btn').disabled = true;
            
            // Lock all puzzle inputs
            Object.values(state.cellInputs).forEach(input => {
                input.disabled = true;
            });
            
            // Collect grids and submit non-empty puzzles to backend
            state.puzzles.forEach((puzzle, idx) => {
                // Check if puzzle is empty
                const isEmpty = puzzle.grid.every(row => row.every(cell => cell === 0));
                
                if (isEmpty) {
                    puzzle.status = 'idle';
                    addActivity(`Puzzle ${puzzle.id} skipped (empty)`);
                } else {
                    // Submit with staggered timing
                    setTimeout(() => {
                        submitPuzzleToBackend(puzzle.id);
                    }, idx * 150);
                }
            });
            
            renderPuzzleWall();
            updateStats();
            renderJobTracking();
        }

        async function submitPuzzleToBackend(puzzleId) {
            const puzzle = state.puzzles[puzzleId - 1];
            
            try {
                puzzle.status = 'queued';
                puzzle.submittedAt = new Date().toLocaleTimeString();
                puzzle.submittedGrid = puzzle.grid.map(row => [...row]);  // Freeze submitted state
                
                // Serialize grid as compact JSON
                const formula = JSON.stringify(puzzle.grid);
                
                const response = await fetch(`${API_BASE}/jobs/submit`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        formula: formula,
                        notation: 'RPN',
                        mode: 'CNF_SUDOKU'
                    })
                });

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }

                const data = await response.json();
                puzzle.runId = String(data.run_id);  // Convert to string for display
                puzzle.pollStartedAt = Date.now();
                
                addActivity(`Puzzle ${puzzleId} submitted (run_id: ${puzzle.runId})`);
                renderPuzzleWall();
                updateStats();
                
                // Start polling for this puzzle
                startPollingPuzzle(puzzleId);
            } catch (err) {
                puzzle.status = 'failed';
                puzzle.errorMessage = `Submit failed: ${err.message}`;
                addActivity(`Puzzle ${puzzleId} submit failed: ${err.message}`);
                renderPuzzleWall();
                updateStats();
            }
        }

        function startPollingPuzzle(puzzleId) {
            const puzzle = state.puzzles[puzzleId - 1];
            
            // Cancel any existing poll for this puzzle
            if (state.pollIntervals[puzzleId]) {
                clearInterval(state.pollIntervals[puzzleId]);
            }
            
            const intervalId = setInterval(async () => {
                try {
                    const response = await fetch(`${API_BASE}/jobs/status/${puzzle.runId}`);
                    
                    if (!response.ok) {
                        throw new Error(`HTTP ${response.status}`);
                    }

                    const data = await response.json();
                    const currentStatus = data.status;
                    
                    // Update if status changed
                    if (puzzle.backendStatus !== currentStatus) {
                        puzzle.backendStatus = currentStatus;
                        addActivity(`Puzzle ${puzzleId}: ${currentStatus}`);
                        renderPuzzleWall();
                        updateStats();
                    }
                    
                    // Check for terminal state
                    if (currentStatus === 'COMPLETED') {
                        clearInterval(intervalId);
                        delete state.pollIntervals[puzzleId];
                        fetchPuzzleResult(puzzleId);
                    } else if (currentStatus === 'FAILED' || currentStatus === 'TIMEOUT') {
                        clearInterval(intervalId);
                        delete state.pollIntervals[puzzleId];
                        puzzle.status = 'failed';
                        puzzle.errorMessage = currentStatus;
                        addActivity(`Puzzle ${puzzleId} ${currentStatus}`);
                        renderPuzzleWall();
                        updateStats();
                    }
                } catch (err) {
                    // Don't spam errors, just log once
                    if (!puzzle.errorMessage) {
                        puzzle.errorMessage = `Poll error: ${err.message}`;
                        addActivity(`Puzzle ${puzzleId} poll error: ${err.message}`);
                    }
                }
            }, POLL_INTERVAL_MS);
            
            state.pollIntervals[puzzleId] = intervalId;
        }

        async function fetchPuzzleResult(puzzleId) {
            const puzzle = state.puzzles[puzzleId - 1];
            
            try {
                const response = await fetch(`${API_BASE}/jobs/result/${puzzle.runId}`);
                
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }

                const data = await response.json();
                
                // Check if result is UNSAT (unsolvable)
                if (data.result === 'UNSAT') {
                    puzzle.status = 'failed';
                    puzzle.errorMessage = 'UNSAT (unsolvable)';
                    addActivity(`Puzzle ${puzzleId} UNSAT (no solution exists)`);
                    renderPuzzleWall();
                    updateStats();
                    return;
                }
                
                // Extract solved grid from assignment
                if (data.assignment && Array.isArray(data.assignment)) {
                    const solvedGrid = data.assignment;
                    
                    // Validate it's a proper solution
                    if (solvedGrid.length === 9 && solvedGrid.every(row => row.length === 9)) {
                        puzzle.solutionGrid = solvedGrid;
                        puzzle.status = 'finished';
                        puzzle.result = data;
                        puzzle.runtime = data.runtime;  // Capture runtime from backend
                        
                        // Populate the board with solved values
                        populateSolvedBoard(puzzleId, solvedGrid);
                        
                        addActivity(`Puzzle ${puzzleId} solved!`);
                        renderPuzzleWall();
                        updateStats();
                        return;
                    }
                }
                
                // If we get here, result was not valid
                puzzle.status = 'failed';
                puzzle.errorMessage = 'Invalid result format';
                addActivity(`Puzzle ${puzzleId} invalid result`);
                renderPuzzleWall();
                updateStats();
            } catch (err) {
                puzzle.status = 'failed';
                puzzle.errorMessage = `Result fetch failed: ${err.message}`;
                addActivity(`Puzzle ${puzzleId} result fetch failed: ${err.message}`);
                renderPuzzleWall();
                updateStats();
            }
        }

        function populateSolvedBoard(puzzleId, solvedGrid) {
            const puzzle = state.puzzles[puzzleId - 1];
            
            // Update grid and input elements
            for (let r = 0; r < 9; r++) {
                for (let c = 0; c < 9; c++) {
                    puzzle.grid[r][c] = solvedGrid[r][c];
                    
                    const key = `puzzle-${puzzleId}-${r}-${c}`;
                    const input = state.cellInputs[key];
                    if (input) {
                        input.value = solvedGrid[r][c];
                        
                        // Mark cells that were filled by solver (not in submitted grid)
                        const wasEmpty = puzzle.submittedGrid[r][c] === 0;
                        if (wasEmpty) {
                            input.classList.add('solved');
                        }
                    }
                }
            }
        }

        function cancelAllPolling() {
            Object.values(state.pollIntervals).forEach(intervalId => {
                clearInterval(intervalId);
            });
            state.pollIntervals = {};
        }

        function resetDemo() {
            // Cancel any active polling
            cancelAllPolling();
            
            state.isRunning = false;
            state.activities = [{ time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }), message: 'All puzzles cleared' }];

            // Clear all puzzles to empty and reset backend state
            state.puzzles.forEach(puzzle => {
                for (let r = 0; r < 9; r++) {
                    for (let c = 0; c < 9; c++) {
                        puzzle.grid[r][c] = 0;
                    }
                }
                puzzle.status = 'idle';
                puzzle.runId = null;
                puzzle.backendStatus = null;
                puzzle.submittedGrid = null;
                puzzle.solutionGrid = null;
                puzzle.result = null;
                puzzle.errorMessage = null;
                puzzle.pollStartedAt = null;
                puzzle.submittedAt = null;
                puzzle.runtime = null;
            });

            document.getElementById('demo-run-btn').disabled = false;
            
            // Unlock and clear all puzzle inputs
            state.puzzles.forEach(puzzle => {
                for (let r = 0; r < 9; r++) {
                    for (let c = 0; c < 9; c++) {
                        const key = `puzzle-${puzzle.id}-${r}-${c}`;
                        const input = state.cellInputs[key];
                        if (input) {
                            input.disabled = false;
                            input.value = '';
                            input.classList.remove('given');
                            input.classList.remove('solved');
                        }
                    }
                }
            });
            
            renderPuzzleWall();
            updateStats();
            renderActivityLog();
        }

        function renderPuzzleWall() {
            const wallEl = document.getElementById('puzzle-wall');
            
            state.puzzles.forEach(puzzle => {
                const card = wallEl.querySelector(`[data-puzzle-id="${puzzle.id}"]`);
                if (card) {
                    // Update card state class based on backend status or local status
                    let stateClass = 'state-idle';
                    if (puzzle.status === 'finished') stateClass = 'state-finished';
                    else if (puzzle.status === 'failed') stateClass = 'state-failed';
                    else if (puzzle.backendStatus === 'PROCESSING') stateClass = 'state-running';
                    else if (puzzle.backendStatus === 'QUEUED') stateClass = 'state-queued';
                    else if (puzzle.status === 'queued') stateClass = 'state-queued';
                    
                    card.className = `puzzle-card ${stateClass}`;
                    
                    // Update status badge
                    const statusBadge = card.querySelector('.puzzle-status');
                    statusBadge.className = `puzzle-status ${puzzle.status}`;
                    const statusText = puzzle.errorMessage || puzzle.backendStatus || puzzle.status.charAt(0).toUpperCase() + puzzle.status.slice(1);
                    statusBadge.textContent = statusText;
                    
                    // Update run ID label and submission time
                    const workerLabel = card.querySelector('.puzzle-worker');
                    const timeLabel = card.querySelector('.puzzle-time');
                    const runtimeStr = puzzle.runtime ? ` | Runtime: ${puzzle.runtime.toFixed(3)}s` : '';
                    workerLabel.textContent = puzzle.runId ? `ID: ${puzzle.runId}${runtimeStr}` : '';
                    timeLabel.textContent = puzzle.submittedAt ? puzzle.submittedAt : '';
                    
                    // Ensure failed/finished puzzles show their submitted grid
                    if (puzzle.status === 'failed' || puzzle.status === 'finished') {
                        for (let r = 0; r < 9; r++) {
                            for (let c = 0; c < 9; c++) {
                                const key = `puzzle-${puzzle.id}-${r}-${c}`;
                                const input = state.cellInputs[key];
                                if (input) {
                                    // Show submitted grid values
                                    input.value = puzzle.submittedGrid[r][c] === 0 ? '' : puzzle.submittedGrid[r][c];
                                }
                            }
                        }
                    }
                }
            });
        }

        function initPuzzleWall() {
            const wallEl = document.getElementById('puzzle-wall');
            wallEl.innerHTML = '';

            state.puzzles.forEach(puzzle => {
                // Create card container
                const card = document.createElement('div');
                card.className = `puzzle-card state-${puzzle.status}`;
                card.setAttribute('data-puzzle-id', puzzle.id);

                // Header
                const header = document.createElement('div');
                header.className = 'puzzle-header';
                header.innerHTML = `
                    <span class="puzzle-id">Puzzle ${puzzle.id}</span>
                    <span class="puzzle-status ${puzzle.status}">Idle</span>
                `;
                card.appendChild(header);

                // Mini board (grid of input cells)
                const miniBoard = document.createElement('div');
                miniBoard.className = 'mini-board';
                
                for (let r = 0; r < 9; r++) {
                    for (let c = 0; c < 9; c++) {
                        const input = document.createElement('input');
                        input.className = 'mini-cell';
                        input.type = 'text';
                        input.inputMode = 'numeric';
                        input.maxLength = '1';
                        input.setAttribute('data-row', r);
                        input.setAttribute('data-col', c);
                        input.value = puzzle.grid[r][c] === 0 ? '' : puzzle.grid[r][c];
                        
                        // Mark given cells visually (but still editable)
                        if (puzzle.grid[r][c] !== 0) {
                            input.classList.add('given');
                        }
                        
                        // Store reference
                        const key = `puzzle-${puzzle.id}-${r}-${c}`;
                        state.cellInputs[key] = input;
                        
                        // Add event listeners
                        input.addEventListener('keydown', (e) => handleCellKeydown(e, puzzle.id, r, c));
                        input.addEventListener('input', (e) => handleCellInput(e, puzzle.id, r, c));
                        input.addEventListener('paste', (e) => handleCellPaste(e, puzzle.id, r, c));
                        
                        miniBoard.appendChild(input);
                    }
                }
                card.appendChild(miniBoard);

                // Meta info
                const meta = document.createElement('div');
                meta.className = 'puzzle-meta';
                meta.innerHTML = `
                    <div class="puzzle-worker"></div>
                    <div class="puzzle-time"></div>
                `;
                card.appendChild(meta);

                wallEl.appendChild(card);
            });
        }

        function handleCellKeydown(e, puzzleId, row, col) {
            const puzzle = state.puzzles[puzzleId - 1];
            
            // Don't allow editing while demo is running
            if (state.isRunning) {
                e.preventDefault();
                return;
            }
            
            const key = e.key;
            
            // Handle digit entry (1-9)
            if (/^[1-9]$/.test(key)) {
                e.preventDefault();
                puzzle.grid[row][col] = Number(key);
                updateCellDisplay(puzzleId, row, col);
                moveFocus(puzzleId, row, col, 'ArrowRight');
                return;
            }
            
            // Handle 0, Backspace, Delete
            if (key === '0' || key === 'Backspace' || key === 'Delete') {
                e.preventDefault();
                puzzle.grid[row][col] = 0;
                updateCellDisplay(puzzleId, row, col);
                if (key !== 'Backspace' && key !== 'Delete') {
                    moveFocus(puzzleId, row, col, 'ArrowRight');
                }
                return;
            }
            
            // Handle arrow keys for navigation within the board
            if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(key)) {
                e.preventDefault();
                moveFocus(puzzleId, row, col, key);
                return;
            }
            
            // Prevent other keys
            if (!['Tab', 'Shift', 'Control', 'Meta', 'Alt'].includes(key)) {
                e.preventDefault();
            }
        }

        function handleCellInput(e, puzzleId, row, col) {
            const puzzle = state.puzzles[puzzleId - 1];
            if (state.isRunning) return;
            
            let val = e.target.value.trim();
            if (val === '') {
                puzzle.grid[row][col] = 0;
            } else if (/^[1-9]$/.test(val)) {
                puzzle.grid[row][col] = Number(val);
            } else {
                e.target.value = '';
                puzzle.grid[row][col] = 0;
            }
            updateCellDisplay(puzzleId, row, col);
        }

        function handleCellPaste(e, puzzleId, row, col) {
            e.preventDefault();
            if (state.isRunning) return;
            
            const puzzle = state.puzzles[puzzleId - 1];
            const text = (e.clipboardData || window.clipboardData).getData('text').trim();
            
            if (/^[1-9]$/.test(text)) {
                puzzle.grid[row][col] = Number(text);
                updateCellDisplay(puzzleId, row, col);
            }
        }

        function updateCellDisplay(puzzleId, row, col) {
            const puzzle = state.puzzles[puzzleId - 1];
            const key = `puzzle-${puzzleId}-${row}-${col}`;
            const input = state.cellInputs[key];
            if (input) {
                input.value = puzzle.grid[row][col] === 0 ? '' : puzzle.grid[row][c];
            }
        }

        function moveFocus(puzzleId, row, col, direction) {
            let newRow = row;
            let newCol = col;
            
            if (direction === 'ArrowUp') newRow = Math.max(0, row - 1);
            else if (direction === 'ArrowDown') newRow = Math.min(8, row + 1);
            else if (direction === 'ArrowLeft') newCol = Math.max(0, col - 1);
            else if (direction === 'ArrowRight') newCol = Math.min(8, col + 1);
            
            const key = `puzzle-${puzzleId}-${newRow}-${newCol}`;
            const input = state.cellInputs[key];
            if (input) {
                input.focus();
                input.select();
            }
        }

        function renderJobTracking() {
            const listEl = document.getElementById('worker-list');
            
            // Show puzzles with active runs
            const activeRuns = state.puzzles.filter(p => p.runId && p.status !== 'idle');
            
            if (activeRuns.length === 0) {
                listEl.innerHTML = '<div style="color: var(--muted); font-size: 0.9rem; padding: 0.5rem;">No active jobs</div>';
                return;
            }
            
            listEl.innerHTML = activeRuns.map(puzzle => {
                const statusClass = puzzle.status === 'failed' ? 'failed' : puzzle.status === 'finished' ? 'completed' : 'active';
                const statusText = puzzle.backendStatus || puzzle.status;
                const runtimeStr = puzzle.runtime ? ` | ${puzzle.runtime.toFixed(3)}s` : '';
                
                return `
                    <div class="worker-item">
                        <span class="worker-name">Puzzle ${puzzle.id}</span>
                        <div style="display: flex; gap: 0.5rem; align-items: center; font-size: 0.85rem;">
                            <span style="color: var(--muted);">${puzzle.runId}${runtimeStr}</span>
                            <span class="worker-status ${statusClass}">
                                <span class="worker-dot ${statusClass}"></span>
                                ${statusText}
                            </span>
                        </div>
                    </div>
                `;
            }).join('');
        }

        function updateStats() {
            const queued = state.puzzles.filter(p => p.status === 'queued').length;
            const running = state.puzzles.filter(p => p.backendStatus === 'PROCESSING').length;
            const completed = state.puzzles.filter(p => p.status === 'finished').length;
            
            document.getElementById('queue-count').textContent = queued;
            document.getElementById('running-count').textContent = running;
            document.getElementById('completed-count').textContent = completed;
        }

        function addActivity(message) {
            const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
            state.activities.unshift({ time, message });
            renderActivityLog();
            renderJobTracking();
        }

        function renderActivityLog() {
            const listEl = document.getElementById('activity-list');

            listEl.innerHTML = state.activities.map((activity, idx) => {
                let msgClass = '';
                if (activity.message.includes('submitted')) msgClass = 'submitted';
                else if (activity.message.includes('PROCESSING')) msgClass = 'started';
                else if (activity.message.includes('solved')) msgClass = 'completed';
                else if (activity.message.includes('failed') || activity.message.includes('FAILED')) msgClass = 'failed';

                return `
                    <div class="activity-item" style="animation-delay: ${idx * 30}ms">
                        <span class="activity-time">${activity.time}</span>
                        <span class="activity-msg ${msgClass}">${activity.message}</span>
                    </div>
                `;
            }).join('');
        }
    }
}