from pathlib import Path
from slopcheck.parser import (
    node_line,
    node_text,
    parse_file,
    parse_source,
    run_query,
)


def test_parse_source_module():
    source = "x = 42\n"
    tree, source_bytes = parse_source(source)
    assert tree.root_node.type == "module"
    assert source_bytes == b"x = 42\n"

    tree_from_bytes, bytes_out = parse_source(b"y = 100\n")
    assert tree_from_bytes.root_node.type == "module"
    assert bytes_out == b"y = 100\n"


def test_parse_file(tmp_path: Path):
    file_path = tmp_path / "sample.py"
    file_path.write_bytes(b"def bar():\n    return True\n")

    tree, source_bytes = parse_file(file_path)
    assert tree.root_node.type == "module"
    assert source_bytes == b"def bar():\n    return True\n"


def test_run_query_captures():
    source = """# A greeting comment
def greet(name):
    return f"Hello, {name}!"
"""
    tree, source_bytes = parse_source(source)
    query_str = "(function_definition name: (identifier) @func_name) (comment) @comment"
    captures = run_query(tree, query_str)

    assert "func_name" in captures
    assert "comment" in captures
    assert len(captures["func_name"]) == 1
    assert len(captures["comment"]) == 1

    func_name_node = captures["func_name"][0]
    comment_node = captures["comment"][0]

    assert node_text(func_name_node, source_bytes) == "greet"
    assert node_text(comment_node, source_bytes) == "# A greeting comment"


def test_node_line():
    source = """# Line 1 comment
x = 10
def calculate():
    return x * 2
"""
    tree, _ = parse_source(source)
    query_str = "(comment) @comment (function_definition) @func"
    captures = run_query(tree, query_str)

    comment_node = captures["comment"][0]
    func_node = captures["func"][0]

    assert node_line(comment_node) == 1
    assert node_line(func_node) == 3


def test_node_text_utf8_and_emoji():
    source = '# 🚀 Special comment with café & emojis\nmsg = "✨ Python 3.10+ ✨"\n'
    tree, source_bytes = parse_source(source)
    query_str = "(comment) @comment (string) @str"
    captures = run_query(tree, query_str)

    comment_node = captures["comment"][0]
    string_node = captures["str"][0]

    assert node_text(comment_node, source_bytes) == "# 🚀 Special comment with café & emojis"
    assert node_text(string_node, source_bytes) == '"✨ Python 3.10+ ✨"'
