# KGGraph — plan and checklist

Python-first deterministic codebase graph. JS/TS later = new extractor, same node/edge kinds.

**Source of truth:** static analysis → SQLite graph. Queries never re-index the whole repo. No Jev, embeddings, Neo4j, or LLM in v1.

---

## V1 in / out

**In:** `.py` files, functions, classes, methods, imports, bare-name calls, `who-calls`, keyword `ask` + 2-hop walk, incremental re-index of changed files.

**Out:** Flask/Django routes, ORM models, `self.x()`, `importlib`, Jev, React/TS, perfect dataflow.

**Pass bar:** fixture `happy` + `shadow` — `who-calls` on `api.fetch_user` is `app` only, not `shadow`.

---

## Phases

| Phase | Goal | Done when |
|---|---|---|
| 0 | Fixtures exist | 15 tiny repos named in § fixtures |
| **1** | Crawl + parse + list defs | CLI prints file / class / function + lines; syntax errors skip file |
| 2 | Imports + resolve (same dir + relative) | `from api import fetch_user` → `api.py`; stdlib = external |
| 3 | Bind + CALLS | Shadowing fixture correct; alias `as` correct |
| 4 | SQLite persist | Re-run index is idempotent; `who-calls` CLI |
| 5 | Incremental | Edit/delete/rename file → graph matches full reindex on neighbors |
| 6 | Keyword `ask` + walk | Auth-like query returns seed files + paths; hop cap; no expand externals |
| 7 | Hardening | Star import, circular, two `util.py`, default-arg calls, async |
| Later | Plugins | Routes, TS/JS extractor, optional ranker |

Do not start phase N+1 until that phase’s checklist is ticked.

---

## Phase 0 — fixtures

- [x] `fixtures/happy/` — `api.py` + `app.py`
- [x] `fixtures/shadow/` — local `fetch_user` hides import
- [x] `fixtures/alias/` — `import as`
- [x] `fixtures/relative/` — package + `from .api import`
- [x] `fixtures/missing/` — bad import
- [x] `fixtures/syntax_error/` — one broken file + one good
- [x] `fixtures/stdlib_import/`
- [x] `fixtures/star_import/`
- [x] `fixtures/default_arg/`
- [x] `fixtures/async_def/`
- [x] `fixtures/two_packages/` — two `util.py`
- [x] `fixtures/circular/`
- [x] `fixtures/decorator/`
- [x] `fixtures/delete_file/` — for phase 5
- [x] `fixtures/rename_fn/` — for phase 5

---

## Phase 1 — crawl + parse + defs (code in chat; implement from there)

- [x] Skip `.venv`, `venv`, `__pycache__`, `site-packages`, `.git`
- [x] Recurse `*.py` under a given root
- [x] `ast.parse` UTF-8; on `SyntaxError` / decode error: record, continue
- [x] Module-level `FunctionDef` / `AsyncFunctionDef` / `ClassDef`
- [x] Methods on classes (qualified name `Class.method`)
- [x] Nested defs: include with parent path or skip — **v1: include as `outer.inner`**
- [x] CLI: `python -m kggraph scan <dir>`
- [x] Manual: `syntax_error` still lists the good file
- [x] Manual: two files both named `app.py` in different folders show **different paths**

**Not in phase 1:** imports, calls, SQLite, who-calls.

---

## Phase 2 — imports

- [x] `import x` / `from x import y` / `import x as a` / `from x import y as z`
- [x] Same-directory module file
- [x] Package relative `.` and `..` if cheap
- [x] Stdlib + missing → `external:` / `unresolved:`
- [x] Do not follow `*` into fake symbols
- [x] Circular import: no infinite loop

---

## Phase 3 — bind + calls

- [x] Scope: module → function → nested; inner wins
- [x] Import is a local def pointing at resolved symbol
- [x] `fetch_user()` CALLS bound symbol
- [x] Shadow fixture
- [x] Alias fixture
- [x] `await f()` counts as CALLS
- [x] Call in default arg counted
- [x] Bare builtin `print` → external or skip (pick one, test it)
- [x] Attribute calls `api.f()` / `self.x()` → unresolved or later phase

---

## Phase 4 — store + who-calls

- [x] Schema: nodes + edges; ids = `path::qualname`
- [x] Transaction per index run
- [x] Second full index: same graph
- [x] `who-calls <qualname or name>`
- [x] Two `init` in two files do not merge

---

## Phase 5 — incremental

- [x] Git or mtime list of changed `.py`
- [x] Delete nodes/edges owned by those files
- [x] Re-extract; re-resolve importers of changed modules
- [x] Delete file: importers unresolved
- [x] Rename function: old symbol gone
- [x] Format-only: graph equal

---

## Phase 6 — ask

- [x] FTS or LIKE on file path + symbol name
- [x] Top seeds → walk `calls`/`imports` hop ≤ 2
- [x] Do not expand `external:`
- [x] Zero hits → empty, not random

---

## Phase 7 — edge-case sweep

Tick against the edge-case list (crawl skip, star import, class-body `x` lookup may stay documented miss). Fixture suite + Vortex smoke test done. Method calls (`self.x`) remain `attr:` by design.

---

## Language-agnostic graph (keep stable)

**Nodes:** `file`, `function`, `class` (methods = `function` with `parent_class` or `Class.method` name).  
**Edges:** `contains`, `imports`, `calls` (later `extends`).

TS/JS later emits these only.

---

## Stop rules

- Do not add Jev until keyword + graph is measured on a real Python repo.
- Do not add Neo4j until SQLite is too slow (measure).
- Do not treat heuristic routes as `confidence = 1.0`.
