import os
from pathlib import Path
from slopcheck.parser import node_line, node_text, parse_source, run_query
from slopcheck.rules.base import Violation
from tree_sitter import Node

QUERY_CALLS = "(call) @call"
QUERY_FUNCTIONS = "(function_definition) @func"

SKIP_DIRS = {
    ".venv",
    "venv",
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "build",
    "dist",
}

COMPOUND_BLOCKS = {
    "if_statement",
    "elif_clause",
    "else_clause",
    "for_statement",
    "while_statement",
    "with_statement",
    "try_statement",
    "except_clause",
    "finally_clause",
    "match_statement",
    "case_clause",
}


def should_skip_dir(name: str) -> bool:
    return name in SKIP_DIRS or name.endswith(".egg-info")


def count_repo_calls(repo_root: str | Path) -> dict[str, int]:
    root_path = Path(repo_root)
    call_counts: dict[str, int] = {}
    if not root_path.exists():
        return call_counts

    for root, dirs, files in os.walk(root_path):
        dirs[:] = [d for d in dirs if not should_skip_dir(d)]
        for file in files:
            if file.endswith(".py"):
                file_path = Path(root) / file
                try:
                    source_bytes = file_path.read_bytes()
                except OSError:
                    continue

                tree, _ = parse_source(source_bytes)
                caps = run_query(tree, QUERY_CALLS)
                for call_node in caps.get("call", []):
                    fn_node = call_node.child_by_field_name("function")
                    name = None
                    if fn_node:
                        if fn_node.type == "identifier":
                            name = node_text(fn_node, source_bytes)
                        elif fn_node.type == "attribute":
                            attr_node = fn_node.child_by_field_name("attribute")
                            if attr_node:
                                name = node_text(attr_node, source_bytes)
                    if name:
                        call_counts[name] = call_counts.get(name, 0) + 1

    return call_counts


def is_skipped_function(
    func_node: Node,
    func_name: str,
    source_bytes: bytes,
) -> bool:
    if func_name.startswith("__") and func_name.endswith("__"):
        return True

    if func_name.startswith("test_") or func_name == "main":
        return True

    parent = func_node.parent
    if parent and parent.type == "decorated_definition":
        for child in parent.children:
            if child.type == "decorator":
                dec_text = node_text(child, source_bytes).lstrip("@").strip()
                base_name = dec_text.split("(")[0].strip()
                if base_name in (
                    "property",
                    "abstractmethod",
                    "abc.abstractmethod",
                ) or base_name.endswith((".setter", ".deleter")):
                    return True

    return False


def _count_nested_statements(node: Node) -> int:
    total = 0
    for child in node.children:
        if not child.is_named or child.type == "comment":
            continue
        if child.type == "block":
            total += _count_block_statements(child, strip_docstring=False)
        elif child.type in COMPOUND_BLOCKS:
            total += _count_nested_statements(child)
    return total


def _count_block_statements(block_node: Node, strip_docstring: bool = False) -> int:
    stmts = [c for c in block_node.children if c.is_named and c.type != "comment"]
    if not stmts:
        return 0

    if strip_docstring:
        first = stmts[0]
        if first.type == "expression_statement":
            named_children = [c for c in first.children if c.is_named]
            if len(named_children) == 1 and named_children[0].type == "string":
                stmts = stmts[1:]

    total = 0
    for stmt in stmts:
        total += 1
        if stmt.type in COMPOUND_BLOCKS:
            total += _count_nested_statements(stmt)
    return total


def count_executable_statements(body_node: Node) -> int:
    return _count_block_statements(body_node, strip_docstring=True)


def check_micro_wrappers(
    file_path: str,
    source: str | bytes,
    call_counts: dict[str, int],
    changed_lines: set[int] | None = None,
    max_statements: int = 2,
) -> list[Violation]:
    tree, source_bytes = parse_source(source)
    caps = run_query(tree, QUERY_FUNCTIONS)

    violations: list[Violation] = []

    for func_node in caps.get("func", []):
        def_line = node_line(func_node)
        if changed_lines is not None and def_line not in changed_lines:
            continue

        name_node = func_node.child_by_field_name("name")
        if not name_node:
            continue

        func_name = node_text(name_node, source_bytes)
        if is_skipped_function(func_node, func_name, source_bytes):
            continue

        body_node = func_node.child_by_field_name("body")
        if not body_node:
            continue

        stmt_count = count_executable_statements(body_node)
        if 1 <= stmt_count <= max_statements and call_counts.get(func_name, 0) == 1:
            violations.append(
                Violation(
                    file_path=file_path,
                    line=def_line,
                    rule_id="micro-wrapper",
                    message=(
                        f"Single-use micro-wrapper '{func_name}' has "
                        f"{stmt_count} statement(s) and is only called once"
                    ),
                )
            )

    return violations