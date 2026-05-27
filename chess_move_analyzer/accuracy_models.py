from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .models import CandidateLine, EngineEvaluation

TrainingSource = Literal["chesscom", "lichess_pgn"]
TrainingDifficulty = Literal["easy", "medium", "hard", "expert"]


SOURCE_LABELS: dict[TrainingSource, str] = {
    "chesscom": "Chess.com personal games",
    "lichess_pgn": "Lichess public PGN",
}

DIFFICULTY_LABELS: dict[TrainingDifficulty, str] = {
    "easy": "Easy",
    "medium": "Medium",
    "hard": "Hard",
    "expert": "Expert",
}


class TrainingConfig(BaseModel):
    source: TrainingSource = "lichess_pgn"
    difficulty: TrainingDifficulty = "medium"
    scenario_count: int = Field(default=10, ge=1, le=30)
    consecutive_moves: int = Field(default=1, ge=1, le=3)
    chesscom_username: str | None = None
    lichess_pgn: str | None = None
    lichess_pgn_path: str | None = None
    recent_months: int = Field(default=3, ge=1, le=12)
    max_games: int = Field(default=80, ge=1, le=500)
    random_seed: int | None = None


class TrainingGame(BaseModel):
    pgn: str
    source_label: str
    headers: dict[str, str] = Field(default_factory=dict)
    white: str | None = None
    black: str | None = None
    date: str | None = None
    result: str | None = None
    game_id: str | None = None

    @property
    def display_name(self) -> str:
        players = " vs ".join(part for part in [self.white, self.black] if part)
        if players and self.date:
            return f"{players} ({self.date})"
        return players or self.source_label


class TrainingScenario(BaseModel):
    scenario_id: int
    fen: str
    source_label: str
    game_index: int
    ply: int
    move_number: int
    color: str
    difficulty_gap: float | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class MoveFeedback(BaseModel):
    scenario_id: int
    scenario_index: int
    step_index: int
    fen_before: str
    fen_after_user: str
    user_move_uci: str
    user_move_san: str
    eval_before: EngineEvaluation
    eval_after: EngineEvaluation
    expected_loss: float
    move_score: float
    classification: str
    top_candidates: list[CandidateLine] = Field(default_factory=list)
    best_reply: CandidateLine | None = None
    worst_found: CandidateLine | None = None


class TrainingSummary(BaseModel):
    accuracy: float = 0.0
    total_moves: int = 0
    average_loss: float = 0.0
    classifications: dict[str, int] = Field(default_factory=dict)


class StoredTrainingSession(BaseModel):
    session_id: int
    started_at: str
    completed_at: str | None = None
    config: TrainingConfig
    summary: TrainingSummary | None = None
    accuracy: float | None = None
