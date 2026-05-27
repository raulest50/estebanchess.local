from chess_move_analyzer.accuracy_models import MoveFeedback
from chess_move_analyzer.accuracy_scoring import classify_training_loss, move_score, summarize_feedback
from chess_move_analyzer.models import EngineEvaluation


def test_move_score_uses_expected_loss_scale():
    assert move_score(0.0) == 100.0
    assert move_score(0.10) == 50.0
    assert move_score(0.20) == 0.0
    assert move_score(0.50) == 0.0


def test_summarize_feedback_averages_accuracy_and_loss():
    summary = summarize_feedback(
        [
            _feedback(expected_loss=0.0, move_score_value=100.0, classification="excellent"),
            _feedback(expected_loss=0.1, move_score_value=50.0, classification="mistake"),
        ]
    )

    assert summary.accuracy == 75.0
    assert summary.total_moves == 2
    assert summary.average_loss == 0.05
    assert summary.classifications == {"excellent": 1, "mistake": 1}


def test_classify_training_loss_reuses_analysis_thresholds():
    assert classify_training_loss(0.08) == "inaccuracy"


def _feedback(expected_loss: float, move_score_value: float, classification: str) -> MoveFeedback:
    return MoveFeedback(
        scenario_id=1,
        scenario_index=0,
        step_index=0,
        fen_before="start",
        fen_after_user="after",
        user_move_uci="e2e4",
        user_move_san="e4",
        eval_before=EngineEvaluation(cp_white=20, expected_white=0.55),
        eval_after=EngineEvaluation(cp_white=10, expected_white=0.45),
        expected_loss=expected_loss,
        move_score=move_score_value,
        classification=classification,
    )

