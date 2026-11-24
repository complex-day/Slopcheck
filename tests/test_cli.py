from pathlib import Path
import subprocess
import pytest
from slopcheck.cli import main

DIRTY_CODE = '''"""This module is responsible for testing all rules."""

# Calculate total
def calculate_total():
    a = 10
    b = 90
    return a + b

def _tiny_helper(x: int) -> int:
    return x + 1

def run_all():
    val = _tiny_helper(10)
    try:
        return calculate_total() + val
    except:
        pass
'''


def init_repo(repo_dir: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )


def test_cli_version(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "slopcheck 0.1.0" in captured.out


def test_cli_non_git_repo(tmp_path: Path, capsys):
    exit_code = main(["--repo", str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "slopcheck error:" in captured.err


def test_cli_no_staged_files(tmp_path: Path, capsys):
    init_repo(tmp_path)
    exit_code = main(["--repo", str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "slopcheck: No staged Python files to check." in captured.out


def test_cli_clean_file(tmp_path: Path, capsys):
    init_repo(tmp_path)
    clean_file = tmp_path / "clean.py"
    clean_file.write_text(
        "def add(a: int, b: int) -> int:\n    return a + b\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "clean.py"], cwd=tmp_path, check=True)

    exit_code = main(["--repo", str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "slopcheck: Clean! Scanned 1 staged file(s) with 0 violations." in captured.out


def test_cli_dirty_file_all_rules(tmp_path: Path, capsys):
    init_repo(tmp_path)
    dirty_file = tmp_path / "app.py"
    dirty_file.write_text(DIRTY_CODE, encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=tmp_path, check=True)

    exit_code = main(["--repo", str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "obvious-comment" in captured.out
    assert "swallowed-exception" in captured.out
    assert "micro-wrapper" in captured.out
    assert "filler-docstring" in captured.out
    assert "slopcheck: Found 4 violation(s) across 1 staged file(s)." in captured.out


def test_cli_untouched_committed_dirty_lines_ignored(tmp_path: Path, capsys):
    init_repo(tmp_path)
    dirty_file = tmp_path / "app.py"
    dirty_file.write_text(DIRTY_CODE, encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "commit dirty code earlier"],
        cwd=tmp_path,
        check=True,
    )

    # Now append a clean variable at the end and only stage that
    with open(dirty_file, "a", encoding="utf-8") as f:
        f.write("\nEXTRA_CLEAN_VAR = 42\n")

    subprocess.run(["git", "add", "app.py"], cwd=tmp_path, check=True)

    exit_code = main(["--repo", str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "slopcheck: Clean! Scanned 1 staged file(s) with 0 violations." in captured.out


def test_cli_from_subdirectory(tmp_path: Path, capsys):
    init_repo(tmp_path)
    pkg_dir = tmp_path / "pkg"
    pkg_dir.mkdir()
    dirty_file = pkg_dir / "app.py"
    dirty_file.write_text(DIRTY_CODE, encoding="utf-8")
    subprocess.run(["git", "add", "pkg/app.py"], cwd=tmp_path, check=True)

    exit_code = main(["--repo", str(pkg_dir)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "obvious-comment" in captured.out
    assert "swallowed-exception" in captured.out
    assert "micro-wrapper" in captured.out
    assert "filler-docstring" in captured.out
    assert "slopcheck: Found 4 violation(s) across 1 staged file(s)." in captured.out


def test_cli_reads_staged_index_not_unstaged_edits(tmp_path: Path, capsys):
    init_repo(tmp_path)
    app_file = tmp_path / "app.py"
    app_file.write_text(DIRTY_CODE, encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=tmp_path, check=True)

    # Overwrite on disk with clean code without staging
    app_file.write_text(
        "def clean_addition(a: int, b: int) -> int:\n    return a + b\n",
        encoding="utf-8",
    )

    exit_code = main(["--repo", str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "obvious-comment" in captured.out
    assert "swallowed-exception" in captured.out
    assert "filler-docstring" in captured.out
    assert "slopcheck: Found 3 violation(s) across 1 staged file(s)." in captured.out
