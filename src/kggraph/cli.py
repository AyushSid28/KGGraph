from __future__ import annotations

import argparse
from pathlib import Path

from kggraph.bind import collect_calls
from kggraph.crawl import iter_python_files, rel_posix
from kggraph.extract import extract_definitions
from kggraph.imports import extract_imports
from kggraph.index import default_db_path, index_repo
from kggraph.parse import parse_file
from kggraph.query import ask, who_calls
from kggraph.resolve import resolve_file_imports


def cmd_scan(root: Path) -> int:
    files = iter_python_files(root)
    if not files:
        print(f"no .py files under {root}")
        return 0
    errors = 0
    for path in files:
        rel = rel_posix(root, path)
        parsed = parse_file(path)
        if parsed.error:
            errors += 1
            print(f"ERROR\t{rel}\t{parsed.error}")
            continue
        defs = extract_definitions(parsed.tree)
        if not defs:
            print(f"FILE\t{rel}\t(no defs)")
            continue
        for definition in defs:
            end = definition.end_lineno if definition.end_lineno is not None else definition.lineno
            print(f"{definition.kind.upper()}\t{rel}\t{definition.qualname}\tL{definition.lineno}-{end}")
    print(f"# files={len(files)} errors={errors}")
    return 0 if errors == 0 else 1


def cmd_imports(root: Path) -> int:
    files = iter_python_files(root)
    if not files:
        print(f"no .py files under {root}")
        return 0
    errors = 0
    for path in files:
        rel = rel_posix(root, path)
        parsed = parse_file(path)
        if parsed.error:
            errors += 1
            print(f"ERROR\t{rel}\t{parsed.error}")
            continue
        resolved = resolve_file_imports(root, path, extract_imports(parsed.tree))
        if not resolved:
            print(f"FILE\t{rel}\t(no imports)")
            continue
        for rec in resolved:
            name = rec.local_name if rec.local_name is not None else "*"
            print(f"IMPORT\t{rel}\tL{rec.lineno}\t{name}\t{rec.origin}")
    print(f"# files={len(files)} errors={errors}")
    return 0 if errors == 0 else 1


def cmd_calls(root: Path) -> int:
    edges = collect_calls(root)
    if not edges:
        print("no calls")
        return 0
    for edge in edges:
        print(f"CALL\t{edge.status}\t{edge.caller}\tL{edge.lineno}\t{edge.callee}")
    print(f"# calls={len(edges)}")
    return 0


def cmd_index(root: Path, db: Path | None, incremental: bool) -> int:
    result = index_repo(root, db, incremental=incremental)
    for key, value in result.items():
        print(f"{key}\t{value}")
    return 0 if result["errors"] == 0 else 1


def cmd_who_calls(db: Path, name: str) -> int:
    hits = who_calls(db, name)
    if not hits:
        print("no callers")
        return 0
    for hit in hits:
        print(f"{hit['caller']}\tL{hit['lineno']}\t->\t{hit['callee']}")
    print(f"# callers={len(hits)}")
    return 0


def cmd_ask(db: Path, query: str, hops: int) -> int:
    result = ask(db, query, hops=hops)
    if not result["seeds"]:
        print("no seeds")
        return 0
    print("SEEDS")
    for seed in result["seeds"]:
        print(f"  {seed}")
    print("PATHS")
    if not result["paths"]:
        print("  (seeds only)")
    for path in result["paths"]:
        print("  " + " -> ".join(path))
    print(f"# nodes={len(result['nodes'])} paths={len(result['paths'])}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kggraph")
    sub = parser.add_subparsers(dest="cmd", required=True)

    scan = sub.add_parser("scan", help="list definitions")
    scan.add_argument("root", type=Path)

    im = sub.add_parser("imports", help="list resolved imports")
    im.add_argument("root", type=Path)

    calls = sub.add_parser("calls", help="list bound calls")
    calls.add_argument("root", type=Path)

    index = sub.add_parser("index", help="build or update the persistent graph")
    index.add_argument("root", type=Path)
    index.add_argument("--db", type=Path, default=None)
    index.add_argument("--incremental", action="store_true")

    who = sub.add_parser("who-calls", help="query callers from the graph")
    who.add_argument("name")
    who.add_argument("--db", type=Path, required=True)

    ask_p = sub.add_parser("ask", help="keyword retrieval + graph walk")
    ask_p.add_argument("query")
    ask_p.add_argument("--db", type=Path, required=True)
    ask_p.add_argument("--hops", type=int, default=2)

    args = parser.parse_args(argv)
    if args.cmd == "scan":
        return cmd_scan(args.root)
    if args.cmd == "imports":
        return cmd_imports(args.root)
    if args.cmd == "calls":
        return cmd_calls(args.root)
    if args.cmd == "index":
        return cmd_index(args.root, args.db, args.incremental)
    if args.cmd == "who-calls":
        return cmd_who_calls(args.db, args.name)
    if args.cmd == "ask":
        return cmd_ask(args.db, args.query, args.hops)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
