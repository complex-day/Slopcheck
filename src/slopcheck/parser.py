from pathlib import Path
from tree_sitter import Language, Node, Parser, Query, QueryCursor, Tree
import tree_sitter_javascript as tsjavascript
import tree_sitter_python as tspython
import tree_sitter_typescript as tstypescript

PY_LANGUAGE = Language(tspython.language())
JS_LANGUAGE = Language(tsjavascript.language())
TS_LANGUAGE = Language(tstypescript.language_typescript())
TSX_LANGUAGE = Language(tstypescript.language_tsx())

LANGUAGES: dict[str, Language] = {
    "python": PY_LANGUAGE,
    "javascript": JS_LANGUAGE,
    "typescript": TS_LANGUAGE,
    "tsx": TSX_LANGUAGE,
}

PARSERS: dict[str, Parser] = {
    name: Parser(lang) for name, lang in LANGUAGES.items()
}

PARSER = PARSERS["python"]

_EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".tsx": "tsx",
}


def detect_language(file_path: str | Path) -> str | None:
    return _EXTENSION_TO_LANGUAGE.get(Path(file_path).suffix.lower())


def _get_language(language: str) -> Language:
    lang = LANGUAGES.get(language)
    if lang is None:
        raise ValueError(
            f"Unsupported language {language!r}; expected one of {sorted(LANGUAGES)}"
        )
    return lang


def _get_parser(language: str) -> Parser:
    parser = PARSERS.get(language)
    if parser is None:
        raise ValueError(
            f"Unsupported language {language!r}; expected one of {sorted(LANGUAGES)}"
        )
    return parser


def parse_source(
    source: str | bytes,
    language: str = "python",
) -> tuple[Tree, bytes]:
    parser = _get_parser(language)
    if isinstance(source, str):
        source_bytes = source.removeprefix("\ufeff").encode("utf-8")
    else:
        source_bytes = bytes(source).removeprefix(b"\xef\xbb\xbf")
    tree = parser.parse(source_bytes)
    return tree, source_bytes


def parse_file(
    file_path: str | Path,
    language: str | None = None,
) -> tuple[Tree, bytes]:
    path = Path(file_path)
    resolved_language = language if language is not None else (detect_language(path) or "python")
    return parse_source(path.read_bytes(), language=resolved_language)


def run_query(
    tree: Tree,
    query_str: str,
    language: str = "python",
) -> dict[str, list[Node]]:
    lang = _get_language(language)
    query = Query(lang, query_str)
    cursor = QueryCursor(query)
    return cursor.captures(tree.root_node)


def run_matches(
    tree: Tree,
    query_str: str,
    language: str = "python",
) -> list[tuple[int, dict[str, list[Node]]]]:
    lang = _get_language(language)
    query = Query(lang, query_str)
    cursor = QueryCursor(query)
    return cursor.matches(tree.root_node)


def node_line(node: Node) -> int:
    return node.start_point[0] + 1


def node_text(node: Node, source_bytes: bytes) -> str:
    return source_bytes[node.start_byte:node.end_byte].decode(
        "utf-8", errors="replace"
    )
