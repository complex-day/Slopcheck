from pathlib import Path
from tree_sitter import Language, Node, Parser, Query, QueryCursor, Tree
import tree_sitter_python as tspython

PY_LANGUAGE = Language(tspython.language())
PARSER = Parser(PY_LANGUAGE)


def parse_source(source: str | bytes) -> tuple[Tree, bytes]:
    if isinstance(source, str):
        source_bytes = source.removeprefix("\ufeff").encode("utf-8")
    else:
        source_bytes = bytes(source).removeprefix(b"\xef\xbb\xbf")
    tree = PARSER.parse(source_bytes)
    return tree, source_bytes


def parse_file(file_path: str | Path) -> tuple[Tree, bytes]:
    path = Path(file_path)
    return parse_source(path.read_bytes())


def run_query(tree: Tree, query_str: str) -> dict[str, list[Node]]:
    query = Query(PY_LANGUAGE, query_str)
    cursor = QueryCursor(query)
    return cursor.captures(tree.root_node)


def run_matches(
    tree: Tree, query_str: str
) -> list[tuple[int, dict[str, list[Node]]]]:
    query = Query(PY_LANGUAGE, query_str)
    cursor = QueryCursor(query)
    return cursor.matches(tree.root_node)


def node_line(node: Node) -> int:
    return node.start_point[0] + 1


def node_text(node: Node, source_bytes: bytes) -> str:
    return source_bytes[node.start_byte:node.end_byte].decode(
        "utf-8", errors="replace"
    )