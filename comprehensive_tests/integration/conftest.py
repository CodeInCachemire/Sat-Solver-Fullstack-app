"""
Session-scoped PostgreSQL fixtures for integration tests.
Requires postgres-test container from docker-compose.test.yml.

Start with:
    docker compose -f docker-compose.test.yml up -d

Run only integration tests with:
    pytest backend/tests/integration/ -m integration

Skip integration tests with:
    pytest -m "not integration"
"""

import time
import pytest
import psycopg2
from psycopg2.extensions import connection


TEST_DB_CONFIG = {
    "host": "localhost",
    "port": 5433,
    "dbname": "sat_solver_test",
    "user": "sat_user",
    "password": "test_password",
    "connect_timeout": 5,
}

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS formulas (
    id SERIAL PRIMARY KEY,
    normalized_input TEXT NOT NULL,
    hash VARCHAR(64) UNIQUE NOT NULL,
    notation VARCHAR(10) NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id SERIAL PRIMARY KEY,
    formula_id INTEGER NOT NULL REFERENCES formulas(id),
    status VARCHAR(20) NOT NULL DEFAULT 'CREATED',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    timeout_s INTEGER NOT NULL DEFAULT 5,
    mode VARCHAR(20) NOT NULL DEFAULT 'RPN'
);

CREATE TABLE IF NOT EXISTS results (
    id SERIAL PRIMARY KEY,
    run_id INTEGER UNIQUE NOT NULL REFERENCES runs(id),
    result VARCHAR(30),
    assignment TEXT,
    stdout TEXT,
    stderr TEXT,
    error_type VARCHAR(50),
    error_message TEXT,
    runtime_s FLOAT
);
"""


@pytest.fixture(scope="session")
def pg_connection():
    """
    Session-scoped fixture that provides a real PostgreSQL connection.

    Retries up to 10 times with 1s sleep between attempts to allow
    the postgres-test container time to finish starting up.

    Skips all tests in the session if the database is unreachable.
    Creates all required tables on first connect and drops test data
    after the session completes.
    """
    conn = None
    last_error = None

    for attempt in range(1, 11):
        try:
            conn = psycopg2.connect(**TEST_DB_CONFIG)
            break
        except psycopg2.OperationalError as exc:
            last_error = exc
            if attempt < 10:
                time.sleep(1)

    if conn is None:
        pytest.skip(
            f"PostgreSQL not available on localhost:5433 after 10 attempts. "
            f"Start with: docker compose -f docker-compose.test.yml up -d  "
            f"(last error: {last_error})"
        )

    # Create tables for the test session
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(CREATE_TABLES_SQL)
    except Exception as exc:
        conn.close()
        pytest.skip(f"Failed to create test tables: {exc}")

    yield conn

    # Tear down: remove all test data, leave the schema intact
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM results")
                cur.execute("DELETE FROM runs")
                cur.execute("DELETE FROM formulas")
    finally:
        conn.close()


@pytest.fixture(scope="function")
def db_service(pg_connection):
    """
    Function-scoped fixture that creates a DatabaseService backed by the
    session-scoped pg_connection.

    The connection is reused across calls (no pool); release_conn is a no-op
    so the session connection is never closed mid-test.

    After each test all rows are deleted from results, runs, and formulas to
    guarantee full isolation between tests.
    """
    from backend.app.services.database_service import DatabaseService

    def get_conn():
        return pg_connection

    def release_conn(conn):
        # Do not close — we reuse the session-scoped connection
        pass

    yield DatabaseService(get_conn, release_conn)

    # Cleanup after each test
    with pg_connection:
        with pg_connection.cursor() as cur:
            cur.execute("DELETE FROM results")
            cur.execute("DELETE FROM runs")
            cur.execute("DELETE FROM formulas")
