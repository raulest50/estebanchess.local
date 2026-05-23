from __future__ import annotations

from typing import Any

import chess
from pydantic import BaseModel, ConfigDict, Field


class EngineEvaluation(BaseModel):
    """Evaluation from White's perspective."""

    cp_white: int | None = None
    mate_white: int | None = None
    expected_white: float = Field(ge=0.0, le=1.0)
    wdl_white: tuple[int, int, int] | None = None

    def expected_for(self, color: chess.Color) -> float:
        if color == chess.WHITE:
            return self.expected_white
        return 1.0 - self.expected_white

    @property
    def label(self) -> str:
        if self.mate_white is not None:
            sign = "+" if self.mate_white > 0 else "-"
            return f"M{sign}{abs(self.mate_white)}"
        if self.cp_white is None:
            return "?"
        return f"{self.cp_white / 100:+.2f}"


class CandidateLine(BaseModel):
    rank: int = Field(ge=1)
    move_uci: str | None = None
    move_san: str | None = None
    evaluation: EngineEvaluation
    pv_uci: list[str] = Field(default_factory=list)
    pv_san: list[str] = Field(default_factory=list)
    depth: int | None = None


class PositionAnalysis(BaseModel):
    fen: str
    engine_name: str
    profile: str
    multipv: int
    depth: int | None = None
    nodes: int | None = None
    time_ms: int | None = None
    best_move_uci: str | None = None
    pv_uci: list[str] = Field(default_factory=list)
    evaluation: EngineEvaluation
    candidates: list[CandidateLine] = Field(default_factory=list)


class AnalysisProgress(BaseModel):
    phase: str
    message: str
    ply: int | None = None
    total_plies: int | None = None
    position_index: int | None = None
    total_positions: int | None = None
    move_san: str | None = None
    position_label: str | None = None
    cache_status: str | None = None
    depth: int | None = None
    nodes: int | None = None
    nps: int | None = None
    elapsed_ms: int | None = None
    eval_label: str | None = None
    best_move_uci: str | None = None
    pv_uci: list[str] = Field(default_factory=list)


class BasicMove(BaseModel):
    ply: int
    move_number: int
    color: str
    san: str
    uci: str
    fen_before: str
    fen_after: str
    comment: str = ""
    clock: str | None = None
    clock_seconds: int | None = None
    time_spent_seconds: int | None = None


class MoveAnalysis(BaseModel):
    ply: int
    move_number: int
    color: str
    san: str
    uci: str
    fen_before: str
    fen_after: str
    clock: str | None = None
    time_spent_seconds: int | None = None
    eval_before: EngineEvaluation
    eval_after: EngineEvaluation
    best_move_uci: str | None = None
    best_move_san: str | None = None
    pv_san: list[str] = Field(default_factory=list)
    pv_uci: list[str] = Field(default_factory=list)
    candidates: list[CandidateLine] = Field(default_factory=list)
    reply_move_uci: str | None = None
    reply_move_san: str | None = None
    reply_eval: EngineEvaluation | None = None
    reply_pv_uci: list[str] = Field(default_factory=list)
    reply_pv_san: list[str] = Field(default_factory=list)
    expected_loss: float
    classification: str


class GameRecord(BaseModel):
    pgn: str
    source_url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    white: str | None = None
    black: str | None = None
    white_elo: str | None = None
    black_elo: str | None = None
    result: str | None = None
    date: str | None = None
    time_control: str | None = None
    end_time: str | None = None
    game_id: str | None = None


class GameAnalysis(BaseModel):
    game: GameRecord
    moves: list[MoveAnalysis]
    final_fen: str
    engine_name: str
    profile: str
    cache_hits: int = 0
    cache_misses: int = 0
    warnings: list[str] = Field(default_factory=list)


class ChessComUrl(BaseModel):
    model_config = ConfigDict(frozen=True)

    original: str
    game_id: str
    kind: str


JsonDict = dict[str, Any]
