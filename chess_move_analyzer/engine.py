from __future__ import annotations

import math
import os
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import chess
import chess.engine

from .models import AnalysisProgress, CandidateLine, EngineEvaluation, PositionAnalysis


class EngineNotFoundError(RuntimeError):
    pass


@dataclass(frozen=True)
class AnalysisProfile:
    name: str
    seconds_per_position: float
    multipv: int
    hash_mb: int


PROFILES: dict[str, AnalysisProfile] = {
    "fast": AnalysisProfile("fast", seconds_per_position=0.3, multipv=3, hash_mb=256),
    "balanced": AnalysisProfile("balanced", seconds_per_position=1.0, multipv=3, hash_mb=512),
    "deep": AnalysisProfile("deep", seconds_per_position=3.0, multipv=5, hash_mb=1024),
}


def normalize_multipv(value: int | str | None, minimum: int = 1, maximum: int = 5) -> int:
    try:
        parsed = int(value) if value is not None else 3
    except (TypeError, ValueError):
        parsed = 3
    return max(minimum, min(maximum, parsed))


def effective_profile(profile_name: str = "balanced", multipv: int | str | None = None) -> AnalysisProfile:
    base = PROFILES.get(profile_name, PROFILES["balanced"])
    return AnalysisProfile(
        name=base.name,
        seconds_per_position=base.seconds_per_position,
        multipv=normalize_multipv(multipv if multipv is not None else base.multipv),
        hash_mb=base.hash_mb,
    )


class StockfishEngine:
    def __init__(self, path: str | Path | None = None, threads: int | None = None) -> None:
        self.path = Path(path) if path else resolve_stockfish_path()
        self.threads = threads or max(1, min(4, os.cpu_count() or 1))
        self._engine: chess.engine.SimpleEngine | None = None
        self.engine_name = "Stockfish"

    def __enter__(self) -> "StockfishEngine":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.quit()

    def start(self) -> None:
        if self._engine is not None:
            return
        self._engine = chess.engine.SimpleEngine.popen_uci(str(self.path))
        self.engine_name = self._engine.id.get("name", self.path.name)

    def configure_for_profile(self, profile: AnalysisProfile) -> None:
        engine = self._require_engine()
        options: dict[str, object] = {}
        if "Threads" in engine.options:
            options["Threads"] = self.threads
        if "Hash" in engine.options:
            options["Hash"] = profile.hash_mb
        if "UCI_ShowWDL" in engine.options:
            options["UCI_ShowWDL"] = True
        if options:
            engine.configure(options)

    def analyze_position(
        self,
        board: chess.Board,
        profile: AnalysisProfile,
        progress: Callable[[AnalysisProgress], None] | None = None,
        progress_context: dict | None = None,
    ) -> PositionAnalysis:
        engine = self._require_engine()
        self.configure_for_profile(profile)
        started = time.perf_counter()
        progress_context = progress_context or {}
        primary: dict = {}
        last_depth = -1
        with engine.analysis(
            board,
            chess.engine.Limit(time=profile.seconds_per_position),
            multipv=profile.multipv,
        ) as analysis:
            for info in analysis:
                if info.get("multipv", 1) != 1:
                    continue
                if not analysis.multipv:
                    continue
                primary = analysis.multipv[0].copy()
                depth = primary.get("depth")
                if depth is None or depth == last_depth:
                    continue
                last_depth = depth
                if progress is not None:
                    progress(_progress_from_info(primary, board, started, progress_context))
            multipv_infos = multipv_infos_from_analysis(analysis.multipv)
            primary = multipv_infos[0] if multipv_infos else {}
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        candidates = candidate_lines_from_multipv(multipv_infos, board)
        primary_candidate = candidates[0] if candidates else None
        pv = primary_candidate.pv_uci if primary_candidate else [move.uci() for move in primary.get("pv", [])]
        best_move = primary_candidate.move_uci if primary_candidate else (pv[0] if pv else None)
        evaluation = primary_candidate.evaluation if primary_candidate else evaluation_from_info(primary, board)
        return PositionAnalysis(
            fen=board.fen(),
            engine_name=self.engine_name,
            profile=profile.name,
            multipv=profile.multipv,
            depth=primary.get("depth"),
            nodes=primary.get("nodes"),
            time_ms=elapsed_ms,
            best_move_uci=best_move,
            pv_uci=pv,
            evaluation=evaluation,
            candidates=candidates,
        )

    def quit(self) -> None:
        if self._engine is None:
            return
        try:
            self._engine.quit()
        finally:
            self._engine = None

    def _require_engine(self) -> chess.engine.SimpleEngine:
        if self._engine is None:
            self.start()
        if self._engine is None:
            raise RuntimeError("Stockfish engine did not start.")
        return self._engine


