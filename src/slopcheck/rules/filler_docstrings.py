import re
from slopcheck.parser import node_line, node_text, parse_source, run_query
from slopcheck.rules.base import Violation
from tree_sitter import Node

QUERY_DEFINITIONS = "(class_definition) @cls (function_definition) @func"

FILLER_PATTERNS = [
    re.compile(r"\bthis function is responsible for\b", re.IGNORECASE),
    re.compile(r"\bthis method is responsible for\b", re.IGNORECASE),
    re.compile(r"\bthis class is responsible for\b", re.IGNORECASE),
    re.compile(r"\bthis module is responsible for\b", re.IGNORECASE),
    re.compile(r"\bhelper function to\b", re.IGNORECASE),
    re.compile(r"\bhelper function that\b", re.IGNORECASE),
    re.compile(r"\bhelper method to\b", re.IGNORECASE),
    re.compile(r"\bhelper method that\b", re.IGNORECASE),
    re.compile(r"\butility function to\b", re.IGNORECASE),
    re.compile(r"\butility method to\b", re.IGNORECASE),
    re.compile(r"\ba simple function to\b", re.IGNORECASE),
    re.compile(r"\ba simple helper\b", re.IGNORECASE),
    re.compile(r"\bthis function takes\b", re.IGNORECASE),
    re.compile(r"\bthis method takes\b", re.IGNORECASE),
    re.compile(r"\bas the name suggests\b", re.IGNORECASE),
    re.compile(r"\bprovides a convenient way to\b", re.IGNORECASE),
]


def extract_docstring_node(body_node: Node | None) -> Node | None:
    if not body_node:
        return None

    for child in body_node.children:
        if child.is_named and child.type != "comment":
            if child.type == "expression_statement":
                named = [c for c in child.children if c.is_named]
                if len(named) == 1 and named[0].type == "string":
                    return named[0]
            return None

    return None


def normalize_docstring(raw_text: str) -> str:
    text = raw_text.strip()
    match = re.match(r"^[rRuUfFbB]{0,2}(\"\"\"|'''|\"|')", text)
    if match:
        quote = match.group(1)
        text = text[match.end():]
        if text.endswith(quote):
            text = text[:-len(quote)]

    return " ".join(text.split()).lower()


def find_matching_filler_phrase(normalized_text: str) -> str | None:
    for pattern in FILLER_PATTERNS:
        match = pattern.search(normalized_text)
        if match:
            return match.group(0)
    return None


def check_filler_docstrings(
    file_path: str,
    source: str | bytes,
    changed_lines: set[int] | None = None,
) -> list[Violation]:
    tree, source_bytes = parse_source(source)

    docstring_nodes: list[Node] = []
    seen_ids: set[int] = set()

    # 1. Module-level docstring
    module_doc = extract_docstring_node(tree.root_node)
    if module_doc is not None:
        docstring_nodes.append(module_doc)
        seen_ids.add(module_doc.id)

    # 2. Class and function docstrings
    caps = run_query(tree, QUERY_DEFINITIONS)
    for target in caps.get("cls", []) + caps.get("func", []):
        body_node = target.child_by_field_name("body")
        doc_node = extract_docstring_node(body_node)
        if doc_node is not None and doc_node.id not in seen_ids:
            docstring_nodes.append(doc_node)
            seen_ids.add(doc_node.id)

    violations: list[Violation] = []

    for doc_node in docstring_nodes:
        start_line = node_line(doc_node)
        end_line = doc_node.end_point[0] + 1
        covered_lines = set(range(start_line, end_line + 1))

        if changed_lines is not None and not (covered_lines & changed_lines):
            continue

        raw_text = node_text(doc_node, source_bytes)
        normalized = normalize_docstring(raw_text)
        matched_phrase = find_matching_filler_phrase(normalized)

        if matched_phrase:
            violations.append(
                Violation(
                    file_path=file_path,
                    line=start_line,
                    rule_id="filler-docstring",
                    message=f"AI filler docstring detected: contains boilerplate phrase '{matched_phrase}'",
                )
            )
    violations.sort(key=lambda v: v.line)

    return violations
