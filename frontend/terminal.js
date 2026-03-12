// Configuration
const API_BASE_URL = 'http://localhost:8000';

// State
let currentPanel = 'left';
let commandHistory = {
    left: [],
    right: []
};
let historyIndex = {
    left: -1,
    right: -1
};

// DOM Elements
const submitInput = document.getElementById('submit-input');
const statusInput = document.getElementById('status-input');
const submitOutput = document.getElementById('submit-output');
const statusOutput = document.getElementById('status-output');
const connectionStatus = document.getElementById('connection-status');
const currentTimeEl = document.getElementById('current-time');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    setupEventListeners();
    updateTime();
    setInterval(updateTime, 1000);
    checkConnection();
    setInterval(checkConnection, 60000); // Check every 60 seconds (1 minute)
    focusPanel('left');
});

// Event Listeners
function setupEventListeners() {
    submitInput.addEventListener('keydown', (e) => handleKeydown(e, 'left'));
    statusInput.addEventListener('keydown', (e) => handleKeydown(e, 'right'));

    submitInput.addEventListener('focus', () => focusPanel('left'));
    statusInput.addEventListener('focus', () => focusPanel('right'));
}

function handleKeydown(e, panel) {
    const input = panel === 'left' ? submitInput : statusInput;

    if (e.key === 'Enter') {
        e.preventDefault();
        const command = input.value.trim();
        if (command) {
            processCommand(command, panel);
            addToHistory(command, panel);
            input.value = '';
        }
    } else if (e.key === 'Tab') {
        e.preventDefault();
        switchPanel();
    } else if (e.key === 'Escape') {
        e.preventDefault();
        input.value = '';
        historyIndex[panel] = -1;
    } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        navigateHistory('up', panel);
    } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        navigateHistory('down', panel);
    }
}

// Command Processing
async function processCommand(command, panel) {
    const parts = command.split(' ');
    const cmd = parts[0].toLowerCase();
    const args = parts.slice(1);

    appendOutput(`<span class="output-command">&gt; ${escapeHtml(command)}</span>`, panel);

    switch (cmd) {
        case 'help':
            showHelp(panel);
            break;
        case 'clear':
            clearOutput(panel);
            break;
        case 'submit':
            await submitJob(args.join(' '), panel);
            break;
        case 'status':
            await checkStatus(args[0], panel);
            break;
        case 'result':
            await getResult(args[0], panel);
            break;
        case 'health':
            await checkHealth(panel);
            break;
        case 'time':
            appendOutput(`Current time: ${new Date().toLocaleString()}`, panel, 'info');
            break;
        default:
            if (panel === 'left' && command.match(/^[A-Za-z0-9\s&|!()~=><]+$/)) {
                // Treat as formula submission (supports RPN operators: &&, ||, !, =>, etc.)
                await submitJob(command, panel);
            } else {
                appendOutput(`Unknown command: ${cmd}. Type 'help' for available commands.`, panel, 'error');
            }
    }
}

function showHelp(panel) {
    const leftHelp = [
        '',
        '═══════════════ JOB SUBMISSION COMMANDS ═══════════════',
        '',
        '  submit <formula>    Submit a SAT formula (RPN notation)',
        '                      Example: submit A B &&',
        '  <formula>           Directly type formula to submit',
        '                      Supports: &&, ||, !, =>, <=> variables',
        '  help                Show this help message',
        '  clear               Clear the terminal output',
        '  health              Check API server health',
        '',
        '═══════════════════════════════════════════════════════',
        ''
    ];

    const rightHelp = [
        '',
        '═══════════════ STATUS CHECK COMMANDS ═════════════════',
        '',
        '  status <run_id>     Check status of a job',
        '                      Example: status 42',
        '  result <run_id>     Get result of completed job',
        '                      Example: result 42',
        '  help                Show this help message',
        '  clear               Clear the terminal output',
        '  health              Check API server health',
        '',
        '═══════════════════════════════════════════════════════',
        ''
    ];

    const helpText = panel === 'left' ? leftHelp : rightHelp;
    helpText.forEach(line => appendOutput(line, panel, 'info'));
}

// API Calls
async function submitJob(formula, panel) {
    if (!formula) {
        appendOutput('Error: No formula provided', panel, 'error');
        return;
    }

    appendOutput(`Submitting formula: ${formula}`, panel, 'info');

    const output = panel === 'left' ? submitOutput : statusOutput;
    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'output-line output-muted';
    loadingDiv.innerHTML = '<span class="loading">Processing</span>';
    output.appendChild(loadingDiv);
    output.scrollTop = output.scrollHeight;

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 second timeout

        const response = await fetch(`${API_BASE_URL}/jobs/submit`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                formula: formula,
                notation: 'RPN',
                mode: 'RPN'
            }),
            signal: controller.signal
        });

        clearTimeout(timeoutId);
        loadingDiv.remove(); // Remove loading message

        if (!response.ok) {
            let errorMsg = `HTTP ${response.status}`;
            try {
                const error = await response.json();
                errorMsg = error.detail || errorMsg;
            } catch (e) {
                // Response is not JSON
            }
            throw new Error(errorMsg);
        }

        const data = await response.json();
        displayJobSubmission(data, panel);
    } catch (error) {
        loadingDiv.remove(); // Remove loading message on error too
        if (error.name === 'AbortError') {
            appendOutput('Error: Request timeout - server not responding', panel, 'error');
        } else {
            const errorMsg = error.message || String(error) || 'Unknown error';
            appendOutput(`Error: ${errorMsg}`, panel, 'error');
        }
    }
}

