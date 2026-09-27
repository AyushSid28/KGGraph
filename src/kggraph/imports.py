from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass(frozen=True)
class ImportRecord:
    lineno: int
    kind: str
    module: str | None
    names: tuple[tuple[str, str], ...]
    level: int


class _ImportVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.records: list[ImportRecord] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            local = alias.asname or alias.name
            self.records.append(
                ImportRecord(
                    lineno=node.lineno,
                    kind="import",
                    module=alias.name,
                    names=((alias.name, local),),
                    level=0,
                )
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if any(a.name == "*" for a in node.names):
            self.records.append(
                ImportRecord(
                    lineno=node.lineno,
                    kind="from_star",
                    module=node.module,
                    names=(),
                    level=node.level or 0,
                )
            )
            return
        names = tuple((a.name, a.asname or a.name) for a in node.names)
        self.records.append(
            ImportRecord(
                lineno=node.lineno,
                kind="from",
                module=node.module,
                names=names,
                level=node.level or 0,
            )
        )


def extract_imports(tree: ast.AST) -> list[ImportRecord]:
    visitor = _ImportVisitor()
    visitor.visit(tree)
    return visitor.records
