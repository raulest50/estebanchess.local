from nicegui import ui

import chess

from chess_move_analyzer.app import (
    state,
    _chart_options,
    _clear_pv_selection,
    _detail_line,
    _empty_chart,
    _move_clock_label,
    _move_owner_badge_label,
    _normalize_user_color,
    _render_analysis,
    _render_detail,
    _resolve_host,
    _resolve_show,
    _select_move,
    _select_pv_move,
    _select_reply_pv_move,
    _select_relative_move,
    _should_display_reply_after,
    _should_show_move_clocks,
    _run_analysis,
    _select_candidate_pv_move,
    _user_color_badge_label,
)
from chess_move_analyzer.board_view import create_board_panel
from chess_move_analyzer.models import CandidateLine, EngineEvaluation, GameAnalysis, GameRecord, MoveAnalysis


def test_detail_line_uses_nicegui_labels_without_attribute_error():
    with ui.column():
        assert _detail_line("Played", "e2e4") is None


def test_runtime_host_and_show_are_configurable(monkeypatch):
    monkeypatch.delenv("CHESS_ANALYZER_HOST", raising=False)
    monkeypatch.delenv("CHESS_ANALYZER_SHOW", raising=False)

    assert _resolve_host() == "127.0.0.1"
    assert _resolve_show() is True

    monkeypatch.setenv("CHESS_ANALYZER_HOST", "0.0.0.0")
    monkeypatch.setenv("CHESS_ANALYZER_SHOW", "false")

    assert _resolve_host() == "0.0.0.0"
    assert _resolve_show() is False


def test_render_analysis_uses_column_context_without_add():
    result = GameAnalysis(
        game=GameRecord(pgn="1. e4 *", white="A", black="B"),
        moves=[
            MoveAnalysis(
                ply=1,
                move_number=1,
                color="white",
                san="e4",
                uci="e2e4",
                fen_before="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                fen_after="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
                eval_before=EngineEvaluation(cp_white=20, expected_white=0.53),
                eval_after=EngineEvaluation(cp_white=25, expected_white=0.54),
                expected_loss=0.0,
                classification="excellent",
                best_move_uci="e2e4",
                best_move_san="e4",
                pv_san=["e4"],
                pv_uci=["e2e4"],
            )
        ],
        final_fen="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
        engine_name="Stockfish 18",
        profile="fast",
    )
    with ui.column() as moves_container:
        pass
    board_panel = create_board_panel(chess.Board())
    detail_panel = ui.column()
    chart = ui.echart(_empty_chart())

    assert _render_analysis(result, moves_container, board_panel, detail_panel, chart) is None


def test_render_analysis_marks_move_rows_by_color_and_selection():
    result = _sample_analysis()
    with ui.column() as moves_container:
        pass
    board_panel = create_board_panel(chess.Board())
    detail_panel = ui.column()
    chart = ui.echart(_empty_chart())

    assert _render_analysis(result, moves_container, board_panel, detail_panel, chart) is None

    white_classes = set(state.move_buttons[0]._classes)
    black_classes = set(state.move_buttons[1]._classes)
    assert "move-row-white" in white_classes
    assert "move-row-black" in black_classes
    assert "move-row-selected" not in white_classes
    assert "move-row-selected" in black_classes

    assert _select_move(0, board_panel, detail_panel) is None

    white_classes = set(state.move_buttons[0]._classes)
    black_classes = set(state.move_buttons[1]._classes)
    assert "move-row-selected" in white_classes
    assert "move-row-selected" not in black_classes


def test_render_analysis_supports_post_move_clocks():
    result = _sample_analysis()
    result.moves[0].clock = "0:02:44.8"
    with ui.column() as moves_container:
        pass
    board_panel = create_board_panel(chess.Board())
    detail_panel = ui.column()
    chart = ui.echart(_empty_chart())

    assert _render_analysis(result, moves_container, board_panel, detail_panel, chart) is None

    white_classes = set(state.move_buttons[0]._classes)
    black_classes = set(state.move_buttons[1]._classes)
    assert "move-row-white" in white_classes
    assert "move-row-black" in black_classes
    assert "move-row-selected" in black_classes


