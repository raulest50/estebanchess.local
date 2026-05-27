from __future__ import annotations

import random
from collections.abc import Iterable

import chess

from .accuracy_models import TrainingConfig, TrainingDifficulty, TrainingGame, TrainingScenario
from .pgn_utils import iter_basic_moves

MAX_POSITIONS_TO_SCORE = 80
MIN_PLY = 6
MIN_LEGAL_MOVES = 6


def extract_candidate_scenarios(games: Iterable[TrainingGame]) -> list[TrainingScenario]:
    scenarios: list[TrainingScenario] = []
    scenario_id = 1
    for game_index, game in enumerate(games):
        try:
            moves = iter_basic_moves(game.pgn)
        except ValueError:
            continue
        for move in moves:
            board = chess.Board(move.fen_before)
            if not _is_trainable_board(board, move.ply):
                continue
            scenarios.append(
                TrainingScenario(
                    scenario_id=scenario_id,
                    fen=move.fen_before,
                    source_label=game.source_label,
                    game_index=game_index,
                    ply=move.ply,
                    move_number=move.move_number,
                    color=move.color,
                    metadata={
                        "game": game.display_name,
                        "played_move": move.san,
                        "result": game.result or "",
                    },
                )
            )
            scenario_id += 1
    return scenarios


def select_scenarios(
    candidates: list[TrainingScenario],
    config: TrainingConfig,
) -> list[TrainingScenario]:
    if not candidates:
        return []

    rng = random.Random(config.random_seed)
    pool = list(candidates)
    rng.shuffle(pool)
    return pool[: config.scenario_count]


def difficulty_matches(gap: float, difficulty: TrainingDifficulty) -> bool:
    if difficulty == "easy":
        return gap >= 0.12
    if difficulty == "medium":
        return 0.07 <= gap < 0.12
    if difficulty == "hard":
        return 0.03 <= gap < 0.07
    return gap < 0.03


def _is_trainable_board(board: chess.Board, ply: int) -> bool:
    if ply < MIN_PLY:
        return False
    if not board.is_valid() or board.is_game_over(claim_draw=True):
        return False
    legal_moves = list(board.legal_moves)
    if len(legal_moves) < MIN_LEGAL_MOVES:
        return False
    if board.is_check():
        return False
    return True
