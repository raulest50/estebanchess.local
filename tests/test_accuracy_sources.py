import httpx
import pytest

from chess_move_analyzer.accuracy_models import TrainingConfig
from chess_move_analyzer.accuracy_sources import ChessComPersonalSource, LichessPgnSource, games_from_pgn_collection, games_from_pgn_file

PGN_ONE = """
[Event "Rated Rapid"]
[Site "https://lichess.org/abc"]
[Date "2026.05.20"]
[White "A"]
[Black "B"]
[Result "1-0"]

1. e4 e5 2. Nf3 Nc6 1-0
"""

PGN_TWO = """
[Event "Live Chess"]
[Site "Chess.com"]
[Date "2026.05.21"]
[White "C"]
[Black "D"]
[Result "0-1"]

1. d4 Nf6 2. c4 g6 0-1
"""


def test_games_from_pgn_collection_reads_multiple_games():
    games = games_from_pgn_collection(PGN_ONE + "\n\n" + PGN_TWO, "sample")

    assert len(games) == 2
    assert games[0].white == "A"
    assert games[1].black == "D"
    assert "1. d4" in games[1].pgn


def test_games_from_pgn_collection_stops_at_max_games():
    games = games_from_pgn_collection(PGN_ONE + "\n\n" + PGN_TWO, "sample", max_games=1)

    assert len(games) == 1
    assert games[0].white == "A"


def test_games_from_pgn_file_reads_local_path_with_limit(tmp_path):
    pgn_path = tmp_path / "sample.pgn"
    pgn_path.write_text(PGN_ONE + "\n\n" + PGN_TWO, encoding="utf-8")

    games = games_from_pgn_file(pgn_path, "file", max_games=1)

    assert len(games) == 1
    assert games[0].source_label == "file"


def test_lichess_source_loads_uploaded_file_from_temp_path_without_saving(tmp_path):
    pgn_path = tmp_path / "uploaded.pgn"
    pgn_path.write_text(PGN_ONE + "\n\n" + PGN_TWO, encoding="utf-8")
    upload = _UploadedTempFile(pgn_path)

    games = LichessPgnSource().load_uploaded_games_sync(
        TrainingConfig(source="lichess_pgn", max_games=1, random_seed=1),
        upload,
    )

    assert len(games) == 1
    assert upload.save_called is False
    assert not (tmp_path / "data" / "uploads").exists()


def test_lichess_source_loads_uploaded_small_file_from_memory():
    upload = _UploadedMemoryFile(PGN_ONE.encode("utf-8") + b"\n\n" + PGN_TWO.encode("utf-8"))

    games = LichessPgnSource().load_uploaded_games_sync(
        TrainingConfig(source="lichess_pgn", max_games=1),
        upload,
    )

    assert len(games) == 1
    assert games[0].white == "A"


@pytest.mark.anyio
async def test_lichess_source_loads_games_from_pasted_pgn():
    games = await LichessPgnSource().load_games(
        TrainingConfig(source="lichess_pgn", lichess_pgn=PGN_ONE + "\n\n" + PGN_TWO)
    )

    assert len(games) == 2
    assert all(game.source_label == "Lichess public PGN" for game in games)


@pytest.mark.anyio
async def test_lichess_source_loads_games_from_local_path(tmp_path):
    pgn_path = tmp_path / "lichess.pgn"
    pgn_path.write_text(PGN_ONE + "\n\n" + PGN_TWO, encoding="utf-8")

    games = await LichessPgnSource().load_games(
        TrainingConfig(source="lichess_pgn", lichess_pgn_path=str(pgn_path), max_games=1, random_seed=1)
    )

    assert len(games) == 1
    assert games[0].source_label == "Lichess public PGN"


@pytest.mark.anyio
async def test_chesscom_source_loads_recent_archives_with_mocked_http():
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/games/archives"):
            return httpx.Response(
                200,
                json={
                    "archives": [
                        "https://api.chess.com/pub/player/demo/games/2026/03",
                        "https://api.chess.com/pub/player/demo/games/2026/04",
                    ]
                },
            )
        return httpx.Response(200, json={"games": [{"pgn": PGN_ONE}, {"pgn": PGN_TWO}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        games = await ChessComPersonalSource().load_games(
            TrainingConfig(source="chesscom", chesscom_username="Demo", recent_months=1, max_games=2),
            client=client,
        )
    finally:
        await client.aclose()

    assert len(games) == 2
    assert all(game.source_label == "Chess.com personal games" for game in games)


class _UploadedTempFile:
    name = "uploaded.pgn"

    def __init__(self, path):
        self._path = path
        self.save_called = False

    def size(self):
        return self._path.stat().st_size

    async def save(self, path):
        self.save_called = True
        path.write_text("should not be saved", encoding="utf-8")


class _UploadedMemoryFile:
    name = "memory.pgn"

    def __init__(self, data: bytes):
        self._data = data

    def size(self):
        return len(self._data)
