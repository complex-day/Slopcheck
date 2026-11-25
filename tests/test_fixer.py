"""Tests for the Tree-sitter auto-fixer engine."""

import pytest

from slopcheck.fixer import FixResult, fix_python_source
from slopcheck.parser import parse_source, run_query


def _has_syntax_errors(source: bytes) -> bool:
    tree, _ = parse_source(source)
    caps = run_query(tree, "(ERROR) @err")
    return bool(caps.get("err")) or tree.root_node.has_error


class TestObviousCommentFixing:
    def test_removes_obvious_comments_keeps_pragmas_and_helpful(self):
        source = (
            "# Calculate total\n"
            "def calculate_total(a, b):\n"
            "    # Account for tax adjustment before rounding\n"
            "    # type: ignore\n"
            "    # noqa: E501\n"
            "    # User id\n"
            "    user_id = a + b\n"
            "    return user_id\n"
        )
        result = fix_python_source("app.py", source)

        assert isinstance(result, FixResult)
        assert result.fixes_applied == 2
        assert result.applied_rule_ids == ("obvious-comment",)
        assert not _has_syntax_errors(result.fixed_source)

        fixed_text = result.fixed_source.decode("utf-8")
        assert "# Calculate total" not in fixed_text
        assert "# User id" not in fixed_text
        assert "# Account for tax adjustment before rounding" in fixed_text
        assert "# type: ignore" in fixed_text
        assert "# noqa: E501" in fixed_text
        assert "def calculate_total(a, b):" in fixed_text
        assert "    user_id = a + b" in fixed_text


class TestFillerDocstringFixing:
    def test_removes_single_and_multiline_docstrings(self):
        source = (
            '"""This module is responsible for user math."""\n'
            "\n"
            "class Calculator:\n"
            '    """\n'
            "    This class is responsible for basic arithmetic.\n"
            '    """\n'
            "    def add(self, a: int, b: int) -> int:\n"
            '        """Helper method to add two numbers."""\n'
            "        return a + b\n"
            "\n"
            "    async def fetch_value(self) -> int:\n"
            '        """\n'
            "        This method takes nothing and returns one.\n"
            '        """\n'
            "        return 1\n"
        )
        result = fix_python_source("calc.py", source)

        assert result.fixes_applied == 4
        assert result.applied_rule_ids == ("filler-docstring",)
        assert not _has_syntax_errors(result.fixed_source)

        fixed_text = result.fixed_source.decode("utf-8")
        assert "This module is responsible for" not in fixed_text
        assert "This class is responsible for" not in fixed_text
        assert "Helper method to" not in fixed_text
        assert "This method takes" not in fixed_text
        assert "class Calculator:" in fixed_text
        assert "def add(self, a: int, b: int) -> int:" in fixed_text
        assert "return a + b" in fixed_text
        assert "async def fetch_value(self) -> int:" in fixed_text
        assert "return 1" in fixed_text

    def test_empty_body_safety_guard_replaces_with_pass(self):
        source = (
            "class EmptyModel:\n"
            '    """This class is responsible for representing an empty model."""\n'
            "\n"
            "def stub_sync():\n"
            '    """\n'
            "    This function is responsible for doing nothing.\n"
            '    """\n'
            "\n"
            "async def stub_async():\n"
            '    """Helper function to handle async stubs."""\n'
            "\n"
            "def stub_with_comment():\n"
            '    """Utility function to mark a future hook."""\n'
            "    # TODO: implement later\n"
        )
        result = fix_python_source("stubs.py", source)

        assert result.fixes_applied == 4
        assert result.applied_rule_ids == ("filler-docstring",)
        assert not _has_syntax_errors(result.fixed_source)

        fixed_text = result.fixed_source.decode("utf-8")
        assert "class EmptyModel:\n    pass\n" in fixed_text
        assert "def stub_sync():\n    pass\n" in fixed_text
        assert "async def stub_async():\n    pass\n" in fixed_text
        assert (
            "def stub_with_comment():\n    pass\n    # TODO: implement later\n"
            in fixed_text
        )

    def test_inline_function_docstring_empty_body_replaced_with_pass(self):
        source = 'def one_liner(): """Helper function to return nothing."""\n'
        result = fix_python_source("inline.py", source)

        assert result.fixes_applied == 1
        assert not _has_syntax_errors(result.fixed_source)
        assert result.fixed_source == b"def one_liner(): pass\n"

    def test_standalone_docstring_with_trailing_semicolon_deletes_full_line(self):
        source = (
            "def add(a: int, b: int) -> int:\n"
            '    """Helper method to add two numbers.""";\n'
            "    return a + b\n"
        )
        result = fix_python_source("semi.py", source)

        assert result.fixes_applied == 1
        assert not _has_syntax_errors(result.fixed_source)
        assert result.fixed_source == b"def add(a: int, b: int) -> int:\n    return a + b\n"


