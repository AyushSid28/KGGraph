from __future__ import annotations

import ast
import builtins
from dataclasses import dataclass, field
from pathlib import Path

from kggraph.crawl import iter_python_files, rel_posix
from kggraph.imports import extract_imports
from kggraph.parse import parse_file
from kggraph.resolve import ResolvedImport, resolve_file_imports

BUILTIN_NAMES = set(dir(builtins))


@dataclass(frozen=True)
class CallEdge:
    caller: str
    callee: str
    lineno: int
    status: str


@dataclass
class _Scope:
    parent: _Scope | None
    names: dict[str, str] = field(default_factory=dict)
    qual: str = ""


def import_bindings(resolved: list[ResolvedImport]) -> dict[str, str]:
    out: dict[str, str] = {}
    for rec in resolved:
        if rec.kind == "from_star" or rec.local_name is None:
            continue
        out[rec.local_name] = rec.origin
    return out


class _Analyzer(ast.NodeVisitor):
    def __init__(self, rel: str, bindings: dict[str, str]) -> None:
        self.rel = rel
        self.edges: list[CallEdge] = []
        self.scope = _Scope(None, dict(bindings), "")

    def _lookup(self, name: str) -> str:
        scope: _Scope | None = self.scope
        while scope is not None:
            if name in scope.names:
                return scope.names[name]
            scope = scope.parent
        if name in BUILTIN_NAMES:
            return f"external:builtins.{name}"
        return f"unresolved:{name}"

    def _caller(self) -> str:
        qual = self.scope.qual
        return f"{self.rel}::{qual if qual else '<module>'}"

    def _status(self, target: str) -> str:
        if target.startswith("external:"):
            return "external"
        if target.startswith("unresolved:"):
            return "unresolved"
        if target.startswith("attr:"):
            return "attr"
        if target.startswith("param:"):
            return "unresolved"
        return "bound"

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            target = self._lookup(node.func.id)
            self.edges.append(
                CallEdge(self._caller(), target, node.lineno, self._status(target))
            )
        elif isinstance(node.func, ast.Attribute):
            target = f"attr:{node.func.attr}"
            self.edges.append(
                CallEdge(self._caller(), target, node.lineno, "attr")
            )
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._handle_fn(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._handle_fn(node)

    def _handle_fn(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        for default in node.args.defaults:
            self.visit(default)
        for default in node.args.kw_defaults:
            if default is not None:
                self.visit(default)

        parent = self.scope
        qual = f"{parent.qual}.{node.name}" if parent.qual else node.name
        parent.names[node.name] = f"{self.rel}::{qual}"

        child = _Scope(parent, {}, qual)
        for arg in node.args.posonlyargs:
            child.names[arg.arg] = f"param:{qual}.{arg.arg}"
        for arg in node.args.args:
            child.names[arg.arg] = f"param:{qual}.{arg.arg}"
        for arg in node.args.kwonlyargs:
            child.names[arg.arg] = f"param:{qual}.{arg.arg}"
        if node.args.vararg:
            child.names[node.args.vararg.arg] = f"param:{qual}.{node.args.vararg.arg}"
        if node.args.kwarg:
            child.names[node.args.kwarg.arg] = f"param:{qual}.{node.args.kwarg.arg}"

        self.scope = child
        for stmt in node.body:
            self.visit(stmt)
        self.scope = parent

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        for base in node.bases:
            self.visit(base)

        parent = self.scope
        qual = f"{parent.qual}.{node.name}" if parent.qual else node.name
        parent.names[node.name] = f"{self.rel}::{qual}"
        self.scope = _Scope(parent, {}, qual)
        for stmt in node.body:
            self.visit(stmt)
        self.scope = parent

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self.visit(node.body)


def collect_calls(root: Path) -> list[CallEdge]:
    files = iter_python_files(root)
    parsed_ok: list[tuple[Path, str, ast.AST]] = []
    for path in files:
        parsed = parse_file(path)
        if parsed.error or parsed.tree is None:
            continue
        parsed_ok.append((path, rel_posix(root, path), parsed.tree))

    edges: list[CallEdge] = []
    for path, rel, tree in parsed_ok:
        edges.extend(_analyze_tree(rel, tree, root, path))
    return edges


def _predeclare_module_defs(analyzer: _Analyzer, tree: ast.AST) -> None:
    """Bind module-level defs before visiting bodies so later helpers resolve."""
    for stmt in getattr(tree, "body", []):
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            analyzer.scope.names[stmt.name] = f"{analyzer.rel}::{stmt.name}"


def _analyze_tree(rel: str, tree: ast.AST, root: Path, path: Path) -> list[CallEdge]:
    resolved = resolve_file_imports(root, path, extract_imports(tree))
    analyzer = _Analyzer(rel, import_bindings(resolved))
    _predeclare_module_defs(analyzer, tree)
    for stmt in tree.body:
        analyzer.visit(stmt)
    return analyzer.edges


def analyze_file(
    root: Path,
    path: Path,
    tree: ast.AST,
) -> tuple[list[ResolvedImport], list[CallEdge]]:
    rel = rel_posix(root, path)
    resolved = resolve_file_imports(root, path, extract_imports(tree))
    analyzer = _Analyzer(rel, import_bindings(resolved))
    _predeclare_module_defs(analyzer, tree)
    for stmt in tree.body:
        analyzer.visit(stmt)
    return resolved, analyzer.edges
