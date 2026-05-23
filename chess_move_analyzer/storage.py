from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from .models import GameRecord, PositionAnalysis


class AnalysisStorage:
    def __init__(self, path: str | Path = "data/analysis.sqlite") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "AnalysisStorage":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def save_game(self, record: GameRecord) -> None:
        key = record.source_url or record.game_id or hashlib.sha256(record.pgn.encode()).hexdigest()
        self.conn.execute(
            """
            INSERT INTO games (game_key, source_url, pgn, headers_json, imported_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(game_key) DO UPDATE SET
                source_url = excluded.source_url,
                pgn = excluded.pgn,
                headers_json = excluded.headers_json,
                imported_at = excluded.imported_at
            """,
            (key, record.source_url, record.pgn, json.dumps(record.headers, sort_keys=True)),
        )
        self.conn.commit()

    def get_position(self, fen: str, engine_name: str, profile: str, multipv: int) -> PositionAnalysis | None:
        key = cache_key(fen, engine_name, profile, multipv)
        row = self.conn.execute(
            "SELECT result_json FROM analysis_cache WHERE cache_key = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        return PositionAnalysis.model_validate_json(row["result_json"])

    def save_position(self, analysis: PositionAnalysis) -> None:
        key = cache_key(analysis.fen, analysis.engine_name, analysis.profile, analysis.multipv)
        self.conn.execute(
            """
            INSERT INTO analysis_cache
                (cache_key, fen, engine_name, profile, multipv, result_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(cache_key) DO UPDATE SET
                result_json = excluded.result_json,
                created_at = excluded.created_at
            """,
            (
                key,
                analysis.fen,
                analysis.engine_name,
                analysis.profile,
                analysis.multipv,
                analysis.model_dump_json(),
            ),
        )
        self.conn.commit()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS games (
                game_key TEXT PRIMARY KEY,
                source_url TEXT,
                pgn TEXT NOT NULL,
                headers_json TEXT NOT NULL,
                imported_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS analysis_cache (
                cache_key TEXT PRIMARY KEY,
                fen TEXT NOT NULL,
                engine_name TEXT NOT NULL,
                profile TEXT NOT NULL,
                multipv INTEGER NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_analysis_fen
                ON analysis_cache (fen, engine_name, profile, multipv);
            """
        )
        self.conn.commit()


def cache_key(fen: str, engine_name: str, profile: str, multipv: int) -> str:
    raw = f"{fen}|{engine_name}|{profile}|{multipv}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

