"""AI-slop detection rules for JavaScript and TypeScript via Tree-sitter."""

from __future__ import annotations

import os
from pathlib import Path
from tree_sitter import Node

from slopcheck.parser import detect_language, node_line, node_text, parse_source, run_query
from slopcheck.rules.base import Violation
from slopcheck.rules.filler_docstrings import find_matching_filler_phrase
from slopcheck.rules.obvious_comments import extract_words

JS_EXTENSIONS = frozenset(
    {".js", ".jsx", ".mjs", ".cjs", ".ts", ".mts", ".cts", ".tsx"}
)
JS_SKIP_DIRS = frozenset(
    {"node_modules", ".git", ".venv", "venv", "dist", "build", ".next", "coverage"}
)

_JS_DIRECTIVE_PREFIXES = (
    "eslint-disable",
    "eslint-enable",
    "@ts-ignore",
    "@ts-expect-error",
    "@ts-nocheck",
    "@ts-check",
    "prettier-ignore",
    "biome-ignore",
    "istanbul ignore",
    "<reference",
)

_QUERY_OBVIOUS = """
(comment) @comment
(function_declaration) @func_decl
(generator_function_declaration) @func_decl
(class_declaration) @class_decl
(method_definition) @method_def
(variable_declarator) @var_decl
(lexical_declaration) @var_stmt
(variable_declaration) @var_stmt
(export_statement) @export_stmt
"""

_QUERY_CATCH = "(catch_clause) @clause"
_QUERY_CALLS = "(call_expression) @call"
_QUERY_COMMENTS = "(comment) @comment"
_QUERY_FUNCTIONS = """
(function_declaration) @func_decl
(generator_function_declaration) @func_decl
(method_definition) @method_def
(variable_declarator) @var_decl
"""

_COMPOUND_JS_NODES = frozenset(
    {
        "if_statement",
        "else_clause",
        "for_statement",
        "for_in_statement",
        "while_statement",
        "do_statement",
        "try_statement",
        "catch_clause",
        "finally_clause",
        "switch_statement",
        "switch_body",
        "switch_case",
        "switch_default",
        "with_statement",
    }
)

_JSDOC_TARGET_TYPES = frozenset(
    {
        "function_declaration",
        "generator_function_declaration",
        "class_declaration",
        "abstract_class_declaration",
        "method_definition",
        "lexical_declaration",
        "variable_declaration",
        "export_statement",
    }
)


def _is_js_pragma_or_directive(comment_text: str, line: int) -> bool:
    stripped = comment_text.strip()
    if stripped.startswith("#!"):
        return True
    clean = stripped.lstrip("/").strip().lower()
    if line <= 2 and clean.startswith("#!"):
        return True
    return any(clean.startswith(prefix) for prefix in _JS_DIRECTIVE_PREFIXES)


def _is_standalone_line(start_byte: int, source_bytes: bytes) -> bool:
    line_start = source_bytes.rfind(b"\n", 0, start_byte) + 1
    return source_bytes[line_start:start_byte].strip() == b""


def _add_decl_identifiers(
    decl_node: Node,
    line: int,
    source_bytes: bytes,
    line_to_identifiers: dict[int, list[str]],
) -> None:
    if decl_node.type in (
        "function_declaration",
        "generator_function_declaration",
        "class_declaration",
        "abstract_class_declaration",
        "method_definition",
    ):
        name_node = decl_node.child_by_field_name("name")
        if name_node:
            name = node_text(name_node, source_bytes)
            if name:
                line_to_identifiers.setdefault(line, []).append(name)
    elif decl_node.type in ("lexical_declaration", "variable_declaration"):
        for child in decl_node.children:
            if child.type == "variable_declarator":
                name_node = child.child_by_field_name("name")
                if name_node:
                    name = node_text(name_node, source_bytes)
                    if name:
                        line_to_identifiers.setdefault(line, []).append(name)


