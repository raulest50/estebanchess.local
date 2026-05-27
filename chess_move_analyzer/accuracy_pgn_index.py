from __future__ import annotations

import hashlib
import io
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chess.pgn

from .accuracy_models import TrainingGame

INDEX_DIR = Path("data/pgn_indexes")
INDEX_VERSION = 1


@dataclass(frozen=True)
class PgnIndex:
    path: str
    size: int
    mtime_ns: int
    offsets: list[int]


def automatic_sample_game_count(scenario_count: int, consecutive_moves: int) -> int:
    return min(500, max(80, scenario_count * consecutive_moves * 12))


def load_or_build_pgn_index(path: str | Path, index_dir: Path = INDEX_DIR) -> PgnIndex:
    pgn_path = Path(path)
    metadata = _file_metadata(pgn_path)
    cache_path = _cache_path(pgn_path, index_dir)

    cached = _read_cache(cache_path)
    if cached and _cache_matches(cached, metadata):
        return PgnIndex(
            path=str(metadata["path"]),
            size=int(metadata["size"]),
            mtime_ns=int(metadata["mtime_ns"]),
            offsets=[int(offset) for offset in cached["offsets"]],
        )

    offsets = build_pgn_offsets(pgn_path)
    index = PgnIndex(
        path=str(metadata["path"]),
        size=int(metadata["size"]),
        mtime_ns=int(metadata["mtime_ns"]),
        offsets=offsets,
    )
    _write_cache(cache_path, index)
    return index


def build_pgn_offsets(path: str | Path) -> list[int]:
    offsets: list[int] = []
    with Path(path).open("rb") as stream:
        while True:
            offset = stream.tell()
            line = stream.readline()
            if not line:
                break
            if line.lstrip().startswith(b"[Event "):
                offsets.append(offset)
    return offsets


def sample_pgn_game_indices(total_games: int, requested_games: int, random_seed: int | None = None) -> list[int]:
    if total_games <= 0 or requested_games <= 0:
        return []
    sample_count = min(total_games, requested_games)
    rng = random.Random(random_seed)
    return rng.sample(range(total_games), sample_count)


def games_from_indexed_pgn_file(
    path: str | Path,
    source_label: str,
    max_games: int,
    random_seed: int | None = None,
    index_dir: Path = INDEX_DIR,
) -> list[TrainingGame]:
    pgn_path = Path(path)
    index = load_or_build_pgn_index(pgn_path, index_dir=index_dir)
    game_indices = sample_pgn_game_indices(len(index.offsets), max_games, random_seed=random_seed)
    return games_from_pgn_indices(pgn_path, source_label, index.offsets, game_indices)


def games_from_sampled_pgn_file(
    path: str | Path,
    source_label: str,
    max_games: int,
    random_seed: int | None = None,
) -> list[TrainingGame]:
    pgn_path = Path(path)
    offsets = build_pgn_offsets(pgn_path)
    game_indices = sample_pgn_game_indices(len(offsets), max_games, random_seed=random_seed)
    return games_from_pgn_indices(pgn_path, source_label, offsets, game_indices)


def games_from_pgn_indices(
    path: str | Path,
    source_label: str,
    offsets: list[int],
    game_indices: list[int],
) -> list[TrainingGame]:
    games: list[TrainingGame] = []
    pgn_path = Path(path)
    file_size = pgn_path.stat().st_size
    with pgn_path.open("rb") as stream:
        for game_index in game_indices:
            if game_index < 0 or game_index >= len(offsets):
                continue
            start = offsets[game_index]
            end = offsets[game_index + 1] if game_index + 1 < len(offsets) else file_size
            stream.seek(start)
            raw_game = stream.read(max(0, end - start))
            game = chess.pgn.read_game(io.StringIO(raw_game.decode("utf-8", errors="replace")))
            if game is None:
                continue
            games.append(training_game_from_pgn_game(game, source_label))
    return games


def training_game_from_pgn_game(game: chess.pgn.Game, source_label: str) -> TrainingGame:
    exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=True)
    pgn = game.accept(exporter)
    headers = {str(key): str(value) for key, value in game.headers.items()}
    return TrainingGame(
        pgn=pgn,
        source_label=source_label,
        headers=headers,
        white=headers.get("White"),
        black=headers.get("Black"),
        date=headers.get("Date"),
        result=headers.get("Result"),
        game_id=headers.get("GameId") or headers.get("Link") or headers.get("Site"),
    )


def _file_metadata(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    stat = resolved.stat()
    return {
        "version": INDEX_VERSION,
        "path": str(resolved),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def _cache_path(path: Path, index_dir: Path) -> Path:
    index_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:24]
    return index_dir / f"{digest}.json"


def _read_cache(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    offsets = payload.get("offsets")
    if not isinstance(offsets, list) or not all(isinstance(offset, int) for offset in offsets):
        return None
    return payload


def _cache_matches(payload: dict[str, Any], metadata: dict[str, Any]) -> bool:
    return (
        payload.get("version") == metadata["version"]
        and payload.get("path") == metadata["path"]
        and payload.get("size") == metadata["size"]
        and payload.get("mtime_ns") == metadata["mtime_ns"]
    )


def _write_cache(path: Path, index: PgnIndex) -> None:
    payload = {
        "version": INDEX_VERSION,
        "path": index.path,
        "size": index.size,
        "mtime_ns": index.mtime_ns,
        "offsets": index.offsets,
    }
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload), encoding="utf-8")
    temp_path.replace(path)
