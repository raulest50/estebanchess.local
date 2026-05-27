from chess_move_analyzer import accuracy_pgn_index
from chess_move_analyzer.accuracy_pgn_index import (
    automatic_sample_game_count,
    games_from_indexed_pgn_file,
    load_or_build_pgn_index,
    sample_pgn_game_indices,
)

PGN_ONE = """
[Event "Game One"]
[White "A"]
[Black "B"]
[Result "*"]

1. e4 e5 *
"""

PGN_TWO = """
[Event "Game Two"]
[White "C"]
[Black "D"]
[Result "*"]

1. d4 d5 *
"""

PGN_THREE = """
[Event "Game Three"]
[White "E"]
[Black "F"]
[Result "*"]

1. c4 e5 *
"""


def test_automatic_sample_game_count_scales_from_training_shape():
    assert automatic_sample_game_count(5, 1) == 80
    assert automatic_sample_game_count(10, 3) == 360
    assert automatic_sample_game_count(30, 3) == 500


def test_pgn_index_is_cached_when_file_metadata_matches(tmp_path, monkeypatch):
    pgn_path = tmp_path / "sample.pgn"
    pgn_path.write_text(PGN_ONE + PGN_TWO, encoding="utf-8")
    index_dir = tmp_path / "indexes"

    first = load_or_build_pgn_index(pgn_path, index_dir=index_dir)
    monkeypatch.setattr(
        accuracy_pgn_index,
        "build_pgn_offsets",
        lambda _: (_ for _ in ()).throw(AssertionError("cache was not used")),
    )
    second = load_or_build_pgn_index(pgn_path, index_dir=index_dir)

    assert first.offsets == second.offsets
    assert len(second.offsets) == 2


def test_pgn_index_rebuilds_when_file_changes(tmp_path):
    pgn_path = tmp_path / "sample.pgn"
    index_dir = tmp_path / "indexes"
    pgn_path.write_text(PGN_ONE + PGN_TWO, encoding="utf-8")

    first = load_or_build_pgn_index(pgn_path, index_dir=index_dir)
    pgn_path.write_text(PGN_ONE + PGN_TWO + PGN_THREE, encoding="utf-8")
    second = load_or_build_pgn_index(pgn_path, index_dir=index_dir)

    assert len(first.offsets) == 2
    assert len(second.offsets) == 3


def test_sample_pgn_game_indices_is_reproducible():
    first = sample_pgn_game_indices(100, 10, random_seed=42)
    second = sample_pgn_game_indices(100, 10, random_seed=42)

    assert first == second
    assert len(first) == 10
    assert len(set(first)) == 10


def test_games_from_indexed_pgn_file_loads_only_sampled_games(tmp_path):
    pgn_path = tmp_path / "sample.pgn"
    pgn_path.write_text(PGN_ONE + PGN_TWO + PGN_THREE, encoding="utf-8")
    index_dir = tmp_path / "indexes"
    expected_indices = sample_pgn_game_indices(3, 2, random_seed=7)

    games = games_from_indexed_pgn_file(
        pgn_path,
        "sample",
        max_games=2,
        random_seed=7,
        index_dir=index_dir,
    )

    expected_whites = [["A", "C", "E"][index] for index in expected_indices]
    assert [game.white for game in games] == expected_whites
