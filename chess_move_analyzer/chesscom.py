from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import httpx

from .models import ChessComUrl, GameRecord
from .pgn_utils import record_from_pgn

CHESSCOM_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?chess\.com/"
    r"(?:(?:analysis/game|game)/(?P<kind_a>live|daily|computer)|(?P<kind_b>live|daily|computer))"
    r"/(?P<id>\d+)",
    re.IGNORECASE,
)


class ChessComImportError(RuntimeError):
    pass


def parse_chesscom_url(url: str) -> ChessComUrl:
    cleaned = url.strip()
    match = CHESSCOM_URL_RE.search(cleaned)
    if not match:
        raise ChessComImportError("The URL does not look like a supported Chess.com game link.")
    kind = match.group("kind_a") or match.group("kind_b")
    return ChessComUrl(original=cleaned, game_id=match.group("id"), kind=kind.lower())


class ChessComImporter:
    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout

    async def fetch_game(self, url: str) -> GameRecord:
        parsed = parse_chesscom_url(url)
        headers = {
            "User-Agent": "chess-move-analyzer/0.1 (+local)",
            "Accept": "application/json,text/plain,*/*",
        }
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True, headers=headers) as client:
            callback_data = await self._fetch_callback(client, parsed)
            pgn = _recursive_find_text(callback_data, "pgn")
            if pgn:
                return record_from_pgn(pgn, source_url=parsed.original, game_id=parsed.game_id)

            candidates = _player_month_candidates(callback_data)
            for username, year, month in candidates:
                pgn = await self._fetch_from_public_archive(client, username, year, month, parsed.game_id)
                if pgn:
                    return record_from_pgn(pgn, source_url=parsed.original, game_id=parsed.game_id)

        raise ChessComImportError(
            "The game could not be resolved from the public Chess.com data. Paste the PGN manually."
        )

    async def _fetch_callback(self, client: httpx.AsyncClient, parsed: ChessComUrl) -> dict[str, Any]:
        url = f"https://www.chess.com/callback/live/game/{parsed.game_id}"
        response = await client.get(url)
        if response.status_code >= 400:
            return {}
        try:
            data = response.json()
        except ValueError:
            return {}
        if isinstance(data, dict):
            return data
        return {}

    async def _fetch_from_public_archive(
        self,
        client: httpx.AsyncClient,
        username: str,
        year: int,
        month: int,
        game_id: str,
    ) -> str | None:
        url = f"https://api.chess.com/pub/player/{username.lower()}/games/{year:04d}/{month:02d}"
        response = await client.get(url)
        if response.status_code >= 400:
            return None
        try:
            payload = response.json()
        except ValueError:
            return None
        games = payload.get("games") if isinstance(payload, dict) else None
        if not isinstance(games, list):
            return None
        for game in games:
            if not isinstance(game, dict):
                continue
            game_url = str(game.get("url") or "")
            if game_id in game_url and isinstance(game.get("pgn"), str):
                return game["pgn"]
        return None


def _recursive_find_text(data: Any, key: str) -> str | None:
    if isinstance(data, dict):
        for current_key, value in data.items():
            if str(current_key).lower() == key.lower() and isinstance(value, str) and value.strip():
                return value
            found = _recursive_find_text(value, key)
            if found:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _recursive_find_text(item, key)
            if found:
                return found
    return None


def _player_month_candidates(data: dict[str, Any]) -> list[tuple[str, int, int]]:
    usernames = _recursive_usernames(data)
    timestamps = _recursive_timestamps(data)
    dates = [_datetime_from_timestamp(value) for value in timestamps]
    dates = [date for date in dates if date is not None]
    candidates: list[tuple[str, int, int]] = []
    for username in usernames:
        for date in dates:
            item = (username, date.year, date.month)
            if item not in candidates:
                candidates.append(item)
    return candidates


def _recursive_usernames(data: Any) -> list[str]:
    found: list[str] = []
    if isinstance(data, dict):
        for key, value in data.items():
            if str(key).lower() in {"username", "user"} and isinstance(value, str):
                if value and value not in found:
                    found.append(value)
            found.extend(_recursive_usernames(value))
    elif isinstance(data, list):
        for item in data:
            found.extend(_recursive_usernames(item))
    return found


def _recursive_timestamps(data: Any) -> list[int]:
    found: list[int] = []
    timestamp_keys = {"end_time", "endtime", "start_time", "starttime", "date", "createdat"}
    if isinstance(data, dict):
        for key, value in data.items():
            normalized = str(key).lower()
            if normalized in timestamp_keys and isinstance(value, int) and value > 1_000_000_000:
                found.append(value)
            found.extend(_recursive_timestamps(value))
    elif isinstance(data, list):
        for item in data:
            found.extend(_recursive_timestamps(item))
    return found


def _datetime_from_timestamp(value: int) -> datetime | None:
    try:
        if value > 10_000_000_000:
            value = value // 1000
        return datetime.fromtimestamp(value, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None
