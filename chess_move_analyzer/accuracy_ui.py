from __future__ import annotations

import html
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import chess
from nicegui import run, ui

from .accuracy_board import render_training_board, training_board_css
from .accuracy_engine import AccuracyEngine
from .accuracy_models import (
    SOURCE_LABELS,
    MoveFeedback,
    StoredTrainingSession,
    TrainingConfig,
    TrainingGame,
)
from .accuracy_pgn_index import automatic_sample_game_count
from .accuracy_session import TrainingSession, TrainingSessionError, build_move_from_squares, create_training_session
from .accuracy_sources import LichessPgnSource, TrainingSourceError, load_training_games
from .accuracy_storage import TrainingHistoryStorage
from .engine import EngineNotFoundError, StockfishEngine
from .storage import AnalysisStorage

logger = logging.getLogger(__name__)

_ACCURACY_STYLES_ADDED = False


@dataclass
class AccuracyUiState:
    session: TrainingSession | None = None
    selected_square: int | None = None
    last_move: chess.Move | None = None
    last_feedback: MoveFeedback | None = None
    uploaded_pgn_file: object | None = None
    uploaded_pgn_name: str | None = None
    uploaded_pgn_size: int | None = None
    upload_in_progress: bool = False
    log_lines: list[str] = field(default_factory=list)


accuracy_state = AccuracyUiState()


