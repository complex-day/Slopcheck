from pathlib import Path
from slopcheck.rules.swallowed_exceptions import check_swallowed_exceptions

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "swallowed_exceptions"


def test_dirty_swallowed_basic_fixture():
    fixture_path = FIXTURES_DIR / "dirty_swallowed_basic.py"
    source = fixture_path.read_bytes()

    violations = check_swallowed_exceptions(str(fixture_path), source)
    assert len(violations) == 4

    lines = [v.line for v in violations]
    # bare except (line 5), except Exception (line 11), except* Exception (line 17), except BaseException (line 23)
    assert lines == [5, 11, 17, 23]
    for v in violations:
        assert v.rule_id == "swallowed-exception"


def test_dirty_swallowed_nested_async_fixture():
    fixture_path = FIXTURES_DIR / "dirty_swallowed_nested_async.py"
    source = fixture_path.read_bytes()

    violations = check_swallowed_exceptions(str(fixture_path), source)
    assert len(violations) == 3

    lines = [v.line for v in violations]
    # except Exception as err: raise err (line 8)
    # except (ValueError, Exception): raise (line 15)
    # except: ... (line 17)
    assert lines == [8, 15, 17]
    for v in violations:
        assert v.rule_id == "swallowed-exception"


def test_clean_specific_exceptions_fixture():
    fixture_path = FIXTURES_DIR / "clean_specific_exceptions.py"
    source = fixture_path.read_bytes()

    violations = check_swallowed_exceptions(str(fixture_path), source)
    assert len(violations) == 0


def test_clean_logging_and_context_fixture():
    fixture_path = FIXTURES_DIR / "clean_logging_and_context.py"
    source = fixture_path.read_bytes()

    violations = check_swallowed_exceptions(str(fixture_path), source)
    assert len(violations) == 0


def test_changed_lines_filtering():
    fixture_path = FIXTURES_DIR / "dirty_swallowed_basic.py"
    source = fixture_path.read_bytes()

    # Changing only line 5 (the bare except line itself)
    v1 = check_swallowed_exceptions(str(fixture_path), source, changed_lines={5})
    assert len(v1) == 1
    assert v1[0].line == 5

    # Changing only line 6 (the body statement `pass` inside bare except)
    v2 = check_swallowed_exceptions(str(fixture_path), source, changed_lines={6})
    assert len(v2) == 1
    assert v2[0].line == 5

    # Changing lines outside any except block
    v_outside = check_swallowed_exceptions(
        str(fixture_path), source, changed_lines={1, 2, 3}
    )
    assert len(v_outside) == 0

    # Empty changed_lines
    v_empty = check_swallowed_exceptions(
        str(fixture_path), source, changed_lines=set()
    )
    assert len(v_empty) == 0
