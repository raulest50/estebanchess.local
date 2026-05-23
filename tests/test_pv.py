import chess

from chess_move_analyzer.models import CandidateLine, EngineEvaluation, MoveAnalysis
from chess_move_analyzer.pv import pv_board_at


def test_move_analysis_accepts_and_serializes_pv_uci():
    move = MoveAnalysis(
        ply=1,
        move_number=1,
        color="white",
        san="e4",
        uci="e2e4",
        fen_before="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        fen_after="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
        eval_before=EngineEvaluation(cp_white=20, expected_white=0.53),
        eval_after=EngineEvaluation(cp_white=25, expected_white=0.54),
        pv_san=["e4", "e5"],
        pv_uci=["e2e4", "e7e5"],
        reply_move_uci="e7e5",
        reply_move_san="e5",
        reply_eval=EngineEvaluation(cp_white=10, expected_white=0.52),
        reply_pv_san=["e5", "Nf3"],
        reply_pv_uci=["e7e5", "g1f3"],
        expected_loss=0.0,
        classification="excellent",
    )

    restored = MoveAnalysis.model_validate_json(move.model_dump_json())

    assert restored.pv_uci == ["e2e4", "e7e5"]
    assert restored.reply_move_san == "e5"
    assert restored.reply_pv_uci == ["e7e5", "g1f3"]


def test_candidate_line_serializes_pv_and_evaluation():
    candidate = CandidateLine(
        rank=2,
        move_uci="d2d4",
        move_san="d4",
        evaluation=EngineEvaluation(cp_white=18, expected_white=0.53),
        pv_uci=["d2d4", "g8f6"],
        pv_san=["d4", "Nf6"],
        depth=12,
    )

    restored = CandidateLine.model_validate_json(candidate.model_dump_json())

    assert restored.rank == 2
    assert restored.move_san == "d4"
    assert restored.evaluation.label == "+0.18"
    assert restored.pv_uci == ["d2d4", "g8f6"]


def test_pv_board_at_applies_moves_until_index():
    board, last_move = pv_board_at(
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        ["e2e4", "e7e5", "g1f3"],
        1,
    )

    assert last_move == chess.Move.from_uci("e7e5")
    assert board.piece_at(chess.E4) == chess.Piece(chess.PAWN, chess.WHITE)
    assert board.piece_at(chess.E5) == chess.Piece(chess.PAWN, chess.BLACK)
