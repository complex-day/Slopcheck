from dataclasses import dataclass
import fnmatch
from pathlib import Path
import subprocess
from slopcheck.config import SlopcheckConfig, VALID_RULE_IDS, load_config
from slopcheck.diff_parser import GitDiffError, parse_staged_diff
from slopcheck.fixer import fix_python_source
from slopcheck.rules import (
    Violation,
    check_filler_docstrings,
    check_micro_wrappers,
    check_obvious_comments,
    check_swallowed_exceptions,
    count_repo_calls,
)


@dataclass(frozen=True)
class FixSummary:
    files_scanned: int
    files_fixed: int
    total_fixes: int
    skipped_unstaged: tuple[str, ...]
    remaining_violations: list[Violation]


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


def _is_excluded(rel_path: str, exclude_patterns: tuple[str, ...]) -> bool:
    normalized_path = rel_path.replace("\\", "/")
    for pattern in exclude_patterns:
        normalized_pattern = pattern.replace("\\", "/")
        if normalized_pattern.endswith("/"):
            normalized_pattern = f"{normalized_pattern}*"
        if fnmatch.fnmatch(normalized_path, normalized_pattern):
            return True
    return False


def _load_filtered_staged(
    repo_root: str | Path | None = None,
) -> tuple[Path, SlopcheckConfig, dict[str, set[int]]]:
    start_dir = Path(repo_root).resolve() if repo_root else Path.cwd().resolve()
    root = get_git_toplevel(start_dir)
    config = load_config(root)
    staged_map = parse_staged_diff(cwd=root)

    if config.exclude:
        staged_map = {
            rel_path: changed_lines
            for rel_path, changed_lines in staged_map.items()
            if not _is_excluded(rel_path, config.exclude)
        }

    return root, config, staged_map


def scan_staged(repo_root: str | Path | None = None) -> tuple[list[Violation], int]:
    root, config, staged_map = _load_filtered_staged(repo_root)

    if not staged_map:
        return [], 0

    if VALID_RULE_IDS.issubset(config.disabled_rules):
        return [], len(staged_map)

    call_counts = (
        count_repo_calls(root)
        if "micro-wrapper" not in config.disabled_rules
        else {}
    )
    violations: list[Violation] = []

    for rel_path, changed_lines in staged_map.items():
        source_bytes = read_staged_file_bytes(root, rel_path)
        if source_bytes is None:
            continue

        if "obvious-comment" not in config.disabled_rules:
            violations.extend(
                check_obvious_comments(
                    rel_path,
                    source_bytes,
                    changed_lines,
                    threshold=config.obvious_comment_threshold,
                )
            )
        if "swallowed-exception" not in config.disabled_rules:
            violations.extend(
                check_swallowed_exceptions(rel_path, source_bytes, changed_lines)
            )
        if "micro-wrapper" not in config.disabled_rules:
            violations.extend(
                check_micro_wrappers(
                    rel_path,
                    source_bytes,
                    call_counts,
                    changed_lines,
                    max_statements=config.micro_wrapper_max_statements,
                )
            )
        if "filler-docstring" not in config.disabled_rules:
            violations.extend(
                check_filler_docstrings(rel_path, source_bytes, changed_lines)
            )

    violations.sort(key=lambda v: (v.file_path, v.line, v.rule_id))
    return violations, len(staged_map)


def _has_unstaged_edits(
    repo_root: Path,
    rel_path: str,
    staged_bytes: bytes,
    disk_bytes: bytes,
) -> bool:
    if disk_bytes == staged_bytes:
        return False
    try:
        result = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            capture_output=True,
            cwd=repo_root,
        )
        return result.returncode != 0
    except OSError:
        return True


def fix_staged(repo_root: str | Path | None = None) -> FixSummary:
    root, config, staged_map = _load_filtered_staged(repo_root)

    if not staged_map:
        return FixSummary(0, 0, 0, (), [])

    files_fixed = 0
    total_fixes = 0
    skipped_unstaged: list[str] = []

    for rel_path, changed_lines in staged_map.items():
        staged_bytes = read_staged_file_bytes(root, rel_path)
        if staged_bytes is None:
            continue

        file_path = root / rel_path
        try:
            disk_bytes = file_path.read_bytes()
        except OSError:
            skipped_unstaged.append(rel_path)
            continue

        if _has_unstaged_edits(root, rel_path, staged_bytes, disk_bytes):
            skipped_unstaged.append(rel_path)
            continue

        result = fix_python_source(
            rel_path,
            disk_bytes,
            changed_lines=changed_lines,
            disabled_rules=config.disabled_rules,
            obvious_comment_threshold=config.obvious_comment_threshold,
        )

        if result.fixes_applied > 0:
            try:
                file_path.write_bytes(result.fixed_source)
                subprocess.run(
                    ["git", "add", "--", rel_path],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=True,
                    cwd=root,
                )
            except OSError as err:
                raise GitDiffError(f"Failed to write '{rel_path}': {err}") from err
            except (subprocess.CalledProcessError, FileNotFoundError) as err:
                err_msg = (
                    err.stderr.strip()
                    if isinstance(err, subprocess.CalledProcessError) and err.stderr
                    else str(err)
                )
                raise GitDiffError(
                    f"Git add failed for '{rel_path}': {err_msg}"
                ) from err

            files_fixed += 1
            total_fixes += result.fixes_applied

    remaining_violations, _ = scan_staged(repo_root=root)

    return FixSummary(
        files_scanned=len(staged_map),
        files_fixed=files_fixed,
        total_fixes=total_fixes,
        skipped_unstaged=tuple(skipped_unstaged),
        remaining_violations=remaining_violations,
    )