from __future__ import annotations

import io
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TextIO

import chess.pgn
import httpx

from .accuracy_models import TrainingConfig, TrainingGame
from .accuracy_pgn_index import games_from_indexed_pgn_file, games_from_sampled_pgn_file, training_game_from_pgn_game

CHESSCOM_ARCHIVES_URL = "https://api.chess.com/pub/player/{username}/games/archives"
CHESSCOM_USER_AGENT = "chess-move-analyzer/0.1 (+local accuracy-training)"


class TrainingSourceError(RuntimeError):
    pass


def games_from_pgn_collection(pgn_text: str, source_label: str, max_games: int | None = None) -> list[TrainingGame]:
    stream = io.StringIO(pgn_text.strip())
    return games_from_pgn_stream(stream, source_label, max_games=max_games)


def games_from_pgn_file(path: str | Path, source_label: str, max_games: int | None = None) -> list[TrainingGame]:
    with Path(path).open("r", encoding="utf-8", errors="replace") as stream:
        return games_from_pgn_stream(stream, source_label, max_games=max_games)


def games_from_pgn_stream(stream: TextIO, source_label: str, max_games: int | None = None) -> list[TrainingGame]:
    games: list[TrainingGame] = []
    while True:
        if max_games is not None and len(games) >= max_games:
            break
        game = chess.pgn.read_game(stream)
        if game is None:
            break
        games.append(training_game_from_pgn_game(game, source_label))
    return games


class LichessPgnSource:
    async def load_games(self, config: TrainingConfig) -> list[TrainingGame]:
        games = self.load_games_sync(config)
        return games

    def load_games_sync(self, config: TrainingConfig) -> list[TrainingGame]:
        if config.lichess_pgn_path:
            games = games_from_indexed_pgn_file(
                config.lichess_pgn_path,
                "Lichess public PGN",
                max_games=config.max_games,
                random_seed=config.random_seed,
            )
        elif config.lichess_pgn and config.lichess_pgn.strip():
            games = games_from_pgn_collection(config.lichess_pgn, "Lichess public PGN", max_games=config.max_games)
        else:
            raise TrainingSourceError("Upload a PGN file for the Lichess source.")
        if not games:
            raise TrainingSourceError("No valid PGN games were found in the Lichess input.")
        return games

    def load_uploaded_games_sync(self, config: TrainingConfig, upload_file: object) -> list[TrainingGame]:
        path = _uploaded_file_path(upload_file)
        if path is not None:
            if not path.exists():
                raise TrainingSourceError("Upload the PGN file again.")
            games = games_from_sampled_pgn_file(
                path,
                "Lichess public PGN",
                max_games=config.max_games,
                random_seed=config.random_seed,
            )
        else:
            pgn_text = _uploaded_file_text_sync(upload_file)
            games = games_from_pgn_collection(pgn_text, "Lichess public PGN", max_games=config.max_games)
        if not games:
            raise TrainingSourceError("No valid PGN games were found in the Lichess input.")
        return games


class ChessComPersonalSource:
    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout

    async def load_games(
        self,
        config: TrainingConfig,
        client: httpx.AsyncClient | None = None,
    ) -> list[TrainingGame]:
        username = (config.chesscom_username or "").strip()
        if not username:
            raise TrainingSourceError("Enter a Chess.com username.")

        close_client = client is None
        if client is None:
            client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                headers={"User-Agent": CHESSCOM_USER_AGENT, "Accept": "application/json"},
            )

        try:
            archives_payload = await self._get_json(client, CHESSCOM_ARCHIVES_URL.format(username=username.lower()))
            archive_urls = _archive_urls(archives_payload)
            if not archive_urls:
                raise TrainingSourceError("No public Chess.com monthly archives were found for this user.")

            selected_archives = archive_urls[-config.recent_months :]
            pgns: list[str] = []
            for archive_url in reversed(selected_archives):
                payload = await self._get_json(client, archive_url)
                pgns.extend(_pgns_from_archive_payload(payload))
                if len(pgns) >= config.max_games:
                    break
        finally:
            if close_client:
                await client.aclose()

        games = []
        for pgn in pgns[: config.max_games]:
            games.extend(games_from_pgn_collection(pgn, "Chess.com personal games"))
        if not games:
            raise TrainingSourceError("No PGN games were available in the selected Chess.com archives.")
        return games[: config.max_games]

    async def _get_json(self, client: httpx.AsyncClient, url: str) -> dict[str, Any]:
        response = await client.get(url)
        if response.status_code >= 400:
            raise TrainingSourceError(f"Chess.com request failed with HTTP {response.status_code}.")
        try:
            payload = response.json()
        except ValueError as exc:
            raise TrainingSourceError("Chess.com returned a response that was not valid JSON.") from exc
        if not isinstance(payload, dict):
            raise TrainingSourceError("Chess.com returned an unexpected response shape.")
        return payload


async def load_training_games(config: TrainingConfig) -> list[TrainingGame]:
    if config.source == "chesscom":
        return await ChessComPersonalSource().load_games(config)
    return await LichessPgnSource().load_games(config)


def _archive_urls(payload: dict[str, Any]) -> list[str]:
    archives = payload.get("archives")
    if not isinstance(archives, Sequence) or isinstance(archives, (str, bytes)):
        return []
    return [str(item) for item in archives if str(item).startswith("https://")]


def _pgns_from_archive_payload(payload: dict[str, Any]) -> list[str]:
    games = payload.get("games")
    if not isinstance(games, list):
        return []
    pgns: list[str] = []
    for game in games:
        if isinstance(game, dict) and isinstance(game.get("pgn"), str) and game["pgn"].strip():
            pgns.append(game["pgn"])
    return list(reversed(pgns))


def _uploaded_file_path(upload_file: object) -> Path | None:
    for candidate in (upload_file, getattr(upload_file, "content", None)):
        value = getattr(candidate, "_path", None)
        if value:
            return Path(value)
    return None


def _uploaded_file_text_sync(upload_file: object) -> str:
    for candidate in (upload_file, getattr(upload_file, "content", None)):
        data = getattr(candidate, "_data", None)
        if data is not None:
            return _decode_upload_data(data)
    content = getattr(upload_file, "content", upload_file)
    if isinstance(content, (bytes, bytearray, memoryview, str)):
        return _decode_upload_data(content)
    if hasattr(content, "getvalue"):
        return _decode_upload_data(content.getvalue())
    raise TrainingSourceError("Upload the PGN file again.")


def _decode_upload_data(data: object) -> str:
    if isinstance(data, str):
        return data
    if isinstance(data, memoryview):
        data = data.tobytes()
    if isinstance(data, bytearray):
        data = bytes(data)
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return str(data or "")