async function checkStatus(runId, panel) {
    if (!runId) {
        appendOutput('Error: No run_id provided', panel, 'error');
        appendOutput('Usage: status <run_id>', panel, 'muted');
        return;
    }

    appendOutput(`Checking status for run_id: ${runId}`, panel, 'info');

    try {
        const response = await fetch(`${API_BASE_URL}/jobs/status/${runId}`);

        if (!response.ok) {
            let errorMsg = `HTTP ${response.status}`;
            try {
                const error = await response.json();
                errorMsg = error.detail || errorMsg;
            } catch (e) {
                // Response is not JSON
            }
            throw new Error(errorMsg);
        }

        const data = await response.json();
        displayStatus(data, panel);
    } catch (error) {
        const errorMsg = error.message || String(error) || 'Unknown error';
        appendOutput(`Error: ${errorMsg}`, panel, 'error');

        if (errorMsg.includes('not found') || errorMsg.includes('404')) {
            appendOutput('', panel);
            appendOutput('💡 Tip: Submit a job first to get a run_id, then check its status.', panel, 'info');
            appendOutput('   Example: Submit "A B &&" then use "status <run_id>"', panel, 'muted');
        }
    }
}

async function getResult(runId, panel) {
    if (!runId) {
        appendOutput('Error: No run_id provided', panel, 'error');
        appendOutput('Usage: result <run_id>', panel, 'muted');
        return;
    }

    appendOutput(`Fetching result for run_id: ${runId}`, panel, 'info');

    try {
        const response = await fetch(`${API_BASE_URL}/jobs/result/${runId}`);

        if (!response.ok) {
            let errorMsg = `HTTP ${response.status}`;
            try {
                const error = await response.json();
                errorMsg = error.detail || errorMsg;
            } catch (e) {
                // Response is not JSON
            }
            throw new Error(errorMsg);
        }

        const data = await response.json();
        displayResult(data, panel);
    } catch (error) {
        const errorMsg = error.message || String(error) || 'Unknown error';
        appendOutput(`Error: ${errorMsg}`, panel, 'error');

        if (errorMsg.includes('not found') || errorMsg.includes('404')) {
            appendOutput('', panel);
            appendOutput('💡 Tip: Make sure the run_id exists and the job has completed.', panel, 'info');
            appendOutput('   Use "status <run_id>" to check if the job is done first.', panel, 'muted');
        }
    }
}

async function checkConnection() {
    try {
        const response = await fetch(`${API_BASE_URL}/health`, { method: 'GET' });
        if (response.ok) {
            connectionStatus.textContent = '● CONNECTED';
            connectionStatus.className = 'status-connected';
        } else {
            throw new Error('Not OK');
        }
    } catch (error) {
        connectionStatus.textContent = '● DISCONNECTED';
        connectionStatus.className = 'status-disconnected';
    }
}

function createCard(title, rows, panel, colorClass = '') {
    const output = panel === 'left' ? submitOutput : statusOutput;

    const card = document.createElement('div');
    card.className = 'job-card';

    if (colorClass) {
        card.classList.add(`output-${colorClass}`);
    }

    const header = document.createElement('div');
    header.className = 'job-card-header';
    header.textContent = title;

    card.appendChild(header);

    rows.forEach(([label, value]) => {
        const row = document.createElement('div');
        row.className = 'job-card-row';

        const labelEl = document.createElement('div');
        labelEl.className = 'job-card-label';
        labelEl.textContent = label;

        const valueEl = document.createElement('div');
        valueEl.className = 'job-card-value';
        valueEl.textContent = value;

        row.appendChild(labelEl);
        row.appendChild(valueEl);
        card.appendChild(row);
    });

    output.appendChild(card);
    output.scrollTop = output.scrollHeight;
}

// Display Functions
function displayJobSubmission(data, panel) {
    createCard(
        'JOB SUBMITTED',
        [
            ['Run ID:', data.run_id],
            ['Formula ID:', data.formula_id],
            ['Status:', data.status],
            ['Formula:', data.formula],
            ['Message:', data.msg]
        ],
        panel,
        'success'
    );

    if (data.status === 'QUEUED' || data.status === 'CREATED') {
        appendOutput(`➜ Use 'status ${data.run_id}' to check progress`, panel, 'info');
    } else if (data.status === 'COMPLETED') {
        appendOutput(`➜ Use 'result ${data.run_id}' to view the solution`, panel, 'info');
    }
}
function displayStatus(data, panel) {
    const statusColor = getStatusColor(data.status);

    createCard(
        'JOB STATUS',
        [
            ['Run ID:', data.run_id],
            ['Status:', data.status]
        ],
        panel,
        statusColor
    );

    if (data.status === 'COMPLETED') {
        appendOutput(`➜ Use 'result ${data.run_id}' to get the solution`, panel, 'info');
    } else if (data.status === 'PROCESSING') {
        appendOutput('➜ Job is currently being processed...', panel, 'warning');
    } else if (data.status === 'QUEUED') {
        appendOutput('➜ Job is queued and waiting for worker', panel, 'warning');
    }
}

