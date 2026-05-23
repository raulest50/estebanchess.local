from __future__ import annotations

import chess
import chess.svg
from nicegui import ui

DEFAULT_BOARD_SIZE = 430


def render_board_svg(
    board: chess.Board,
    last_move: chess.Move | None = None,
    arrows: list[chess.svg.Arrow] | None = None,
    size: int = DEFAULT_BOARD_SIZE,
) -> str:
    svg = chess.svg.board(board=board, lastmove=last_move, arrows=arrows or [], size=size)
    return f"<div style='max-width: {size}px; width: 100%;'>{svg}</div>"


def create_board_panel(board: chess.Board, size: int = DEFAULT_BOARD_SIZE):
    return ui.html(render_board_svg(board, size=size), sanitize=False).classes("panel")


def update_board_panel(
    panel,
    board: chess.Board,
    last_move: chess.Move | None = None,
    arrows: list[chess.svg.Arrow] | None = None,
    size: int = DEFAULT_BOARD_SIZE,
) -> None:
    panel.set_content(render_board_svg(board, last_move=last_move, arrows=arrows, size=size))


def move_arrow(move: chess.Move, color: str = "blue") -> chess.svg.Arrow:
    return chess.svg.Arrow(move.from_square, move.to_square, color=color)
