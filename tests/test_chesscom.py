import pytest

from chess_move_analyzer.chesscom import ChessComImportError, parse_chesscom_url


def test_parse_live_game_url():
    parsed = parse_chesscom_url("https://www.chess.com/game/live/123456789")
    assert parsed.game_id == "123456789"
    assert parsed.kind == "live"


def test_parse_analysis_game_url():
    parsed = parse_chesscom_url("https://www.chess.com/analysis/game/live/987654321")
    assert parsed.game_id == "987654321"
    assert parsed.kind == "live"


def test_rejects_unsupported_url():
    with pytest.raises(ChessComImportError):
        parse_chesscom_url("https://example.com/game/live/123")

