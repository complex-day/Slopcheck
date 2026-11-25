import io
import json
from pathlib import Path
import subprocess
import urllib.error
from unittest.mock import patch

import pytest

from slopcheck import __version__
from slopcheck.cli import main
from slopcheck.license import activate_license


class _FakeHTTPResponse:
    def __init__(self, payload: dict):
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _make_http_error(code: int, detail: str) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="https://api.polar.sh/v1/customer-portal/license-keys/activate",
        code=code,
        msg="Error",
        hdrs=None,
        fp=io.BytesIO(json.dumps({"detail": detail}).encode("utf-8")),
    )


@pytest.fixture(autouse=True)
def _isolated_slopcheck_home(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SLOPCHECK_HOME", str(tmp_path / ".slopcheck_test_home"))


def _activate_mock_pro(key: str = "SLOP-PRO-TEST", expires_at: str | None = None) -> None:
    payload = {
        "id": "act_cli_test",
        "license_key": {
            "status": "granted",
            "expires_at": expires_at,
        },
    }
    with patch("urllib.request.urlopen", return_value=_FakeHTTPResponse(payload)):
        activate_license(key)

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
    assert f"slopcheck {__version__}" in captured.out
    assert "slopcheck 0.2.0" in captured.out


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
    assert "slopcheck: No staged Python or JS/TS files to check." in captured.out


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


def test_cli_config_disabled_rules(tmp_path: Path, capsys, monkeypatch):
    import slopcheck.runner as runner

    _activate_mock_pro()
    init_repo(tmp_path)
    (tmp_path / ".slopcheck.toml").write_text(
        '[slopcheck]\ndisabled_rules = ["micro-wrapper", "filler-docstring"]\n',
        encoding="utf-8",
    )
    app_file = tmp_path / "app.py"
    app_file.write_text(DIRTY_CODE, encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=tmp_path, check=True)

    called = False

    def fail_if_called(_root):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(runner, "count_repo_calls", fail_if_called)

    exit_code = main(["--repo", str(tmp_path)])
    captured = capsys.readouterr()

    assert not called
    assert exit_code == 1
    assert "obvious-comment" in captured.out
    assert "swallowed-exception" in captured.out
    assert "micro-wrapper" not in captured.out
    assert "filler-docstring" not in captured.out
    assert "slopcheck: Found 2 violation(s) across 1 staged file(s)." in captured.out


def test_cli_config_exclude_skips_matching_files(tmp_path: Path, capsys):
    _activate_mock_pro()
    init_repo(tmp_path)
    (tmp_path / ".slopcheck.toml").write_text(
        '[slopcheck]\nexclude = ["vendor/*", "legacy\\\\*"]\n',
        encoding="utf-8",
    )

    excluded_code = (
        "# Calculate total\n"
        "def calculate_total():\n"
        "    return 1\n"
    )

    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "gen.py").write_text(excluded_code, encoding="utf-8")
    (tmp_path / "legacy").mkdir()
    (tmp_path / "legacy" / "old.py").write_text(excluded_code, encoding="utf-8")
    (tmp_path / "app.py").write_text(DIRTY_CODE, encoding="utf-8")

    subprocess.run(
        ["git", "add", "vendor/gen.py", "legacy/old.py", "app.py"],
        cwd=tmp_path,
        check=True,
    )

    exit_code = main(["--repo", str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "vendor/gen.py" not in captured.out
    assert "legacy/old.py" not in captured.out
    assert "app.py:" in captured.out
    assert "slopcheck: Found 4 violation(s) across 1 staged file(s)." in captured.out


def test_cli_config_exclude_all_staged_skips_repo_walk(
    tmp_path: Path, capsys, monkeypatch
):
    import slopcheck.runner as runner

    _activate_mock_pro()
    init_repo(tmp_path)
    (tmp_path / ".slopcheck.toml").write_text(
        '[slopcheck]\nexclude = ["vendor/*"]\n',
        encoding="utf-8",
    )

    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "gen.py").write_text(DIRTY_CODE, encoding="utf-8")
    subprocess.run(["git", "add", "vendor/gen.py"], cwd=tmp_path, check=True)

    called = False

    def fail_if_called(_root):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(runner, "count_repo_calls", fail_if_called)

    exit_code = main(["--repo", str(tmp_path)])
    captured = capsys.readouterr()

    assert not called
    assert exit_code == 0
    assert "slopcheck: No staged Python or JS/TS files to check." in captured.out


def test_cli_config_custom_threshold_and_max_statements(tmp_path: Path, capsys):
    init_repo(tmp_path)
    sample_code = (
        "# calculate total amount\n"
        "def calculate_total():\n"
        "    return 1\n\n"
        "def _three_step_helper(x: int) -> int:\n"
        "    a = x + 1\n"
        "    b = a * 2\n"
        "    return b\n\n"
        "def run() -> int:\n"
        "    return _three_step_helper(3)\n"
    )
    app_file = tmp_path / "app.py"
    app_file.write_text(sample_code, encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=tmp_path, check=True)

    # Without config: 2/3 overlap <= 0.70 and 3 statements > 2 -> clean
    assert main(["--repo", str(tmp_path)]) == 0
    capsys.readouterr()

    # With Pro + looser threshold and higher max_statements -> both flagged
    _activate_mock_pro()
    (tmp_path / ".slopcheck.toml").write_text(
        "[rules.obvious_comment]\n"
        "threshold = 0.5\n"
        "[rules.micro_wrapper]\n"
        "max_statements = 3\n",
        encoding="utf-8",
    )

    exit_code = main(["--repo", str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "obvious-comment" in captured.out
    assert "micro-wrapper" in captured.out
    assert "slopcheck: Found 2 violation(s) across 1 staged file(s)." in captured.out


def test_cli_malformed_config_exits_2(tmp_path: Path, capsys):
    _activate_mock_pro()
    init_repo(tmp_path)
    (tmp_path / ".slopcheck.toml").write_text(
        "[slopcheck\nbroken",
        encoding="utf-8",
    )
    app_file = tmp_path / "app.py"
    app_file.write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=tmp_path, check=True)

    exit_code = main(["--repo", str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "slopcheck config error:" in captured.err
    assert captured.out == ""


def test_cli_config_exclude_trailing_slash_folder(tmp_path: Path, capsys):
    _activate_mock_pro()
    init_repo(tmp_path)
    (tmp_path / ".slopcheck.toml").write_text(
        '[slopcheck]\nexclude = ["migrations/"]\n',
        encoding="utf-8",
    )

    (tmp_path / "migrations").mkdir()
    (tmp_path / "migrations" / "0001_init.py").write_text(
        "# Calculate total\ndef calculate_total():\n    return 1\n",
        encoding="utf-8",
    )
    (tmp_path / "app.py").write_text(
        "def clean(a: int, b: int) -> int:\n    return a + b\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "migrations/0001_init.py", "app.py"],
        cwd=tmp_path,
        check=True,
    )

    exit_code = main(["--repo", str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "slopcheck: Clean! Scanned 1 staged file(s) with 0 violations." in captured.out


def test_cli_all_rules_disabled_skips_file_reads(tmp_path: Path, capsys, monkeypatch):
    import slopcheck.runner as runner

    _activate_mock_pro()
    init_repo(tmp_path)
    (tmp_path / ".slopcheck.toml").write_text(
        '[slopcheck]\ndisabled_rules = ["obvious-comment", "swallowed-exception", "micro-wrapper", "filler-docstring"]\n',
        encoding="utf-8",
    )
    (tmp_path / "app.py").write_text(DIRTY_CODE, encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=tmp_path, check=True)

    called = False

    def fail_if_called(_root, _rel_path):
        nonlocal called
        called = True
        return b""

    monkeypatch.setattr(runner, "read_staged_file_bytes", fail_if_called)

    exit_code = main(["--repo", str(tmp_path)])
    captured = capsys.readouterr()

    assert not called
    assert exit_code == 0
    assert "slopcheck: Clean! Scanned 1 staged file(s) with 0 violations." in captured.out


def test_cli_fix_auto_removes_safe_slop_and_restages(tmp_path: Path, capsys):
    _activate_mock_pro()
    init_repo(tmp_path)
    app_file = tmp_path / "app.py"
    app_file.write_text(
        '"""This module is responsible for math."""\n\n'
        "# Calculate total\n"
        "def calculate_total(a: int, b: int) -> int:\n"
        '    """Helper function to add two numbers."""\n'
        "    return a + b\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "app.py"], cwd=tmp_path, check=True)

    exit_code = main(["--repo", str(tmp_path), "--fix"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "slopcheck: Auto-fixed 3 issue(s) across 1 file(s) and re-staged." in captured.out
    assert "slopcheck: Clean! 0 violations remaining." in captured.out

    # Subsequent normal scan should also be clean
    follow_up_code = main(["--repo", str(tmp_path)])
    follow_up_out = capsys.readouterr().out
    assert follow_up_code == 0
    assert "slopcheck: Clean! Scanned 1 staged file(s) with 0 violations." in follow_up_out

    # Verify working tree and staged index are in sync and fixed
    staged_blob = subprocess.run(
        ["git", "show", ":app.py"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    ).stdout
    assert staged_blob.decode("utf-8") == app_file.read_text(encoding="utf-8")
    assert subprocess.run(["git", "diff", "--quiet", "--", "app.py"], cwd=tmp_path).returncode == 0
    assert "This module is responsible for" not in app_file.read_text(encoding="utf-8")
    assert "# Calculate total" not in app_file.read_text(encoding="utf-8")
    assert "Helper function to" not in app_file.read_text(encoding="utf-8")


def test_cli_fix_leaves_swallowed_exception_and_exits_1(tmp_path: Path, capsys):
    _activate_mock_pro()
    init_repo(tmp_path)
    app_file = tmp_path / "app.py"
    app_file.write_text(
        "# Calculate total\n"
        "def calculate_total():\n"
        '    """Helper function to return 1."""\n'
        "    try:\n"
        "        return 1\n"
        "    except:\n"
        "        pass\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "app.py"], cwd=tmp_path, check=True)

    exit_code = main(["--repo", str(tmp_path), "--fix"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "slopcheck: Auto-fixed 2 issue(s) across 1 file(s) and re-staged." in captured.out
    assert "swallowed-exception" in captured.out
    assert "1 violation(s) remaining that require manual review." in captured.out

    fixed_text = app_file.read_text(encoding="utf-8")
    assert "# Calculate total" not in fixed_text
    assert "Helper function to" not in fixed_text
    assert "except:\n        pass" in fixed_text


def test_cli_fix_skips_file_with_unstaged_edits(tmp_path: Path, capsys):
    _activate_mock_pro()
    init_repo(tmp_path)
    app_file = tmp_path / "app.py"
    app_file.write_text(
        "# Calculate total\n"
        "def calculate_total():\n"
        "    return 1\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "app.py"], cwd=tmp_path, check=True)

    unstaged_content = (
        "# Calculate total\n"
        "def calculate_total():\n"
        "    # Unstaged local WIP edit\n"
        "    return 2\n"
    )
    app_file.write_text(unstaged_content, encoding="utf-8")

    exit_code = main(["--repo", str(tmp_path), "--fix"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "slopcheck warning: Skipped 'app.py'" in captured.err
    assert "unstaged edits" in captured.err
    assert "obvious-comment" in captured.out
    assert "1 violation(s) remaining that require manual review." in captured.out
    assert app_file.read_text(encoding="utf-8") == unstaged_content


def test_cli_fix_skips_fix_loop_when_fixable_rules_disabled(
    tmp_path: Path, capsys, monkeypatch
):
    import slopcheck.runner as runner

    _activate_mock_pro()
    init_repo(tmp_path)
    (tmp_path / ".slopcheck.toml").write_text(
        '[slopcheck]\ndisabled_rules = ["obvious-comment", "filler-docstring"]\n',
        encoding="utf-8",
    )
    app_file = tmp_path / "app.py"
    app_file.write_text(
        "# Calculate total\n"
        "def calculate_total():\n"
        "    try:\n"
        "        return 1\n"
        "    except:\n"
        "        pass\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "app.py"], cwd=tmp_path, check=True)

    called = False

    def fail_if_called(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("fix_source should not be called")

    monkeypatch.setattr(runner, "fix_source", fail_if_called)

    exit_code = main(["--repo", str(tmp_path), "--fix"])
    captured = capsys.readouterr()

    assert not called
    assert exit_code == 1
    assert "swallowed-exception" in captured.out
    assert "1 violation(s) remaining that require manual review." in captured.out


# ---------------------------------------------------------------------------
# JS/TS end-to-end tests
# ---------------------------------------------------------------------------

DIRTY_TS = """\
/** Helper method to calculate the total amount. */
// Calculate total
function calculateTotal(a: number, b: number): number {
    try {
        return a + b;
    } catch (e) {
        // swallowed
    }
    return 0;
}

function _tinyHelper(x: number): number {
    return x + 1;
}

function runAll(): number {
    return calculateTotal(1, _tinyHelper(2));
}
"""


def test_cli_scans_staged_ts_file_all_rules(tmp_path: Path, capsys):
    _activate_mock_pro()
    init_repo(tmp_path)
    ts_file = tmp_path / "service.ts"
    ts_file.write_text(DIRTY_TS, encoding="utf-8")
    subprocess.run(["git", "add", "service.ts"], cwd=tmp_path, check=True)

    exit_code = main(["--repo", str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "obvious-comment" in captured.out
    assert "filler-docstring" in captured.out
    assert "swallowed-exception" in captured.out
    assert "micro-wrapper" in captured.out
    assert "slopcheck: Found 4 violation(s) across 1 staged file(s)." in captured.out


def test_cli_fix_ts_file_removes_safe_slop_leaves_exception(tmp_path: Path, capsys):
    _activate_mock_pro()
    init_repo(tmp_path)
    ts_file = tmp_path / "service.ts"
    ts_file.write_text(
        "/**\n"
        " * Helper method to compute the total.\n"
        " */\n"
        "// Calculate total\n"
        "function calculateTotal(a: number, b: number): number {\n"
        "    try {\n"
        "        return a + b;\n"
        "    } catch (e) {}\n"
        "    return 0;\n"
        "}\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "service.ts"], cwd=tmp_path, check=True)

    exit_code = main(["--repo", str(tmp_path), "--fix"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "slopcheck: Auto-fixed 2 issue(s) across 1 file(s) and re-staged." in captured.out
    assert "swallowed-exception" in captured.out
    assert "1 violation(s) remaining that require manual review." in captured.out

    fixed_text = ts_file.read_text(encoding="utf-8")
    assert "// Calculate total" not in fixed_text
    assert "Helper method to compute the total" not in fixed_text
    assert "try {" in fixed_text
    assert subprocess.run(["git", "diff", "--quiet", "--", "service.ts"], cwd=tmp_path).returncode == 0


def test_cli_mixed_py_and_ts_staged_files(tmp_path: Path, capsys):
    _activate_mock_pro()
    init_repo(tmp_path)
    py_file = tmp_path / "app.py"
    py_file.write_text(
        '"""This module is responsible for math."""\n'
        "# Calculate total\n"
        "def calculate_total():\n"
        "    return 1\n",
        encoding="utf-8",
    )
    ts_file = tmp_path / "service.ts"
    ts_file.write_text(
        "/** Helper method to calculate total. */\n"
        "function calculateTotal(a: number, b: number): number {\n"
        "    return a + b;\n"
        "}\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "app.py", "service.ts"], cwd=tmp_path, check=True
    )

    exit_code = main(["--repo", str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "app.py" in captured.out
    assert "service.ts" in captured.out
    assert "obvious-comment" in captured.out
    assert "filler-docstring" in captured.out
    assert "slopcheck: Found 3 violation(s) across 2 staged file(s)." in captured.out


def test_cli_ignores_non_supported_staged_files(tmp_path: Path, capsys):
    init_repo(tmp_path)
    readme = tmp_path / "README.md"
    readme.write_text("# Calculate total\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)

    exit_code = main(["--repo", str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "slopcheck: No staged Python or JS/TS files to check." in captured.out


# ---------------------------------------------------------------------------
# License CLI commands & Free vs. Pro gating tests
# ---------------------------------------------------------------------------


def test_cli_activate_status_deactivate_flow(capsys):
    # Initial status: Free
    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "slopcheck Free: Not activated (not_activated)." in out

    # Missing or blank license key on activate -> usage error exit 2
    assert main(["activate"]) == 2
    err = capsys.readouterr().err
    assert "Usage: slopcheck activate <LICENSE_KEY>" in err

    assert main(["activate", "   "]) == 2
    err = capsys.readouterr().err
    assert "Usage: slopcheck activate <LICENSE_KEY>" in err

    # Invalid key from API -> license error exit 2
    with patch(
        "urllib.request.urlopen",
        side_effect=_make_http_error(404, "License key not found"),
    ):
        assert main(["activate", "SLOP-INVALID"]) == 2
    err = capsys.readouterr().err
    assert "slopcheck license error:" in err
    assert "License key not found" in err

    # Valid activation -> exit 0
    payload = {
        "id": "act_cli_flow",
        "license_key": {
            "status": "granted",
            "expires_at": "2099-01-01T00:00:00+00:00",
        },
    }
    with patch("urllib.request.urlopen", return_value=_FakeHTTPResponse(payload)):
        assert main(["activate", "SLOP-VALID-KEY"]) == 0
    out = capsys.readouterr().out
    assert "slopcheck Pro activated! Offline cache valid for 14 days." in out
    assert "2099-01-01T00:00:00+00:00" in out

    # Status now reports Active without making network calls
    with patch("urllib.request.urlopen") as mock_urlopen:
        assert main(["status"]) == 0
    mock_urlopen.assert_not_called()
    out = capsys.readouterr().out
    assert "slopcheck Pro: Active (active_cached)" in out
    assert "2099-01-01T00:00:00+00:00" in out

    # Deactivate removes local license
    assert main(["deactivate"]) == 0
    out = capsys.readouterr().out
    assert "slopcheck: Local Pro license removed." in out

    # Second deactivate reports no local license
    assert main(["deactivate"]) == 0
    out = capsys.readouterr().out
    assert "slopcheck: No local license found." in out


def test_cli_free_scans_python_all_rules_successfully(tmp_path: Path, capsys):
    init_repo(tmp_path)
    py_file = tmp_path / "app.py"
    py_file.write_text(DIRTY_CODE, encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=tmp_path, check=True)

    exit_code = main(["--repo", str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "obvious-comment" in captured.out
    assert "swallowed-exception" in captured.out
    assert "micro-wrapper" in captured.out
    assert "filler-docstring" in captured.out
    assert captured.err == ""


def test_cli_free_fix_requires_pro_exits_2(tmp_path: Path, capsys):
    init_repo(tmp_path)
    py_file = tmp_path / "app.py"
    py_file.write_text("# Calculate total\ndef calculate_total():\n    return 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=tmp_path, check=True)

    exit_code = main(["--repo", str(tmp_path), "--fix"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "slopcheck Pro required:" in captured.err
    assert "'--fix' auto-cleanup requires a Pro license" in captured.err
    assert captured.out == ""


def test_cli_free_toml_config_requires_pro_exits_2(tmp_path: Path, capsys):
    init_repo(tmp_path)
    (tmp_path / ".slopcheck.toml").write_text(
        '[slopcheck]\ndisabled_rules = ["obvious-comment"]\n',
        encoding="utf-8",
    )
    py_file = tmp_path / "app.py"
    py_file.write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=tmp_path, check=True)

    exit_code = main(["--repo", str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "slopcheck Pro required:" in captured.err
    assert ".slopcheck.toml" in captured.err
    assert captured.out == ""


def test_cli_free_skips_ts_file_with_notice_and_exits_0(tmp_path: Path, capsys):
    init_repo(tmp_path)
    ts_file = tmp_path / "service.ts"
    ts_file.write_text(DIRTY_TS, encoding="utf-8")
    subprocess.run(["git", "add", "service.ts"], cwd=tmp_path, check=True)

    exit_code = main(["--repo", str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "slopcheck notice: Skipped 1 JS/TS file(s) (Pro feature" in captured.err
    assert "slopcheck activate <LICENSE_KEY>" in captured.err
    assert captured.out == ""


def test_cli_free_mixed_py_and_ts_scans_py_and_skips_ts(tmp_path: Path, capsys):
    init_repo(tmp_path)
    py_file = tmp_path / "app.py"
    py_file.write_text(
        "# Calculate total\ndef calculate_total():\n    return 1\n",
        encoding="utf-8",
    )
    ts_file = tmp_path / "service.ts"
    ts_file.write_text(DIRTY_TS, encoding="utf-8")
    subprocess.run(
        ["git", "add", "app.py", "service.ts"], cwd=tmp_path, check=True
    )

    exit_code = main(["--repo", str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "slopcheck notice: Skipped 1 JS/TS file(s)" in captured.err
    assert "app.py:1: [obvious-comment]" in captured.out
    assert "service.ts" not in captured.out
    assert "slopcheck: Found 1 violation(s) across 1 staged file(s)." in captured.out
