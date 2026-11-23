from slopcheck.parser import node_line, node_text, parse_source, run_query
from slopcheck.rules.base import Violation
from tree_sitter import Node

QUERY_EXCEPT = "(except_clause) @clause"


def is_broad_catch(clause: Node, source_bytes: bytes) -> tuple[bool, str | None]:
    val = clause.child_by_field_name("value")
    if val is None:
        return True, None

    caught_var: str | None = None
    expr_node = val
    if val.type == "as_pattern":
        alias_node = val.child_by_field_name("alias")
        if alias_node:
            caught_var = node_text(alias_node, source_bytes).strip()
        if val.named_children:
            expr_node = val.named_children[0]

    def get_identifiers(node: Node) -> list[str]:
        if node.type == "identifier":
            return [node_text(node, source_bytes)]
        ids: list[str] = []
        for child in node.children:
            ids.extend(get_identifiers(child))
        return ids

    caught_types = set(get_identifiers(expr_node))
    is_broad = bool(caught_types & {"Exception", "BaseException"})
    return is_broad, caught_var


def is_pass_or_ellipsis(stmt: Node) -> bool:
    if stmt.type == "pass_statement":
        return True
    if stmt.type == "expression_statement":
        named = [c for c in stmt.children if c.is_named]
        if len(named) == 1 and named[0].type == "ellipsis":
            return True
    return False


def is_print_call(stmt: Node, source_bytes: bytes) -> bool:
    if stmt.type == "expression_statement":
        named = [c for c in stmt.children if c.is_named]
        if len(named) == 1 and named[0].type == "call":
            func_node = named[0].child_by_field_name("function")
            if func_node and func_node.type == "identifier":
                return node_text(func_node, source_bytes) == "print"
    return False


def is_contextless_raise(
    stmt: Node,
    caught_var: str | None,
    source_bytes: bytes,
) -> bool:
    if stmt.type != "raise_statement":
        return False

    if any(child.type == "from" for child in stmt.children):
        return False

    named_children = [c for c in stmt.children if c.is_named]
    if not named_children:
        return True

    if len(named_children) == 1:
        child = named_children[0]
        if child.type == "identifier" and caught_var is not None:
            return node_text(child, source_bytes) == caught_var

    return False


def is_swallowed_body(
    stmts: list[Node],
    caught_var: str | None,
    source_bytes: bytes,
) -> bool:
    if not stmts:
        return True

    if all(is_pass_or_ellipsis(s) or is_print_call(s, source_bytes) for s in stmts):
        return True

    if len(stmts) == 1 and is_contextless_raise(stmts[0], caught_var, source_bytes):
        return True

    return False


def check_swallowed_exceptions(
    file_path: str,
    source: str | bytes,
    changed_lines: set[int] | None = None,
) -> list[Violation]:
    tree, source_bytes = parse_source(source)
    captures = run_query(tree, QUERY_EXCEPT)

    violations: list[Violation] = []

    for clause in captures.get("clause", []):
        clause_line = node_line(clause)
        clause_span_lines = set(
            range(clause.start_point[0] + 1, clause.end_point[0] + 2)
        )

        if changed_lines is not None and not (clause_span_lines & changed_lines):
            continue

        is_broad, caught_var = is_broad_catch(clause, source_bytes)
        if not is_broad:
            continue

        block_nodes = [c for c in clause.children if c.type == "block"]
        if not block_nodes:
            continue

        block = block_nodes[0]
        executable_stmts = [
            c for c in block.children if c.is_named and c.type != "comment"
        ]

        if is_swallowed_body(executable_stmts, caught_var, source_bytes):
            violations.append(
                Violation(
                    file_path=file_path,
                    line=clause_line,
                    rule_id="swallowed-exception",
                    message="Swallowed exception caught without proper logging or handling",
                )
            )

    return violations