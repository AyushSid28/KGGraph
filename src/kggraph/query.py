from __future__ import annotations

from pathlib import Path

from kggraph.store import connect


def _matches(node_id: str, name: str) -> bool:
    needle = name.strip()
    if not needle:
        return False
    if node_id == needle:
        return True
    if node_id.endswith(f"::{needle}"):
        return True
    if node_id.endswith(f".{needle}"):
        return True
    if "/" not in needle and "::" not in needle:
        return node_id.split("::")[-1] == needle or node_id.split(".")[-1] == needle
    return False


def who_calls(db_path: Path, name: str) -> list[dict]:
    conn = connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT e.from_id, e.to_id, e.lineno, n.file, n.kind
            FROM edges e
            LEFT JOIN nodes n ON n.id = e.from_id
            WHERE e.kind = 'calls'
            """
        ).fetchall()
        hits = []
        for row in rows:
            if _matches(row["to_id"], name):
                hits.append(
                    {
                        "caller": row["from_id"],
                        "callee": row["to_id"],
                        "lineno": row["lineno"],
                        "file": row["file"] or "",
                    }
                )
        return hits
    finally:
        conn.close()


def _seed_ids(conn, query: str, limit: int = 12) -> list[str]:
    tokens = [t for t in query.lower().replace("/", " ").replace("::", " ").split() if t]
    if not tokens:
        return []
    scored: dict[str, int] = {}
    for row in conn.execute("SELECT id, name, file, kind FROM nodes"):
        if row["kind"] in {"external", "unresolved", "attr"}:
            continue
        blob = f"{row['id']} {row['name']} {row['file']}".lower()
        score = sum(1 for token in tokens if token in blob)
        if score:
            scored[row["id"]] = score
    ranked = sorted(scored.items(), key=lambda item: (-item[1], item[0]))
    return [node_id for node_id, _ in ranked[:limit]]


def _neighbors(conn, node_id: str) -> list[tuple[str, str]]:
    if node_id.startswith("external:") or node_id.startswith("unresolved:") or node_id.startswith("attr:"):
        return []
    rows = conn.execute(
        """
        SELECT to_id, kind FROM edges
        WHERE from_id = ? AND kind IN ('calls', 'imports', 'imports_symbol', 'contains')
        """,
        (node_id,),
    ).fetchall()
    out = []
    for row in rows:
        target = row["to_id"]
        if target.startswith("external:") or target.startswith("unresolved:") or target.startswith("attr:"):
            continue
        out.append((target, row["kind"]))
    return out


def ask(db_path: Path, query: str, hops: int = 2) -> dict:
    conn = connect(db_path)
    try:
        seeds = _seed_ids(conn, query)
        if not seeds:
            return {"query": query, "seeds": [], "nodes": [], "paths": []}

        seen = set(seeds)
        paths: list[list[str]] = [[seed] for seed in seeds]
        frontier = list(seeds)
        for _ in range(max(hops, 0)):
            nxt: list[str] = []
            new_paths: list[list[str]] = []
            for path in paths:
                node = path[-1]
                expanded = False
                for neighbor, kind in _neighbors(conn, node):
                    if neighbor in path:
                        continue
                    expanded = True
                    new_path = path + [neighbor]
                    new_paths.append(new_path)
                    if neighbor not in seen:
                        seen.add(neighbor)
                        nxt.append(neighbor)
                if not expanded:
                    new_paths.append(path)
            paths = new_paths
            frontier = nxt
            if not frontier:
                break

        nodes = []
        for node_id in sorted(seen):
            row = conn.execute("SELECT id, kind, name, file FROM nodes WHERE id = ?", (node_id,)).fetchone()
            if row:
                nodes.append(dict(row))
            else:
                nodes.append({"id": node_id, "kind": "unknown", "name": node_id, "file": ""})
        compact_paths = [path for path in paths if len(path) > 1][:40]
        return {
            "query": query,
            "seeds": seeds,
            "nodes": nodes,
            "paths": compact_paths,
        }
    finally:
        conn.close()
