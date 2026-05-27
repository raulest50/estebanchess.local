from __future__ import annotations

from dataclasses import dataclass, field

import chess

from .accuracy_engine import AccuracyEngine
from .accuracy_models import MoveFeedback, TrainingConfig, TrainingGame, TrainingScenario, TrainingSummary
from .accuracy_position_selector import extract_candidate_scenarios, select_scenarios
from .accuracy_scoring import summarize_feedback
from .accuracy_storage import TrainingHistoryStorage


class TrainingSessionError(RuntimeError):
    pass


@dataclass
class TrainingSession:
    config: TrainingConfig
    scenarios: list[TrainingScenario]
    session_id: int | None = None
    scenario_index: int = 0
    step_index: int = 0
    feedbacks: list[MoveFeedback] = field(default_factory=list)
    board: chess.Board | None = None
    awaiting_next: bool = False
    completed: bool = False

    def __post_init__(self) -> None:
        if not self.scenarios:
            raise TrainingSessionError("No training scenarios were available.")
        self.board = chess.Board(self.scenarios[0].fen)

    @property
    def current_scenario(self) -> TrainingScenario:
        return self.scenarios[self.scenario_index]

    @property
    def progress_label(self) -> str:
        return f"Scenario {self.scenario_index + 1}/{len(self.scenarios)} | Move {self.step_index + 1}/{self.config.consecutive_moves}"

    def submit_move(self, move_uci: str, analyzer: AccuracyEngine) -> MoveFeedback:
        if self.completed:
            raise TrainingSessionError("The training session is already complete.")
        if self.awaiting_next:
            raise TrainingSessionError("Advance to the next scenario before submitting another move.")
        if self.board is None:
            raise TrainingSessionError("The training board is not initialized.")

        try:
            move = chess.Move.from_uci(move_uci)
        except ValueError as exc:
            raise TrainingSessionError(f"{move_uci} is not a valid UCI move.") from exc
        if move not in self.board.legal_moves:
            raise TrainingSessionError(f"{move_uci} is not legal in the current position.")

        feedback = analyzer.feedback_for_move(
            self.board.copy(stack=False),
            move,
            scenario_id=self.current_scenario.scenario_id,
            scenario_index=self.scenario_index,
            step_index=self.step_index,
        )
        self.feedbacks.append(feedback)
        self.board.push(move)
        self._continue_after_user_move(feedback)
        return feedback

    def advance_to_next_scenario(self) -> None:
        if self.completed:
            return
        if self.scenario_index + 1 >= len(self.scenarios):
            self.completed = True
            self.awaiting_next = False
            return
        self.scenario_index += 1
        self.step_index = 0
        self.awaiting_next = False
        self.board = chess.Board(self.current_scenario.fen)

    def summary(self) -> TrainingSummary:
        return summarize_feedback(self.feedbacks)

    def _continue_after_user_move(self, feedback: MoveFeedback) -> None:
        if self.board is None:
            return
        sequence_finished = self.step_index + 1 >= self.config.consecutive_moves
        if sequence_finished or self.board.is_game_over(claim_draw=True) or feedback.best_reply is None:
            self.awaiting_next = True
            if self.scenario_index + 1 >= len(self.scenarios):
                self.completed = True
            return

        reply_uci = feedback.best_reply.move_uci
        if not reply_uci:
            self.awaiting_next = True
            return
        reply_move = chess.Move.from_uci(reply_uci)
        if reply_move not in self.board.legal_moves:
            self.awaiting_next = True
            return
        self.board.push(reply_move)
        self.step_index += 1


def build_move_from_squares(board: chess.Board, from_square: int, to_square: int) -> chess.Move:
    piece = board.piece_at(from_square)
    promotion = None
    if piece and piece.piece_type == chess.PAWN and chess.square_rank(to_square) in {0, 7}:
        promotion = chess.QUEEN
    return chess.Move(from_square, to_square, promotion=promotion)


def create_training_session(
    config: TrainingConfig,
    games: list[TrainingGame],
    analyzer: AccuracyEngine,
    history: TrainingHistoryStorage | None = None,
) -> TrainingSession:
    candidates = extract_candidate_scenarios(games)
    scenarios = select_scenarios(candidates, config)
    if len(scenarios) < config.scenario_count:
        raise TrainingSessionError(
            f"Only {len(scenarios)} suitable scenarios were found. Provide more games or choose fewer scenarios."
        )
    session_id = history.create_session(config) if history else None
    return TrainingSession(config=config, scenarios=scenarios, session_id=session_id)
