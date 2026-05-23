import chess
from nicegui import ui

from chess_move_analyzer.board_view import create_board_panel, move_arrow, render_board_svg, update_board_panel


def test_render_board_svg_contains_piece_symbols():
    svg = render_board_svg(chess.Board())
    assert "<svg" in svg
    assert "white-king" in svg
    assert "black-king" in svg
    assert "<use" in svg


def test_render_board_svg_with_last_move_keeps_pieces():
    board = chess.Board()
    move = chess.Move.from_uci("e2e4")
    board.push(move)
    svg = render_board_svg(board, last_move=move)
    assert "white-king" in svg
    assert "black-king" in svg
    assert "<use" in svg


def test_create_and_update_board_panel_do_not_fail():
    panel = create_board_panel(chess.Board())
    assert panel._props["sanitize"] is False
    board = chess.Board()
    move = chess.Move.from_uci("e2e4")
    board.push(move)
    assert update_board_panel(panel, board, last_move=move) is None


def test_render_board_svg_with_arrow_keeps_pieces():
    board = chess.Board()
    move = chess.Move.from_uci("e2e4")
    board.push(move)
    svg = render_board_svg(board, last_move=move, arrows=[move_arrow(move)])
    assert "white-king" in svg
    assert "black-king" in svg
    assert "arrow" in svg
