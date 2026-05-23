import chess
import chess.engine

from chess_move_analyzer.engine import candidate_lines_from_multipv, effective_profile, normalize_multipv


def test_normalize_multipv_clamps_to_supported_range():
    assert normalize_multipv(None) == 3
    assert normalize_multipv(0) == 1
    assert normalize_multipv(9) == 5
    assert normalize_multipv("4") == 4
    assert normalize_multipv("bad") == 3


def test_effective_profile_preserves_profile_settings_and_overrides_multipv():
    profile = effective_profile("deep", multipv=2)
    assert profile.name == "deep"
    assert profile.seconds_per_position == 3.0
    assert profile.hash_mb == 1024
    assert profile.multipv == 2


def test_candidate_lines_from_multipv_sorts_and_preserves_each_pv():
    board = chess.Board()
    infos = [
        {
            "multipv": 2,
            "score": chess.engine.PovScore(chess.engine.Cp(12), chess.WHITE),
            "pv": [chess.Move.from_uci("d2d4"), chess.Move.from_uci("g8f6")],
            "depth": 13,
        },
        {
            "multipv": 1,
            "score": chess.engine.PovScore(chess.engine.Cp(30), chess.WHITE),
            "pv": [chess.Move.from_uci("e2e4"), chess.Move.from_uci("e7e5")],
            "depth": 14,
        },
    ]

    candidates = candidate_lines_from_multipv(infos, board)

    assert [candidate.rank for candidate in candidates] == [1, 2]
    assert candidates[0].move_uci == "e2e4"
    assert candidates[0].move_san == "e4"
    assert candidates[0].pv_san == ["e4", "e5"]
    assert candidates[1].move_uci == "d2d4"
    assert candidates[1].pv_uci == ["d2d4", "g8f6"]
    assert candidates[1].depth == 13
