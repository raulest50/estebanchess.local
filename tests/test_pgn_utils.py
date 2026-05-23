from chess_move_analyzer.pgn_utils import clock_to_seconds, iter_basic_moves, parse_time_control

PGN = """
[Event "Live Chess"]
[Site "Chess.com"]
[Date "2026.05.20"]
[White "WhitePlayer"]
[Black "BlackPlayer"]
[Result "1-0"]
[TimeControl "60+1"]

1. e4 {[%clk 0:00:59]} e5 {[%clk 0:00:58]} 2. Nf3 {[%clk 0:00:57]} Nc6 {[%clk 0:00:57]} 1-0
"""


def test_clock_to_seconds():
    assert clock_to_seconds("0:03:21") == 201
    assert clock_to_seconds("3:21") == 201


def test_parse_time_control():
    tc = parse_time_control("60+1")
    assert tc is not None
    assert tc.initial_seconds == 60
    assert tc.increment_seconds == 1


def test_iter_basic_moves_extracts_clocks_and_time_spent():
    moves = iter_basic_moves(PGN)
    assert len(moves) == 4
    assert moves[0].san == "e4"
    assert moves[0].move_number == 1
    assert moves[0].clock == "0:00:59"
    assert moves[0].time_spent_seconds == 2
    assert moves[1].san == "e5"
    assert moves[1].move_number == 1
    assert moves[1].time_spent_seconds == 3