def test_detail_pv_selection_blocks_relative_navigation_and_can_clear():
    result = GameAnalysis(
        game=GameRecord(pgn="1. e4 e5 *", white="A", black="B"),
        moves=[
            MoveAnalysis(
                ply=1,
                move_number=1,
                color="white",
                san="e4",
                uci="e2e4",
                fen_before="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                fen_after="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
                eval_before=EngineEvaluation(cp_white=20, expected_white=0.53),
                eval_after=EngineEvaluation(cp_white=25, expected_white=0.54),
                expected_loss=0.0,
                classification="excellent",
                best_move_uci="e2e4",
                best_move_san="e4",
                pv_san=["e4", "e5"],
                pv_uci=["e2e4", "e7e5"],
            ),
            MoveAnalysis(
                ply=2,
                move_number=1,
                color="black",
                san="e5",
                uci="e7e5",
                fen_before="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
                fen_after="rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2",
                eval_before=EngineEvaluation(cp_white=25, expected_white=0.54),
                eval_after=EngineEvaluation(cp_white=10, expected_white=0.52),
                expected_loss=0.0,
                classification="excellent",
            ),
        ],
        final_fen="rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2",
        engine_name="Stockfish 18",
        profile="fast",
    )
    board_panel = create_board_panel(chess.Board())
    detail_panel = ui.column()
    state.analysis = result
    state.selected = result.moves[0]
    state.selected_index = 0
    state.selected_pv_index = None

    assert _render_detail(detail_panel, board_panel) is None
    assert _select_pv_move(1, board_panel, detail_panel) is None
    assert state.selected_pv_index == 1
    assert _select_relative_move(1, board_panel, detail_panel) is None
    assert state.selected_index == 0
    assert _clear_pv_selection(board_panel, detail_panel) is None
    assert state.selected_pv_index is None


def test_detail_candidate_pv_selection_tracks_rank_and_blocks_navigation():
    result = GameAnalysis(
        game=GameRecord(pgn="1. e4 *", white="A", black="B"),
        moves=[
            MoveAnalysis(
                ply=1,
                move_number=1,
                color="white",
                san="e4",
                uci="e2e4",
                fen_before="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                fen_after="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
                eval_before=EngineEvaluation(cp_white=20, expected_white=0.53),
                eval_after=EngineEvaluation(cp_white=25, expected_white=0.54),
                expected_loss=0.0,
                classification="excellent",
                candidates=[
                    CandidateLine(
                        rank=1,
                        move_uci="e2e4",
                        move_san="e4",
                        evaluation=EngineEvaluation(cp_white=30, expected_white=0.55),
                        pv_uci=["e2e4", "e7e5"],
                        pv_san=["e4", "e5"],
                    ),
                    CandidateLine(
                        rank=2,
                        move_uci="d2d4",
                        move_san="d4",
                        evaluation=EngineEvaluation(cp_white=12, expected_white=0.52),
                        pv_uci=["d2d4", "g8f6"],
                        pv_san=["d4", "Nf6"],
                    ),
                ],
            ),
            MoveAnalysis(
                ply=2,
                move_number=1,
                color="black",
                san="e5",
                uci="e7e5",
                fen_before="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
                fen_after="rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2",
                eval_before=EngineEvaluation(cp_white=25, expected_white=0.54),
                eval_after=EngineEvaluation(cp_white=10, expected_white=0.52),
                expected_loss=0.0,
                classification="excellent",
            ),
        ],
        final_fen="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
        engine_name="Stockfish 18",
        profile="fast",
    )
    board_panel = create_board_panel(chess.Board())
    detail_panel = ui.column()
    state.analysis = result
    state.selected = result.moves[0]
    state.selected_index = 0
    state.selected_candidate_rank = None
    state.selected_pv_index = None

    assert _render_detail(detail_panel, board_panel) is None
    assert _select_candidate_pv_move(2, 1, board_panel, detail_panel) is None
    assert state.selected_candidate_rank == 2
    assert state.selected_pv_index == 1
    assert _select_relative_move(1, board_panel, detail_panel) is None
    assert state.selected_index == 0
    assert _clear_pv_selection(board_panel, detail_panel) is None
    assert state.selected_candidate_rank is None
    assert state.selected_pv_index is None


def test_reply_after_is_shown_only_for_relevant_errors():
    result = _sample_analysis()
    mistake = result.moves[1]
    mistake.reply_move_uci = "g1f3"
    mistake.reply_move_san = "Nf3"
    mistake.reply_pv_uci = ["g1f3"]
    mistake.reply_pv_san = ["Nf3"]

    excellent = result.moves[0]
    excellent.reply_move_uci = "e7e5"
    excellent.reply_move_san = "e5"
    excellent.reply_pv_uci = ["e7e5"]
    excellent.reply_pv_san = ["e5"]

    assert _should_display_reply_after(mistake) is True
    assert _should_display_reply_after(excellent) is False


