from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ParsedFile:
    path: Path
    tree: ast.AST | None
    error: str | None


def parse_file(path: Path) -> ParsedFile:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return ParsedFile(path=path, tree=None, error=f"decode: {exc}")
    try:
        tree = ast.parse(text, filename=str(path))
        return ParsedFile(path=path, tree=tree, error=None)
    except SyntaxError as exc:
        return ParsedFile(path=path, tree=None, error=f"syntax: {exc}")
