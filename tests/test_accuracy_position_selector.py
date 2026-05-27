import chess

from chess_move_analyzer.accuracy_models import TrainingConfig, TrainingGame
from chess_move_analyzer.accuracy_position_selector import (
    difficulty_matches,
    extract_candidate_scenarios,
    select_scenarios,
)

PGN = """
[Event "Training sample"]
[White "A"]
[Black "B"]
[Result "*"]

1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7 *
"""


def test_extract_candidate_scenarios_uses_real_game_positions_after_opening():
    scenarios = extract_candidate_scenarios([_game()])

    assert scenarios
    assert all(chess.Board(item.fen).is_valid() for item in scenarios)
    assert min(item.ply for item in scenarios) >= 6
    assert scenarios[0].metadata["game"] == "A vs B"


def test_extract_candidate_scenarios_includes_white_and_black_to_move():
    scenarios = extract_candidate_scenarios([_game()])

    colors = {item.color for item in scenarios}
    board_turns = {chess.Board(item.fen).turn for item in scenarios}
    assert {"white", "black"}.issubset(colors)
    assert {chess.WHITE, chess.BLACK}.issubset(board_turns)


def test_difficulty_matches_expected_gap_ranges():
    assert difficulty_matches(0.13, "easy") is True
    assert difficulty_matches(0.08, "medium") is True
    assert difficulty_matches(0.04, "hard") is True
    assert difficulty_matches(0.02, "expert") is True
    assert difficulty_matches(0.02, "easy") is False


def test_select_scenarios_filters_by_difficulty_gap():
    candidates = extract_candidate_scenarios([_game()])
    selected = select_scenarios(
        candidates,
        TrainingConfig(difficulty="medium", scenario_count=2, random_seed=1),
    )

    assert len(selected) == 2
    assert all(item in candidates for item in selected)


def _game() -> TrainingGame:
    return TrainingGame(pgn=PGN, source_label="sample", white="A", black="B")
