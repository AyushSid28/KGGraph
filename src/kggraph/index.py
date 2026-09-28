from __future__ import annotations

from pathlib import Path

from kggraph.bind import analyze_file
from kggraph.crawl import iter_python_files, rel_posix
from kggraph.extract import extract_definitions
from kggraph.parse import parse_file
from kggraph.store import connect, delete_file_subgraph, replace_file_subgraph, snapshot_counts


def default_db_path(root: Path) -> Path:
    return root.resolve() / ".kggraph.sqlite"


def _mtime(path: Path) -> float:
    return path.stat().st_mtime


def _ensure_aux_node(nodes: dict[str, tuple], node_id: str, kind: str, name: str) -> None:
    if node_id not in nodes:
        nodes[node_id] = (node_id, kind, name, "", 0, 0)


def index_file(root: Path, path: Path) -> tuple[list[tuple], list[tuple], str | None]:
    rel = rel_posix(root, path)
    parsed = parse_file(path)
    file_id = f"file:{rel}"
    nodes: dict[str, tuple] = {
        file_id: (file_id, "file", Path(rel).name, rel, 1, 1),
    }
    edges: list[tuple] = []

    if parsed.error or parsed.tree is None:
        return list(nodes.values()), edges, parsed.error

    for definition in extract_definitions(parsed.tree):
        node_id = f"{rel}::{definition.qualname}"
        end = definition.end_lineno or definition.lineno
        nodes[node_id] = (
            node_id,
            definition.kind,
            definition.qualname,
            rel,
            definition.lineno,
            end,
        )
        edges.append((file_id, node_id, "contains", definition.lineno))

    resolved, calls = analyze_file(root, path, parsed.tree)
    for rec in resolved:
        origin = rec.origin
        if origin.startswith("star:"):
            origin = origin.removeprefix("star:")
        if origin.startswith("file:"):
            if "::" in origin:
                target_file = origin[5:].split("::", 1)[0]
                target_id = origin[5:]
                edges.append((file_id, f"file:{target_file}", "imports", rec.lineno))
                edges.append((file_id, target_id, "imports_symbol", rec.lineno))
            else:
                edges.append((file_id, f"file:{origin[5:]}", "imports", rec.lineno))
        elif origin.startswith("external:"):
            _ensure_aux_node(nodes, origin, "external", origin.split(":", 1)[1])
            edges.append((file_id, origin, "imports", rec.lineno))
        elif origin.startswith("unresolved:"):
            _ensure_aux_node(nodes, origin, "unresolved", origin.split(":", 1)[1])
            edges.append((file_id, origin, "imports", rec.lineno))

    for call in calls:
        callee = call.callee
        if callee.startswith("file:"):
            callee = callee[5:]
        if call.status == "attr":
            _ensure_aux_node(nodes, callee, "attr", callee.split(":", 1)[-1])
        elif call.status == "external":
            _ensure_aux_node(nodes, callee, "external", callee.split(":", 1)[-1])
        elif call.status == "unresolved":
            _ensure_aux_node(nodes, callee, "unresolved", callee.split(":", 1)[-1])
        edges.append((call.caller, callee, "calls", call.lineno))
        if call.caller not in nodes:
            name = call.caller.split("::", 1)[-1]
            nodes[call.caller] = (
                call.caller,
                "function",
                name,
                rel,
                call.lineno,
                call.lineno,
            )

    return list(nodes.values()), edges, None


def index_repo(root: Path, db_path: Path | None = None, incremental: bool = False) -> dict:
    root = root.resolve()
    db_path = db_path or default_db_path(root)
    files = iter_python_files(root)
    conn = connect(db_path)

    existing = {
        row["path"]: row["mtime"]
        for row in conn.execute("SELECT path, mtime FROM file_meta")
    }
    current = {rel_posix(root, path): path for path in files}

    to_index: list[Path]
    if incremental and existing:
        changed = []
        for rel, path in current.items():
            prev = existing.get(rel)
            if prev is None or abs(_mtime(path) - prev) > 1e-6:
                changed.append(path)
        importer_rels = set()
        for path in changed:
            rel = rel_posix(root, path)
            rows = conn.execute(
                "SELECT n.file FROM edges e JOIN nodes n ON n.id = e.from_id "
                "WHERE e.kind = 'imports' AND e.to_id = ?",
                (f"file:{rel}",),
            ).fetchall()
            for row in rows:
                if row["file"]:
                    importer_rels.add(row["file"])
        extra = [current[rel] for rel in importer_rels if rel in current]
        to_index = list({*changed, *extra})
        deleted = [rel for rel in existing if rel not in current]
    else:
        to_index = list(current.values())
        deleted = [rel for rel in existing if rel not in current]
        if not incremental:
            conn.execute("DELETE FROM edges")
            conn.execute("DELETE FROM nodes")
            conn.execute("DELETE FROM file_meta")
            existing = {}
            deleted = []
            to_index = list(current.values())

    errors = 0
    try:
        for rel in deleted:
            delete_file_subgraph(conn, rel)
        for path in to_index:
            rel = rel_posix(root, path)
            nodes, edges, error = index_file(root, path)
            replace_file_subgraph(conn, rel, nodes, edges, _mtime(path), error)
            if error:
                errors += 1
        conn.commit()
        node_count, edge_count = snapshot_counts(conn)
    finally:
        conn.close()

    return {
        "root": str(root),
        "db": str(db_path),
        "files": len(files),
        "indexed": len(to_index),
        "deleted": len(deleted),
        "errors": errors,
        "nodes": node_count,
        "edges": edge_count,
        "incremental": incremental,
    }