function displayResult(data, panel) {
    const resultColor =
        data.result === 'SAT'
            ? 'success'
            : data.result === 'UNSAT'
                ? 'warning'
                : 'error';

    const rows = [
        ['Run ID:', data.run_id],
        ['Formula:', data.formula],
        ['Result:', data.result],
        ['Runtime:', (data.runtime * 1000).toFixed(3) + 'ms']
    ];

    createCard('SOLVER RESULT', rows, panel, resultColor);

    if (data.assignment && Object.keys(data.assignment).length > 0) {
        const assignmentRows = Object.entries(data.assignment).map(
            ([key, value]) => [key, value ? 'TRUE' : 'FALSE']
        );

        createCard('ASSIGNMENT', assignmentRows, panel, resultColor);
    }
}

async function checkHealth(panel) {
    try {
        const response = await fetch(`${API_BASE_URL}/health`);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();

        createCard(
            'HEALTH CHECK',
            [
                ['Status:', (data.status || 'unknown').toUpperCase()],
                ['Database:', data.database || 'unknown'],
                ['Redis:', data.redis || 'unknown']
            ],
            panel,
            'success'
        );

    } catch (error) {
        createCard(
            'HEALTH CHECK FAILED',
            [
                ['Error:', error.message]
            ],
            panel,
            'error'
        );
    }
}


function getStatusColor(status) {
    switch (status) {
        case 'COMPLETED': return 'success';
        case 'PROCESSING':
        case 'QUEUED': return 'warning';
        case 'FAILED':
        case 'TIMEOUT': return 'error';
        default: return 'info';
    }
}

// Output Management
function appendOutput(html, panel, className = '') {
    const output = panel === 'left' ? submitOutput : statusOutput;
    const div = document.createElement('div');
    div.className = `output-line ${className ? 'output-' + className : ''}`;
    div.innerHTML = html;
    output.appendChild(div);
    output.scrollTop = output.scrollHeight;
}

function clearOutput(panel) {
    const output = panel === 'left' ? submitOutput : statusOutput;
    output.innerHTML = '';
    appendOutput('Terminal cleared.', panel, 'muted');
}

// History Management
function addToHistory(command, panel) {
    commandHistory[panel].push(command);
    historyIndex[panel] = commandHistory[panel].length;
}

function navigateHistory(direction, panel) {
    const input = panel === 'left' ? submitInput : statusInput;
    const history = commandHistory[panel];

    if (direction === 'up' && historyIndex[panel] > 0) {
        historyIndex[panel]--;
        input.value = history[historyIndex[panel]];
    } else if (direction === 'down' && historyIndex[panel] < history.length - 1) {
        historyIndex[panel]++;
        input.value = history[historyIndex[panel]];
    } else if (direction === 'down' && historyIndex[panel] === history.length - 1) {
        historyIndex[panel] = history.length;
        input.value = '';
    }
}

// Panel Management
function focusPanel(panel) {
    currentPanel = panel;
    const leftPanel = document.querySelector('.left-panel');
    const rightPanel = document.querySelector('.right-panel');

    leftPanel.classList.toggle('focused', panel === 'left');
    rightPanel.classList.toggle('focused', panel === 'right');

    if (panel === 'left') {
        submitInput.focus();
    } else {
        statusInput.focus();
    }
}

function switchPanel() {
    focusPanel(currentPanel === 'left' ? 'right' : 'left');
}

// Utilities
function updateTime() {
    const now = new Date();
    currentTimeEl.textContent = now.toLocaleTimeString();
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function truncate(text, maxLength) {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength - 3) + '...';
}

// Box formatting helpers
function centerText(text, width) {
    const padding = Math.max(0, width - text.length);
    const leftPad = Math.floor(padding / 2);
    const rightPad = padding - leftPad;
    return ' '.repeat(leftPad) + text + ' '.repeat(rightPad);
}

function leftText(text, width) {
    const padding = Math.max(0, width - text.length);
    return text + ' '.repeat(padding);
}

function formatKeyValue(key, value, width, valueClass = 'value') {
    const keySpan = `<span class="output-key">${key}</span>`;
    const valueSpan = `<span class="output-${valueClass}">${value}</span>`;

    // Calculate spacing: total width - key length - value length - 1 space
    const spacing = Math.max(1, width - key.length - value.length);

    return keySpan + ' '.repeat(spacing) + valueSpan;
}
