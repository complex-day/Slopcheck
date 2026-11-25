from pathlib import Path
import pytest
from slopcheck.parser import (
    detect_language,
    node_line,
    node_text,
    parse_file,
    parse_source,
    run_matches,
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


def test_parse_source_strips_utf8_bom():
    tree_str, bytes_str = parse_source("\ufeffx = 42\n")
    assert bytes_str == b"x = 42\n"
    assert tree_str.root_node.type == "module"

    tree_bytes, bytes_bytes = parse_source(b"\xef\xbb\xbfx = 42\n")
    assert bytes_bytes == b"x = 42\n"
    assert tree_bytes.root_node.type == "module"


def test_detect_language():
    assert detect_language("app.py") == "python"
    assert detect_language(Path("src/APP.PY")) == "python"
    assert detect_language("index.js") == "javascript"
    assert detect_language("Button.jsx") == "javascript"
    assert detect_language("mod.mjs") == "javascript"
    assert detect_language("legacy.cjs") == "javascript"
    assert detect_language("service.ts") == "typescript"
    assert detect_language("service.mts") == "typescript"
    assert detect_language("service.cts") == "typescript"
    assert detect_language("Widget.tsx") == "tsx"
    assert detect_language("README.md") is None
    assert detect_language("package.json") is None
    assert detect_language("Makefile") is None


def test_parse_js_ts_tsx_with_bom():
    js_src = "\ufeff// Fetch user\nexport function fetchUser(id) { return id; }\n"
    js_tree, js_bytes = parse_source(js_src, language="javascript")
    assert js_tree.root_node.type == "program"
    assert not js_tree.root_node.has_error
    assert js_bytes.startswith(b"// Fetch user")

    ts_src = b"\xef\xbb\xbfinterface User { id: number; }\nconst getUser = (u: User): number => u.id;\n"
    ts_tree, ts_bytes = parse_source(ts_src, language="typescript")
    assert ts_tree.root_node.type == "program"
    assert not ts_tree.root_node.has_error
    assert ts_bytes.startswith(b"interface User")

    tsx_src = "\ufeffexport const Greeting = ({ name }: { name: string }) => <span>Hello {name}</span>;\n"
    tsx_tree, tsx_bytes = parse_source(tsx_src, language="tsx")
    assert tsx_tree.root_node.type == "program"
    assert not tsx_tree.root_node.has_error
    assert tsx_bytes.startswith(b"export const Greeting")


def test_run_query_and_matches_on_js_and_ts():
    js_code = """// Calculate total
function calculateTotal() {
  try {
    return 1;
  } catch (err) {
    return 0;
  }
}
"""
    js_tree, js_bytes = parse_source(js_code, language="javascript")
    js_caps = run_query(
        js_tree,
        "(comment) @comment (catch_clause) @catch",
        language="javascript",
    )
    assert len(js_caps["comment"]) == 1
    assert node_text(js_caps["comment"][0], js_bytes) == "// Calculate total"
    assert node_line(js_caps["comment"][0]) == 1
    assert len(js_caps["catch"]) == 1
    assert node_line(js_caps["catch"][0]) == 5

    ts_code = """// Handle request
async function handleRequest(id: string): Promise<void> {
  try {
    console.log(id);
  } catch (e) {
  }
}
"""
    ts_tree, ts_bytes = parse_source(ts_code, language="typescript")
    ts_caps = run_query(
        ts_tree,
        "(comment) @comment (catch_clause) @catch",
        language="typescript",
    )
    assert len(ts_caps["comment"]) == 1
    assert node_text(ts_caps["comment"][0], ts_bytes) == "// Handle request"
    assert len(ts_caps["catch"]) == 1

    ts_matches = run_matches(ts_tree, "(catch_clause) @catch", language="typescript")
    assert len(ts_matches) == 1


def test_unsupported_language_raises_value_error():
    with pytest.raises(ValueError, match="Unsupported language"):
        parse_source("fn main() {}", language="rust")

    tree, _ = parse_source("x = 1\n")
    with pytest.raises(ValueError, match="Unsupported language"):
        run_query(tree, "(comment) @c", language="rust")
    with pytest.raises(ValueError, match="Unsupported language"):
        run_matches(tree, "(comment) @c", language="rust")

