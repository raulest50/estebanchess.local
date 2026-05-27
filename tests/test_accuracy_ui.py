import chess
import pytest
from nicegui import ui

from chess_move_analyzer import accuracy_ui
from chess_move_analyzer.accuracy_models import MoveFeedback, TrainingConfig, TrainingScenario
from chess_move_analyzer.accuracy_session import TrainingSession
from chess_move_analyzer.models import CandidateLine, EngineEvaluation


def test_accuracy_ui_renders_initial_controls(monkeypatch):
    monkeypatch.setattr(accuracy_ui, "_recent_sessions", lambda: [])
    before = set(ui.context.client.elements)

    accuracy_ui.render_accuracy_training_section()

    created = _created_elements(before)
    labels = {element._props.get("label") for element in created if hasattr(element, "_props")}
    button_texts = {element.text for element in created if type(element).__name__ == "Button"}
    texts = {getattr(element, "text", None) for element in created}
    expansions = [element for element in created if type(element).__name__ == "Expansion"]
    expansion_labels = {element._props.get("label") for element in expansions}
    class_strings = [_class_string(element) for element in created]
    assert {"Source", "Consecutive moves", "Scenarios"}.issubset(labels)
    assert "Lichess PGN" not in labels
    assert "No PGN file uploaded." in texts
    assert {"Recent sessions", "Training log"}.issubset(expansion_labels)
    assert any("accuracy-main-grid" in classes for classes in class_strings)
    assert any("accuracy-panel-board" in classes for classes in class_strings)
    assert any("accuracy-panel-feedback" in classes for classes in class_strings)
    assert "Difficulty" not in labels
    assert "Start Training" in button_texts


def test_accuracy_layout_css_defines_responsive_workspace():
    css = accuracy_ui.accuracy_layout_css()

    assert ".accuracy-main-grid" in css
    assert ".accuracy-secondary-grid" in css
    assert ".accuracy-panel-feedback" in css
    assert ".accuracy-log-frame .progress-log" in css
    assert "@media (max-width: 760px)" in css


def test_next_scenario_control_renders_in_board_panel(monkeypatch):
    monkeypatch.setattr(accuracy_ui, "_recent_sessions", lambda: [])
    previous_state = accuracy_ui.accuracy_state
    session = TrainingSession(TrainingConfig(scenario_count=2), [_scenario(1), _scenario(2)])
    session.awaiting_next = True
    accuracy_ui.accuracy_state = accuracy_ui.AccuracyUiState(session=session, last_feedback=_feedback())
    before = set(ui.context.client.elements)

    try:
        accuracy_ui.render_accuracy_training_section()
    finally:
        accuracy_ui.accuracy_state = previous_state

    created = _created_elements(before)
    next_buttons = [element for element in created if type(element).__name__ == "Button" and element.text == "Next Scenario"]
    assert len(next_buttons) == 1
    assert _has_ancestor_class(next_buttons[0], "accuracy-panel-board")
    assert not _has_ancestor_class(next_buttons[0], "accuracy-panel-feedback")


def test_completed_training_shows_summary_without_next_control(monkeypatch):
    monkeypatch.setattr(accuracy_ui, "_recent_sessions", lambda: [])
    previous_state = accuracy_ui.accuracy_state
    session = TrainingSession(TrainingConfig(scenario_count=1), [_scenario(1)])
    feedback = _feedback()
    session.feedbacks.append(feedback)
    session.awaiting_next = True
    session.completed = True
    accuracy_ui.accuracy_state = accuracy_ui.AccuracyUiState(session=session, last_feedback=feedback)
    before = set(ui.context.client.elements)

    try:
        accuracy_ui.render_accuracy_training_section()
    finally:
        accuracy_ui.accuracy_state = previous_state

    created = _created_elements(before)
    texts = {getattr(element, "text", None) for element in created}
    button_texts = {element.text for element in created if type(element).__name__ == "Button"}
    assert "Next Scenario" not in button_texts
    assert "Training complete" in texts
    assert "Training complete." in texts
    assert "Accuracy" in texts


def test_continuing_sequence_renders_engine_reply_prompt_without_next_control(monkeypatch):
    monkeypatch.setattr(accuracy_ui, "_recent_sessions", lambda: [])
    previous_state = accuracy_ui.accuracy_state
    session = TrainingSession(
        TrainingConfig(scenario_count=2, consecutive_moves=2),
        [_scenario(1), _scenario(2)],
    )
    feedback = _feedback()
    session.feedbacks.append(feedback)
    session.board = chess.Board(feedback.fen_after_user)
    session.board.push(chess.Move.from_uci("e7e5"))
    session.step_index = 1
    accuracy_ui.accuracy_state = accuracy_ui.AccuracyUiState(
        session=session,
        last_feedback=feedback,
        last_move=chess.Move.from_uci("e7e5"),
    )
    before = set(ui.context.client.elements)

    try:
        accuracy_ui.render_accuracy_training_section()
    finally:
        accuracy_ui.accuracy_state = previous_state

    created = _created_elements(before)
    texts = {getattr(element, "text", None) for element in created}
    button_texts = {element.text for element in created if type(element).__name__ == "Button"}
    assert "Stockfish replied: e5" in texts
    assert "Your move 2/2" in texts
    assert "Play your next move on the board." in texts
    assert "Move 1: You e4 | Stockfish e5" in texts
    assert "Next Scenario" not in button_texts