def render_accuracy_training_section() -> None:
    _ensure_accuracy_styles()

    with ui.column().classes("accuracy-workspace w-full gap-4"):
        with ui.element("div").classes("accuracy-main-grid"):
            with ui.column().classes("panel accuracy-panel-config gap-3"):
                ui.label("Accuracy Training").classes("text-xl font-semibold")
                source_select = ui.select(
                    SOURCE_LABELS,
                    value="lichess_pgn",
                    label="Source",
                ).props("outlined dense").classes("w-full")
                with ui.row().classes("w-full gap-2"):
                    consecutive_select = ui.select(
                        {value: str(value) for value in range(1, 4)},
                        value=1,
                        label="Consecutive moves",
                    ).props("outlined dense").style("flex: 1 1 140px;")
                    scenario_select = ui.select(
                        {value: str(value) for value in [5, 10, 15, 20, 30]},
                        value=10,
                        label="Scenarios",
                    ).props("outlined dense").style("flex: 1 1 120px;")

                chesscom_field = ui.input("Chess.com username").props("outlined dense clearable").classes("w-full")
                uploaded_file_label = ui.label("No PGN file uploaded.").classes("meta")
                upload_status = ui.badge("Waiting for PGN", color="grey")

                async def handle_pgn_upload(event) -> None:
                    start_button.disable()
                    await _load_uploaded_pgn(event, uploaded_file_label, upload_status, refresh_log)
                    start_button.enable()

                upload_control = ui.upload(
                    label="Upload PGN",
                    auto_upload=True,
                    on_upload=handle_pgn_upload,
                ).props("accept=.pgn,.txt").classes("w-full")

                with ui.row().classes("items-center gap-2"):
                    start_button = ui.button("Start Training", icon="play_arrow").props("unelevated color=primary")
                    status = ui.label("Configure a training session.").classes("meta")

            board_container = ui.column().classes("panel accuracy-panel-board gap-3")
            feedback_container = ui.column().classes("panel accuracy-panel-feedback gap-2")

        with ui.element("div").classes("accuracy-secondary-grid"):
            with ui.expansion("Recent sessions", icon="history", value=True).classes("panel accuracy-expansion accuracy-panel-history"):
                history_container = ui.column().classes("w-full gap-2")
            with ui.expansion("Training log", icon="terminal", value=False).classes("panel accuracy-expansion accuracy-panel-log"):
                log_container = ui.column().classes("w-full gap-2")

        def source_value() -> str:
            return str(source_select.value or "lichess_pgn")

        def refresh_source_visibility() -> None:
            use_chesscom = source_value() == "chesscom"
            chesscom_field.set_visibility(use_chesscom)
            uploaded_file_label.set_visibility(not use_chesscom)
            upload_status.set_visibility(not use_chesscom)
            upload_control.set_visibility(not use_chesscom)

        def current_config() -> TrainingConfig:
            return TrainingConfig(
                source=source_value(),
                difficulty="medium",
                consecutive_moves=int(consecutive_select.value or 1),
                scenario_count=int(scenario_select.value or 10),
                chesscom_username=chesscom_field.value or None,
            )

        def refresh_board() -> None:
            board_container.clear()
            with board_container:
                session = accuracy_state.session
                if session is None or session.board is None:
                    ui.label("Start a session to load the first position.").classes("meta")
                    return
                ui.label(session.progress_label).classes("font-medium")
                ui.label(_side_to_move_label(session.board)).classes("meta")
                render_training_board(
                    session.board,
                    on_square_click,
                    selected_square=accuracy_state.selected_square,
                    last_move=accuracy_state.last_move,
                )
                _render_board_guidance(session, accuracy_state.last_feedback)
                _render_scenario_move_history(session)
                if session.completed:
                    ui.label("Training complete.").classes("meta")
                elif session.awaiting_next:
                    ui.button("Next Scenario", icon="skip_next", on_click=advance_to_next).props("unelevated color=primary")

        def refresh_feedback() -> None:
            feedback_container.clear()
            with feedback_container:
                session = accuracy_state.session
                if session is None:
                    ui.label("Feedback").classes("text-lg font-medium")
                    ui.label("Analysis will appear after each legal move.").classes("meta")
                    return
                if session.completed:
                    _render_summary(session)
                    return
                ui.label("Feedback").classes("text-lg font-medium")
                if accuracy_state.last_feedback is None:
                    ui.label("Choose a legal move on the board.").classes("meta")
                    return
                _render_feedback(accuracy_state.last_feedback)

        def refresh_history() -> None:
            history_container.clear()
            with history_container:
                sessions = _recent_sessions()
                if not sessions:
                    ui.label("No saved sessions yet.").classes("meta")
                    return
                for item in sessions:
                    accuracy = "?" if item.accuracy is None else f"{item.accuracy:.1f}"
                    ui.label(f"#{item.session_id} | {accuracy} | {item.started_at}").classes("meta")

        def refresh_all() -> None:
            refresh_board()
            refresh_feedback()
            refresh_history()
            refresh_log()

        def refresh_log() -> None:
            log_container.clear()
            with log_container:
                if not accuracy_state.log_lines:
                    ui.label("No events yet.").classes("meta")
                    return
                ui.html(_log_html(accuracy_state.log_lines[-12:])).classes("accuracy-log-frame w-full")

        def log_event(message: str, level: str = "info") -> None:
            _append_log(message, level)
            refresh_log()

        async def on_square_click(square: int) -> None:
            session = accuracy_state.session
            if session is None or session.board is None or session.completed:
                return
            if session.awaiting_next:
                ui.notify("Review the feedback, then continue to the next scenario.", type="warning")
                return
            board = session.board
            if accuracy_state.selected_square is None:
                piece = board.piece_at(square)
                if piece is None or piece.color != board.turn:
                    ui.notify("Select one of your pieces first.", type="warning")
                    return
                accuracy_state.selected_square = square
                refresh_board()
                return
            if accuracy_state.selected_square == square:
                accuracy_state.selected_square = None
                refresh_board()
                return
            move = build_move_from_squares(board, accuracy_state.selected_square, square)
            accuracy_state.selected_square = None
            if move not in board.legal_moves:
                ui.notify(f"{move.uci()} is not legal here.", type="negative")
                refresh_board()
                return
            await submit_move(move.uci())

        async def start_training() -> None:
            start_button.disable()
            status.set_text("Loading games and selecting positions...")
            log_event("Start Training clicked.")
            accuracy_state.session = None
            accuracy_state.selected_square = None
            accuracy_state.last_move = None
            accuracy_state.last_feedback = None
            refresh_all()
            try:
                config = _prepare_training_config(current_config())
                log_event(f"Source: {SOURCE_LABELS.get(config.source, config.source)}.")
                if config.source == "lichess_pgn":
                    if accuracy_state.upload_in_progress:
                        log_event("PGN upload is still being saved.", "error")
                        raise TrainingSourceError("Wait until the PGN upload finishes.")
                    if accuracy_state.uploaded_pgn_file is None:
                        log_event("No PGN file is available for Lichess.", "error")
                        raise TrainingSourceError("Upload a PGN file for the Lichess source.")
                    if not _uploaded_file_available(accuracy_state.uploaded_pgn_file):
                        log_event("The uploaded PGN file is no longer available.", "error")
                        raise TrainingSourceError("Upload the PGN file again.")
                    log_event(f"Sampling up to {config.max_games} games from PGN.")
                games = await _load_games_for_config(config, accuracy_state.uploaded_pgn_file)
                log_event(f"Loaded {len(games)} games.")
                log_event("Extracting positions and creating session.")
                session = await run.io_bound(_create_session_io, config, games)
                accuracy_state.session = session
                log_event(f"Selected {len(session.scenarios)} scenarios.")
                log_event("Training ready.", "success")
                status.set_text(f"Loaded {len(session.scenarios)} scenarios.")
            except (TrainingSourceError, TrainingSessionError, EngineNotFoundError, ValueError) as exc:
                logger.info("Accuracy training setup error: %s", exc)
                log_event(str(exc), "error")
                status.set_text(str(exc))
            except Exception as exc:
                logger.exception("Unexpected accuracy training setup error")
                log_event(f"Unexpected error: {exc}", "error")
                status.set_text(f"Unexpected error: {exc}")
            finally:
                start_button.enable()
                refresh_all()

        async def submit_move(move_uci: str) -> None:
            session = accuracy_state.session
            if session is None:
                return
            status.set_text("Analyzing move...")
            try:
                feedback = await run.io_bound(_submit_move_io, session, move_uci)
                accuracy_state.last_feedback = feedback
                accuracy_state.last_move = _last_applied_move_for_feedback(session, feedback)
                if session.completed:
                    status.set_text("Training complete.")
                elif session.awaiting_next:
                    status.set_text(_sequence_end_message(session, feedback))
                else:
                    reply = _candidate_label(feedback.best_reply)
                    status.set_text(
                        f"Stockfish replied: {reply}. Find the next move."
                        if reply
                        else "Find the next move."
                    )
            except (TrainingSessionError, EngineNotFoundError, ValueError) as exc:
                logger.info("Accuracy training move error: %s", exc)
                status.set_text(str(exc))
            except Exception as exc:
                logger.exception("Unexpected accuracy training move error")
                status.set_text(f"Unexpected error: {exc}")
            finally:
                refresh_all()

        def advance_to_next() -> None:
            session = accuracy_state.session
            if session is None:
                return
            session.advance_to_next_scenario()
            accuracy_state.selected_square = None
            accuracy_state.last_move = None
            accuracy_state.last_feedback = None
            status.set_text("Next scenario loaded." if not session.completed else "Training complete.")
            refresh_all()

        source_select.on_value_change(lambda _: refresh_source_visibility())
        start_button.on_click(start_training)
        refresh_source_visibility()
        refresh_all()


