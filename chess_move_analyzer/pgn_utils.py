from __future__ import annotations

import io
import re
from dataclasses import dataclass

import chess
import chess.pgn

from .models import BasicMove, GameRecord

CLOCK_RE = re.compile(r"\[%clk\s+([^\]]+)\]")


@dataclass(frozen=True)
class TimeControl:
    initial_seconds: int
    increment_seconds: int


def parse_pgn_game(pgn_text: str) -> chess.pgn.Game:
    game = chess.pgn.read_game(io.StringIO(pgn_text.strip()))
    if game is None:
        raise ValueError("No valid PGN game was found.")
    return game


def record_from_pgn(pgn_text: str, source_url: str | None = None, game_id: str | None = None) -> GameRecord:
    game = parse_pgn_game(pgn_text)
    headers = {str(key): str(value) for key, value in game.headers.items()}
    return GameRecord(
        pgn=pgn_text.strip(),
        source_url=source_url or headers.get("Link") or headers.get("Site"),
        headers=headers,
        white=headers.get("White"),
        black=headers.get("Black"),
        white_elo=headers.get("WhiteElo"),
        black_elo=headers.get("BlackElo"),
        result=headers.get("Result"),
        date=headers.get("Date"),
        time_control=headers.get("TimeControl"),
        end_time=headers.get("EndTime") or headers.get("EndDate"),
        game_id=game_id,
    )


def parse_clock(comment: str) -> tuple[str | None, int | None]:
    match = CLOCK_RE.search(comment or "")
    if not match:
        return None, None
    raw = match.group(1).strip()
    return raw, clock_to_seconds(raw)


def clock_to_seconds(raw: str) -> int | None:
    raw = raw.strip()
    parts = raw.split(":")
    try:
        values = [float(part) for part in parts]
    except ValueError:
        return None
    if len(values) == 3:
        hours, minutes, seconds = values
    elif len(values) == 2:
        hours = 0
        minutes, seconds = values
    elif len(values) == 1:
        hours = 0
        minutes = 0
        seconds = values[0]
    else:
        return None
    return int(round(hours * 3600 + minutes * 60 + seconds))


def parse_time_control(raw: str | None) -> TimeControl | None:
    if not raw or raw in {"-", "?"}:
        return None
    match = re.fullmatch(r"(\d+)(?:\+(\d+))?", raw.strip())
    if not match:
        return None
    return TimeControl(
        initial_seconds=int(match.group(1)),
        increment_seconds=int(match.group(2) or 0),
    )


def iter_basic_moves(pgn_text: str) -> list[BasicMove]:
    game = parse_pgn_game(pgn_text)
    board = game.board()
    time_control = parse_time_control(game.headers.get("TimeControl"))
    previous_clock: dict[chess.Color, int | None] = {
        chess.WHITE: time_control.initial_seconds if time_control else None,
        chess.BLACK: time_control.initial_seconds if time_control else None,
    }
    moves: list[BasicMove] = []

    node = game
    ply = 0
    while node.variations:
        child = node.variations[0]
        move = child.move
        ply += 1
        color = board.turn
        move_number = board.fullmove_number
        fen_before = board.fen()
        san = board.san(move)
        clock, clock_seconds = parse_clock(child.comment)
        time_spent = _time_spent(previous_clock[color], clock_seconds, time_control)

        board.push(move)
        fen_after = board.fen()

        if clock_seconds is not None:
            previous_clock[color] = clock_seconds

        moves.append(
            BasicMove(
                ply=ply,
                move_number=move_number,
                color="white" if color == chess.WHITE else "black",
                san=san,
                uci=move.uci(),
                fen_before=fen_before,
                fen_after=fen_after,
                comment=child.comment or "",
                clock=clock,
                clock_seconds=clock_seconds,
                time_spent_seconds=time_spent,
            )
        )
        node = child

    return moves


def final_fen(pgn_text: str) -> str:
    game = parse_pgn_game(pgn_text)
    board = game.board()
    for move in game.mainline_moves():
        board.push(move)
    return board.fen()


def _time_spent(
    previous: int | None,
    current: int | None,
    time_control: TimeControl | None,
) -> int | None:
    if previous is None or current is None:
        return None
    increment = time_control.increment_seconds if time_control else 0
    spent = previous + increment - current
    if spent < 0:
        return 0
    return spent
