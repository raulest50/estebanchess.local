from __future__ import annotations

import chess

from .accuracy_models import MoveFeedback
from .accuracy_scoring import classify_training_loss, move_score
from .engine import AnalysisProfile, StockfishEngine
from .models import CandidateLine, PositionAnalysis
from .storage import AnalysisStorage

TRAINING_PROFILE = AnalysisProfile("training", seconds_per_position=0.25, multipv=3, hash_mb=256)
TRAINING_REVIEW_PROFILE = AnalysisProfile("training-review", seconds_per_position=0.75, multipv=5, hash_mb=512)
WORST_MOVE_PROFILE = AnalysisProfile("training-worst", seconds_per_position=0.06, multipv=1, hash_mb=128)
WORST_MOVE_LIMIT = 10
REVIEW_SCORE_THRESHOLD = 95.0
MAX_FEEDBACK_CANDIDATES = 5


class AccuracyEngine:
    def __init__(self, engine: StockfishEngine, storage: AnalysisStorage) -> None:
        self.engine = engine
        self.storage = storage

    def analyze_position(self, board: chess.Board, multipv: int = 3) -> PositionAnalysis:
        profile = _profile_with_multipv(TRAINING_PROFILE, multipv)
        return self._cached_analysis(board, profile)

    def difficulty_gap(self, board: chess.Board) -> float | None:
        analysis = self.analyze_position(board, multipv=2)
        if len(analysis.candidates) < 2:
            return None
        mover = board.turn
        first, second = analysis.candidates[:2]
        return max(0.0, first.evaluation.expected_for(mover) - second.evaluation.expected_for(mover))

    def feedback_for_move(
        self,
        board: chess.Board,
        move: chess.Move,
        scenario_id: int,
        scenario_index: int,
        step_index: int,
    ) -> MoveFeedback:
        if move not in board.legal_moves:
            raise ValueError(f"Illegal move {move.uci()} for {board.fen()}")

        mover = board.turn
        before = self.analyze_position(board, multipv=3)
        user_move_san = board.san(move)
        board_after_user = board.copy(stack=False)
        board_after_user.push(move)
        after = self.analyze_position(board_after_user, multipv=2)

        loss = _expected_loss(mover, before, after)
        score = move_score(loss)
        if _needs_deeper_review(move, before, score):
            before = self._cached_analysis(board, TRAINING_REVIEW_PROFILE)
            after = self._cached_analysis(board_after_user, TRAINING_REVIEW_PROFILE)
            loss = _expected_loss(mover, before, after)
            score = move_score(loss)
        reply = after.candidates[0] if after.candidates else None
        worst = self.worst_found(board, before)

        return MoveFeedback(
            scenario_id=scenario_id,
            scenario_index=scenario_index,
            step_index=step_index,
            fen_before=board.fen(),
            fen_after_user=board_after_user.fen(),
            user_move_uci=move.uci(),
            user_move_san=user_move_san,
            eval_before=before.evaluation,
            eval_after=after.evaluation,
            expected_loss=round(loss, 4),
            move_score=score,
            classification=classify_training_loss(loss),
            top_candidates=before.candidates[:MAX_FEEDBACK_CANDIDATES],
            best_reply=reply,
            worst_found=worst,
        )

    def worst_found(self, board: chess.Board, baseline: PositionAnalysis | None = None) -> CandidateLine | None:
        baseline = baseline or self.analyze_position(board, multipv=2)
        mover = board.turn
        best_moves = {candidate.move_uci for candidate in baseline.candidates[:2] if candidate.move_uci}
        legal_moves = [move for move in sorted(board.legal_moves, key=lambda item: item.uci()) if move.uci() not in best_moves]
        if not legal_moves:
            return None

        worst_candidate: CandidateLine | None = None
        worst_expected = 2.0
        for move in legal_moves[:WORST_MOVE_LIMIT]:
            local_board = board.copy(stack=False)
            san = local_board.san(move)
            local_board.push(move)
            analysis = self._cached_analysis(local_board, WORST_MOVE_PROFILE)
            expected = analysis.evaluation.expected_for(mover)
            if expected < worst_expected:
                worst_expected = expected
                worst_candidate = CandidateLine(
                    rank=1,
                    move_uci=move.uci(),
                    move_san=san,
                    evaluation=analysis.evaluation,
                    pv_uci=[move.uci()] + analysis.pv_uci,
                    pv_san=[san] + _pv_to_san(local_board, analysis.pv_uci),
                    depth=analysis.depth,
                )
        return worst_candidate

    def _cached_analysis(self, board: chess.Board, profile: AnalysisProfile) -> PositionAnalysis:
        cached = self.storage.get_position(board.fen(), self.engine.engine_name, profile.name, profile.multipv)
        if cached is not None:
            return cached
        analysis = self.engine.analyze_position(board, profile)
        self.storage.save_position(analysis)
        return analysis


def _pv_to_san(board: chess.Board, pv_uci: list[str]) -> list[str]:
    result: list[str] = []
    local_board = board.copy(stack=False)
    for uci in pv_uci:
        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            break
        if move not in local_board.legal_moves:
            break
        result.append(local_board.san(move))
        local_board.push(move)
    return result


def _profile_with_multipv(profile: AnalysisProfile, multipv: int) -> AnalysisProfile:
    return AnalysisProfile(
        profile.name,
        seconds_per_position=profile.seconds_per_position,
        multipv=multipv,
        hash_mb=profile.hash_mb,
    )


def _expected_loss(mover: chess.Color, before: PositionAnalysis, after: PositionAnalysis) -> float:
    return max(0.0, before.evaluation.expected_for(mover) - after.evaluation.expected_for(mover))


def _needs_deeper_review(move: chess.Move, before: PositionAnalysis, score: float) -> bool:
    if score < REVIEW_SCORE_THRESHOLD:
        return False
    return move.uci() not in {candidate.move_uci for candidate in before.candidates}
