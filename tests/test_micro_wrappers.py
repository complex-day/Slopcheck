from pathlib import Path
from slopcheck.rules.micro_wrappers import (
    check_micro_wrappers,
    count_repo_calls,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "micro_wrappers"


def test_dirty_sync_wrappers_fixture():
    fixture_path = FIXTURES_DIR / "dirty_sync_wrappers.py"
    source = fixture_path.read_bytes()

    # Pre-calculated call counts for this file
    call_counts = count_repo_calls(fixture_path.parent)

    violations = check_micro_wrappers(str(fixture_path), source, call_counts)
    assert len(violations) == 2

    lines = [v.line for v in violations]
    assert lines == [1, 6]
    for v in violations:
        assert v.rule_id == "micro-wrapper"


def test_dirty_async_wrappers_fixture():
    fixture_path = FIXTURES_DIR / "dirty_async_wrappers.py"
    source = fixture_path.read_bytes()

    call_counts = count_repo_calls(fixture_path.parent)

    violations = check_micro_wrappers(str(fixture_path), source, call_counts)
    assert len(violations) == 2

    lines = [v.line for v in violations]
    assert lines == [1, 5]
    for v in violations:
        assert v.rule_id == "micro-wrapper"


def test_clean_decorators_and_dunders_fixture():
    fixture_path = FIXTURES_DIR / "clean_decorators_and_dunders.py"
    source = fixture_path.read_bytes()

    call_counts = {
        "__init__": 1,
        "processor_name": 1,
        "process": 1,
        "test_example": 1,
        "main": 1,
    }

    violations = check_micro_wrappers(str(fixture_path), source, call_counts)
    assert len(violations) == 0


def test_clean_multicall_and_large_fixture():
    fixture_path = FIXTURES_DIR / "clean_multicall_and_large.py"
    source = fixture_path.read_bytes()

    call_counts = count_repo_calls(fixture_path.parent)
    assert call_counts.get("reusable_helper", 0) >= 2

    violations = check_micro_wrappers(str(fixture_path), source, call_counts)
    assert len(violations) == 0


def test_count_repo_calls_multi_file_and_skips(tmp_path: Path):
    # Setup directory structure:
    # root/
    #   src/
    #     module_a.py (calls foo(), self.bar(), obj.bar())
    #     module_b.py (calls foo())
    #   .venv/
    #     lib.py (calls foo(), foo())
    #   .git/
    #     hook.py (calls foo())
    #   __pycache__/
    #     cache.py (calls foo())
    #   dist/
    #     dist.py (calls foo())
    #   build/
    #     build.py (calls foo())
    #   my_pkg.egg-info/
    #     info.py (calls foo())

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "module_a.py").write_text(
        "def run(self, obj):\n    foo()\n    self.bar()\n    obj.bar()\n",
        encoding="utf-8",
    )
    (src_dir / "module_b.py").write_text("def other():\n    foo()\n", encoding="utf-8")

    # Skipped dirs
    for skip_name in [
        ".venv",
        ".git",
        "__pycache__",
        "build",
        "dist",
        "pkg.egg-info",
    ]:
        skip_dir = tmp_path / skip_name
        skip_dir.mkdir()
        (skip_dir / "ignored.py").write_text("foo()\nfoo()\n", encoding="utf-8")

    counts = count_repo_calls(tmp_path)
    assert counts.get("foo") == 2
    assert counts.get("bar") == 2


def test_changed_lines_filtering():
    fixture_path = FIXTURES_DIR / "dirty_sync_wrappers.py"
    source = fixture_path.read_bytes()
    call_counts = {"_wrap_int": 1, "_double_val": 1}

    # Only line 1 (_wrap_int) is changed
    v1 = check_micro_wrappers(
        str(fixture_path), source, call_counts, changed_lines={1}
    )
    assert len(v1) == 1
    assert v1[0].line == 1

    # Only line 6 (_double_val) is changed
    v2 = check_micro_wrappers(
        str(fixture_path), source, call_counts, changed_lines={6}
    )
    assert len(v2) == 1
    assert v2[0].line == 6

    # Neither line is changed
    v_none = check_micro_wrappers(
        str(fixture_path), source, call_counts, changed_lines={2, 3, 4}
    )
    assert len(v_none) == 0

    # Empty changed_lines
    v_empty = check_micro_wrappers(
        str(fixture_path), source, call_counts, changed_lines=set()
    )
    assert len(v_empty) == 0


def test_custom_max_statements():
    source = (
        "def _three_steps(x):\n"
        "    a = x + 1\n"
        "    b = a * 2\n"
        "    return b\n"
    )
    call_counts = {"_three_steps": 1}

    # Default max_statements=2 ignores 3-statement functions
    assert check_micro_wrappers("sample.py", source, call_counts) == []

    # Raising max_statements=3 flags it
    violations = check_micro_wrappers(
        "sample.py", source, call_counts, max_statements=3
    )
    assert len(violations) == 1
    assert violations[0].rule_id == "micro-wrapper"


def test_count_repo_calls_and_check_with_utf8_bom(tmp_path: Path):
    bom_source = (
        b"\xef\xbb\xbf"
        b"def _tiny_bom_helper(x: int) -> int:\n"
        b"    return x + 1\n\n"
        b"def caller() -> int:\n"
        b"    return _tiny_bom_helper(41)\n"
    )
    file_path = tmp_path / "bom_module.py"
    file_path.write_bytes(bom_source)

    call_counts = count_repo_calls(tmp_path)
    assert call_counts.get("_tiny_bom_helper") == 1

    violations = check_micro_wrappers(str(file_path), bom_source, call_counts)
    assert len(violations) == 1
    assert violations[0].rule_id == "micro-wrapper"
    assert violations[0].line == 1
    assert "_tiny_bom_helper" in violations[0].message
