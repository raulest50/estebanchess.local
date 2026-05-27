from chess_move_analyzer.accuracy_models import MoveFeedback, TrainingConfig, TrainingSummary
from chess_move_analyzer.accuracy_storage import TrainingHistoryStorage
from chess_move_analyzer.models import CandidateLine, EngineEvaluation


def test_training_history_storage_roundtrip(tmp_path):
    storage_path = tmp_path / "accuracy.sqlite"
    feedback = _feedback()
    summary = TrainingSummary(accuracy=91.5, total_moves=1, average_loss=0.017, classifications={"excellent": 1})

    with TrainingHistoryStorage(storage_path) as storage:
        session_id = storage.create_session(TrainingConfig(difficulty="easy", scenario_count=5))
        storage.save_attempt(session_id, feedback)
        storage.complete_session(session_id, summary)
        sessions = storage.recent_sessions()
        attempts = storage.attempts_for_session(session_id)

    assert sessions[0].session_id == session_id
    assert sessions[0].config.difficulty == "easy"
    assert sessions[0].summary == summary
    assert attempts[0].user_move_uci == "e2e4"
    assert attempts[0].top_candidates[0].move_san == "e4"


def _feedback() -> MoveFeedback:
    return MoveFeedback(
        scenario_id=1,
        scenario_index=0,
        step_index=0,
        fen_before="start",
        fen_after_user="after",
        user_move_uci="e2e4",
        user_move_san="e4",
        eval_before=EngineEvaluation(cp_white=20, expected_white=0.55),
        eval_after=EngineEvaluation(cp_white=10, expected_white=0.53),
        expected_loss=0.02,
        move_score=90.0,
        classification="excellent",
        top_candidates=[
            CandidateLine(
                rank=1,
                move_uci="e2e4",
                move_san="e4",
                evaluation=EngineEvaluation(cp_white=20, expected_white=0.55),
            )
        ],
    )

