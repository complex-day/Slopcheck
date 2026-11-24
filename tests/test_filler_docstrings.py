from pathlib import Path
from slopcheck.rules.filler_docstrings import check_filler_docstrings

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "filler_docstrings"


def test_dirty_sync_and_module_fixture():
    fixture_path = FIXTURES_DIR / "dirty_sync_and_module.py"
    source = fixture_path.read_bytes()

    violations = check_filler_docstrings(str(fixture_path), source)
    assert len(violations) == 4

    # 1: module docstring (line 1)
    # 2: class docstring (line 5)
    # 3: calculate_balance (line 8)
    # 4: format_summary (line 12)
    lines = [v.line for v in violations]
    assert lines == [1, 5, 8, 12]
    for v in violations:
        assert v.rule_id == "filler-docstring"


def test_dirty_async_and_methods_fixture():
    fixture_path = FIXTURES_DIR / "dirty_async_and_methods.py"
    source = fixture_path.read_bytes()

    violations = check_filler_docstrings(str(fixture_path), source)
    assert len(violations) == 3

    lines = [v.line for v in violations]
    # fetch_remote_data (line 2)
    # process_item (line 7)
    # connect_service (line 14)
    assert lines == [2, 7, 14]
    for v in violations:
        assert v.rule_id == "filler-docstring"


def test_clean_docstrings_fixture():
    fixture_path = FIXTURES_DIR / "clean_docstrings.py"
    source = fixture_path.read_bytes()

    violations = check_filler_docstrings(str(fixture_path), source)
    assert len(violations) == 0


def test_clean_string_variables_fixture():
    fixture_path = FIXTURES_DIR / "clean_string_variables.py"
    source = fixture_path.read_bytes()

    violations = check_filler_docstrings(str(fixture_path), source)
    assert len(violations) == 0


def test_changed_lines_filtering():
    fixture_path = FIXTURES_DIR / "dirty_sync_and_module.py"
    source = fixture_path.read_bytes()

    # Hit starting line of calculate_balance docstring (line 8)
    v1 = check_filler_docstrings(
        str(fixture_path), source, changed_lines={8}
    )
    assert len(v1) == 1
    assert v1[0].line == 8

    # Hit line 2 of the multiline format_summary docstring (starts at 12, line 13 is middle)
    v2 = check_filler_docstrings(
        str(fixture_path), source, changed_lines={13}
    )
    assert len(v2) == 1
    assert v2[0].line == 12

    # Line not touching any docstring
    v_none = check_filler_docstrings(
        str(fixture_path), source, changed_lines={9}  # return 0.0 line
    )
    assert len(v_none) == 0

    # Empty changed_lines
    v_empty = check_filler_docstrings(
        str(fixture_path), source, changed_lines=set()
    )
    assert len(v_empty) == 0