def _create_session_io(config: TrainingConfig, games: list[TrainingGame]) -> TrainingSession:
    with TrainingHistoryStorage() as history:
        with AnalysisStorage() as analysis_storage:
            with StockfishEngine() as engine:
                analyzer = AccuracyEngine(engine, analysis_storage)
                return create_training_session(config, games, analyzer, history)


async def _load_games_for_config(config: TrainingConfig, uploaded_pgn_file: object | None = None) -> list[TrainingGame]:
    if config.source == "lichess_pgn":
        return await run.io_bound(_load_lichess_games_io, config, uploaded_pgn_file)
    return await load_training_games(config)


def _load_lichess_games_io(config: TrainingConfig, uploaded_pgn_file: object | None = None) -> list[TrainingGame]:
    if uploaded_pgn_file is not None:
        return LichessPgnSource().load_uploaded_games_sync(config, uploaded_pgn_file)
    return LichessPgnSource().load_games_sync(config)


def _prepare_training_config(config: TrainingConfig) -> TrainingConfig:
    updates = {
        "random_seed": config.random_seed if config.random_seed is not None else random.SystemRandom().randint(0, 2**31 - 1),
    }
    if config.source == "lichess_pgn":
        updates["max_games"] = automatic_sample_game_count(config.scenario_count, config.consecutive_moves)
    return config.model_copy(update=updates)