def test_last_applied_move_uses_engine_reply_only_while_sequence_continues():
    session = TrainingSession(
        TrainingConfig(scenario_count=2, consecutive_moves=2),
        [_scenario(1), _scenario(2)],
    )
    feedback = _feedback()
    session.step_index = 1

    assert accuracy_ui._last_applied_move_for_feedback(session, feedback) == chess.Move.from_uci("e7e5")

    session.awaiting_next = True
    assert accuracy_ui._last_applied_move_for_feedback(session, feedback) == chess.Move.from_uci("e2e4")


def test_render_feedback_displays_hidden_analysis_after_move():
    before = set(ui.context.client.elements)

    with ui.column():
        accuracy_ui._render_feedback(_feedback())

    created = _created_elements(before)
    texts = {getattr(element, "text", None) for element in created}
    assert {"Your move", "Top moves", "Best reply", "Worst found"}.issubset(texts)
    assert "e4" in texts


@pytest.mark.anyio
async def test_load_uploaded_pgn_stores_reference_without_copying(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(accuracy_ui.ui, "notify", lambda *args, **kwargs: None)
    previous_state = accuracy_ui.accuracy_state
    upload = _UploadReference("lichess sample.pgn", b"[Event \"Sample\"]\n\n1. e4 *")
    file_label = _FakeElement()
    upload_status = _FakeElement()

    try:
        accuracy_ui.accuracy_state = accuracy_ui.AccuracyUiState()
        await accuracy_ui._load_uploaded_pgn(_UploadEvent(upload), file_label, upload_status, lambda: None)
        assert accuracy_ui.accuracy_state.uploaded_pgn_file is upload
        assert accuracy_ui.accuracy_state.uploaded_pgn_name == "lichess sample.pgn"
        assert accuracy_ui.accuracy_state.uploaded_pgn_size == len(upload._data)
        assert upload.save_called is False
        assert not (tmp_path / "data" / "uploads").exists()
        assert upload_status.text == "Ready"
    finally:
        accuracy_ui.accuracy_state = previous_state


@pytest.mark.anyio
async def test_load_uploaded_pgn_replaces_previous_reference(monkeypatch):
    monkeypatch.setattr(accuracy_ui.ui, "notify", lambda *args, **kwargs: None)
    previous_state = accuracy_ui.accuracy_state
    first = _UploadReference("first.pgn", b"[Event \"First\"]\n\n1. e4 *")
    second = _UploadReference("second.pgn", b"[Event \"Second\"]\n\n1. d4 *")

    try:
        accuracy_ui.accuracy_state = accuracy_ui.AccuracyUiState()
        await accuracy_ui._load_uploaded_pgn(_UploadEvent(first), _FakeElement(), _FakeElement(), lambda: None)
        await accuracy_ui._load_uploaded_pgn(_UploadEvent(second), _FakeElement(), _FakeElement(), lambda: None)
        assert accuracy_ui.accuracy_state.uploaded_pgn_file is second
        assert accuracy_ui.accuracy_state.uploaded_pgn_name == "second.pgn"
    finally:
        accuracy_ui.accuracy_state = previous_state


def test_prepare_training_config_sets_seed_and_automatic_sample_size():
    config = accuracy_ui._prepare_training_config(
        accuracy_ui.TrainingConfig(scenario_count=10, consecutive_moves=3, random_seed=None)
    )

    assert config.max_games == 360
    assert config.random_seed is not None


def _feedback() -> MoveFeedback:
    board = chess.Board()
    move = chess.Move.from_uci("e2e4")
    fen_before = board.fen()
    user_move_san = board.san(move)
    board.push(move)
    evaluation = EngineEvaluation(cp_white=20, expected_white=0.55)
    return MoveFeedback(
        scenario_id=1,
        scenario_index=0,
        step_index=0,
        fen_before=fen_before,
        fen_after_user=board.fen(),
        user_move_uci="e2e4",
        user_move_san=user_move_san,
        eval_before=evaluation,
        eval_after=EngineEvaluation(cp_white=10, expected_white=0.52),
        expected_loss=0.03,
        move_score=85.0,
        classification="excellent",
        top_candidates=[
            CandidateLine(rank=1, move_uci="e2e4", move_san="e4", evaluation=evaluation),
            CandidateLine(rank=2, move_uci="d2d4", move_san="d4", evaluation=evaluation),
        ],
        best_reply=CandidateLine(rank=1, move_uci="e7e5", move_san="e5", evaluation=evaluation),
        worst_found=CandidateLine(rank=1, move_uci="a2a3", move_san="a3", evaluation=evaluation),
    )


def _scenario(scenario_id: int) -> TrainingScenario:
    return TrainingScenario(
        scenario_id=scenario_id,
        fen=chess.Board().fen(),
        source_label="sample",
        game_index=0,
        ply=10,
        move_number=5,
        color="white",
    )


class _UploadEvent:
    def __init__(self, file):
        self.file = file


class _UploadReference:
    def __init__(self, name: str, data: bytes):
        self.name = name
        self._data = data
        self.save_called = False

    def size(self) -> int:
        return len(self._data)

    async def save(self, path):
        self.save_called = True
        path.write_bytes(self._data)


class _FakeElement:
    def __init__(self):
        self.text = ""
        self.props_calls: list[str] = []

    def set_text(self, text: str) -> None:
        self.text = text

    def props(self, value: str):
        self.props_calls.append(value)
        return self


def _created_elements(before: set[int]) -> list[object]:
    return [element for element_id, element in ui.context.client.elements.items() if element_id not in before]


def _class_string(element: object) -> str:
    return " ".join(getattr(element, "_classes", []))


def _has_ancestor_class(element: object, class_name: str) -> bool:
    current = element
    while current is not None:
        if class_name in getattr(current, "_classes", []):
            return True
        parent_slot = getattr(current, "parent_slot", None)
        current = getattr(parent_slot, "parent", None) if parent_slot else None
    return False
