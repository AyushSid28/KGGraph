from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    file TEXT NOT NULL,
    start_line INTEGER NOT NULL DEFAULT 0,
    end_line INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS edges (
    from_id TEXT NOT NULL,
    to_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    lineno INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (from_id, to_id, kind, lineno)
);

CREATE TABLE IF NOT EXISTS file_meta (
    path TEXT PRIMARY KEY,
    mtime REAL NOT NULL,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name);
CREATE INDEX IF NOT EXISTS idx_nodes_file ON nodes(file);
CREATE INDEX IF NOT EXISTS idx_edges_to ON edges(to_id);
CREATE INDEX IF NOT EXISTS idx_edges_from ON edges(from_id);
CREATE INDEX IF NOT EXISTS idx_edges_kind ON edges(kind);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def replace_file_subgraph(
    conn: sqlite3.Connection,
    rel: str,
    nodes: list[tuple],
    edges: list[tuple],
    mtime: float,
    error: str | None,
) -> None:
    # Only drop edges this file owns. Inbound calls from other files stay
    # until those files are re-indexed.
    conn.execute(
        "DELETE FROM edges WHERE from_id = ? OR from_id LIKE ?",
        (f"file:{rel}", f"{rel}::%"),
    )
    conn.execute("DELETE FROM nodes WHERE file = ? OR id = ?", (rel, f"file:{rel}"))
    conn.executemany(
        "INSERT OR REPLACE INTO nodes(id, kind, name, file, start_line, end_line) VALUES (?,?,?,?,?,?)",
        nodes,
    )
    conn.executemany(
        "INSERT OR REPLACE INTO edges(from_id, to_id, kind, lineno) VALUES (?,?,?,?)",
        edges,
    )
    conn.execute(
        "INSERT OR REPLACE INTO file_meta(path, mtime, error) VALUES (?,?,?)",
        (rel, mtime, error),
    )


def delete_file_subgraph(conn: sqlite3.Connection, rel: str) -> None:
    conn.execute("DELETE FROM edges WHERE from_id LIKE ? OR to_id LIKE ?", (f"{rel}::%", f"{rel}::%"))
    conn.execute("DELETE FROM edges WHERE from_id = ? OR to_id = ?", (f"file:{rel}", f"file:{rel}"))
    conn.execute("DELETE FROM nodes WHERE file = ? OR id = ?", (rel, f"file:{rel}"))
    conn.execute("DELETE FROM file_meta WHERE path = ?", (rel,))


def snapshot_counts(conn: sqlite3.Connection) -> tuple[int, int]:
    nodes = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    return int(nodes), int(edges)