def check_js_obvious_comments(
    file_path: str,
    source: str | bytes,
    language: str,
    changed_lines: set[int] | None = None,
    threshold: float = 0.70,
) -> list[Violation]:
    tree, source_bytes = parse_source(source, language=language)
    captures = run_query(tree, _QUERY_OBVIOUS, language=language)

    line_to_identifiers: dict[int, list[str]] = {}

    for node in (
        captures.get("func_decl", [])
        + captures.get("class_decl", [])
        + captures.get("method_def", [])
    ):
        _add_decl_identifiers(node, node_line(node), source_bytes, line_to_identifiers)

    for var_decl in captures.get("var_decl", []):
        name_node = var_decl.child_by_field_name("name")
        if name_node:
            name = node_text(name_node, source_bytes)
            if name:
                line_to_identifiers.setdefault(node_line(var_decl), []).append(name)

    for var_stmt in captures.get("var_stmt", []):
        _add_decl_identifiers(
            var_stmt, node_line(var_stmt), source_bytes, line_to_identifiers
        )

    for exp_stmt in captures.get("export_stmt", []):
        inner = exp_stmt.child_by_field_name("declaration")
        if inner is not None:
            _add_decl_identifiers(
                inner, node_line(exp_stmt), source_bytes, line_to_identifiers
            )

    violations: list[Violation] = []

    for comment_node in captures.get("comment", []):
        comment_line = node_line(comment_node)
        if changed_lines is not None and comment_line not in changed_lines:
            continue

        comment_raw = node_text(comment_node, source_bytes)
        if not comment_raw.lstrip().startswith("//"):
            continue

        if not _is_standalone_line(comment_node.start_byte, source_bytes):
            continue

        if _is_js_pragma_or_directive(comment_raw, comment_line):
            continue

        comment_words = extract_words(comment_raw.lstrip("/"))
        if len(comment_words) < 2:
            continue

        target_identifiers = line_to_identifiers.get(comment_line + 1, [])
        for identifier in target_identifiers:
            identifier_words = extract_words(identifier)
            if not identifier_words:
                continue

            overlap = len(comment_words & identifier_words) / len(comment_words)
            if overlap > threshold:
                violations.append(
                    Violation(
                        file_path=file_path,
                        line=comment_line,
                        rule_id="obvious-comment",
                        message=f"Obvious comment duplicates identifier '{identifier}'",
                    )
                )
                break

    return violations


def _is_console_log_call(stmt: Node, source_bytes: bytes) -> bool:
    if stmt.type != "expression_statement":
        return False
    named = [c for c in stmt.children if c.is_named and c.type != "comment"]
    if len(named) != 1 or named[0].type != "call_expression":
        return False
    fn_node = named[0].child_by_field_name("function")
    if fn_node is None or fn_node.type != "member_expression":
        return False
    obj_node = fn_node.child_by_field_name("object")
    prop_node = fn_node.child_by_field_name("property")
    if obj_node is None or prop_node is None:
        return False
    return (
        obj_node.type == "identifier"
        and node_text(obj_node, source_bytes) == "console"
        and node_text(prop_node, source_bytes) == "log"
    )


def _is_contextless_throw(
    stmt: Node,
    caught_var: str | None,
    source_bytes: bytes,
) -> bool:
    if stmt.type != "throw_statement" or caught_var is None:
        return False
    named = [c for c in stmt.children if c.is_named and c.type != "comment"]
    return (
        len(named) == 1
        and named[0].type == "identifier"
        and node_text(named[0], source_bytes) == caught_var
    )


