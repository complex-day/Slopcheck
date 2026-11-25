"""Tests for JavaScript and TypeScript AI-slop detection rules."""

from pathlib import Path

from slopcheck.rules import (
    check_js_filler_docstrings,
    check_js_micro_wrappers,
    check_js_obvious_comments,
    check_js_swallowed_exceptions,
    count_js_repo_calls,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "js_rules"


class TestDirtyFixtures:
    def test_dirty_service_ts_all_rules(self):
        path = FIXTURES_DIR / "dirty_service.ts"
        source = path.read_bytes()
        call_counts = count_js_repo_calls(FIXTURES_DIR)

        obvious = check_js_obvious_comments(str(path), source, "typescript")
        assert [(v.line, v.rule_id) for v in obvious] == [
            (1, "obvious-comment"),
            (7, "obvious-comment"),
            (27, "obvious-comment"),
        ]

        filler = check_js_filler_docstrings(str(path), source, "typescript")
        assert [(v.line, v.rule_id) for v in filler] == [
            (4, "filler-docstring"),
            (24, "filler-docstring"),
        ]

        swallowed = check_js_swallowed_exceptions(str(path), source, "typescript")
        assert [(v.line, v.rule_id) for v in swallowed] == [
            (33, "swallowed-exception"),
            (36, "swallowed-exception"),
            (49, "swallowed-exception"),
        ]

        wrappers = check_js_micro_wrappers(
            str(path), source, "typescript", call_counts
        )
        wrapper_names = [v.message for v in wrappers]
        assert len(wrappers) == 3
        assert any("doubleValue" in msg for msg in wrapper_names)
        assert any("formatTag" in msg for msg in wrapper_names)
        assert any("wrapId" in msg for msg in wrapper_names)
        # Exported function must not be flagged
        assert not any("calculateTotal" in msg for msg in wrapper_names)

    def test_dirty_component_tsx_all_rules(self):
        path = FIXTURES_DIR / "dirty_component.tsx"
        source = path.read_bytes()
        call_counts = count_js_repo_calls(FIXTURES_DIR)

        obvious = check_js_obvious_comments(str(path), source, "tsx")
        assert len(obvious) == 1
        assert obvious[0].line == 20
        assert "UserCard" in obvious[0].message

        filler = check_js_filler_docstrings(str(path), source, "tsx")
        assert [v.line for v in filler] == [3, 17]

        swallowed = check_js_swallowed_exceptions(str(path), source, "tsx")
        assert len(swallowed) == 1
        assert swallowed[0].line == 10

        wrappers = check_js_micro_wrappers(str(path), source, "tsx", call_counts)
        assert len(wrappers) == 1
        assert "trimLabel" in wrappers[0].message


class TestCleanFixtures:
    def test_clean_utils_js_zero_violations(self):
        path = FIXTURES_DIR / "clean_utils.js"
        source = path.read_bytes()
        call_counts = count_js_repo_calls(FIXTURES_DIR)

        assert check_js_obvious_comments(str(path), source, "javascript") == []
        assert check_js_swallowed_exceptions(str(path), source, "javascript") == []
        assert check_js_filler_docstrings(str(path), source, "javascript") == []
        assert (
            check_js_micro_wrappers(str(path), source, "javascript", call_counts) == []
        )

    def test_clean_typed_ts_zero_violations(self):
        path = FIXTURES_DIR / "clean_typed.ts"
        source = path.read_bytes()
        call_counts = count_js_repo_calls(FIXTURES_DIR)

        assert check_js_obvious_comments(str(path), source, "typescript") == []
        assert check_js_swallowed_exceptions(str(path), source, "typescript") == []
        assert check_js_filler_docstrings(str(path), source, "typescript") == []
        assert (
            check_js_micro_wrappers(str(path), source, "typescript", call_counts) == []
        )


class TestEdgeCasesAndParameters:
    def test_changed_lines_filtering_across_rules(self):
        path = FIXTURES_DIR / "dirty_service.ts"
        source = path.read_bytes()
        call_counts = count_js_repo_calls(FIXTURES_DIR)

        # Line 1 obvious comment only
        assert [
            v.line
            for v in check_js_obvious_comments(
                str(path), source, "typescript", changed_lines={1}
            )
        ] == [1]

        # Line 5 is inside the multiline JSDoc (lines 4-6)
        assert [
            v.line
            for v in check_js_filler_docstrings(
                str(path), source, "typescript", changed_lines={5}
            )
        ] == [4]

        # Line 37 is inside catch (innerErr) { throw innerErr; } (lines 36-38)
        assert [
            v.line
            for v in check_js_swallowed_exceptions(
                str(path), source, "typescript", changed_lines={37}
            )
        ] == [36]

        # Line 14 is formatTag declaration
        wrappers = check_js_micro_wrappers(
            str(path), source, "typescript", call_counts, changed_lines={14}
        )
        assert len(wrappers) == 1
        assert "formatTag" in wrappers[0].message

        # Empty changed_lines returns nothing
        assert (
            check_js_obvious_comments(
                str(path), source, "typescript", changed_lines=set()
            )
            == []
        )
        assert (
            check_js_filler_docstrings(
                str(path), source, "typescript", changed_lines=set()
            )
            == []
        )
        assert (
            check_js_swallowed_exceptions(
                str(path), source, "typescript", changed_lines=set()
            )
            == []
        )
        assert (
            check_js_micro_wrappers(
                str(path), source, "typescript", call_counts, changed_lines=set()
            )
            == []
        )

    def test_custom_obvious_comment_threshold(self):
        source = "// Calculate total amount\nconst calculateTotal = () => 1;\n"
        # 2/3 ~= 0.667: clean at 0.70, flagged at 0.50
        assert check_js_obvious_comments("app.js", source, "javascript") == []
        flagged = check_js_obvious_comments(
            "app.js", source, "javascript", threshold=0.50
        )
        assert len(flagged) == 1
        assert flagged[0].rule_id == "obvious-comment"

    def test_custom_micro_wrapper_max_statements(self):
        source = (
            "function threeStep(x) {\n"
            "  const a = x + 1;\n"
            "  const b = a * 2;\n"
            "  return b;\n"
            "}\n"
            "threeStep(5);\n"
        )
        call_counts = {"threeStep": 1}
        assert (
            check_js_micro_wrappers("app.js", source, "javascript", call_counts) == []
        )
        flagged = check_js_micro_wrappers(
            "app.js", source, "javascript", call_counts, max_statements=3
        )
        assert len(flagged) == 1
        assert "threeStep" in flagged[0].message

    def test_count_js_repo_calls_skips_ignored_dirs_and_handles_bom(self, tmp_path):
        bom_file = tmp_path / "app.ts"
        bom_file.write_bytes(
            b"\xef\xbb\xbf"
            b"// Calculate total\n"
            b"function calculateTotal(x: number): number {\n"
            b"  return x + 1;\n"
            b"}\n"
            b"const run = (): number => calculateTotal(1);\n"
            b"run();\n"
        )

        node_modules = tmp_path / "node_modules" / "pkg"
        node_modules.mkdir(parents=True)
        (node_modules / "index.js").write_text(
            "calculateTotal(99); calculateTotal(100);\n",
            encoding="utf-8",
        )
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        (dist_dir / "bundle.js").write_text("calculateTotal(1);\n", encoding="utf-8")

        counts = count_js_repo_calls(tmp_path)
        assert counts.get("calculateTotal") == 1
        assert counts.get("run") == 1

        bom_bytes = bom_file.read_bytes()
        obvious = check_js_obvious_comments(str(bom_file), bom_bytes, "typescript")
        assert len(obvious) == 1
        assert obvious[0].line == 1

        wrappers = check_js_micro_wrappers(
            str(bom_file), bom_bytes, "typescript", counts
        )
        assert len(wrappers) == 2
        assert [w.line for w in wrappers] == [2, 5]

    def test_optional_catch_and_console_error_pass(self):
        source = """
async function load() {
  try {
    return await fetchData();
  } catch {}
}

function safeLoad() {
  try {
    return fetchData();
  } catch (err) {
    console.error(err);
  }
}
"""
        violations = check_js_swallowed_exceptions("app.js", source, "javascript")
        assert len(violations) == 1
        assert violations[0].line == 5

    def test_exported_arrow_and_function_skipped_by_micro_wrappers(self):
        source = (
            "export const exportedArrow = (x: number) => x + 1;\n"
            "export function exportedFn(x: number) { return x + 1; }\n"
            "exportedArrow(1);\n"
            "exportedFn(2);\n"
        )
        counts = {"exportedArrow": 1, "exportedFn": 1}
        assert (
            check_js_micro_wrappers("mod.ts", source, "typescript", counts) == []
        )
