import re
from slopcheck.parser import node_line, node_text, parse_source, run_query
from slopcheck.rules.base import Violation

QUERY_STATEMENTS = """
(comment) @comment
(function_definition) @func_def
(class_definition) @class_def
(assignment) @assign_def
(decorated_definition) @dec_def
"""

DIRECTIVE_PREFIXES = (
    "type: ignore",
    "type:ignore",
    "noqa",
    "pragma:",
    "fmt:",
    "isort:",
    "pylint:",
)


def is_pragma_or_directive(comment_text: str, line: int) -> bool:
    stripped = comment_text.strip()
    if stripped.startswith("#!"):
        return True

    clean = stripped.lstrip("#").strip().lower()
    if line <= 2 and ("coding:" in clean or "coding=" in clean):
        return True

    for prefix in DIRECTIVE_PREFIXES:
        if clean.startswith(prefix):
            return True

    return False


def is_standalone_comment(start_byte: int, source_bytes: bytes) -> bool:
    line_start = source_bytes.rfind(b"\n", 0, start_byte) + 1
    return source_bytes[line_start:start_byte].strip() == b""


def extract_words(text: str) -> set[str]:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", " ", text)
    cleaned = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", cleaned)
    cleaned = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", cleaned)
    return {w.lower() for w in cleaned.split() if w}


def check_obvious_comments(
    file_path: str,
    source: str | bytes,
    changed_lines: set[int] | None = None,
    threshold: float = 0.70,
) -> list[Violation]:
    tree, source_bytes = parse_source(source)
    captures = run_query(tree, QUERY_STATEMENTS)

    line_to_identifiers: dict[int, list[str]] = {}

    def add_identifier(line: int, identifier: str) -> None:
        if identifier:
            line_to_identifiers.setdefault(line, []).append(identifier)

    for func in captures.get("func_def", []):
        name_node = func.child_by_field_name("name")
        if name_node:
            add_identifier(node_line(func), node_text(name_node, source_bytes))

    for cls in captures.get("class_def", []):
        name_node = cls.child_by_field_name("name")
        if name_node:
            add_identifier(node_line(cls), node_text(name_node, source_bytes))

    for assign in captures.get("assign_def", []):
        left_node = assign.child_by_field_name("left")
        line = node_line(assign)
        if left_node and left_node.type == "identifier":
            add_identifier(line, node_text(left_node, source_bytes))
        elif left_node and left_node.type == "attribute":
            attr = left_node.child_by_field_name("attribute")
            if attr:
                add_identifier(line, node_text(attr, source_bytes))

    for dec in captures.get("dec_def", []):
        inner = dec.child_by_field_name("definition")
        if inner and inner.type in ("function_definition", "class_definition"):
            name_node = inner.child_by_field_name("name")
            if name_node:
                add_identifier(node_line(dec), node_text(name_node, source_bytes))

    violations: list[Violation] = []

    for comment_node in captures.get("comment", []):
        comment_line = node_line(comment_node)
        if changed_lines is not None and comment_line not in changed_lines:
            continue

        if not is_standalone_comment(comment_node.start_byte, source_bytes):
            continue

        comment_raw = node_text(comment_node, source_bytes)
        if is_pragma_or_directive(comment_raw, comment_line):
            continue

        comment_body = comment_raw.lstrip("#")
        comment_words = extract_words(comment_body)
        if len(comment_words) < 2:
            continue

        next_line = comment_line + 1
        target_identifiers = line_to_identifiers.get(next_line, [])

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