from __future__ import annotations

from collections.abc import Callable

import chess

from .engine import AnalysisProfile, StockfishEngine, effective_profile
from .models import AnalysisProgress, CandidateLine, EngineEvaluation, GameAnalysis, GameRecord, MoveAnalysis, PositionAnalysis
from .pgn_utils import final_fen, iter_basic_moves
from .storage import AnalysisStorage


def classify_loss(expected_loss: float) -> str:
    if expected_loss <= 0.03:
        return "excellent"
    if expected_loss <= 0.06:
        return "good"
    if expected_loss <= 0.10:
        return "inaccuracy"
    if expected_loss <= 0.20:
        return "mistake"
    return "blunder"


def analyze_game(
    record: GameRecord,
    engine: StockfishEngine,
    storage: AnalysisStorage,
    profile_name: str = "balanced",
    multipv: int | None = None,
    progress: Callable[[AnalysisProgress], None] | None = None,
) -> GameAnalysis:
    profile = effective_profile(profile_name, multipv)
    basic_moves = iter_basic_moves(record.pgn)
    analyses: list[MoveAnalysis] = []
    cache_hits = 0
    cache_misses = 0
    total_positions = len(basic_moves) * 2
    position_index = 0
    _emit(
        progress,
        phase="setup",
        message=(
            f"Parsed {len(basic_moves)} plies. Starting {engine.engine_name} "
            f"with {profile.name} profile, Top N {profile.multipv}."
        ),
        total_plies=len(basic_moves),
        total_positions=total_positions,
    )

    for basic in basic_moves:
        board_before = chess.Board(basic.fen_before)
        mover = board_before.turn
        position_index += 1
        before, before_hit = _position_analysis(
            board_before,
            engine,
            storage,
            profile,
            progress,
            {
                "ply": basic.ply,
                "total_plies": len(basic_moves),
                "position_index": position_index,
                "total_positions": total_positions,
                "move_san": basic.san,
                "position_label": f"Before {basic.move_number}{'.' if basic.color == 'white' else '...'} {basic.san}",
            },
        )
        board_after = chess.Board(basic.fen_after)
        position_index += 1
        after, after_hit = _position_analysis(
            board_after,
            engine,
            storage,
            profile,
            progress,
            {
                "ply": basic.ply,
                "total_plies": len(basic_moves),
                "position_index": position_index,
                "total_positions": total_positions,
                "move_san": basic.san,
                "position_label": f"After {basic.move_number}{'.' if basic.color == 'white' else '...'} {basic.san}",
            },
        )
        cache_hits += int(before_hit) + int(after_hit)
        cache_misses += int(not before_hit) + int(not after_hit)

        before_expected = before.evaluation.expected_for(mover)
        after_expected = after.evaluation.expected_for(mover)
        loss = max(0.0, before_expected - after_expected)
        candidate_board = chess.Board(basic.fen_before)
        candidates = _candidates_to_san(candidate_board, before.candidates)
        primary_candidate = candidates[0] if candidates else None
        best_move_uci = primary_candidate.move_uci if primary_candidate else before.best_move_uci
        best_move_san = (
            primary_candidate.move_san
            if primary_candidate and primary_candidate.move_san
            else _uci_to_san(chess.Board(basic.fen_before), before.best_move_uci)
        )
        pv_uci = primary_candidate.pv_uci if primary_candidate else before.pv_uci
        pv_san = primary_candidate.pv_san if primary_candidate else _pv_to_san(chess.Board(basic.fen_before), before.pv_uci)
        reply_move_uci, reply_move_san, reply_eval, reply_pv_uci, reply_pv_san = _best_reply_from_after(
            chess.Board(basic.fen_after),
            after,
        )

        analyses.append(
            MoveAnalysis(
                ply=basic.ply,
                move_number=basic.move_number,
                color=basic.color,
                san=basic.san,
                uci=basic.uci,
                fen_before=basic.fen_before,
                fen_after=basic.fen_after,
                clock=basic.clock,
                time_spent_seconds=basic.time_spent_seconds,
                eval_before=before.evaluation,
                eval_after=after.evaluation,
                best_move_uci=best_move_uci,
                best_move_san=best_move_san,
                pv_san=pv_san,
                pv_uci=pv_uci,
                candidates=candidates,
                reply_move_uci=reply_move_uci,
                reply_move_san=reply_move_san,
                reply_eval=reply_eval,
                reply_pv_uci=reply_pv_uci,
                reply_pv_san=reply_pv_san,
                expected_loss=loss,
                classification=classify_loss(loss),
            )
        )
        _emit(
            progress,
            phase="move_done",
            message=(
                f"{basic.move_number}{'.' if basic.color == 'white' else '...'} {basic.san}: "
                f"{classify_loss(loss)} | loss {loss * 100:.1f}% | "
                f"best {best_move_san or best_move_uci or '?'}"
            ),
            ply=basic.ply,
            total_plies=len(basic_moves),
            position_index=position_index,
            total_positions=total_positions,
            move_san=basic.san,
            eval_label=after.evaluation.label,
            best_move_uci=best_move_uci,
            cache_status=f"{cache_hits} hits / {cache_misses} misses",
        )

    storage.save_game(record)
    _emit(
        progress,
        phase="done",
        message=f"Finished analysis: {len(analyses)} plies, {cache_hits} cache hits, {cache_misses} cache misses.",
        total_plies=len(basic_moves),
        position_index=total_positions,
        total_positions=total_positions,
        cache_status=f"{cache_hits} hits / {cache_misses} misses",
    )
    return GameAnalysis(
        game=record,
        moves=analyses,
        final_fen=final_fen(record.pgn),
        engine_name=engine.engine_name,
        profile=profile.name,
        cache_hits=cache_hits,
        cache_misses=cache_misses,
    )


