from __future__ import annotations

import sqlite3
from pathlib import Path

from .accuracy_models import MoveFeedback, StoredTrainingSession, TrainingConfig, TrainingSummary


class TrainingHistoryStorage:
    def __init__(self, path: str | Path = "data/accuracy_training.sqlite") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "TrainingHistoryStorage":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def create_session(self, config: TrainingConfig) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO training_sessions (started_at, config_json)
            VALUES (datetime('now'), ?)
            """,
            (config.model_dump_json(),),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def save_attempt(self, session_id: int, feedback: MoveFeedback) -> None:
        best_move = feedback.top_candidates[0].move_uci if feedback.top_candidates else None
        self.conn.execute(
            """
            INSERT INTO training_attempts
                (session_id, scenario_index, step_index, fen_before, user_move_uci,
                 best_move_uci, expected_loss, classification, feedback_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                session_id,
                feedback.scenario_index,
                feedback.step_index,
                feedback.fen_before,
                feedback.user_move_uci,
                best_move,
                feedback.expected_loss,
                feedback.classification,
                feedback.model_dump_json(),
            ),
        )
        self.conn.commit()

    def complete_session(self, session_id: int, summary: TrainingSummary) -> None:
        self.conn.execute(
            """
            UPDATE training_sessions
            SET completed_at = datetime('now'), accuracy = ?, summary_json = ?
            WHERE session_id = ?
            """,
            (summary.accuracy, summary.model_dump_json(), session_id),
        )
        self.conn.commit()

    def recent_sessions(self, limit: int = 5) -> list[StoredTrainingSession]:
        rows = self.conn.execute(
            """
            SELECT session_id, started_at, completed_at, config_json, summary_json, accuracy
            FROM training_sessions
            ORDER BY session_id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        sessions: list[StoredTrainingSession] = []
        for row in rows:
            summary = None
            if row["summary_json"]:
                summary = TrainingSummary.model_validate_json(row["summary_json"])
            sessions.append(
                StoredTrainingSession(
                    session_id=int(row["session_id"]),
                    started_at=str(row["started_at"]),
                    completed_at=row["completed_at"],
                    config=TrainingConfig.model_validate_json(row["config_json"]),
                    summary=summary,
                    accuracy=row["accuracy"],
                )
            )
        return sessions

    def attempts_for_session(self, session_id: int) -> list[MoveFeedback]:
        rows = self.conn.execute(
            """
            SELECT feedback_json
            FROM training_attempts
            WHERE session_id = ?
            ORDER BY attempt_id ASC
            """,
            (session_id,),
        ).fetchall()
        return [MoveFeedback.model_validate_json(row["feedback_json"]) for row in rows]

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS training_sessions (
                session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                config_json TEXT NOT NULL,
                summary_json TEXT,
                accuracy REAL
            );

            CREATE TABLE IF NOT EXISTS training_attempts (
                attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                scenario_index INTEGER NOT NULL,
                step_index INTEGER NOT NULL,
                fen_before TEXT NOT NULL,
                user_move_uci TEXT NOT NULL,
                best_move_uci TEXT,
                expected_loss REAL NOT NULL,
                classification TEXT NOT NULL,
                feedback_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES training_sessions(session_id)
            );

            CREATE INDEX IF NOT EXISTS idx_training_attempts_session
                ON training_attempts (session_id, attempt_id);
            """
        )
        self.conn.commit()
