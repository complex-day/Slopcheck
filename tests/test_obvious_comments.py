from pathlib import Path
from slopcheck.rules.obvious_comments import check_obvious_comments

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "obvious_comments"


def test_dirty_functions_fixture():
    fixture_path = FIXTURES_DIR / "dirty_functions.py"
    source = fixture_path.read_bytes()

    violations = check_obvious_comments(str(fixture_path), source)
    assert len(violations) == 2

    assert violations[0].line == 1
    assert violations[0].rule_id == "obvious-comment"
    assert "calculate_total" in violations[0].message

    assert violations[1].line == 6
    assert violations[1].rule_id == "obvious-comment"
    assert "fetch_user_data" in violations[1].message


def test_dirty_variables_fixture():
    fixture_path = FIXTURES_DIR / "dirty_variables.py"
    source = fixture_path.read_bytes()

    violations = check_obvious_comments(str(fixture_path), source)
    # Triggers on: user_id (line 1), maxRetryCount (line 5), UserAccount (line 9), isActive (line 11)
    assert len(violations) >= 3

    lines = {v.line for v in violations}
    assert 1 in lines
    assert 5 in lines
    for v in violations:
        assert v.rule_id == "obvious-comment"


def test_clean_pragmas_fixture():
    fixture_path = FIXTURES_DIR / "clean_pragmas.py"
    source = fixture_path.read_bytes()

    violations = check_obvious_comments(str(fixture_path), source)
    assert len(violations) == 0


def test_clean_helpful_fixture():
    fixture_path = FIXTURES_DIR / "clean_helpful.py"
    source = fixture_path.read_bytes()

    violations = check_obvious_comments(str(fixture_path), source)
    assert len(violations) == 0


def test_changed_lines_filtering():
    fixture_path = FIXTURES_DIR / "dirty_functions.py"
    source = fixture_path.read_bytes()

    # Only line 1 is changed; line 6 must be ignored
    violations_filtered = check_obvious_comments(
        str(fixture_path), source, changed_lines={1}
    )
    assert len(violations_filtered) == 1
    assert violations_filtered[0].line == 1

    # Neither comment line is in changed_lines
    violations_none = check_obvious_comments(
        str(fixture_path), source, changed_lines={2, 3, 4}
    )
    assert len(violations_none) == 0

    # Empty changed_lines
    violations_empty = check_obvious_comments(
        str(fixture_path), source, changed_lines=set()
    )
    assert len(violations_empty) == 0


def test_obvious_comment_with_utf8_bom():
    source_bytes = (
        b"\xef\xbb\xbf# calculate total\n"
        b"def calculate_total(a, b):\n"
        b"    return a + b\n"
    )
    violations = check_obvious_comments("test_bom.py", source_bytes)
    assert len(violations) == 1
    assert violations[0].line == 1
    assert violations[0].rule_id == "obvious-comment"
    assert "calculate_total" in violations[0].message

    source_str = (
        "\ufeff# calculate total\n"
        "def calculate_total(a, b):\n"
        "    return a + b\n"
    )
    violations_str = check_obvious_comments("test_bom.py", source_str)
    assert len(violations_str) == 1
    assert violations_str[0].line == 1

