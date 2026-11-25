"""Pure Tree-sitter auto-fixer for safe, non-behavioral slopcheck rules."""

from __future__ import annotations

from dataclasses import dataclass
from tree_sitter import Node

from slopcheck.parser import detect_language, node_line, parse_source, run_query
from slopcheck.rules.filler_docstrings import check_filler_docstrings
from slopcheck.rules.js_rules import check_js_filler_docstrings, check_js_obvious_comments
from slopcheck.rules.obvious_comments import check_obvious_comments

QUERY_DEFINITIONS = "(class_definition) @cls (function_definition) @func"


@dataclass(frozen=True)
class FixResult:
    fixed_source: bytes
    fixes_applied: int
    applied_rule_ids: tuple[str, ...]


def _compute_line_spans(content_bytes: bytes) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = 0
    total_len = len(content_bytes)
    while start < total_len:
        nl_idx = content_bytes.find(b"\n", start)
        if nl_idx == -1:
            spans.append((start, total_len))
            break
        spans.append((start, nl_idx + 1))
        start = nl_idx + 1
    return spans


def _first_docstring_expr(body_node: Node | None) -> Node | None:
    if not body_node:
        return None
    for child in body_node.children:
        if child.is_named and child.type != "comment":
            if child.type == "expression_statement":
                named = [c for c in child.children if c.is_named]
                if len(named) == 1 and named[0].type == "string":
                    return child
            return None
    return None


def _collect_docstring_exprs(tree) -> dict[int, tuple[Node, Node]]:
    """Map 1-based start line to (expression_statement_node, parent_body_node)."""
    by_line: dict[int, tuple[Node, Node]] = {}

    module_expr = _first_docstring_expr(tree.root_node)
    if module_expr is not None:
        by_line[node_line(module_expr)] = (module_expr, tree.root_node)

    caps = run_query(tree, QUERY_DEFINITIONS)
    for target in caps.get("cls", []) + caps.get("func", []):
        body_node = target.child_by_field_name("body")
        expr_node = _first_docstring_expr(body_node)
        if expr_node is not None and body_node is not None:
            line = node_line(expr_node)
            by_line.setdefault(line, (expr_node, body_node))

    return by_line


def _docstring_edit(
    expr_node: Node,
    parent_body: Node,
    content_bytes: bytes,
    line_spans: list[tuple[int, int]],
) -> tuple[int, int, bytes]:
    is_only_stmt_in_block = (
        parent_body.type == "block"
        and len(
            [c for c in parent_body.children if c.is_named and c.type != "comment"]
        )
        == 1
    )
    if is_only_stmt_in_block:
        return (expr_node.start_byte, expr_node.end_byte, b"pass")

    start_line = node_line(expr_node)
    end_line = expr_node.end_point[0] + 1
    first_line_start = line_spans[start_line - 1][0]
    last_line_end = line_spans[end_line - 1][1]

    prefix = content_bytes[first_line_start : expr_node.start_byte]
    suffix = content_bytes[expr_node.end_byte : last_line_end].rstrip(b"\r\n")

    if prefix.strip() == b"" and suffix.strip() in (b"", b";"):
        return (first_line_start, last_line_end, b"")

    if suffix.lstrip().startswith(b";"):
        semi_pos = content_bytes.find(b";", expr_node.end_byte, last_line_end)
        del_end = semi_pos + 1
        while (
            del_end < last_line_end
            and content_bytes[del_end : del_end + 1] in (b" ", b"\t")
        ):
            del_end += 1
        return (expr_node.start_byte, del_end, b"")

    del_end = expr_node.end_byte
    while (
        del_end < last_line_end
        and content_bytes[del_end : del_end + 1] in (b" ", b"\t")
    ):
        del_end += 1
    return (expr_node.start_byte, del_end, b"")


def _apply_byte_edits(
    raw_bytes: bytes,
    content_bytes: bytes,
    has_bom: bool,
    edits: list[tuple[int, int, bytes, str]],
) -> FixResult:
    """Sort byte edits bottom-to-top, skip overlaps, and preserve UTF-8 BOM."""
    if not edits:
        return FixResult(
            fixed_source=raw_bytes,
            fixes_applied=0,
            applied_rule_ids=(),
        )

    edits.sort(key=lambda item: (item[0], item[1]), reverse=True)
    result_buf = bytearray(content_bytes)
    applied_rules: set[str] = set()
    fixes_applied = 0
    last_start = len(content_bytes)

    for start_b, end_b, replacement, rule_id in edits:
        if end_b > last_start:
            continue
        result_buf[start_b:end_b] = replacement
        last_start = start_b
        fixes_applied += 1
        applied_rules.add(rule_id)

    fixed_bytes = bytes(result_buf)
    if has_bom:
        fixed_bytes = b"\xef\xbb\xbf" + fixed_bytes

    return FixResult(
        fixed_source=fixed_bytes,
        fixes_applied=fixes_applied,
        applied_rule_ids=tuple(sorted(applied_rules)),
    )


