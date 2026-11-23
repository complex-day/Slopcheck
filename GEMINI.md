# Project Rules for `slopcheck`

## 1. Project Overview
- `slopcheck` is a 100% offline, zero-cost Python CLI tool that scans `git diff --cached` and catches 4 types of AI-generated code smells ("AI slop"):
  1. Captain Obvious Comments (>70% word overlap with next-line identifier; skip `# type: ignore` and `# noqa`)
  2. Swallowed Exceptions (`try/except` or `try/except*` catching bare `except:` or `Exception` with only `pass`, `print()`, or contextless `raise`)
  3. Single-Use Micro-Wrappers (<3-statement newly added functions called only once in the repo; skip `@property` and `@abstractmethod`)
  4. AI Filler Docstrings (LLM boilerplate like "This function is responsible for..." or "Helper method to...")

## 2. Tech Stack & Packaging (Strict)
- Python 3.10+ using modern `src/` layout (`src/slopcheck/`) and `pyproject.toml` with `setuptools`.
- CLI parsing: Use Python's built-in `argparse` only (no Click/Typer unless explicitly asked).
- Static Analysis Parser: Use ONLY `tree-sitter` (v0.27.0+) and `tree-sitter-python`. Do NOT mix with Python's built-in `ast` or `tokenize` modules.
- Zero external API calls or cloud services. Must run 100% offline.

## 3. Tree-sitter v0.27.0+ API Rules (CRITICAL)
- NEVER use deprecated APIs:
  - NO `Language.build_library()`
  - NO `tree_sitter_languages`
  - NO direct `query.captures()` without `QueryCursor`
- ALWAYS use the latest pattern:
  - `Language(tspython.language())`
  - `Parser(PY_LANGUAGE)`
  - `Query(PY_LANGUAGE, query_str)`
  - `QueryCursor(query)` (note: `.captures()` returns a `dict` mapping capture names to lists of nodes)

## 4. Coding Discipline (No AI Slop)
- Follow step-by-step scope strictly: ONLY build what is asked in the current prompt. Never jump ahead or scaffold future rules early.
- Keep functions small, clear, and readable—no unnecessary wrapper functions or obvious comments.
- Always consider Python edge cases when implementing rules: `async def`, nested functions, decorators (`@property`, `@abstractmethod`), bare `except:`, `except Exception as e:`, and `except*`.

## 5. Testing Requirement
- Use `pytest` for all tests inside `tests/`.
- For every detection rule, create `tests/fixtures/` with at least 2 dirty (should trigger) and 2 clean (should pass) Python files.