def test_reply_pv_selection_uses_fen_after():
    result = _sample_analysis()
    move = result.moves[0]
    move.classification = "blunder"
    move.reply_move_uci = "e7e5"
    move.reply_move_san = "e5"
    move.reply_pv_uci = ["e7e5", "g1f3"]
    move.reply_pv_san = ["e5", "Nf3"]
    board_panel = create_board_panel(chess.Board())
    detail_panel = ui.column()
    state.analysis = result
    state.selected = move
    state.selected_index = 0
    state.selected_pv_source = None
    state.selected_candidate_rank = None
    state.selected_pv_index = None

    assert _render_detail(detail_panel, board_panel) is None
    assert _select_reply_pv_move(0, board_panel, detail_panel) is None
    assert state.selected_pv_source == "reply"
    assert state.selected_candidate_rank is None
    assert state.selected_pv_index == 0
    assert _select_relative_move(1, board_panel, detail_panel) is None
    assert state.selected_index == 0


def test_user_color_badge_labels_are_normalized():
    assert _normalize_user_color("black") == "black"
    assert _normalize_user_color("invalid") == "white"
    assert _user_color_badge_label("black") == "You: Black"


def test_move_owner_badge_label_distinguishes_user_move():
    move = MoveAnalysis(
        ply=1,
        move_number=1,
        color="black",
        san="e5",
        uci="e7e5",
        fen_before="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
        fen_after="rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2",
        eval_before=EngineEvaluation(cp_white=25, expected_white=0.54),
        eval_after=EngineEvaluation(cp_white=10, expected_white=0.52),
        expected_loss=0.0,
        classification="excellent",
    )

    assert _move_owner_badge_label(move, "black") == "Your move"
    assert _move_owner_badge_label(move, "white") == "Opponent"


def test_move_clock_helpers_use_only_pgn_clock_values():
    result = _sample_analysis()

    assert _should_show_move_clocks(result) is False
    assert _move_clock_label(result.moves[0]) == ""

    result.moves[1].clock = "0:02:44.8"

    assert _should_show_move_clocks(result) is True
    assert _move_clock_label(result.moves[1]) == "0:02:44.8"
    assert _move_clock_label(result.moves[0]) == ""


def test_run_analysis_accepts_multipv_parameter():
    assert callable(_run_analysis)


def test_chart_options_use_side_areas_instead_of_user_areas():
    options = _chart_options(_sample_analysis(), "white")

    assert options["legend"]["data"] == ["White area", "Black area", "White expected score"]
    assert options["grid"]["show"] is True
    assert options["grid"]["backgroundColor"] == "#eef1f5"
    assert options["series"][0]["name"] == "White area"
    assert options["series"][0]["data"] == [0.54, 0.2]
    assert options["series"][0]["stack"] == "player-area"
    assert options["series"][0]["areaStyle"]["color"] == "#ffffff"
    assert options["series"][0]["tooltip"] == {"show": False}
    assert options["series"][1]["name"] == "Black area"
    assert options["series"][1]["data"] == [0.46, 0.8]
    assert options["series"][1]["stack"] == "player-area"
    assert options["series"][1]["areaStyle"]["color"] == "#111827"
    assert options["series"][2]["name"] == "White expected score"
    assert options["series"][2]["data"] == [0.54, 0.2]
    assert all("markLine" not in series for series in options["series"])


def test_chart_options_do_not_change_side_areas_with_user_color():
    white_user_options = _chart_options(_sample_analysis(), "white")
    black_user_options = _chart_options(_sample_analysis(), "black")

    assert black_user_options["legend"] == white_user_options["legend"]
    assert black_user_options["grid"] == white_user_options["grid"]
    assert black_user_options["series"][0] == white_user_options["series"][0]
    assert black_user_options["series"][1] == white_user_options["series"][1]
    assert "You" not in " ".join(black_user_options["legend"]["data"])
    assert "Opponent" not in " ".join(black_user_options["legend"]["data"])


def _sample_analysis() -> GameAnalysis:
    return GameAnalysis(
        game=GameRecord(pgn="1. e4 e5 *", white="A", black="B"),
        moves=[
            MoveAnalysis(
                ply=1,
                move_number=1,
                color="white",
                san="e4",
                uci="e2e4",
                fen_before="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                fen_after="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
                eval_before=EngineEvaluation(cp_white=20, expected_white=0.53),
                eval_after=EngineEvaluation(cp_white=25, expected_white=0.54),
                expected_loss=0.0,
                classification="excellent",
            ),
            MoveAnalysis(
                ply=2,
                move_number=1,
                color="black",
                san="e5",
                uci="e7e5",
                fen_before="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
                fen_after="rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2",
                eval_before=EngineEvaluation(cp_white=25, expected_white=0.54),
                eval_after=EngineEvaluation(cp_white=-180, expected_white=0.2),
                expected_loss=0.1,
                classification="mistake",
            ),
        ],
        final_fen="rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2",
        engine_name="Stockfish 18",
        profile="fast",
    )