def _jsdoc_edit(
    comment_node: Node,
    content_bytes: bytes,
    line_spans: list[tuple[int, int]],
) -> tuple[int, int, bytes] | None:
    """Compute safe byte deletion range for a JSDoc comment node."""
    start_line_0 = comment_node.start_point[0]
    end_line_0 = comment_node.end_point[0]
    if start_line_0 >= len(line_spans) or end_line_0 >= len(line_spans):
        return None

    span_start = line_spans[start_line_0][0]
    span_end = line_spans[end_line_0][1]
    prefix = content_bytes[span_start : comment_node.start_byte]
    suffix = content_bytes[comment_node.end_byte : span_end].rstrip(b"\r\n")

    if prefix.strip() == b"" and suffix.strip() == b"":
        return (span_start, span_end, b"")

    del_start = comment_node.start_byte
    if prefix.strip() != b"" and suffix.strip() == b"":
        while (
            del_start > span_start
            and content_bytes[del_start - 1 : del_start] in (b" ", b"\t")
        ):
            del_start -= 1

    del_end = comment_node.end_byte
    while (
        del_end < span_end
        and content_bytes[del_end : del_end + 1] in (b" ", b"\t")
    ):
        del_end += 1
    return (del_start, del_end, b"")


def fix_python_source(
    file_path: str,
    source: str | bytes,
    changed_lines: set[int] | None = None,
    disabled_rules: frozenset[str] = frozenset(),
    obvious_comment_threshold: float = 0.70,
) -> FixResult:
    raw_bytes = source.encode("utf-8") if isinstance(source, str) else bytes(source)
    has_bom = raw_bytes.startswith(b"\xef\xbb\xbf")

    tree, content_bytes = parse_source(raw_bytes)
    line_spans = _compute_line_spans(content_bytes)
    edits: list[tuple[int, int, bytes, str]] = []

    if "obvious-comment" not in disabled_rules:
        obvious_violations = check_obvious_comments(
            file_path,
            content_bytes,
            changed_lines,
            threshold=obvious_comment_threshold,
        )
        for line_num in {v.line for v in obvious_violations}:
            if 1 <= line_num <= len(line_spans):
                line_start, line_end = line_spans[line_num - 1]
                edits.append((line_start, line_end, b"", "obvious-comment"))

    if "filler-docstring" not in disabled_rules:
        filler_violations = check_filler_docstrings(
            file_path,
            content_bytes,
            changed_lines,
        )
        if filler_violations:
            doc_exprs = _collect_docstring_exprs(tree)
            for line_num in {v.line for v in filler_violations}:
                matched = doc_exprs.get(line_num)
                if matched is None:
                    continue
                expr_node, parent_body = matched
                start_b, end_b, replacement = _docstring_edit(
                    expr_node, parent_body, content_bytes, line_spans
                )
                edits.append((start_b, end_b, replacement, "filler-docstring"))

    return _apply_byte_edits(raw_bytes, content_bytes, has_bom, edits)


def fix_js_source(
    file_path: str,
    source: str | bytes,
    language: str,
    changed_lines: set[int] | None = None,
    disabled_rules: frozenset[str] = frozenset(),
    obvious_comment_threshold: float = 0.70,
) -> FixResult:
    """Auto-remove safe obvious comments and filler JSDoc from JS/TS source."""
    raw_bytes = source.encode("utf-8") if isinstance(source, str) else bytes(source)
    has_bom = raw_bytes.startswith(b"\xef\xbb\xbf")

    tree, content_bytes = parse_source(raw_bytes, language=language)
    line_spans = _compute_line_spans(content_bytes)
    edits: list[tuple[int, int, bytes, str]] = []

    if "obvious-comment" not in disabled_rules:
        obvious_violations = check_js_obvious_comments(
            file_path,
            content_bytes,
            language,
            changed_lines,
            threshold=obvious_comment_threshold,
        )
        for line_num in {v.line for v in obvious_violations}:
            if 1 <= line_num <= len(line_spans):
                line_start, line_end = line_spans[line_num - 1]
                edits.append((line_start, line_end, b"", "obvious-comment"))

    if "filler-docstring" not in disabled_rules:
        filler_violations = check_js_filler_docstrings(
            file_path, content_bytes, language, changed_lines
        )
        if filler_violations:
            caps = run_query(tree, "(comment) @comment", language=language)
            comment_by_line: dict[int, Node] = {}
            for node in caps.get("comment", []):
                comment_by_line.setdefault(node.start_point[0] + 1, node)

            for line_num in {v.line for v in filler_violations}:
                node = comment_by_line.get(line_num)
                if node is None:
                    continue
                edit = _jsdoc_edit(node, content_bytes, line_spans)
                if edit is not None:
                    edits.append((*edit, "filler-docstring"))

    return _apply_byte_edits(raw_bytes, content_bytes, has_bom, edits)


def fix_source(
    file_path: str,
    source: str | bytes,
    changed_lines: set[int] | None = None,
    disabled_rules: frozenset[str] = frozenset(),
    obvious_comment_threshold: float = 0.70,
) -> FixResult:
    lang = detect_language(file_path)
    if lang == "python":
        return fix_python_source(
            file_path, source, changed_lines, disabled_rules, obvious_comment_threshold
        )
    if lang in ("javascript", "typescript", "tsx"):
        return fix_js_source(
            file_path,
            source,
            lang,
            changed_lines,
            disabled_rules,
            obvious_comment_threshold,
        )
    raw = source.encode("utf-8") if isinstance(source, str) else bytes(source)
    return FixResult(fixed_source=raw, fixes_applied=0, applied_rule_ids=())
