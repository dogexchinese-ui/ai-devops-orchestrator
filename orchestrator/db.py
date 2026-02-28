from __future__ import annotations

import os
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass

SCHEMA_VERSION = 2


@dataclass(frozen=True)
class DbConfig:
    path: str


def connect(cfg: DbConfig) -> sqlite3.Connection:
    d = os.path.dirname(cfg.path)
    if d:
        os.makedirs(d, exist_ok=True)
    con = sqlite3.connect(cfg.path, isolation_level=None)  # autocommit
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    con.execute("PRAGMA foreign_keys=ON;")
    return con


def migrate(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS meta (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );
        """
    )

    row = con.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    current = int(row["value"]) if row else 0

    if current >= SCHEMA_VERSION:
        return

    if current == 0:
        _migrate_0_to_1(con)
        current = 1

    if current == 1:
        _migrate_1_to_2(con)
        current = 2

    con.execute(
        "INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version', ?)",
        (str(current),),
    )
    return


def _migrate_0_to_1(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
          id TEXT PRIMARY KEY,
          kind TEXT NOT NULL,                 -- plan|subtask
          title TEXT,
          routing TEXT,                       -- e.g. codex-backend|claude-frontend|gemini-design
          prompt TEXT,
          repo TEXT,                          -- logical repo name
          repo_path TEXT,                     -- absolute path (optional)
          worktree_path TEXT,                 -- absolute path (optional)
          status TEXT NOT NULL,               -- queued|running|succeeded|failed|blocked|canceled
          blocked_reason TEXT,
          failure_kind TEXT,                  -- ci|lint|test|build|agent|unknown
          failure_detail TEXT,
          attempt INTEGER NOT NULL DEFAULT 0,
          max_attempts INTEGER NOT NULL DEFAULT 3,
          idempotency_key TEXT,               -- unique when provided
          created_at INTEGER NOT NULL,
          updated_at INTEGER NOT NULL
        );
        """
    )
    con.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_idempotency ON tasks(idempotency_key) WHERE idempotency_key IS NOT NULL;"
    )

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS deps (
          task_id TEXT NOT NULL,
          depends_on TEXT NOT NULL,
          PRIMARY KEY(task_id, depends_on),
          FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
          FOREIGN KEY(depends_on) REFERENCES tasks(id) ON DELETE CASCADE
        );
        """
    )

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          task_id TEXT NOT NULL,
          ts INTEGER NOT NULL,
          level TEXT NOT NULL,               -- info|warn|error
          message TEXT NOT NULL,
          data TEXT,
          FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
        );
        """
    )


def _migrate_1_to_2(con: sqlite3.Connection) -> None:
    cols = {r["name"] for r in con.execute("PRAGMA table_info(tasks)").fetchall()}
    if "plan_id" not in cols:
        con.execute("ALTER TABLE tasks ADD COLUMN plan_id TEXT")

    # Backfill plan rows so downstream queries can use plan_id consistently.
    con.execute("UPDATE tasks SET plan_id=id WHERE kind='plan' AND (plan_id IS NULL OR plan_id='')")


@contextmanager
def tx_immediate(con: sqlite3.Connection):
    """Acquire a write lock early; safe for worker claim."""
    con.execute("BEGIN IMMEDIATE")
    try:
        yield
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise


def now_ts() -> int:
    return int(time.time())
