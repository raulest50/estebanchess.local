from chess_move_analyzer.models import CandidateLine, EngineEvaluation, PositionAnalysis
from chess_move_analyzer.storage import AnalysisStorage


def test_position_cache_roundtrip(tmp_path):
    storage_path = tmp_path / "analysis.sqlite"
    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    analysis = PositionAnalysis(
        fen=fen,
        engine_name="Stockfish 18",
        profile="balanced",
        multipv=3,
        best_move_uci="e2e4",
        pv_uci=["e2e4", "e7e5"],
        evaluation=EngineEvaluation(cp_white=32, expected_white=0.55),
        candidates=[
            CandidateLine(
                rank=1,
                move_uci="e2e4",
                move_san="e4",
                evaluation=EngineEvaluation(cp_white=32, expected_white=0.55),
                pv_uci=["e2e4", "e7e5"],
                pv_san=["e4", "e5"],
            )
        ],
    )
    with AnalysisStorage(storage_path) as storage:
        assert storage.get_position(fen, "Stockfish 18", "balanced", 3) is None
        storage.save_position(analysis)
        cached = storage.get_position(fen, "Stockfish 18", "balanced", 3)
        other_multipv = storage.get_position(fen, "Stockfish 18", "balanced", 1)

    assert cached is not None
    assert cached.best_move_uci == "e2e4"
    assert cached.evaluation.expected_white == 0.55
    assert cached.candidates[0].pv_san == ["e4", "e5"]
    assert other_multipv is None
