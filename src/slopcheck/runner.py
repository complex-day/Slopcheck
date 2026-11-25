from dataclasses import dataclass
import fnmatch
from pathlib import Path
import subprocess
from slopcheck.config import SlopcheckConfig, VALID_RULE_IDS, load_config
from slopcheck.diff_parser import GitDiffError, parse_staged_diff, SUPPORTED_EXTENSIONS
from slopcheck.fixer import fix_source
from slopcheck.license import check_pro_license
from slopcheck.parser import detect_language
from slopcheck.rules import (
    Violation,
    check_filler_docstrings,
    check_js_filler_docstrings,
    check_js_micro_wrappers,
    check_js_obvious_comments,
    check_js_swallowed_exceptions,
    check_micro_wrappers,
    check_obvious_comments,
    check_swallowed_exceptions,
    count_js_repo_calls,
    count_repo_calls,
)


_JS_TS_LANGUAGES = frozenset({"javascript", "typescript", "tsx"})


class ProRequiredError(Exception):
    """Raised when an operation requires an active slopcheck Pro license."""


@dataclass(frozen=True)
class ScanSummary:
    violations: list[Violation]
    files_scanned: int
    skipped_pro_files: tuple[str, ...] = ()


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
    *,
    is_pro: bool | None = None,
) -> tuple[Path, SlopcheckConfig, dict[str, set[int]], bool]:
    start_dir = Path(repo_root).resolve() if repo_root else Path.cwd().resolve()
    root = get_git_toplevel(start_dir)
    pro_active = check_pro_license().is_pro if is_pro is None else is_pro
    if (root / ".slopcheck.toml").exists() and not pro_active:
        raise ProRequiredError(
            "Custom '.slopcheck.toml' configuration requires slopcheck Pro. "
            "Run 'slopcheck activate <LICENSE_KEY>' to unlock."
        )
    config = load_config(root)
    staged_map = parse_staged_diff(cwd=root, extensions=SUPPORTED_EXTENSIONS)

    if config.exclude:
        staged_map = {
            rel_path: changed_lines
            for rel_path, changed_lines in staged_map.items()
            if not _is_excluded(rel_path, config.exclude)
        }

    return root, config, staged_map, pro_active


def _scan_file_violations(
    rel_path: str,
    source_bytes: bytes,
    changed_lines: set[int],
    config: SlopcheckConfig,
    py_call_counts: dict[str, int],
    js_call_counts: dict[str, int],
) -> list[Violation]:
    lang = detect_language(rel_path)
    if lang is None:
        return []

    violations: list[Violation] = []
    disabled = config.disabled_rules

    if lang == "python":
        if "obvious-comment" not in disabled:
            violations.extend(
                check_obvious_comments(
                    rel_path,
                    source_bytes,
                    changed_lines,
                    threshold=config.obvious_comment_threshold,
                )
            )
        if "swallowed-exception" not in disabled:
            violations.extend(
                check_swallowed_exceptions(rel_path, source_bytes, changed_lines)
            )
        if "micro-wrapper" not in disabled:
            violations.extend(
                check_micro_wrappers(
                    rel_path,
                    source_bytes,
                    py_call_counts,
                    changed_lines,
                    max_statements=config.micro_wrapper_max_statements,
                )
            )
        if "filler-docstring" not in disabled:
            violations.extend(
                check_filler_docstrings(rel_path, source_bytes, changed_lines)
            )
    elif lang in _JS_TS_LANGUAGES:
        if "obvious-comment" not in disabled:
            violations.extend(
                check_js_obvious_comments(
                    rel_path,
                    source_bytes,
                    lang,
                    changed_lines,
                    threshold=config.obvious_comment_threshold,
                )
            )
        if "swallowed-exception" not in disabled:
            violations.extend(
                check_js_swallowed_exceptions(rel_path, source_bytes, lang, changed_lines)
            )
        if "micro-wrapper" not in disabled:
            violations.extend(
                check_js_micro_wrappers(
                    rel_path,
                    source_bytes,
                    lang,
                    js_call_counts,
                    changed_lines,
                    max_statements=config.micro_wrapper_max_statements,
                )
            )
        if "filler-docstring" not in disabled:
            violations.extend(
                check_js_filler_docstrings(rel_path, source_bytes, lang, changed_lines)
            )

    return violations


def scan_staged_with_summary(
    repo_root: str | Path | None = None,
    *,
    is_pro: bool | None = None,
) -> ScanSummary:
    root, config, staged_map, pro_active = _load_filtered_staged(
        repo_root, is_pro=is_pro
    )

    skipped_pro_files: tuple[str, ...] = ()
    if not pro_active and staged_map:
        skipped = [p for p in staged_map if detect_language(p) in _JS_TS_LANGUAGES]
        if skipped:
            skipped_pro_files = tuple(sorted(skipped))
            staged_map = {
                p: lines
                for p, lines in staged_map.items()
                if detect_language(p) not in _JS_TS_LANGUAGES
            }

    if not staged_map:
        return ScanSummary(
            violations=[],
            files_scanned=0,
            skipped_pro_files=skipped_pro_files,
        )

    if VALID_RULE_IDS.issubset(config.disabled_rules):
        return ScanSummary(
            violations=[],
            files_scanned=len(staged_map),
            skipped_pro_files=skipped_pro_files,
        )

    has_py = any(detect_language(p) == "python" for p in staged_map)
    has_js = any(detect_language(p) in _JS_TS_LANGUAGES for p in staged_map)

    py_call_counts = (
        count_repo_calls(root)
        if "micro-wrapper" not in config.disabled_rules and has_py
        else {}
    )
    js_call_counts = (
        count_js_repo_calls(root)
        if "micro-wrapper" not in config.disabled_rules and has_js
        else {}
    )
    violations: list[Violation] = []

    for rel_path, changed_lines in staged_map.items():
        source_bytes = read_staged_file_bytes(root, rel_path)
        if source_bytes is None:
            continue
        violations.extend(
            _scan_file_violations(
                rel_path,
                source_bytes,
                changed_lines,
                config,
                py_call_counts,
                js_call_counts,
            )
        )

    violations.sort(key=lambda v: (v.file_path, v.line, v.rule_id))
    return ScanSummary(
        violations=violations,
        files_scanned=len(staged_map),
        skipped_pro_files=skipped_pro_files,
    )


def scan_staged(repo_root: str | Path | None = None) -> tuple[list[Violation], int]:
    summary = scan_staged_with_summary(repo_root=repo_root)
    return summary.violations, summary.files_scanned


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
    is_pro = check_pro_license().is_pro
    if not is_pro:
        raise ProRequiredError(
            "'--fix' auto-cleanup requires a Pro license. Run 'slopcheck activate <LICENSE_KEY>' to unlock."
        )

    root, config, staged_map, _ = _load_filtered_staged(repo_root, is_pro=True)

    if not staged_map:
        return FixSummary(0, 0, 0, (), [])

    if {"obvious-comment", "filler-docstring"}.issubset(config.disabled_rules):
        remaining = scan_staged_with_summary(repo_root=root, is_pro=True)
        return FixSummary(len(staged_map), 0, 0, (), remaining.violations)

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

        result = fix_source(
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

    remaining = scan_staged_with_summary(repo_root=root, is_pro=True)

    return FixSummary(
        files_scanned=len(staged_map),
        files_fixed=files_fixed,
        total_fixes=total_fixes,
        skipped_unstaged=tuple(skipped_unstaged),
        remaining_violations=remaining.violations,
    )