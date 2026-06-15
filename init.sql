CREATE TABLE IF NOT EXISTS formulas (
    id SERIAL PRIMARY KEY,
    normalized_input TEXT NOT NULL,
    hash TEXT NOT NULL UNIQUE,
    notation TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS runs (
    id SERIAL PRIMARY KEY,
    formula_id INTEGER NOT NULL REFERENCES formulas(id),
    status TEXT NOT NULL DEFAULT 'CREATED',
    timeout_s FLOAT,
    mode TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS results (
    id SERIAL PRIMARY KEY,
    run_id INTEGER NOT NULL UNIQUE REFERENCES runs(id),
    result TEXT,
    assignment TEXT,
    stdout TEXT,
    stderr TEXT,
    error_type TEXT,
    error_message TEXT,
    runtime_s FLOAT
);

CREATE TABLE IF NOT EXISTS sync_sat_table (
    id SERIAL PRIMARY KEY,
    formula TEXT NOT NULL,
    formula_hash TEXT NOT NULL UNIQUE,
    result TEXT,
    return_code INTEGER,
    runtime FLOAT
);