def _submit_move_io(session: TrainingSession, move_uci: str) -> MoveFeedback:
    with TrainingHistoryStorage() as history:
        with AnalysisStorage() as analysis_storage:
            with StockfishEngine() as engine:
                analyzer = AccuracyEngine(engine, analysis_storage)
                feedback = session.submit_move(move_uci, analyzer)
                if session.session_id is not None:
                    history.save_attempt(session.session_id, feedback)
                    if session.completed:
                        history.complete_session(session.session_id, session.summary())
                return feedback


def _recent_sessions() -> list[StoredTrainingSession]:
    with TrainingHistoryStorage() as history:
        return history.recent_sessions(limit=5)


def _render_feedback(feedback: MoveFeedback) -> None:
    _detail_line("Your move", feedback.user_move_san)
    _detail_line("Move score", f"{feedback.move_score:.1f}")
    _detail_line("Classification", feedback.classification)
    _detail_line("Before", feedback.eval_before.label)
    _detail_line("After", feedback.eval_after.label)
    _detail_line("Loss", f"{feedback.expected_loss * 100:.1f}%")
    if feedback.top_candidates:
        ui.separator()
        ui.label("Top moves").classes("meta")
        for candidate in feedback.top_candidates[:2]:
            _detail_line(f"#{candidate.rank}", f"{candidate.move_san or candidate.move_uci or '?'} | {candidate.evaluation.label}")
    if feedback.best_reply:
        ui.separator()
        _detail_line("Best reply", feedback.best_reply.move_san or feedback.best_reply.move_uci or "?")
    if feedback.worst_found:
        _detail_line("Worst found", feedback.worst_found.move_san or feedback.worst_found.move_uci or "?")


def _render_board_guidance(session: TrainingSession, feedback: MoveFeedback | None) -> None:
    if feedback is None or feedback.scenario_index != session.scenario_index:
        ui.label("Play the best move you can find.").classes("meta")
        return
    if session.completed:
        return
    if session.awaiting_next:
        ui.label(_sequence_end_message(session, feedback)).classes("meta")
        return

    reply = _candidate_label(feedback.best_reply)
    if reply:
        ui.label(f"Stockfish replied: {reply}").classes("accuracy-board-callout")
    ui.label(f"Your move {session.step_index + 1}/{session.config.consecutive_moves}").classes("font-medium")
    ui.label("Play your next move on the board.").classes("meta")


def _render_scenario_move_history(session: TrainingSession) -> None:
    scenario_feedbacks = [item for item in session.feedbacks if item.scenario_index == session.scenario_index]
    if not scenario_feedbacks:
        return

    with ui.element("div").classes("scenario-move-history w-full"):
        ui.label("Scenario moves").classes("meta")
        for feedback in sorted(scenario_feedbacks, key=lambda item: item.step_index):
            user_move = feedback.user_move_san or feedback.user_move_uci
            parts = [f"Move {feedback.step_index + 1}: You {user_move}"]
            if _engine_reply_was_applied(feedback, session.config):
                parts.append(f"Stockfish {_candidate_label(feedback.best_reply)}")
            ui.label(" | ".join(parts)).classes("scenario-move-row")


def _render_summary(session: TrainingSession) -> None:
    summary = session.summary()
    ui.label("Training complete").classes("text-lg font-medium")
    _detail_line("Accuracy", f"{summary.accuracy:.1f}")
    _detail_line("Moves", str(summary.total_moves))
    _detail_line("Average loss", f"{summary.average_loss * 100:.1f}%")
    if summary.classifications:
        ui.separator()
        ui.label("Distribution").classes("meta")
        for label, count in sorted(summary.classifications.items()):
            _detail_line(label, str(count))


