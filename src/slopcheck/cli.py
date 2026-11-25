import argparse
import sys
from slopcheck import __version__
from slopcheck.config import ConfigError
from slopcheck.diff_parser import GitDiffError
from slopcheck.runner import scan_staged


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

    args = parser.parse_args(argv)

    try:
        violations, files_scanned = scan_staged(repo_root=args.repo)
    except ConfigError as err:
        print(f"slopcheck config error: {err}", file=sys.stderr)
        return 2
    except GitDiffError as err:
        print(f"slopcheck error: {err}", file=sys.stderr)
        return 2

    if files_scanned == 0:
        print("slopcheck: No staged Python files to check.")
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
