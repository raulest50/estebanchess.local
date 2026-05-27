import chess

from chess_move_analyzer.accuracy_engine import AccuracyEngine
from chess_move_analyzer.engine import AnalysisProfile
from chess_move_analyzer.models import CandidateLine, EngineEvaluation, PositionAnalysis


def test_feedback_skips_deeper_review_when_user_move_is_in_fast_candidates(monkeypatch):
    monkeypatch.setattr(AccuracyEngine, "worst_found", lambda self, board, baseline=None: None)
    board = chess.Board()
    move = chess.Move.from_uci("e2e4")
    after_board = board.copy(stack=False)
    after_board.push(move)
    engine = _FakeEngine(
        {
            (board.fen(), "training", 3): (0.55, ["e2e4", "d2d4", "g1f3"]),
            (after_board.fen(), "training", 2): (0.55, ["e7e5", "c7c5"]),
        }
    )

    feedback = AccuracyEngine(engine, _FakeStorage()).feedback_for_move(board, move, 1, 0, 0)

    assert feedback.move_score == 100.0
    assert feedback.top_candidates[0].move_uci == "e2e4"
    assert feedback.best_reply is not None
    assert feedback.best_reply.move_uci == "e7e5"
    assert all(call.profile_name != "training-review" for call in engine.calls)


def test_feedback_runs_deeper_review_for_high_score_move_missing_from_fast_candidates(monkeypatch):
    monkeypatch.setattr(AccuracyEngine, "worst_found", lambda self, board, baseline=None: None)
    board = chess.Board()
    move = chess.Move.from_uci("e2e4")
    after_board = board.copy(stack=False)
    after_board.push(move)
    engine = _FakeEngine(
        {
            (board.fen(), "training", 3): (0.55, ["d2d4", "g1f3", "c2c4"]),
            (after_board.fen(), "training", 2): (0.55, ["e7e5", "c7c5"]),
            (board.fen(), "training-review", 5): (0.60, ["d2d4", "g1f3", "c2c4", "b1c3", "f1b5"]),
            (after_board.fen(), "training-review", 5): (0.50, ["e7e5", "c7c5", "g8f6", "d7d5", "b8c6"]),
        }
    )

    feedback = AccuracyEngine(engine, _FakeStorage()).feedback_for_move(board, move, 1, 0, 0)

    review_calls = [call for call in engine.calls if call.profile_name == "training-review"]
    assert len(review_calls) == 2
    assert {call.multipv for call in review_calls} == {5}
    assert {call.seconds_per_position for call in review_calls} == {0.75}
    assert {call.hash_mb for call in review_calls} == {512}
    assert feedback.expected_loss == 0.1
    assert feedback.move_score == 50.0
    assert feedback.classification == "inaccuracy"
    assert [candidate.move_uci for candidate in feedback.top_candidates] == [
        "d2d4",
        "g1f3",
        "c2c4",
        "b1c3",
        "f1b5",
    ]
    assert feedback.best_reply is not None
    assert feedback.best_reply.move_uci == "e7e5"


def test_feedback_preserves_high_score_when_deeper_review_confirms_no_loss(monkeypatch):
    monkeypatch.setattr(AccuracyEngine, "worst_found", lambda self, board, baseline=None: None)
    board = chess.Board()
    move = chess.Move.from_uci("e2e4")
    after_board = board.copy(stack=False)
    after_board.push(move)
    engine = _FakeEngine(
        {
            (board.fen(), "training", 3): (0.55, ["d2d4", "g1f3", "c2c4"]),
            (after_board.fen(), "training", 2): (0.55, ["e7e5", "c7c5"]),
            (board.fen(), "training-review", 5): (0.58, ["d2d4", "e2e4", "g1f3", "c2c4", "b1c3"]),
            (after_board.fen(), "training-review", 5): (0.58, ["e7e5", "c7c5", "g8f6", "d7d5", "b8c6"]),
        }
    )

    feedback = AccuracyEngine(engine, _FakeStorage()).feedback_for_move(board, move, 1, 0, 0)

    assert any(call.profile_name == "training-review" for call in engine.calls)
    assert feedback.expected_loss == 0.0
    assert feedback.move_score == 100.0
    assert len(feedback.top_candidates) == 5


def test_feedback_skips_deeper_review_for_low_score_move_missing_from_fast_candidates(monkeypatch):
    monkeypatch.setattr(AccuracyEngine, "worst_found", lambda self, board, baseline=None: None)
    board = chess.Board()
    move = chess.Move.from_uci("e2e4")
    after_board = board.copy(stack=False)
    after_board.push(move)
    engine = _FakeEngine(
        {
            (board.fen(), "training", 3): (0.80, ["d2d4", "g1f3", "c2c4"]),
            (after_board.fen(), "training", 2): (0.50, ["e7e5", "c7c5"]),
        }
    )

    feedback = AccuracyEngine(engine, _FakeStorage()).feedback_for_move(board, move, 1, 0, 0)

    assert feedback.move_score == 0.0
    assert all(call.profile_name != "training-review" for call in engine.calls)


class _FakeEngine:
    engine_name = "Fakefish"

    def __init__(self, plans: dict[tuple[str, str, int], tuple[float, list[str]]]) -> None:
        self.plans = plans
        self.calls: list[_EngineCall] = []

    def analyze_position(self, board: chess.Board, profile: AnalysisProfile) -> PositionAnalysis:
        self.calls.append(
            _EngineCall(
                profile_name=profile.name,
                multipv=profile.multipv,
                seconds_per_position=profile.seconds_per_position,
                hash_mb=profile.hash_mb,
            )
        )
        expected_white, move_ucis = self.plans[(board.fen(), profile.name, profile.multipv)]
        return _analysis(board, profile, expected_white, move_ucis, self.engine_name)


class _EngineCall:
    def __init__(self, profile_name: str, multipv: int, seconds_per_position: float, hash_mb: int) -> None:
        self.profile_name = profile_name
        self.multipv = multipv
        self.seconds_per_position = seconds_per_position
        self.hash_mb = hash_mb


class _FakeStorage:
    def get_position(self, fen: str, engine_name: str, profile: str, multipv: int):
        return None

    def save_position(self, analysis: PositionAnalysis) -> None:
        pass


def _analysis(
    board: chess.Board,
    profile: AnalysisProfile,
    expected_white: float,
    move_ucis: list[str],
    engine_name: str,
) -> PositionAnalysis:
    evaluation = EngineEvaluation(cp_white=int((expected_white - 0.5) * 800), expected_white=expected_white)
    return PositionAnalysis(
        fen=board.fen(),
        engine_name=engine_name,
        profile=profile.name,
        multipv=profile.multipv,
        evaluation=evaluation,
        candidates=[
            CandidateLine(
                rank=index,
                move_uci=move_uci,
                move_san=_san_or_uci(board, move_uci),
                evaluation=evaluation,
                pv_uci=[move_uci],
                pv_san=[_san_or_uci(board, move_uci)],
            )
            for index, move_uci in enumerate(move_ucis, start=1)
        ],
    )


def _san_or_uci(board: chess.Board, move_uci: str) -> str:
    move = chess.Move.from_uci(move_uci)
    return board.san(move) if move in board.legal_moves else move_uci
