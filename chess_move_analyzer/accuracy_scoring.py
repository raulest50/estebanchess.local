from __future__ import annotations

from collections import Counter

from .analysis import classify_loss
from .accuracy_models import MoveFeedback, TrainingSummary

LOSS_FOR_ZERO_SCORE = 0.20


def move_score(expected_loss: float) -> float:
    score = 100.0 * (1.0 - max(0.0, expected_loss) / LOSS_FOR_ZERO_SCORE)
    return round(max(0.0, min(100.0, score)), 1)


def summarize_feedback(feedbacks: list[MoveFeedback]) -> TrainingSummary:
    if not feedbacks:
        return TrainingSummary()

    total_score = sum(item.move_score for item in feedbacks)
    total_loss = sum(item.expected_loss for item in feedbacks)
    classifications = Counter(item.classification for item in feedbacks)
    return TrainingSummary(
        accuracy=round(total_score / len(feedbacks), 1),
        total_moves=len(feedbacks),
        average_loss=round(total_loss / len(feedbacks), 4),
        classifications=dict(classifications),
    )


def classify_training_loss(expected_loss: float) -> str:
    return classify_loss(expected_loss)

