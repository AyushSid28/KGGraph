from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from kggraph.crawl import rel_posix
from kggraph.imports import ImportRecord

try:
    STDLIB = set(sys.stdlib_module_names)
except AttributeError:
    STDLIB = {"os", "sys", "json", "re", "ast", "pathlib", "typing", "collections"}


@dataclass(frozen=True)
class ResolvedImport:
    lineno: int
    kind: str
    local_name: str | None
    origin: str


def _file_for_module(search_root: Path, parts: list[str]) -> Path | None:
    if not parts:
        return None
    base = search_root.joinpath(*parts)
    py = base.with_suffix(".py")
    init = base / "__init__.py"
    if py.is_file():
        return py
    if init.is_file():
        return init
    return None


def _anchor_dir(file: Path, level: int) -> Path:
    directory = file.parent
    for _ in range(max(level - 1, 0)):
        directory = directory.parent
    return directory


def _top(mod: str) -> str:
    return mod.split(".", 1)[0]


def resolve_module_spec(root: Path, file: Path, spec: str, level: int) -> str:
    root = root.resolve()
    file = file.resolve()

    if level > 0:
        start = _anchor_dir(file, level)
        parts = [p for p in spec.split(".") if p] if spec else []
        try:
            start.resolve().relative_to(root)
        except ValueError:
            return f"unresolved:{'.' * level}{spec}"
        found = (
            _file_for_module(start, parts)
            if parts
            else ((start / "__init__.py") if (start / "__init__.py").is_file() else None)
        )
        if found and found.is_file():
            return f"file:{rel_posix(root, found)}"
        return f"unresolved:{'.' * level}{spec}"

    if not spec:
        return "unresolved:"

    if _top(spec) in STDLIB or spec in STDLIB:
        return f"external:{spec}"

    found = _file_for_module(file.parent, spec.split("."))
    if found:
        return f"file:{rel_posix(root, found)}"
    found = _file_for_module(root, spec.split("."))
    if found:
        return f"file:{rel_posix(root, found)}"
    return f"unresolved:{spec}"


def resolve_one(root: Path, file: Path, rec: ImportRecord) -> list[ResolvedImport]:
    if rec.kind == "from_star":
        origin = resolve_module_spec(root, file, rec.module or "", rec.level)
        return [
            ResolvedImport(
                lineno=rec.lineno,
                kind="from_star",
                local_name=None,
                origin=f"star:{origin}",
            )
        ]

    if rec.kind == "import":
        origin = resolve_module_spec(root, file, rec.module or "", 0)
        return [
            ResolvedImport(rec.lineno, "import", rec.names[0][1], origin)
        ]

    origin = resolve_module_spec(root, file, rec.module or "", rec.level)
    resolved: list[ResolvedImport] = []
    for imported, local in rec.names:
        if origin.startswith("file:"):
            target = f"{origin}::{imported}"
        elif origin.startswith("external:"):
            target = f"{origin}.{imported}"
        else:
            target = f"{origin}.{imported}"
        resolved.append(ResolvedImport(rec.lineno, "from", local, target))
    return resolved


def resolve_file_imports(
    root: Path,
    file: Path,
    records: list[ImportRecord],
) -> list[ResolvedImport]:
    resolved: list[ResolvedImport] = []
    for rec in records:
        resolved.extend(resolve_one(root, file, rec))
    return resolved