def check_js_swallowed_exceptions(
    file_path: str,
    source: str | bytes,
    language: str,
    changed_lines: set[int] | None = None,
) -> list[Violation]:
    tree, source_bytes = parse_source(source, language=language)
    captures = run_query(tree, _QUERY_CATCH, language=language)

    violations: list[Violation] = []

    for clause in captures.get("clause", []):
        clause_line = node_line(clause)
        clause_span = set(
            range(clause.start_point[0] + 1, clause.end_point[0] + 2)
        )
        if changed_lines is not None and not (clause_span & changed_lines):
            continue

        param_node = clause.child_by_field_name("parameter")
        caught_var: str | None = None
        if param_node is not None and param_node.type == "identifier":
            caught_var = node_text(param_node, source_bytes).strip()

        body_node = clause.child_by_field_name("body")
        if body_node is None:
            continue

        executable_stmts = [
            c
            for c in body_node.children
            if c.is_named and c.type not in ("comment", "empty_statement")
        ]

        swallowed = False
        if not executable_stmts:
            swallowed = True
        elif all(_is_console_log_call(s, source_bytes) for s in executable_stmts):
            swallowed = True
        elif len(executable_stmts) == 1 and _is_contextless_throw(
            executable_stmts[0], caught_var, source_bytes
        ):
            swallowed = True

        if swallowed:
            violations.append(
                Violation(
                    file_path=file_path,
                    line=clause_line,
                    rule_id="swallowed-exception",
                    message="Swallowed exception caught without proper logging or handling",
                )
            )

    return violations


def count_js_repo_calls(repo_root: str | Path) -> dict[str, int]:
    root_path = Path(repo_root)
    call_counts: dict[str, int] = {}
    if not root_path.exists():
        return call_counts

    for root, dirs, files in os.walk(root_path):
        dirs[:] = [d for d in dirs if d not in JS_SKIP_DIRS]
        for file in files:
            if Path(file).suffix.lower() not in JS_EXTENSIONS:
                continue
            file_path = Path(root) / file
            language = detect_language(file_path)
            if language is None:
                continue
            try:
                source_bytes = file_path.read_bytes()
            except OSError:
                continue

            tree, source_bytes = parse_source(source_bytes, language=language)
            caps = run_query(tree, _QUERY_CALLS, language=language)
            for call_node in caps.get("call", []):
                fn_node = call_node.child_by_field_name("function")
                name: str | None = None
                if fn_node is not None:
                    if fn_node.type == "identifier":
                        name = node_text(fn_node, source_bytes)
                    elif fn_node.type == "member_expression":
                        prop_node = fn_node.child_by_field_name("property")
                        if prop_node is not None:
                            name = node_text(prop_node, source_bytes)
                if name:
                    call_counts[name] = call_counts.get(name, 0) + 1

    return call_counts


def _is_exported_declaration(node: Node) -> bool:
    parent = node.parent
    if parent is None:
        return False
    if parent.type == "export_statement":
        return True
    if node.type == "variable_declarator" and parent.type in (
        "lexical_declaration",
        "variable_declaration",
    ):
        grandparent = parent.parent
        return grandparent is not None and grandparent.type == "export_statement"
    return False


def _is_skipped_js_function(func_name: str, decl_node: Node) -> bool:
    if func_name in ("constructor", "main") or func_name.startswith("test"):
        return True
    return _is_exported_declaration(decl_node)


def _count_js_nested_statements(node: Node) -> int:
    total = 0
    for child in node.children:
        if not child.is_named or child.type in ("comment", "empty_statement"):
            continue
        if child.type == "statement_block":
            total += _count_js_block_statements(child)
        elif child.type in _COMPOUND_JS_NODES:
            total += _count_js_nested_statements(child)
        elif child.type not in ("parenthesized_expression",):
            if node.type in (
                "if_statement",
                "else_clause",
                "for_statement",
                "for_in_statement",
                "while_statement",
                "do_statement",
                "switch_case",
                "switch_default",
            ) and child.type.endswith("_statement"):
                total += 1
    return total


def _count_js_block_statements(block_node: Node) -> int:
    stmts = [
        c
        for c in block_node.children
        if c.is_named and c.type not in ("comment", "empty_statement")
    ]
    total = 0
    for stmt in stmts:
        total += 1
        if stmt.type in _COMPOUND_JS_NODES:
            total += _count_js_nested_statements(stmt)
    return total