def resolve_stockfish_path() -> Path:
    env_path = os.environ.get("STOCKFISH_PATH")
    candidates = []
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(Path.cwd() / "engines" / "stockfish.exe")
    path_in_shell = shutil.which("stockfish")
    if path_in_shell:
        candidates.append(Path(path_in_shell))

    for candidate in candidates:
        if candidate.exists():
            return candidate

    raise EngineNotFoundError(
        "Stockfish was not found. Put stockfish.exe in engines/ or set STOCKFISH_PATH."
    )


def evaluation_from_info(info: dict, board: chess.Board) -> EngineEvaluation:
    score = info.get("score")
    if score is None:
        return EngineEvaluation(expected_white=0.5)

    white_score = score.white()
    cp_white = white_score.score(mate_score=100000)
    mate_white = white_score.mate()
    wdl_white = _wdl_from_info(info)
    expected_white = _expected_from_score(score, chess.WHITE, board.ply())
    return EngineEvaluation(
        cp_white=cp_white,
        mate_white=mate_white,
        expected_white=expected_white,
        wdl_white=wdl_white,
    )


def multipv_infos_from_analysis(raw_infos: list[dict]) -> list[dict]:
    infos = [info.copy() for info in raw_infos if info]
    return sorted(infos, key=lambda info: int(info.get("multipv", len(infos) + 1)))


def candidate_lines_from_multipv(raw_infos: list[dict], board: chess.Board) -> list[CandidateLine]:
    candidates: list[CandidateLine] = []
    for fallback_rank, info in enumerate(multipv_infos_from_analysis(raw_infos), start=1):
        pv_uci = [move.uci() for move in info.get("pv", [])]
        pv_san = _pv_to_san(board, pv_uci)
        rank = int(info.get("multipv") or fallback_rank)
        candidates.append(
            CandidateLine(
                rank=rank,
                move_uci=pv_uci[0] if pv_uci else None,
                move_san=pv_san[0] if pv_san else None,
                evaluation=evaluation_from_info(info, board),
                pv_uci=pv_uci,
                pv_san=pv_san,
                depth=info.get("depth"),
            )
        )
    return candidates


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


def _wdl_from_info(info: dict) -> tuple[int, int, int] | None:
    wdl = info.get("wdl")
    if wdl is None:
        return None
    try:
        white_wdl = wdl.white()
        return (int(white_wdl.wins), int(white_wdl.draws), int(white_wdl.losses))
    except AttributeError:
        try:
            return (int(wdl.wins), int(wdl.draws), int(wdl.losses))
        except AttributeError:
            return None


def _expected_from_score(score: chess.engine.PovScore, color: chess.Color, ply: int) -> float:
    pov = score.pov(color)
    try:
        wdl = pov.wdl(model="sf16", ply=ply)
        return float(wdl.expectation())
    except Exception:
        pass

    cp = pov.score(mate_score=100000)
    if cp is None:
        return 0.5
    if cp >= 100000:
        return 1.0
    if cp <= -100000:
        return 0.0
    return 1.0 / (1.0 + math.exp(-cp / 400.0))


def _progress_from_info(
    info: dict,
    board: chess.Board,
    started: float,
    context: dict,
) -> AnalysisProgress:
    pv = [move.uci() for move in info.get("pv", [])]
    evaluation = evaluation_from_info(info, board) if info.get("score") is not None else None
    depth = info.get("depth")
    label = context.get("position_label") or "Position"
    eval_label = evaluation.label if evaluation else None
    best_move = pv[0] if pv else None
    parts = [str(label)]
    if depth is not None:
        parts.append(f"depth {depth}")
    if eval_label is not None:
        parts.append(f"eval {eval_label}")
    if best_move:
        parts.append(f"best {best_move}")
    return AnalysisProgress(
        phase="engine",
        message=" | ".join(parts),
        ply=context.get("ply"),
        total_plies=context.get("total_plies"),
        position_index=context.get("position_index"),
        total_positions=context.get("total_positions"),
        move_san=context.get("move_san"),
        position_label=context.get("position_label"),
        cache_status="miss",
        depth=depth,
        nodes=info.get("nodes"),
        nps=info.get("nps"),
        elapsed_ms=int((time.perf_counter() - started) * 1000),
        eval_label=eval_label,
        best_move_uci=best_move,
        pv_uci=pv,
    )
