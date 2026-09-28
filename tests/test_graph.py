from __future__ import annotations

from pathlib import Path

from kggraph.bind import collect_calls
from kggraph.extract import extract_definitions
from kggraph.index import index_repo
from kggraph.parse import parse_file
from kggraph.query import ask, who_calls

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"


def _index(name: str, tmp_path: Path) -> Path:
    db = tmp_path / f"{name}.sqlite"
    index_repo(FIXTURES / name, db)
    return db


def test_happy_who_calls(tmp_path: Path) -> None:
    db = _index("happy", tmp_path)
    hits = who_calls(db, "fetch_user")
    callers = {h["caller"] for h in hits}
    assert "app.py::app" in callers
    assert all("shadow" not in h["caller"] for h in hits)


def test_shadow_does_not_call_api(tmp_path: Path) -> None:
    db = _index("shadow", tmp_path)
    hits = who_calls(db, "api.py::fetch_user")
    assert hits == []
    local = who_calls(db, "shadow.py::fetch_user")
    assert any(h["caller"] == "shadow.py::run" for h in local)


def test_alias_call_binds_to_export(tmp_path: Path) -> None:
    db = _index("alias", tmp_path)
    hits = who_calls(db, "api.py::fetch_user")
    assert any(h["caller"] == "app.py::app" for h in hits)


def test_syntax_error_skips_bad_file() -> None:
    parsed = parse_file(FIXTURES / "syntax_error" / "bad.py")
    assert parsed.error
    good = parse_file(FIXTURES / "syntax_error" / "good.py")
    assert good.tree is not None
    names = [d.qualname for d in extract_definitions(good.tree)]
    assert names == ["good"]


def test_relative_import(tmp_path: Path) -> None:
    db = _index("relative", tmp_path)
    hits = who_calls(db, "pkg/api.py::fetch_user")
    assert any(h["caller"] == "pkg/app.py::app" for h in hits)


def test_stdlib_is_external() -> None:
    from kggraph.imports import extract_imports
    from kggraph.parse import parse_file
    from kggraph.resolve import resolve_file_imports

    path = FIXTURES / "stdlib_import" / "app.py"
    resolved = resolve_file_imports(
        FIXTURES / "stdlib_import",
        path,
        extract_imports(parse_file(path).tree),
    )
    origins = {r.origin for r in resolved}
    assert any(o.startswith("external:os") for o in origins)
    assert any(o.startswith("external:json") for o in origins)


def test_star_import_does_not_bind_symbol() -> None:
    edges = collect_calls(FIXTURES / "star_import")
    fetch_calls = [e for e in edges if e.caller.endswith("::app")]
    assert fetch_calls
    assert all(e.status != "bound" or "api.py::fetch_user" not in e.callee for e in fetch_calls)


def test_async_and_default_arg() -> None:
    async_edges = collect_calls(FIXTURES / "async_def")
    assert any(e.callee.endswith("::fetch_user") for e in async_edges)
    default_edges = collect_calls(FIXTURES / "default_arg")
    assert any(e.callee.endswith("::helper") for e in default_edges)


def test_two_packages_do_not_merge(tmp_path: Path) -> None:
    db = _index("two_packages", tmp_path)
    a_hits = who_calls(db, "pkg_a/util.py::helper")
    b_hits = who_calls(db, "pkg_b/util.py::helper")
    assert a_hits == []
    assert b_hits == []
    from kggraph.extract import extract_definitions
    from kggraph.parse import parse_file

    a = extract_definitions(parse_file(FIXTURES / "two_packages" / "pkg_a" / "util.py").tree)
    b = extract_definitions(parse_file(FIXTURES / "two_packages" / "pkg_b" / "util.py").tree)
    assert a[0].qualname == b[0].qualname == "helper"


def test_ask_finds_app(tmp_path: Path) -> None:
    db = _index("happy", tmp_path)
    result = ask(db, "fetch_user app")
    assert result["seeds"]
    blob = " ".join(result["seeds"])
    assert "fetch_user" in blob or "app" in blob


def test_index_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "id.sqlite"
    first = index_repo(FIXTURES / "happy", db)
    second = index_repo(FIXTURES / "happy", db)
    assert first["nodes"] == second["nodes"]
    assert first["edges"] == second["edges"]


def test_incremental_delete(tmp_path: Path) -> None:
    src = tmp_path / "proj"
    src.mkdir()
    (src / "api.py").write_text("def fetch_user():\n    return 1\n")
    (src / "app.py").write_text("from api import fetch_user\n\ndef app():\n    return fetch_user()\n")
    db = tmp_path / "inc.sqlite"
    index_repo(src, db)
    assert who_calls(db, "fetch_user")
    (src / "api.py").unlink()
    index_repo(src, db, incremental=True)
    remaining = who_calls(db, "api.py::fetch_user")
    assert remaining == []