def _position_analysis(
    board: chess.Board,
    engine: StockfishEngine,
    storage: AnalysisStorage,
    profile: AnalysisProfile,
    progress: Callable[[AnalysisProgress], None] | None,
    progress_context: dict,
) -> tuple[PositionAnalysis, bool]:
    cached = storage.get_position(board.fen(), engine.engine_name, profile.name, profile.multipv)
    if cached is not None:
        _emit(
            progress,
            phase="cache",
            message=f"{progress_context['position_label']}: cache hit | {cached.evaluation.label}",
            cache_status="hit",
            eval_label=cached.evaluation.label,
            best_move_uci=cached.best_move_uci,
            depth=cached.depth,
            **progress_context,
        )
        return cached, True
    _emit(
        progress,
        phase="engine_start",
        message=f"{progress_context['position_label']}: Stockfish thinking...",
        cache_status="miss",
        **progress_context,
    )
    analysis = engine.analyze_position(board, profile, progress=progress, progress_context=progress_context)
    storage.save_position(analysis)
    _emit(
        progress,
        phase="engine_done",
        message=(
            f"{progress_context['position_label']}: depth {analysis.depth or '?'} | "
            f"eval {analysis.evaluation.label} | best {analysis.best_move_uci or '?'}"
        ),
        cache_status="miss",
        depth=analysis.depth,
        nodes=analysis.nodes,
        elapsed_ms=analysis.time_ms,
        eval_label=analysis.evaluation.label,
        best_move_uci=analysis.best_move_uci,
        pv_uci=analysis.pv_uci,
        **progress_context,
    )
    return analysis, False


def _uci_to_san(board: chess.Board, uci: str | None) -> str | None:
    if not uci:
        return None
    try:
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            return uci
        return board.san(move)
    except ValueError:
        return uci


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


def _candidates_to_san(board: chess.Board, candidates: list[CandidateLine]) -> list[CandidateLine]:
    normalized: list[CandidateLine] = []
    for candidate in sorted(candidates, key=lambda item: item.rank):
        pv_san = _pv_to_san(board, candidate.pv_uci)
        move_san = pv_san[0] if pv_san else _uci_to_san(board, candidate.move_uci)
        normalized.append(candidate.model_copy(update={"move_san": move_san, "pv_san": pv_san}))
    return normalized


def _best_reply_from_after(
    board_after: chess.Board,
    after: PositionAnalysis,
) -> tuple[str | None, str | None, EngineEvaluation | None, list[str], list[str]]:
    reply_candidates = _candidates_to_san(board_after, after.candidates)
    if reply_candidates:
        reply = reply_candidates[0]
        return reply.move_uci, reply.move_san, reply.evaluation, reply.pv_uci, reply.pv_san

    reply_move_uci = after.best_move_uci or (after.pv_uci[0] if after.pv_uci else None)
    if not reply_move_uci:
        return None, None, None, [], []

    reply_pv_uci = after.pv_uci or [reply_move_uci]
    reply_pv_san = _pv_to_san(board_after, reply_pv_uci)
    reply_move_san = reply_pv_san[0] if reply_pv_san else _uci_to_san(board_after, reply_move_uci)
    return reply_move_uci, reply_move_san, after.evaluation, reply_pv_uci, reply_pv_san


def _emit(progress: Callable[[AnalysisProgress], None] | None, **data) -> None:
    if progress is None:
        return
    progress(AnalysisProgress(**data))
