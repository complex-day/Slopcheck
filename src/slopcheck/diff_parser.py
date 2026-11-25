from pathlib import Path
import re
import subprocess


class GitDiffError(Exception):
    """Raised when git diff execution fails."""


PYTHON_EXTENSIONS = frozenset({".py"})
SUPPORTED_EXTENSIONS = frozenset(
    {".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".mts", ".cts", ".tsx"}
)


HUNK_HEADER_RE = re.compile(
    r"^@@\s+-[0-9]+(?:,[0-9]+)?\s+\+([0-9]+)(?:,([0-9]+))?\s+@@"
)


def get_staged_diff_text(cwd: str | Path | None = None) -> str:
    cmd = [
        "git",
        "-c",
        "core.quotepath=false",
        "diff",
        "--cached",
        "--unified=0",
        "--diff-filter=ACM",
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            cwd=cwd,
        )
        return result.stdout
    except (subprocess.CalledProcessError, FileNotFoundError) as err:
        err_msg = (
            err.stderr.strip()
            if isinstance(err, subprocess.CalledProcessError) and err.stderr
            else str(err)
        )
        raise GitDiffError(f"Git diff failed: {err_msg}") from err


def parse_diff_output(
    diff_text: str,
    extensions: frozenset[str] = PYTHON_EXTENSIONS,
) -> dict[str, set[int]]:
    diff_map: dict[str, set[int]] = {}
    current_file: str | None = None

    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            current_file = None
            continue

        if line.startswith("Binary files ") or line.startswith("GIT binary patch"):
            if current_file is not None:
                diff_map.pop(current_file, None)
                current_file = None
            continue

        if line.startswith("+++ "):
            raw_path = line[4:].strip()
            if raw_path.startswith('"') and raw_path.endswith('"'):
                raw_path = raw_path[1:-1]
            if raw_path == "/dev/null":
                current_file = None
                continue
            if raw_path.startswith("b/"):
                raw_path = raw_path[2:]

            normalized_path = raw_path.replace("\\", "/")
            if Path(normalized_path).suffix.lower() in extensions:
                current_file = normalized_path
                diff_map.setdefault(current_file, set())
            else:
                current_file = None
            continue

        if current_file is not None:
            match = HUNK_HEADER_RE.match(line)
            if match:
                new_start = int(match.group(1))
                new_count = int(match.group(2)) if match.group(2) is not None else 1
                if new_count > 0:
                    diff_map[current_file].update(
                        range(new_start, new_start + new_count)
                    )

    return {path: lines for path, lines in diff_map.items() if lines}


def parse_staged_diff(
    cwd: str | Path | None = None,
    extensions: frozenset[str] = PYTHON_EXTENSIONS,
) -> dict[str, set[int]]:
    diff_text = get_staged_diff_text(cwd=cwd)
    return parse_diff_output(diff_text, extensions=extensions)


get_staged_diff = parse_staged_diff