def _detail_line(label: str, value: str) -> None:
    with ui.element("div").classes("detail-line w-full"):
        ui.label(label).classes("meta")
        ui.label(value).style("text-align: right; overflow-wrap: anywhere;")


def _side_to_move_label(board: chess.Board) -> str:
    return "White to move" if board.turn == chess.WHITE else "Black to move"


def _last_applied_move_for_feedback(session: TrainingSession, feedback: MoveFeedback) -> chess.Move | None:
    if not session.awaiting_next and not session.completed and _engine_reply_was_applied(feedback, session.config):
        return _move_from_uci(feedback.best_reply.move_uci if feedback.best_reply else None)
    return _move_from_uci(feedback.user_move_uci)


def _sequence_end_message(session: TrainingSession, feedback: MoveFeedback | None) -> str:
    if session.completed:
        return "Training complete."
    if feedback is None:
        return "Scenario complete."
    if feedback.step_index + 1 >= session.config.consecutive_moves:
        return "Scenario complete."
    if feedback.best_reply is None or not feedback.best_reply.move_uci:
        return "Sequence ended because no engine reply was available."
    if not _engine_reply_was_applied(feedback, session.config):
        return "Sequence ended because the engine reply could not be applied."
    return "Scenario complete."


def _engine_reply_was_applied(feedback: MoveFeedback, config: TrainingConfig) -> bool:
    if feedback.step_index + 1 >= config.consecutive_moves:
        return False
    if feedback.best_reply is None or not feedback.best_reply.move_uci:
        return False
    try:
        board = chess.Board(feedback.fen_after_user)
        move = chess.Move.from_uci(feedback.best_reply.move_uci)
    except ValueError:
        return False
    return move in board.legal_moves


def _candidate_label(candidate) -> str:
    if candidate is None:
        return ""
    return candidate.move_san or candidate.move_uci or ""


def _move_from_uci(move_uci: str | None) -> chess.Move | None:
    if not move_uci:
        return None
    try:
        return chess.Move.from_uci(move_uci)
    except ValueError:
        return None


async def _load_uploaded_pgn(event, file_label, upload_status, refresh_log) -> None:
    try:
        accuracy_state.upload_in_progress = True
        accuracy_state.uploaded_pgn_file = None
        accuracy_state.uploaded_pgn_name = None
        accuracy_state.uploaded_pgn_size = None
        file_label.set_text("Reading uploaded PGN...")
        upload_status.set_text("Reading")
        upload_status.props("color=orange")
        file_obj = event.file
        name = _uploaded_file_name(file_obj)
        size = _uploaded_file_size(file_obj)
        accuracy_state.uploaded_pgn_file = file_obj
        accuracy_state.uploaded_pgn_name = name
        accuracy_state.uploaded_pgn_size = size
        file_label.set_text(f"{name} | {_format_bytes(size)}")
        upload_status.set_text("Ready")
        upload_status.props("color=green")
        _append_log(f"File uploaded: {name} ({_format_bytes(size)}).", "success")
        refresh_log()
        ui.notify("PGN uploaded.", type="positive")
    except Exception as exc:
        logger.exception("Could not read uploaded PGN")
        upload_status.set_text("Error")
        upload_status.props("color=red")
        _append_log(f"Upload error: {exc}", "error")
        refresh_log()
        ui.notify(f"Could not read PGN: {exc}", type="negative")
    finally:
        accuracy_state.upload_in_progress = False


def _uploaded_file_name(file_obj) -> str:
    for attr in ("name", "filename"):
        value = getattr(file_obj, attr, None)
        if value:
            return Path(str(value)).name
    content = getattr(file_obj, "content", None)
    for attr in ("name", "filename"):
        value = getattr(content, attr, None)
        if value:
            return Path(str(value)).name
    return "uploaded.pgn"


def _uploaded_file_size(file_obj) -> int:
    size_method = getattr(file_obj, "size", None)
    if callable(size_method):
        return int(size_method())
    for candidate in (file_obj, getattr(file_obj, "content", None)):
        path = getattr(candidate, "_path", None)
        if path:
            return Path(path).stat().st_size
        data = getattr(candidate, "_data", None)
        if data is not None:
            return len(data)
    content = getattr(file_obj, "content", None)
    if isinstance(content, (bytes, bytearray, memoryview, str)):
        return len(content)
    return 0


