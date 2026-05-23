from __future__ import annotations

import html
import logging
import os
import socket
from collections.abc import Callable
from queue import Empty, Queue

import chess
from nicegui import run, ui

from .analysis import analyze_game
from .board_view import create_board_panel, move_arrow, update_board_panel
from .chesscom import ChessComImporter, ChessComImportError
from .engine import EngineNotFoundError, PROFILES, StockfishEngine, normalize_multipv
from .models import AnalysisProgress, CandidateLine, GameAnalysis, GameRecord, MoveAnalysis
from .pgn_utils import record_from_pgn
from .pv import pv_board_at
from .storage import AnalysisStorage

CLASS_COLORS = {
    "excellent": "#1f8a70",
    "good": "#3a86ff",
    "inaccuracy": "#d18b00",
    "mistake": "#d9480f",
    "blunder": "#c92a2a",
}
USER_COLOR_OPTIONS = {
    "white": "White",
    "black": "Black",
}
CHART_WHITE_AREA_COLOR = "#ffffff"
CHART_BLACK_AREA_COLOR = "#111827"
CHART_LINE_COLOR = "#2563eb"
CHART_PLOT_BACKGROUND_COLOR = "#eef1f5"
REPLY_CLASSIFICATIONS = {"inaccuracy", "mistake", "blunder"}

logger = logging.getLogger(__name__)


class AppState:
    def __init__(self) -> None:
        self.analysis: GameAnalysis | None = None
        self.selected: MoveAnalysis | None = None
        self.selected_index: int | None = None
        self.selected_pv_source: str | None = None
        self.selected_candidate_rank: int | None = None
        self.selected_pv_index: int | None = None
        self.user_color: str = "white"
        self.move_buttons: list[object] = []


state = AppState()


