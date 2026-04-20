from __future__ import annotations

import json
from typing import Any

import requests
from backend.app.schemas.sudoku_schema import SudokuGrid


NYT_SUDOKU_URL = "https://www.nytimes.com/puzzles/sudoku/hard"
GAME_DATA_MARKER = "window.gameData = "
REQUEST_TIMEOUT_SECONDS = 20
REQUEST_HEADERS = {
	"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
	"(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}


def fetch_html(url: str = NYT_SUDOKU_URL) -> str:
	response = requests.get(
		url,
		headers=REQUEST_HEADERS,
		timeout=REQUEST_TIMEOUT_SECONDS,
	)
	response.raise_for_status()
	return response.text


def extract_game_data(html: str) -> dict[str, Any]:
	marker_index = html.find(GAME_DATA_MARKER)
	if marker_index == -1:
		raise ValueError("Could not find the NYT gameData payload in the page HTML.")

	json_start = marker_index + len(GAME_DATA_MARKER)
	decoder = json.JSONDecoder()
	payload, _ = decoder.raw_decode(html[json_start:])

	if not isinstance(payload, dict):
		raise ValueError("Unexpected NYT gameData payload format.")

	return payload


def get_difficulty_payload(game_data: dict[str, Any], difficulty: str) -> dict[str, Any]:
	difficulty_key = difficulty.strip().lower()
	puzzle_data = game_data.get(difficulty_key)

	if not isinstance(puzzle_data, dict):
		available = ", ".join(sorted(key for key, value in game_data.items() if isinstance(value, dict)))
		raise ValueError(
			f"Difficulty '{difficulty}' is not available in the NYT puzzle data. "
			f"Available options: {available}"
		)

	return puzzle_data


def flat_puzzle_to_grid(puzzle: list[Any]) -> list[list[int]]:
	if len(puzzle) != 81:
		raise ValueError(f"Expected 81 puzzle cells, got {len(puzzle)}.")

	flat_row = [int(cell) for cell in puzzle]
	return [flat_row[index : index + 9] for index in range(0, 81, 9)]


def parse_nyt_sudoku(url: str = NYT_SUDOKU_URL) -> SudokuGrid:
	"""Parse the NYT Sudoku puzzle from the given URL.
	
	The difficulty is extracted from the URL (e.g., /hard, /medium, /easy).
	The page HTML contains all difficulties in a single response, so only the URL is needed.
	url: The NYT Sudoku URL (e.g., https://www.nytimes.com/puzzles/sudoku/hard)
	SudokuGrid with the puzzle for the requested difficulty.
	"""
	# Extract difficulty from URL (e.g., "https://...sudoku/hard" -> "hard")
	difficulty = url.rstrip("/").split("/")[-1]
	
	html = fetch_html(url)
	game_data = extract_game_data(html)
	difficulty_payload = get_difficulty_payload(game_data, difficulty)

	puzzle_data = difficulty_payload.get("puzzle_data")
	if not isinstance(puzzle_data, dict):
		raise ValueError("Missing puzzle_data in NYT gameData payload.")

	puzzle = puzzle_data.get("puzzle")
	if not isinstance(puzzle, list):
		raise ValueError("Missing puzzle array in NYT puzzle_data payload.")

	return SudokuGrid(grid=flat_puzzle_to_grid(puzzle))