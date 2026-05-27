import chess
from nicegui import ui

from chess_move_analyzer.accuracy_board import render_training_board, training_board_css


def test_render_training_board_creates_64_square_buttons():
    before = set(ui.context.client.elements)

    render_training_board(chess.Board(), lambda square: None)

    created = [element for element_id, element in ui.context.client.elements.items() if element_id not in before]
    buttons = [element for element in created if type(element).__name__ == "Button"]
    html_elements = [element for element in created if type(element).__name__ == "Html"]
    piece_markup = "\n".join(element.content for element in html_elements)
    assert len(buttons) == 64
    assert {button.text for button in buttons} == {""}
    assert "white-king" in piece_markup
    assert "black-king" in piece_markup
    assert "<svg" in piece_markup


def test_training_board_css_contains_stable_square_classes():
    css = training_board_css()

    assert ".training-board" in css
    assert ".training-square-selected" in css
    assert ".training-piece svg" in css
    assert "pointer-events: none" in css
