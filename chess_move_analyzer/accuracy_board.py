from __future__ import annotations

from collections.abc import Callable
from typing import Any

import chess
import chess.svg
from nicegui import ui


def render_training_board(
    board: chess.Board,
    on_square_click: Callable[[int], Any],
    selected_square: int | None = None,
    last_move: chess.Move | None = None,
) -> None:
    with ui.grid(columns=8).classes("training-board"):
        for rank in range(7, -1, -1):
            for file_index in range(8):
                square = chess.square(file_index, rank)
                piece = board.piece_at(square)
                button = ui.button(on_click=lambda sq=square: on_square_click(sq))
                button.props("flat dense no-caps")
                button.classes(_square_classes(square, selected_square, last_move))
                button.tooltip(chess.square_name(square))
                if piece:
                    with button:
                        ui.html(chess.svg.piece(piece, size=42), sanitize=False).classes("training-piece")


def training_board_css() -> str:
    return """
    .training-board {
        border: 1px solid #9ca3af;
        display: grid;
        gap: 0;
        max-width: 430px;
        width: min(100%, 430px);
    }
    .training-square {
        align-items: center;
        aspect-ratio: 1 / 1;
        border-radius: 0;
        display: flex;
        justify-content: center;
        min-height: 0;
        width: 100%;
    }
    .training-square .q-btn__content {
        align-items: center;
        display: flex;
        height: 100%;
        justify-content: center;
        min-width: 0;
        width: 100%;
    }
    .training-piece {
        align-items: center;
        display: flex;
        height: 88%;
        justify-content: center;
        pointer-events: none;
        width: 88%;
    }
    .training-piece svg {
        display: block;
        height: 100%;
        pointer-events: none;
        width: 100%;
    }
    .training-square-light { background: #f0d9b5; color: #111827; }
    .training-square-dark { background: #b58863; color: #111827; }
    .training-square-selected {
        box-shadow: 0 0 0 3px #2563eb inset;
    }
    .training-square-last {
        box-shadow: 0 0 0 3px #f59e0b inset;
    }
    """


def _square_classes(square: int, selected_square: int | None, last_move: chess.Move | None) -> str:
    color_class = "training-square-light" if chess.square_rank(square) % 2 == chess.square_file(square) % 2 else "training-square-dark"
    classes = ["training-square", color_class]
    if selected_square == square:
        classes.append("training-square-selected")
    if last_move and square in {last_move.from_square, last_move.to_square}:
        classes.append("training-square-last")
    return " ".join(classes)
