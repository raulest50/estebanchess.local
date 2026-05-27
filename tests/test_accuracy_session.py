import pytest
import chess

from chess_move_analyzer.accuracy_models import MoveFeedback, TrainingConfig, TrainingScenario
from chess_move_analyzer.accuracy_session import TrainingSession, TrainingSessionError, build_move_from_squares
from chess_move_analyzer.models import CandidateLine, EngineEvaluation


def test_training_session_rejects_illegal_move():
    session = TrainingSession(TrainingConfig(consecutive_moves=1), [_scenario()])

    with pytest.raises(TrainingSessionError):
        session.submit_move("e2e5", _FakeAnalyzer())


def test_training_session_records_feedback_and_completes_single_move_scenario():
    session = TrainingSession(TrainingConfig(consecutive_moves=1), [_scenario()])

    feedback = session.submit_move("e2e4", _FakeAnalyzer())

    assert feedback.user_move_san == "e4"
    assert session.feedbacks == [feedback]
    assert session.completed is True


def test_training_session_applies_engine_reply_between_consecutive_moves():
    session = TrainingSession(TrainingConfig(consecutive_moves=2), [_scenario(), _scenario(scenario_id=2)])

    first = session.submit_move("e2e4", _FakeAnalyzer())

    assert first.best_reply is not None
    assert session.completed is False
    assert session.awaiting_next is False
    assert session.step_index == 1
    assert session.board is not None
    assert session.board.piece_at(chess.E5) == chess.Piece(chess.PAWN, chess.BLACK)


def test_build_move_from_squares_promotes_pawns_to_queen_by_default():
    board = chess.Board("8/P7/8/8/8/8/8/k6K w - - 0 1")

    move = build_move_from_squares(board, chess.A7, chess.A8)

    assert move == chess.Move.from_uci("a7a8q")


def _scenario(scenario_id: int = 1) -> TrainingScenario:
    return TrainingScenario(
        scenario_id=scenario_id,
        fen=chess.Board().fen(),
        source_label="sample",
        game_index=0,
        ply=10,
        move_number=5,
        color="white",
    )


class _FakeAnalyzer:
    def feedback_for_move(self, board, move, scenario_id, scenario_index, step_index):
        reply = None
        if move == chess.Move.from_uci("e2e4"):
            reply = CandidateLine(
                rank=1,
                move_uci="e7e5",
                move_san="e5",
                evaluation=EngineEvaluation(cp_white=10, expected_white=0.52),
                pv_uci=["e7e5"],
                pv_san=["e5"],
            )
        board_after = board.copy(stack=False)
        user_move_san = board_after.san(move)
        board_after.push(move)
        return MoveFeedback(
            scenario_id=scenario_id,
            scenario_index=scenario_index,
            step_index=step_index,
            fen_before=board.fen(),
            fen_after_user=board_after.fen(),
            user_move_uci=move.uci(),
            user_move_san=user_move_san,
            eval_before=EngineEvaluation(cp_white=20, expected_white=0.55),
            eval_after=EngineEvaluation(cp_white=10, expected_white=0.52),
            expected_loss=0.03,
            move_score=85.0,
            classification="excellent",
            best_reply=reply,
        )