def _uploaded_file_available(file_obj) -> bool:
    for candidate in (file_obj, getattr(file_obj, "content", None)):
        path = getattr(candidate, "_path", None)
        if path:
            return Path(path).exists()
    return True


def _format_bytes(size: int) -> str:
    value = float(size)
    for unit in ["B", "KB", "MB", "GB"]:
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def _append_log(message: str, level: str = "info") -> None:
    prefix = {"error": "ERROR", "success": "OK"}.get(level, "INFO")
    timestamp = datetime.now().strftime("%H:%M:%S")
    accuracy_state.log_lines.append(f"[{timestamp}] {prefix}: {message}")
    accuracy_state.log_lines = accuracy_state.log_lines[-50:]


def _log_html(lines: list[str]) -> str:
    content = "\n".join(html.escape(line) for line in lines)
    return f"<pre class='progress-log'>{content}</pre>"


def _ensure_accuracy_styles() -> None:
    global _ACCURACY_STYLES_ADDED
    if _ACCURACY_STYLES_ADDED:
        return
    ui.add_head_html(f"<style>{training_board_css()}{accuracy_layout_css()}</style>", shared=True)
    _ACCURACY_STYLES_ADDED = True


def accuracy_layout_css() -> str:
    return """
    .accuracy-workspace {
        align-items: stretch;
    }
    .accuracy-main-grid {
        align-items: start;
        display: grid;
        gap: 16px;
        grid-template-columns: repeat(12, minmax(0, 1fr));
        width: 100%;
    }
    .accuracy-panel-config,
    .accuracy-panel-board,
    .accuracy-panel-feedback {
        grid-column: span 4;
        min-width: 0;
    }
    .accuracy-panel-board {
        align-items: center;
    }
    .accuracy-panel-board > .q-label,
    .accuracy-panel-board > div:not(.training-board) {
        align-self: stretch;
    }
    .accuracy-panel-feedback {
        max-height: calc(100vh - 150px);
        overflow-y: auto;
    }
    .accuracy-secondary-grid {
        align-items: start;
        display: grid;
        gap: 16px;
        grid-template-columns: repeat(12, minmax(0, 1fr));
        width: 100%;
    }
    .accuracy-panel-history {
        grid-column: span 4;
    }
    .accuracy-panel-log {
        grid-column: span 8;
    }
    .accuracy-expansion {
        padding: 0;
    }
    .accuracy-expansion .q-expansion-item__container > .q-item {
        padding: 12px 14px;
    }
    .accuracy-expansion .q-expansion-item__content {
        padding: 0 14px 14px;
    }
    .accuracy-log-frame .progress-log {
        max-height: 220px;
        overflow-y: auto;
    }
    .accuracy-board-callout {
        align-self: stretch;
        background: #eff6ff;
        border: 1px solid #bfdbfe;
        border-radius: 6px;
        color: #1e3a8a;
        padding: 8px 10px;
    }
    .scenario-move-history {
        border-top: 1px solid #e5e7eb;
        display: flex;
        flex-direction: column;
        gap: 4px;
        padding-top: 8px;
    }
    .scenario-move-row {
        color: #374151;
        font-size: 0.875rem;
        overflow-wrap: anywhere;
    }
    @media (max-width: 1120px) {
        .accuracy-panel-config {
            grid-column: span 12;
        }
        .accuracy-panel-board,
        .accuracy-panel-feedback {
            grid-column: span 6;
        }
        .accuracy-panel-history,
        .accuracy-panel-log {
            grid-column: span 12;
        }
    }
    @media (max-width: 760px) {
        .accuracy-panel-config,
        .accuracy-panel-board,
        .accuracy-panel-feedback,
        .accuracy-panel-history,
        .accuracy-panel-log {
            grid-column: span 12;
        }
        .accuracy-panel-feedback {
            max-height: none;
        }
    }
    """
