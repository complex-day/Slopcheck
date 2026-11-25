import argparse
import sys
from slopcheck import __version__
from slopcheck.config import ConfigError
from slopcheck.diff_parser import GitDiffError
from slopcheck.license import (
    LicenseError,
    activate_license,
    check_pro_license,
    deactivate_local_license,
)
from slopcheck.runner import ProRequiredError, fix_staged, scan_staged_with_summary


def _run_license_command(command: str, key: str | None) -> int:
    if command == "activate":
        if key is None or not key.strip():
            print(
                "slopcheck error: Usage: slopcheck activate <LICENSE_KEY>",
                file=sys.stderr,
            )
            return 2
        try:
            status = activate_license(key)
        except LicenseError as err:
            print(f"slopcheck license error: {err}", file=sys.stderr)
            return 2
        expiry_note = f" (Expires: {status.expires_at})" if status.expires_at else ""
        print(
            f"slopcheck Pro activated! Offline cache valid for 14 days.{expiry_note}"
        )
        return 0

    if command == "status":
        status = check_pro_license()
        if status.is_pro:
            expiry_note = (
                f" (expires: {status.expires_at})" if status.expires_at else ""
            )
            print(f"slopcheck Pro: Active ({status.reason}){expiry_note}")
        else:
            print(
                f"slopcheck Free: Not activated ({status.reason}). Run 'slopcheck activate <LICENSE_KEY>' to unlock Pro."
            )
        return 0

    removed = deactivate_local_license()
    if removed:
        print("slopcheck: Local Pro license removed.")
    else:
        print("slopcheck: No local license found.")
    return 0


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
        "command",
        nargs="?",
        choices=["activate", "status", "deactivate"],
        default=None,
        help="Optional license management command (activate, status, deactivate).",
    )
    parser.add_argument(
        "key",
        nargs="?",
        default=None,
        help="License key used with 'slopcheck activate <LICENSE_KEY>'.",
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

    if args.command is not None:
        return _run_license_command(args.command, args.key)

    try:
        if args.fix:
            license_status = check_pro_license()
            if not license_status.is_pro:
                print(
                    "slopcheck Pro required: '--fix' auto-cleanup requires a Pro license. Run 'slopcheck activate <LICENSE_KEY>' to unlock.",
                    file=sys.stderr,
                )
                return 2
            return _run_fix_mode(args.repo)
        summary = scan_staged_with_summary(repo_root=args.repo)
    except ProRequiredError as err:
        print(f"slopcheck Pro required: {err}", file=sys.stderr)
        return 2
    except ConfigError as err:
        print(f"slopcheck config error: {err}", file=sys.stderr)
        return 2
    except GitDiffError as err:
        print(f"slopcheck error: {err}", file=sys.stderr)
        return 2

    if summary.skipped_pro_files:
        print(
            f"slopcheck notice: Skipped {len(summary.skipped_pro_files)} JS/TS file(s) (Pro feature — run 'slopcheck activate <LICENSE_KEY>' to unlock).",
            file=sys.stderr,
        )

    if summary.files_scanned == 0:
        if not summary.skipped_pro_files:
            print("slopcheck: No staged Python or JS/TS files to check.")
        return 0

    if not summary.violations:
        print(
            f"slopcheck: Clean! Scanned {summary.files_scanned} staged file(s) with 0 violations."
        )
        return 0

    for v in summary.violations:
        print(f"{v.file_path}:{v.line}: [{v.rule_id}] {v.message}")

    print(
        f"\nslopcheck: Found {len(summary.violations)} violation(s) across {summary.files_scanned} staged file(s)."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