def _count_js_body_statements(body_node: Node) -> int:
    if body_node.type == "statement_block":
        return _count_js_block_statements(body_node)
    return 1


def check_js_micro_wrappers(
    file_path: str,
    source: str | bytes,
    language: str,
    call_counts: dict[str, int],
    changed_lines: set[int] | None = None,
    max_statements: int = 2,
) -> list[Violation]:
    tree, source_bytes = parse_source(source, language=language)
    caps = run_query(tree, _QUERY_FUNCTIONS, language=language)

    candidates: list[tuple[int, str, Node, Node]] = []

    for func_node in caps.get("func_decl", []) + caps.get("method_def", []):
        name_node = func_node.child_by_field_name("name")
        body_node = func_node.child_by_field_name("body")
        if name_node is not None and body_node is not None:
            candidates.append(
                (
                    node_line(func_node),
                    node_text(name_node, source_bytes),
                    func_node,
                    body_node,
                )
            )

    for var_decl in caps.get("var_decl", []):
        name_node = var_decl.child_by_field_name("name")
        value_node = var_decl.child_by_field_name("value")
        if (
            name_node is not None
            and name_node.type == "identifier"
            and value_node is not None
            and value_node.type == "arrow_function"
        ):
            body_node = value_node.child_by_field_name("body")
            if body_node is not None:
                candidates.append(
                    (
                        node_line(var_decl),
                        node_text(name_node, source_bytes),
                        var_decl,
                        body_node,
                    )
                )

    violations: list[Violation] = []
    for def_line, func_name, decl_node, body_node in candidates:
        if changed_lines is not None and def_line not in changed_lines:
            continue
        if _is_skipped_js_function(func_name, decl_node):
            continue

        stmt_count = _count_js_body_statements(body_node)
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

    violations.sort(key=lambda v: v.line)
    return violations


def _normalize_jsdoc(raw_text: str) -> str:
    text = raw_text.strip()
    if text.startswith("/**"):
        text = text[3:]
    if text.endswith("*/"):
        text = text[:-2]
    lines = [line.lstrip().lstrip("*").strip() for line in text.splitlines()]
    return " ".join(" ".join(part for part in lines if part).split()).lower()


def check_js_filler_docstrings(
    file_path: str,
    source: str | bytes,
    language: str,
    changed_lines: set[int] | None = None,
) -> list[Violation]:
    tree, source_bytes = parse_source(source, language=language)
    caps = run_query(tree, _QUERY_COMMENTS, language=language)

    violations: list[Violation] = []
    for comment_node in caps.get("comment", []):
        raw_text = node_text(comment_node, source_bytes).strip()
        if not (raw_text.startswith("/**") and raw_text.endswith("*/") and len(raw_text) >= 5):
            continue

        sibling = comment_node.next_named_sibling
        while sibling is not None and (
            sibling.type == "decorator"
            or (
                sibling.type == "comment"
                and not node_text(sibling, source_bytes).strip().startswith("/**")
            )
        ):
            sibling = sibling.next_named_sibling
        if sibling is None or sibling.type not in _JSDOC_TARGET_TYPES:
            continue

        start_line = node_line(comment_node)
        end_line = comment_node.end_point[0] + 1
        covered_lines = set(range(start_line, end_line + 1))
        if changed_lines is not None and not (covered_lines & changed_lines):
            continue

        normalized = _normalize_jsdoc(raw_text)
        matched_phrase = find_matching_filler_phrase(normalized)
        if matched_phrase:
            violations.append(
                Violation(
                    file_path=file_path,
                    line=start_line,
                    rule_id="filler-docstring",
                    message=(
                        f"AI filler docstring detected: contains boilerplate phrase '{matched_phrase}'"
                    ),
                )
            )

    violations.sort(key=lambda v: v.line)
    return violations
