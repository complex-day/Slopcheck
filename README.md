# slopcheck

A 100% offline, zero-cost Python CLI tool that scans `git diff --cached` using Tree-sitter AST analysis to catch AI-generated code slop before you commit.

## Features & Detection Rules

`slopcheck` analyzes only your staged changes across four distinct code smells:

### 1. `obvious-comment` (Captain Obvious Comments)
Flags comments that repeat $>70\%$ of the words from the identifier defined on the immediately following line (skipping pragmas like `# type: ignore` and `# noqa`).

```python
# Bad: repeats the next-line function name
# Calculate total
def calculate_total():
    return 100

# Good: explains why or provides architectural context
# Cache result for 5 minutes to reduce database read load
def calculate_total():
    return 100
```

### 2. `swallowed-exception` (Swallowed Exceptions)
Flags broad catches (`except:`, `except Exception`, `except BaseException`, `except* Exception`) whose body only consists of `pass`, `...`, `print(...)`, or contextless `raise`.

```python
# Bad: silently swallows errors or only prints
try:
    process_order()
except Exception as e:
    print(e)

# Good: proper logging, context re-raising, or specific catch
try:
    process_order()
except ValueError:
    handle_invalid_order()
except Exception as e:
    logger.exception("Order processing failed")
    raise OrderProcessingError("Order failure") from e
```

### 3. `micro-wrapper` (Single-Use Micro-Wrappers)
Flags newly added functions of 1–2 statements that are only invoked once across the entire repository (skipping `@property`, `@abstractmethod`, dunders like `__init__`, and `test_*` functions).

```python
# Bad: single-use helper that adds indirection without reuse
def _fetch_user_raw(user_id: int):
    return db.query(User).get(user_id)

def get_user_profile(user_id: int):
    user = _fetch_user_raw(user_id)  # Only call in the whole repo
    return user.to_dict()
```

### 4. `filler-docstring` (AI Filler Docstrings)
Flags boilerplate docstrings filled with common LLM introductory phrases like *"This function is responsible for..."* or *"Helper method to..."*.

```python
# Bad: LLM boilerplate filler
def parse_config(path: str):
    """This function is responsible for parsing configuration files."""
    ...

# Good: concise and domain-specific
def parse_config(path: str):
    """Parse YAML settings into application configuration options."""
    ...
```

---

## Installation

Install from PyPI:
```bash
pip install git-slopcheck
```

Or install locally for development:
```bash
git clone https://github.com/complex-day/Slopcheck.git
cd Slopcheck
pip install -e ".[dev]"
```

---

## Usage

Run `slopcheck` against currently staged changes in your git repository:

```bash
# Scan staged changes in current working tree
slopcheck

# Scan staged changes in a specific repository root
slopcheck --repo /path/to/repo

# Check version
slopcheck --version
```

### Sample Output

```
app.py:1: [filler-docstring] AI filler docstring detected: contains boilerplate phrase 'this module is responsible for'
app.py:3: [obvious-comment] Obvious comment duplicates identifier 'calculate_total'
app.py:8: [micro-wrapper] Single-use micro-wrapper '_tiny_helper' has 1 statement(s) and is only called once
app.py:16: [swallowed-exception] Swallowed exception caught without proper logging or handling

slopcheck: Found 4 violation(s) across 1 staged file(s).
```

When no violations are found:
```
slopcheck: Clean! Scanned 2 staged file(s) with 0 violations.
```

### Exit Codes

| Exit Code | Meaning |
| :---: | :--- |
| `0` | Clean: No violations detected, or no staged Python files to check. |
| `1` | Violations: One or more code smell violations detected in staged diff. |
| `2` | Error: Git execution failed or directory is not a Git repository. |

---

## Pre-commit Integration

Add `slopcheck` as a pre-commit hook in your `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/complex-day/Slopcheck
    rev: v0.1.0
    hooks:
      - id: slopcheck
```

---

## License

MIT License. See [LICENSE](LICENSE) for details.