class TestChangedLinesAndConfigRespect:
    def test_respects_changed_lines(self):
        source = (
            '"""This module is responsible for untouched code."""\n'
            "# Calculate total\n"
            "def calculate_total():\n"
            "    # User id\n"
            "    user_id = 1\n"
            "    return user_id\n"
        )
        # Only line 4 (# User id) is in changed_lines
        result = fix_python_source("app.py", source, changed_lines={4})

        assert result.fixes_applied == 1
        assert result.applied_rule_ids == ("obvious-comment",)
        assert not _has_syntax_errors(result.fixed_source)

        fixed_text = result.fixed_source.decode("utf-8")
        assert "This module is responsible for untouched code." in fixed_text
        assert "# Calculate total" in fixed_text
        assert "# User id" not in fixed_text

    def test_respects_disabled_rules(self):
        source = (
            '"""This module is responsible for testing."""\n'
            "# Calculate total\n"
            "def calculate_total():\n"
            "    return 1\n"
        )
        result = fix_python_source(
            "app.py",
            source,
            disabled_rules=frozenset({"obvious-comment"}),
        )
        assert result.fixes_applied == 1
        assert result.applied_rule_ids == ("filler-docstring",)

        fixed_text = result.fixed_source.decode("utf-8")
        assert "This module is responsible for testing." not in fixed_text
        assert "# Calculate total" in fixed_text

        none_result = fix_python_source(
            "app.py",
            source,
            disabled_rules=frozenset({"obvious-comment", "filler-docstring"}),
        )
        assert none_result.fixes_applied == 0
        assert none_result.applied_rule_ids == ()
        assert none_result.fixed_source == source.encode("utf-8")

    def test_respects_custom_obvious_comment_threshold(self):
        source = (
            "# calculate total amount\n"
            "def calculate_total():\n"
            "    return 1\n"
        )
        # 2/3 ~= 0.667: untouched at 0.70, removed at 0.50
        no_fix = fix_python_source("app.py", source, obvious_comment_threshold=0.70)
        assert no_fix.fixes_applied == 0
        assert no_fix.fixed_source == source.encode("utf-8")

        applied = fix_python_source("app.py", source, obvious_comment_threshold=0.50)
        assert applied.fixes_applied == 1
        assert applied.applied_rule_ids == ("obvious-comment",)
        assert applied.fixed_source == b"def calculate_total():\n    return 1\n"


class TestBehavioralRulesUntouched:
    def test_swallowed_exception_and_micro_wrapper_are_never_removed(self):
        source = (
            "def _tiny_wrapper(x):\n"
            "    return x + 1\n"
            "\n"
            "def run():\n"
            "    try:\n"
            "        return _tiny_wrapper(1)\n"
            "    except Exception:\n"
            "        pass\n"
        )
        result = fix_python_source("app.py", source)

        assert result.fixes_applied == 0
        assert result.applied_rule_ids == ()
        assert result.fixed_source == source.encode("utf-8")


class TestLineEndingsAndEncoding:
    def test_preserves_crlf_line_endings(self):
        source = (
            b'"""This module is responsible for CRLF tests."""\r\n'
            b"# Calculate total\r\n"
            b"def calculate_total():\r\n"
            b'    """Helper function to return value."""\r\n'
            b"\r\n"
            b"def other():\r\n"
            b"    return 1\r\n"
        )
        result = fix_python_source("crlf.py", source)

        assert result.fixes_applied == 3
        assert result.applied_rule_ids == ("filler-docstring", "obvious-comment")
        assert not _has_syntax_errors(result.fixed_source)

        expected = (
            b"def calculate_total():\r\n"
            b"    pass\r\n"
            b"\r\n"
            b"def other():\r\n"
            b"    return 1\r\n"
        )
        assert result.fixed_source == expected
        assert b"\r\n" in result.fixed_source
        assert b"\n" not in result.fixed_source.replace(b"\r\n", b"")

    def test_preserves_utf8_bom_and_emojis(self):
        source = (
            b"\xef\xbb\xbf"
            b"# Calculate total\n"
            b"def calculate_total():\n"
            b'    """Helper function to greet."""\n'
            b'    return "\xf0\x9f\x9a\x80 caf\xc3\xa9"\n'
        )
        result = fix_python_source("emoji.py", source)

        assert result.fixes_applied == 2
        assert result.fixed_source.startswith(b"\xef\xbb\xbf")
        assert not _has_syntax_errors(result.fixed_source)
        assert result.fixed_source == (
            b"\xef\xbb\xbf"
            b"def calculate_total():\n"
            b'    return "\xf0\x9f\x9a\x80 caf\xc3\xa9"\n'
        )


class TestFixResultFrozen:
    def test_fix_result_is_immutable(self):
        res = FixResult(fixed_source=b"", fixes_applied=0, applied_rule_ids=())
        with pytest.raises(AttributeError):
            res.fixes_applied = 1
