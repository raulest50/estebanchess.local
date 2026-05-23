import chess

from chess_move_analyzer.analysis import _candidates_to_san, analyze_game, classify_loss
from chess_move_analyzer.models import CandidateLine, EngineEvaluation, GameRecord, PositionAnalysis


def test_classify_loss_thresholds():
    assert classify_loss(0.00) == "excellent"
    assert classify_loss(0.05) == "good"
    assert classify_loss(0.08) == "inaccuracy"
    assert classify_loss(0.15) == "mistake"
    assert classify_loss(0.21) == "blunder"


def test_candidates_to_san_sorts_and_normalizes_each_line():
    board = chess.Board()
    candidates = [
        CandidateLine(
            rank=2,
            move_uci="d2d4",
            evaluation=EngineEvaluation(cp_white=12, expected_white=0.52),
            pv_uci=["d2d4", "g8f6"],
        ),
        CandidateLine(
            rank=1,
            move_uci="e2e4",
            evaluation=EngineEvaluation(cp_white=30, expected_white=0.55),
            pv_uci=["e2e4", "e7e5"],
        ),
    ]

    normalized = _candidates_to_san(board, candidates)

    assert [candidate.rank for candidate in normalized] == [1, 2]
    assert normalized[0].move_san == "e4"
    assert normalized[0].pv_san == ["e4", "e5"]
    assert normalized[1].move_san == "d4"
    assert normalized[1].pv_san == ["d4", "Nf6"]


def test_analyze_game_copies_candidates_to_move_analysis_and_keeps_aliases():
    result = analyze_game(
        GameRecord(pgn="1. e4 *"),
        _FakeEngine(),
        _FakeStorage(),
        profile_name="fast",
        multipv=2,
    )

    move = result.moves[0]

    assert len(move.candidates) == 2
    assert move.best_move_uci == "e2e4"
    assert move.best_move_san == "e4"
    assert move.pv_uci == ["e2e4", "e7e5"]
    assert move.pv_san == ["e4", "e5"]
    assert move.candidates[1].move_san == "d4"
    assert move.reply_move_uci == "e7e5"
    assert move.reply_move_san == "e5"
    assert move.reply_pv_uci == ["e7e5", "g1f3"]
    assert move.reply_pv_san == ["e5", "Nf3"]


def test_analyze_game_uses_after_best_move_as_reply_fallback():
    result = analyze_game(
        GameRecord(pgn="1. e4 *"),
        _FallbackReplyEngine(),
        _FakeStorage(),
        profile_name="fast",
        multipv=2,
    )

    move = result.moves[0]

    assert move.reply_move_uci == "e7e5"
    assert move.reply_move_san == "e5"
    assert move.reply_pv_uci == ["e7e5", "g1f3"]
    assert move.reply_pv_san == ["e5", "Nf3"]
    assert move.reply_eval is not None


class _FakeEngine:
    engine_name = "FakeFish"

    def analyze_position(self, board, profile, progress=None, progress_context=None):
        start_fen = chess.Board().fen()
        after_e4 = chess.Board()
        after_e4.push_san("e4")
        candidates = []
        best_move = None
        pv = []
        if board.fen() == start_fen:
            candidates = [
                CandidateLine(
                    rank=1,
                    move_uci="e2e4",
                    evaluation=EngineEvaluation(cp_white=30, expected_white=0.55),
                    pv_uci=["e2e4", "e7e5"],
                ),
                CandidateLine(
                    rank=2,
                    move_uci="d2d4",
                    evaluation=EngineEvaluation(cp_white=12, expected_white=0.52),
                    pv_uci=["d2d4", "g8f6"],
                ),
            ]
            best_move = "e2e4"
            pv = ["e2e4", "e7e5"]
        elif board.fen() == after_e4.fen():
            candidates = [
                CandidateLine(
                    rank=1,
                    move_uci="e7e5",
                    evaluation=EngineEvaluation(cp_white=18, expected_white=0.53),
                    pv_uci=["e7e5", "g1f3"],
                )
            ]
            best_move = "e7e5"
            pv = ["e7e5", "g1f3"]
        return PositionAnalysis(
            fen=board.fen(),
            engine_name=self.engine_name,
            profile=profile.name,
            multipv=profile.multipv,
            best_move_uci=best_move,
            pv_uci=pv,
            evaluation=EngineEvaluation(cp_white=20, expected_white=0.53),
            candidates=candidates,
        )


class _FallbackReplyEngine(_FakeEngine):
    def analyze_position(self, board, profile, progress=None, progress_context=None):
        analysis = super().analyze_position(board, profile, progress=progress, progress_context=progress_context)
        after_e4 = chess.Board()
        after_e4.push_san("e4")
        if board.fen() == after_e4.fen():
            return analysis.model_copy(
                update={
                    "candidates": [],
                    "best_move_uci": "e7e5",
                    "pv_uci": ["e7e5", "g1f3"],
                    "evaluation": EngineEvaluation(cp_white=18, expected_white=0.53),
                }
            )
        return analysis


class _FakeStorage:
    def get_position(self, fen, engine_name, profile, multipv):
        return None

    def save_position(self, analysis):
        return None

    def save_game(self, record):
        return None
