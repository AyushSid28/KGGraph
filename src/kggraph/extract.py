from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass(frozen=True)
class Definition:
    kind: str
    qualname: str
    lineno: int
    end_lineno: int | None


class _DefVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.defs: list[Definition] = []
        self._stack: list[str] = []

    def _qual(self, name: str) -> str:
        return ".".join(self._stack + [name]) if self._stack else name

    def _span(self, node: ast.AST) -> tuple[int, int | None]:
        lineno = getattr(node, "lineno", 0)
        end = getattr(node, "end_lineno", None)
        return lineno, end

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_fn(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_fn(node)

    def _visit_fn(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        lineno, end = self._span(node)
        self.defs.append(Definition("function", self._qual(node.name), lineno, end))
        self._stack.append(node.name)
        self.generic_visit(node)
        self._stack.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        lineno, end = self._span(node)
        self.defs.append(Definition("class", self._qual(node.name), lineno, end))
        self._stack.append(node.name)
        self.generic_visit(node)
        self._stack.pop()


def extract_definitions(tree: ast.AST) -> list[Definition]:
    visitor = _DefVisitor()
    visitor.visit(tree)
    return visitor.defs


def module_level_def_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in getattr(tree, "body", []):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
    return names