def build_ui() -> None:
    ui.add_head_html(
        """
        <style>
        body { background: #f6f7f9; color: #1f2933; }
        .app-shell { max-width: 1320px; margin: 0 auto; padding: 18px; }
        .panel { background: white; border: 1px solid #d8dee7; border-radius: 8px; padding: 14px; }
        .move-row {
            width: 100%;
            justify-content: flex-start;
            margin-bottom: 4px;
            border-radius: 6px;
            transition: background-color 0.16s ease, box-shadow 0.16s ease;
        }
        .move-row.move-row-white { background-color: #ffffff; }
        .move-row.move-row-black { background-color: #f3f4f6; }
        .move-row.move-row-selected {
            background-color: #fef3c7;
            box-shadow: 0 0 0 1px #f59e0b inset;
        }
        .move-row .q-btn__content {
            width: 100%;
        }
        .move-row-content {
            align-items: center;
            display: flex;
            gap: 8px;
            justify-content: space-between;
            min-width: 0;
            width: 100%;
        }
        .move-row-label {
            min-width: 0;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .move-row-clock {
            color: #5c6773;
            flex: 0 0 auto;
            font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
            font-size: 0.78rem;
            line-height: 1;
        }
        .meta { color: #5c6773; font-size: 0.88rem; }
        .detail-line { display: flex; justify-content: space-between; gap: 12px; }
        .detail-line span:first-child { color: #5c6773; }
        .pv-token { margin: 2px 4px 2px 0; }
        .pv-token-selected {
            box-shadow: 0 0 0 2px #2563eb inset;
            background: #dbeafe;
        }
        .top-move-row {
            border: 1px solid #d8dee7;
            border-radius: 6px;
            padding: 8px;
            width: 100%;
        }
        .top-move-row-selected {
            background: #eff6ff;
            border-color: #2563eb;
        }
        .top-move-header {
            align-items: center;
            display: flex;
            gap: 8px;
            justify-content: space-between;
            width: 100%;
        }
        .top-move-eval {
            color: #5c6773;
            font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
            font-size: 0.82rem;
        }
        .progress-log {
            background: #111827;
            border-radius: 6px;
            color: #d7e0ea;
            font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
            font-size: 12px;
            line-height: 1.45;
            margin: 0;
            max-height: 170px;
            overflow-y: auto;
            padding: 10px;
            white-space: pre-wrap;
        }
        .q-field { background: white; }
        </style>
        """
    )

    with ui.column().classes("app-shell w-full gap-4"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("Chess Move Analyzer").classes("text-2xl font-semibold")
            ui.label("Local Stockfish review").classes("meta")

        with ui.row().classes("w-full gap-4"):
            with ui.column().classes("panel gap-3").style("flex: 1 1 420px;"):
                url_input = ui.input("Chess.com link").props("outlined dense clearable").classes("w-full")
                pgn_input = ui.textarea("PGN fallback").props("outlined autogrow").classes("w-full")
                with ui.row().classes("items-center gap-2"):
                    profile_select = ui.select(
                        {key: key.capitalize() for key in PROFILES},
                        value="balanced",
                        label="Profile",
                    ).props("outlined dense").style("min-width: 160px;")
                    multipv_select = ui.select(
                        {value: str(value) for value in range(1, 6)},
                        value=3,
                        label="Top N",
                    ).props("outlined dense").style("min-width: 100px;")
                    user_color_select = ui.select(
                        USER_COLOR_OPTIONS,
                        value=state.user_color,
                        label="User color",
                    ).props("outlined dense").style("min-width: 140px;")
                    user_color_badge = ui.badge(
                        _user_color_badge_label(state.user_color),
                        color=_user_color_badge_color(state.user_color),
                    )
                    analyze_button = ui.button("Analyze", icon="analytics").props("unelevated color=primary")
                status = ui.label("").classes("meta")
                progress_bar = ui.linear_progress(value=0).classes("w-full")
                progress_detail = ui.label("Idle").classes("meta")
                engine_detail = ui.label("").classes("meta").style("overflow-wrap: anywhere;")
                progress_log = ui.html(_progress_log_html([])).classes("w-full")
                ui.separator()
                ui.label("Moves").classes("text-lg font-medium")
                moves_container = ui.column().classes("w-full gap-1").style("max-height: 520px; overflow-y: auto;")

            with ui.column().classes("gap-4").style("flex: 2 1 680px; min-width: 360px;"):
                with ui.row().classes("w-full gap-4"):
                    board_panel = create_board_panel(chess.Board())
                    detail_panel = ui.column().classes("panel gap-2").style("flex: 1 1 260px;")
                    _render_empty_detail(detail_panel)
                chart = ui.echart(_empty_chart()).classes("panel w-full").style("height: 280px;")

        def update_user_color() -> None:
            state.user_color = _normalize_user_color(user_color_select.value)
            user_color_badge.set_text(_user_color_badge_label(state.user_color))
            user_color_badge.props(f"color={_user_color_badge_color(state.user_color)}")
            if state.selected:
                _render_detail(detail_panel, board_panel)
            if state.analysis:
                _set_chart_options(chart, _chart_options(state.analysis, state.user_color))

        user_color_select.on_value_change(lambda _: update_user_color())

        async def on_analyze() -> None:
            analyze_button.disable()
            update_user_color()
            progress_queue: Queue[AnalysisProgress] = Queue()
            progress_lines: list[str] = []

            def enqueue_progress(progress: AnalysisProgress) -> None:
                progress_queue.put(progress)

            def drain_progress() -> None:
                _drain_progress_queue(
                    progress_queue,
                    progress_lines,
                    status,
                    progress_bar,
                    progress_detail,
                    engine_detail,
                    progress_log,
                )

            progress_timer = ui.timer(0.2, drain_progress, active=True, immediate=False)
            status.set_text("Analyzing...")
            progress_bar.set_value(0)
            progress_detail.set_text("Preparing analysis...")
            engine_detail.set_text("")
            progress_log.set_content(_progress_log_html(["Preparing analysis..."]))
            moves_container.clear()
            _render_empty_detail(detail_panel)
            update_board_panel(board_panel, chess.Board())
            state.analysis = None
            state.selected = None
            state.selected_index = None
            state.selected_pv_source = None
            state.selected_candidate_rank = None
            state.selected_pv_index = None
            state.move_buttons = []
            _set_chart_options(chart, _empty_chart())
            try:
                record = await _load_record(url_input.value or "", pgn_input.value or "")
                multipv = normalize_multipv(multipv_select.value)
                result = await run.io_bound(_run_analysis, record, profile_select.value, multipv, enqueue_progress)
                state.analysis = result
                status.set_text(
                    f"{result.game.white or '?'} vs {result.game.black or '?'} | "
                    f"{len(result.moves)} moves | {_user_color_badge_label(state.user_color)} | "
                    f"Top N {multipv} | "
                    f"cache {result.cache_hits}/{result.cache_hits + result.cache_misses}"
                )
                progress_bar.set_value(1)
                drain_progress()
                _render_analysis(result, moves_container, board_panel, detail_panel, chart)
            except (ChessComImportError, EngineNotFoundError, ValueError) as exc:
                logger.info("Expected analysis error: %s", exc)
                status.set_text(str(exc))
            except Exception as exc:
                logger.exception("Unexpected error during analysis/rendering")
                status.set_text(f"Unexpected error: {exc}")
            finally:
                drain_progress()
                progress_timer.cancel()
                analyze_button.enable()

        analyze_button.on_click(on_analyze)


async def _load_record(url: str, pgn: str) -> GameRecord:
    if pgn.strip():
        return record_from_pgn(pgn)
    if not url.strip():
        raise ValueError("Provide a Chess.com link or paste PGN.")
    return await ChessComImporter().fetch_game(url)


def _run_analysis(
    record: GameRecord,
    profile: str,
    multipv: int | None = None,
    progress: Callable[[AnalysisProgress], None] | None = None,
) -> GameAnalysis:
    with AnalysisStorage() as storage:
        with StockfishEngine() as engine:
            return analyze_game(record, engine, storage, profile, multipv=multipv, progress=progress)


def _drain_progress_queue(
    progress_queue: Queue[AnalysisProgress],
    progress_lines: list[str],
    status,
    progress_bar,
    progress_detail,
    engine_detail,
    progress_log,
) -> None:
    latest: AnalysisProgress | None = None
    while True:
        try:
            latest = progress_queue.get_nowait()
        except Empty:
            break
        progress_lines.append(_format_progress_line(latest))

    if latest is None:
        return

    status.set_text(latest.message)
    progress_detail.set_text(_progress_detail(latest))
    if latest.phase in {"engine", "engine_done", "cache"}:
        engine_detail.set_text(_engine_detail(latest))
    progress_bar.set_value(_progress_value(latest))
    progress_log.set_content(_progress_log_html(progress_lines[-12:]))


def _progress_value(progress: AnalysisProgress) -> float:
    if progress.phase == "done":
        return 1.0
    if not progress.total_positions or not progress.position_index:
        return 0.0
    completed = progress.position_index
    if progress.phase in {"engine_start", "engine"}:
        completed -= 1
    return max(0.0, min(1.0, completed / progress.total_positions))


def _progress_detail(progress: AnalysisProgress) -> str:
    parts: list[str] = []
    if progress.ply and progress.total_plies:
        parts.append(f"Ply {progress.ply}/{progress.total_plies}")
    if progress.position_index and progress.total_positions:
        parts.append(f"Position {progress.position_index}/{progress.total_positions}")
    if progress.cache_status:
        parts.append(f"cache {progress.cache_status}")
    if progress.elapsed_ms is not None:
        parts.append(f"{progress.elapsed_ms} ms")
    return " | ".join(parts) if parts else progress.phase


def _engine_detail(progress: AnalysisProgress) -> str:
    parts: list[str] = []
    if progress.depth is not None:
        parts.append(f"depth {progress.depth}")
    if progress.eval_label:
        parts.append(f"eval {progress.eval_label}")
    if progress.best_move_uci:
        parts.append(f"best {progress.best_move_uci}")
    if progress.nodes is not None:
        parts.append(f"nodes {progress.nodes:,}")
    if progress.nps is not None:
        parts.append(f"nps {progress.nps:,}")
    if progress.pv_uci:
        parts.append("pv " + " ".join(progress.pv_uci[:8]))
    return " | ".join(parts)


def _format_progress_line(progress: AnalysisProgress) -> str:
    prefix = ""
    if progress.ply and progress.total_plies:
        prefix = f"[{progress.ply:>3}/{progress.total_plies:<3}] "
    return prefix + progress.message


def _progress_log_html(lines: list[str]) -> str:
    content = "\n".join(html.escape(line) for line in lines)
    return f"<pre class='progress-log'>{content}</pre>"


def _render_analysis(
    result: GameAnalysis,
    moves_container,
    board_panel,
    detail_panel,
    chart,
) -> None:
    state.analysis = result
    state.selected = None
    state.selected_index = None
    state.selected_pv_source = None
    state.selected_candidate_rank = None
    state.selected_pv_index = None
    state.move_buttons = []
    moves_container.clear()
    show_clocks = _should_show_move_clocks(result)
    with moves_container:
        for index, move in enumerate(result.moves):
            label = _move_label(move)
            color = CLASS_COLORS.get(move.classification, "#4b5563")
            button = ui.button(on_click=lambda i=index: _select_move(i, board_panel, detail_panel))
            button.props("flat dense no-caps")
            button.classes(f"move-row {_move_row_color_class(move)}")
            button.style(f"border-left: 5px solid {color}; color: #1f2933;")
            with button:
                with ui.element("div").classes("move-row-content"):
                    ui.label(label).classes("move-row-label")
                    if show_clocks:
                        ui.label(_move_clock_label(move)).classes("move-row-clock")
            state.move_buttons.append(button)

    default_index = _default_selected_index(result)
    if default_index is not None:
        _select_move(default_index, board_panel, detail_panel)
    _set_chart_options(chart, _chart_options(result, state.user_color))


def _select_move(index: int, board_panel, detail_panel) -> None:
    if state.analysis is None or not 0 <= index < len(state.analysis.moves):
        return
    move = state.analysis.moves[index]
    state.selected = move
    state.selected_index = index
    state.selected_pv_source = None
    state.selected_candidate_rank = None
    state.selected_pv_index = None
    _sync_move_selection()
    board = chess.Board(move.fen_before)
    last_move = chess.Move.from_uci(move.uci)
    board.push(last_move)
    update_board_panel(board_panel, board, last_move=last_move)
    _render_detail(detail_panel, board_panel)


def _move_row_color_class(move: MoveAnalysis) -> str:
    return "move-row-white" if move.color == "white" else "move-row-black"


def _should_show_move_clocks(result: GameAnalysis) -> bool:
    return any(bool(move.clock) for move in result.moves)


def _move_clock_label(move: MoveAnalysis) -> str:
    return move.clock or ""


def _sync_move_selection() -> None:
    for index, button in enumerate(state.move_buttons):
        if index == state.selected_index:
            button.classes(add="move-row-selected")
        else:
            button.classes(remove="move-row-selected")


def _render_empty_detail(panel) -> None:
    panel.clear()
    with panel:
        ui.label("Move detail").classes("text-lg font-medium")
        ui.label("No move selected.").classes("meta")


def _render_detail(panel, board_panel) -> None:
    move = state.selected
    panel.clear()
    if move is None:
        _render_empty_detail(panel)
        return
    with panel:
        ui.label(f"{_move_prefix(move)} {move.san}").classes("text-lg font-medium")
        with ui.row().classes("items-center gap-2"):
            ui.badge(move.classification, color=_badge_color(move.classification))
            ui.badge(
                _move_owner_badge_label(move, state.user_color),
                color=_move_owner_badge_color(move, state.user_color),
            )
        _render_detail_navigation(board_panel, panel)
        _detail_line("Played", move.uci)
        _detail_line("Best", move.best_move_san or move.best_move_uci or "?")
        _detail_line("Before", move.eval_before.label)
        _detail_line("After", move.eval_after.label)
        _detail_line("Loss", f"{move.expected_loss * 100:.1f}%")
        if _should_display_reply_after(move):
            ui.separator()
            _detail_line("Best reply after", move.reply_move_san or move.reply_move_uci or "?")
            ui.label("Reply line").classes("meta")
            _render_reply_pv_tokens(move, board_panel, panel)
        if move.clock:
            _detail_line("Clock", move.clock)
        if move.time_spent_seconds is not None:
            _detail_line("Time spent", f"{move.time_spent_seconds}s")
        candidates = _display_candidates(move)
        if candidates:
            ui.separator()
            ui.label("Top moves").classes("meta")
            _render_top_moves(candidates, board_panel, panel)


def _render_detail_navigation(board_panel, detail_panel) -> None:
    selected_index = state.selected_index
    total_moves = len(state.analysis.moves) if state.analysis else 0
    pv_selected = _pv_selection_active()
    with ui.row().classes("items-center gap-2"):
        previous_button = ui.button(icon="chevron_left", on_click=lambda: _select_relative_move(-1, board_panel, detail_panel))
        previous_button.props("flat dense")
        next_button = ui.button(icon="chevron_right", on_click=lambda: _select_relative_move(1, board_panel, detail_panel))
        next_button.props("flat dense")
        if selected_index is None or selected_index <= 0 or pv_selected:
            previous_button.disable()
        if selected_index is None or selected_index >= total_moves - 1 or pv_selected:
            next_button.disable()
        if pv_selected:
            clear_button = ui.button("Clear PV", icon="close", on_click=lambda: _clear_pv_selection(board_panel, detail_panel))
            clear_button.props("flat dense no-caps color=primary")


def _select_relative_move(delta: int, board_panel, detail_panel) -> None:
    if _pv_selection_active() or state.selected_index is None:
        return
    _select_move(state.selected_index + delta, board_panel, detail_panel)


def _clear_pv_selection(board_panel, detail_panel) -> None:
    if state.selected_index is None:
        return
    _select_move(state.selected_index, board_panel, detail_panel)


def _pv_selection_active() -> bool:
    return (
        state.selected_pv_index is not None
        and (state.selected_candidate_rank is not None or state.selected_pv_source == "reply")
    )


def _should_display_reply_after(move: MoveAnalysis) -> bool:
    return move.classification in REPLY_CLASSIFICATIONS and bool(move.reply_move_uci or move.reply_pv_uci)


def _display_candidates(move: MoveAnalysis) -> list[CandidateLine]:
    if move.candidates:
        return sorted(move.candidates, key=lambda candidate: candidate.rank)
    if not (move.pv_uci or move.pv_san or move.best_move_uci):
        return []
    return [
        CandidateLine(
            rank=1,
            move_uci=move.best_move_uci or (move.pv_uci[0] if move.pv_uci else None),
            move_san=move.best_move_san or (move.pv_san[0] if move.pv_san else None),
            evaluation=move.eval_before,
            pv_uci=move.pv_uci,
            pv_san=move.pv_san,
        )
    ]


def _render_top_moves(candidates: list[CandidateLine], board_panel, detail_panel) -> None:
    with ui.column().classes("w-full gap-2"):
        for candidate in candidates:
            row = ui.column().classes("top-move-row gap-2")
            if (
                state.selected_pv_source == "candidate"
                and state.selected_candidate_rank == candidate.rank
                and state.selected_pv_index is not None
            ):
                row.classes("top-move-row-selected")
            with row:
                with ui.element("div").classes("top-move-header"):
                    with ui.row().classes("items-center gap-2"):
                        ui.badge(str(candidate.rank), color="primary" if candidate.rank == 1 else "grey")
                        ui.label(candidate.move_san or candidate.move_uci or "?").classes("font-medium")
                    ui.label(candidate.evaluation.label).classes("top-move-eval")
                _render_candidate_pv_tokens(candidate, board_panel, detail_panel)


def _render_candidate_pv_tokens(candidate: CandidateLine, board_panel, detail_panel) -> None:
    token_count = min(len(candidate.pv_san), len(candidate.pv_uci))
    if token_count == 0:
        ui.label("No PV available").classes("meta")
        return
    with ui.row().classes("items-center gap-1").style("flex-wrap: wrap;"):
        for index in range(token_count):
            selected = (
                state.selected_pv_source == "candidate"
                and state.selected_candidate_rank == candidate.rank
                and state.selected_pv_index == index
            )
            token = ui.button(
                candidate.pv_san[index],
                on_click=lambda rank=candidate.rank, i=index: _select_candidate_pv_move(
                    rank,
                    i,
                    board_panel,
                    detail_panel,
                ),
            )
            token.props("dense no-caps")
            token.classes("pv-token")
            if selected:
                token.props("unelevated color=primary")
                token.classes("pv-token-selected")
            else:
                token.props("outline color=primary")


def _render_reply_pv_tokens(move: MoveAnalysis, board_panel, detail_panel) -> None:
    token_count = min(len(move.reply_pv_san), len(move.reply_pv_uci))
    if token_count == 0:
        ui.label("No reply PV available").classes("meta")
        return
    with ui.row().classes("items-center gap-1").style("flex-wrap: wrap;"):
        for index in range(token_count):
            selected = state.selected_pv_source == "reply" and state.selected_pv_index == index
            token = ui.button(
                move.reply_pv_san[index],
                on_click=lambda i=index: _select_reply_pv_move(i, board_panel, detail_panel),
            )
            token.props("dense no-caps")
            token.classes("pv-token")
            if selected:
                token.props("unelevated color=primary")
                token.classes("pv-token-selected")
            else:
                token.props("outline color=primary")


def _select_pv_move(pv_index: int, board_panel, detail_panel) -> None:
    move = state.selected
    if move is None:
        return
    candidates = _display_candidates(move)
    if not candidates:
        return
    _select_candidate_pv_move(candidates[0].rank, pv_index, board_panel, detail_panel)


def _select_candidate_pv_move(candidate_rank: int, pv_index: int, board_panel, detail_panel) -> None:
    move = state.selected
    if move is None:
        return
    candidate = _candidate_by_rank(move, candidate_rank)
    if candidate is None:
        return
    try:
        board, last_move = pv_board_at(move.fen_before, candidate.pv_uci, pv_index)
    except ValueError as exc:
        logger.exception("Could not render PV move")
        ui.notify(str(exc), type="negative")
        return
    state.selected_candidate_rank = candidate.rank
    state.selected_pv_source = "candidate"
    state.selected_pv_index = pv_index
    arrows = [move_arrow(last_move, "blue")] if last_move else []
    update_board_panel(board_panel, board, last_move=last_move, arrows=arrows)
    _render_detail(detail_panel, board_panel)


def _select_reply_pv_move(pv_index: int, board_panel, detail_panel) -> None:
    move = state.selected
    if move is None or not _should_display_reply_after(move):
        return
    try:
        board, last_move = pv_board_at(move.fen_after, move.reply_pv_uci, pv_index)
    except ValueError as exc:
        logger.exception("Could not render reply PV move")
        ui.notify(str(exc), type="negative")
        return
    state.selected_pv_source = "reply"
    state.selected_candidate_rank = None
    state.selected_pv_index = pv_index
    arrows = [move_arrow(last_move, "red")] if last_move else []
    update_board_panel(board_panel, board, last_move=last_move, arrows=arrows)
    _render_detail(detail_panel, board_panel)


def _candidate_by_rank(move: MoveAnalysis, candidate_rank: int) -> CandidateLine | None:
    for candidate in _display_candidates(move):
        if candidate.rank == candidate_rank:
            return candidate
    return None


def _detail_line(label: str, value: str) -> None:
    with ui.element("div").classes("detail-line w-full"):
        ui.label(label).classes("meta")
        ui.label(value).style("text-align: right; overflow-wrap: anywhere;")


def _empty_chart() -> dict:
    return {
        "tooltip": {"trigger": "axis"},
        "xAxis": {"type": "category", "data": []},
        "yAxis": {"type": "value", "min": 0, "max": 1},
        "series": [{"type": "line", "data": [], "smooth": True}],
    }


def _chart_options(result: GameAnalysis, user_color: str = "white") -> dict:
    labels = [_move_label(move) for move in result.moves]
    white_data = [round(move.eval_after.expected_white, 3) for move in result.moves]
    black_data = [round(1.0 - move.eval_after.expected_white, 3) for move in result.moves]
    return {
        "tooltip": {"trigger": "axis"},
        "legend": {"top": 0, "data": ["White area", "Black area", "White expected score"]},
        "grid": {
            "left": 45,
            "right": 20,
            "top": 55,
            "bottom": 50,
            "show": True,
            "backgroundColor": CHART_PLOT_BACKGROUND_COLOR,
            "borderColor": "transparent",
        },
        "xAxis": {"type": "category", "data": labels, "axisLabel": {"rotate": 45}},
        "yAxis": {"type": "value", "min": 0, "max": 1, "name": "White expected score"},
        "series": [
            {
                "name": "White area",
                "type": "line",
                "data": white_data,
                "stack": "player-area",
                "smooth": True,
                "symbol": "none",
                "lineStyle": {"opacity": 0},
                "itemStyle": {
                    "color": CHART_WHITE_AREA_COLOR,
                    "borderColor": "#9ca3af",
                    "borderWidth": 1,
                },
                "areaStyle": {"color": CHART_WHITE_AREA_COLOR, "opacity": 0.92},
                "tooltip": {"show": False},
                "silent": True,
            },
            {
                "name": "Black area",
                "type": "line",
                "data": black_data,
                "stack": "player-area",
                "smooth": True,
                "symbol": "none",
                "lineStyle": {"opacity": 0},
                "itemStyle": {"color": CHART_BLACK_AREA_COLOR},
                "areaStyle": {"color": CHART_BLACK_AREA_COLOR, "opacity": 0.26},
                "tooltip": {"show": False},
                "silent": True,
            },
            {
                "name": "White expected score",
                "type": "line",
                "data": white_data,
                "smooth": True,
                "symbolSize": 6,
                "lineStyle": {"width": 3, "color": CHART_LINE_COLOR},
                "itemStyle": {"color": CHART_LINE_COLOR},
                "z": 3,
            },
        ],
    }


def _set_chart_options(chart, options: dict) -> None:
    chart.options.clear()
    chart.options.update(options)
    chart.update()


def _move_label(move: MoveAnalysis) -> str:
    return f"{_move_prefix(move)} {move.san} ({move.classification})"


def _move_prefix(move: MoveAnalysis) -> str:
    return f"{move.move_number}." if move.color == "white" else f"{move.move_number}..."


def _normalize_user_color(value: object) -> str:
    return str(value).lower() if str(value).lower() in USER_COLOR_OPTIONS else "white"


def _user_color_badge_label(user_color: str) -> str:
    return f"You: {USER_COLOR_OPTIONS[_normalize_user_color(user_color)]}"


def _user_color_badge_color(user_color: str) -> str:
    return "grey" if _normalize_user_color(user_color) == "white" else "dark"


def _move_owner_badge_label(move: MoveAnalysis, user_color: str) -> str:
    return "Your move" if move.color == _normalize_user_color(user_color) else "Opponent"


def _move_owner_badge_color(move: MoveAnalysis, user_color: str) -> str:
    return "primary" if move.color == _normalize_user_color(user_color) else "grey"


def _default_selected_index(result: GameAnalysis) -> int | None:
    if not result.moves:
        return None
    priority = {"blunder": 5, "mistake": 4, "inaccuracy": 3, "good": 2, "excellent": 1}
    return max(
        range(len(result.moves)),
        key=lambda index: (priority.get(result.moves[index].classification, 0), result.moves[index].expected_loss),
    )


def _badge_color(classification: str) -> str:
    return {
        "excellent": "green",
        "good": "blue",
        "inaccuracy": "orange",
        "mistake": "deep-orange",
        "blunder": "red",
    }.get(classification, "grey")


def main() -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
    build_ui()
    port = _resolve_port()
    ui.run(title="Chess Move Analyzer", host=_resolve_host(), port=port, reload=False, show=_resolve_show())


def _resolve_host() -> str:
    return os.environ.get("CHESS_ANALYZER_HOST", "127.0.0.1")


def _resolve_show() -> bool:
    value = os.environ.get("CHESS_ANALYZER_SHOW")
    if value is None:
        return True
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _resolve_port() -> int:
    explicit = os.environ.get("CHESS_ANALYZER_PORT")
    if explicit:
        return int(explicit)
    for port in [8080, 8765, 8081, 8082, 8083, 9000]:
        if _port_is_free(port):
            return port
    raise RuntimeError("No free local port was found for the app.")


def _port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) != 0


if __name__ in {"__main__", "__mp_main__"}:
    main()
