from pathlib import Path
import subprocess
from slopcheck.diff_parser import GitDiffError, parse_staged_diff
from slopcheck.rules import (
    Violation,
    check_filler_docstrings,
    check_micro_wrappers,
    check_obvious_comments,
    check_swallowed_exceptions,
    count_repo_calls,
)


def get_git_toplevel(cwd: Path) -> Path:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            cwd=cwd,
        )
        return Path(result.stdout.strip()).resolve()
    except (subprocess.CalledProcessError, FileNotFoundError) as err:
        err_msg = (
            err.stderr.strip()
            if isinstance(err, subprocess.CalledProcessError) and err.stderr
            else str(err)
        )
        raise GitDiffError(f"Git diff failed: {err_msg}") from err


def read_staged_file_bytes(repo_root: Path, rel_path: str) -> bytes | None:
    try:
        result = subprocess.run(
            ["git", "show", f":{rel_path}"],
            capture_output=True,
            check=True,
            cwd=repo_root,
        )
        return result.stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        file_path = repo_root / rel_path
        try:
            return file_path.read_bytes()
        except OSError:
            return None


def scan_staged(repo_root: str | Path | None = None) -> tuple[list[Violation], int]:
    start_dir = Path(repo_root).resolve() if repo_root else Path.cwd().resolve()
    root = get_git_toplevel(start_dir)
    staged_map = parse_staged_diff(cwd=root)

    if not staged_map:
        return [], 0

    call_counts = count_repo_calls(root)
    violations: list[Violation] = []

    for rel_path, changed_lines in staged_map.items():
        source_bytes = read_staged_file_bytes(root, rel_path)
        if source_bytes is None:
            continue

        violations.extend(
            check_obvious_comments(rel_path, source_bytes, changed_lines)
        )
        violations.extend(
            check_swallowed_exceptions(rel_path, source_bytes, changed_lines)
        )
        violations.extend(
            check_micro_wrappers(rel_path, source_bytes, call_counts, changed_lines)
        )
        violations.extend(
            check_filler_docstrings(rel_path, source_bytes, changed_lines)
        )

    violations.sort(key=lambda v: (v.file_path, v.line, v.rule_id))
    return violations, len(staged_map)