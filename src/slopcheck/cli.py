import argparse
import sys
from slopcheck import __version__
from slopcheck.config import ConfigError
from slopcheck.diff_parser import GitDiffError
from slopcheck.runner import fix_staged, scan_staged


def _run_fix_mode(repo_root: str | None) -> int:
    summary = fix_staged(repo_root=repo_root)

    if summary.files_scanned == 0:
        print("slopcheck: No staged Python or JS/TS files to check.")
        return 0

    for path in summary.skipped_unstaged:
        print(
            f"slopcheck warning: Skipped '{path}' (has unstaged edits; stage or stash them before --fix).",
            file=sys.stderr,
        )

    if summary.total_fixes > 0:
        print(
            f"slopcheck: Auto-fixed {summary.total_fixes} issue(s) across {summary.files_fixed} file(s) and re-staged."
        )

    if not summary.remaining_violations:
        print("slopcheck: Clean! 0 violations remaining.")
        return 0

    for v in summary.remaining_violations:
        print(f"{v.file_path}:{v.line}: [{v.rule_id}] {v.message}")

    print(
        f"\nslopcheck: {len(summary.remaining_violations)} violation(s) remaining that require manual review."
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="slopcheck",
        description="A 100% offline CLI tool to detect AI-generated code slop in staged git changes.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=None,
        help="Path to the Git repository root (defaults to current working directory).",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Auto-remove safe AI slop (obvious comments and filler docstrings) from staged files and re-stage them.",
    )

    args = parser.parse_args(argv)

    try:
        if args.fix:
            return _run_fix_mode(args.repo)
        violations, files_scanned = scan_staged(repo_root=args.repo)
    except ConfigError as err:
        print(f"slopcheck config error: {err}", file=sys.stderr)
        return 2
    except GitDiffError as err:
        print(f"slopcheck error: {err}", file=sys.stderr)
        return 2

    if files_scanned == 0:
        print("slopcheck: No staged Python or JS/TS files to check.")
        return 0

    if not violations:
        print(
            f"slopcheck: Clean! Scanned {files_scanned} staged file(s) with 0 violations."
        )
        return 0

    for v in violations:
        print(f"{v.file_path}:{v.line}: [{v.rule_id}] {v.message}")

    print(
        f"\nslopcheck: Found {len(violations)} violation(s) across {files_scanned} staged file(s)."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
