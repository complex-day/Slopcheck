import pytest
import subprocess
from slopcheck.diff_parser import (
    GitDiffError,
    PYTHON_EXTENSIONS,
    SUPPORTED_EXTENSIONS,
    parse_diff_output,
    parse_staged_diff,
)


def test_multi_file_staged_diff_parsing():
    diff_text = """diff --git a/src/app.py b/src/app.py
index abcdef1..2345678 100644
--- a/src/app.py
+++ b/src/app.py
@@ -10,3 +10,3 @@
-old1
-old2
-old3
+new1
+new2
+new3
@@ -30,0 +31,2 @@
+extra1
+extra2
diff --git a/src/utils.py b/src/utils.py
new file mode 100644
index 0000000..abcdef1
--- /dev/null
+++ b/src/utils.py
@@ -0,0 +1,4 @@
+def helper():
+    pass
+
+foo = 123
"""
    result = parse_diff_output(diff_text)
    assert result == {
        "src/app.py": {10, 11, 12, 31, 32},
        "src/utils.py": {1, 2, 3, 4},
    }


def test_single_line_hunk_header_without_comma():
    diff_text = """diff --git a/src/app.py b/src/app.py
index abcdef1..2345678 100644
--- a/src/app.py
+++ b/src/app.py
@@ -5 +5 @@
-old
+new
"""
    result = parse_diff_output(diff_text)
    assert result == {"src/app.py": {5}}


def test_ignoring_non_python_files():
    diff_text = """diff --git a/README.md b/README.md
index abcdef1..2345678 100644
--- a/README.md
+++ b/README.md
@@ -1,5 +1,5 @@
-old
+new
diff --git a/config.json b/config.json
new file mode 100644
index 0000000..abcdef1
--- /dev/null
+++ b/config.json
@@ -0,0 +1,2 @@
+{"key": "value"}
+{}
diff --git a/src/app.py b/src/app.py
index abcdef1..2345678 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1,2 +1,2 @@
-old
+new
"""
    result = parse_diff_output(diff_text)
    assert result == {"src/app.py": {1, 2}}
    assert "README.md" not in result
    assert "config.json" not in result


def test_empty_diff_returns_empty_dict():
    assert parse_diff_output("") == {}
    assert parse_diff_output("   \n\n  ") == {}


def test_ignoring_binary_and_deleted_files():
    diff_text = """diff --git a/image.png b/image.png
new file mode 100644
index 0000000..abcdef1
Binary files /dev/null and b/image.png differ
diff --git a/old.py b/old.py
deleted file mode 100644
index abcdef1..0000000
--- a/old.py
+++ /dev/null
@@ -1,3 +0,0 @@
-line1
-line2
-line3
"""
    result = parse_diff_output(diff_text)
    assert result == {}


def test_git_diff_error_on_command_failure(monkeypatch):
    def mock_run(*args, **kwargs):
        raise subprocess.CalledProcessError(
            returncode=128,
            cmd=args[0],
            stderr="fatal: not a git repository",
        )

    monkeypatch.setattr(subprocess, "run", mock_run)
    with pytest.raises(GitDiffError) as exc_info:
        parse_staged_diff()
    assert "fatal: not a git repository" in str(exc_info.value)


def test_live_clean_repo_returns_empty_or_dict():
    result = parse_staged_diff()
    assert isinstance(result, dict)


def test_parse_diff_output_with_supported_extensions():
    diff_text = """diff --git a/src/app.py b/src/app.py
index abcdef1..2345678 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1,0 +1,2 @@
+x = 1
+y = 2
diff --git a/web/index.js b/web/index.js
new file mode 100644
--- /dev/null
+++ b/web/index.js
@@ -0,0 +1,2 @@
+const a = 1;
+console.log(a);
diff --git a/web/service.ts b/web/service.ts
new file mode 100644
--- /dev/null
+++ b/web/service.ts
@@ -0,0 +1,1 @@
+export const ok: boolean = true;
diff --git a/web/App.tsx b/web/App.tsx
new file mode 100644
--- /dev/null
+++ b/web/App.tsx
@@ -0,0 +1,1 @@
+export const App = () => <div />;
diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1,1 +1,1 @@
-old
+new
diff --git a/package.json b/package.json
--- a/package.json
+++ b/package.json
@@ -1,1 +1,1 @@
-{}
+{"name": "app"}
diff --git a/logo.png b/logo.png
Binary files /dev/null and b/logo.png differ
diff --git a/deleted.ts b/deleted.ts
deleted file mode 100644
--- a/deleted.ts
+++ /dev/null
@@ -1,2 +0,0 @@
-const x = 1;
-const y = 2;
"""
    # Default still returns only Python
    assert parse_diff_output(diff_text) == {"src/app.py": {1, 2}}
    assert PYTHON_EXTENSIONS == frozenset({".py"})

    result = parse_diff_output(diff_text, extensions=SUPPORTED_EXTENSIONS)
    assert result == {
        "src/app.py": {1, 2},
        "web/index.js": {1, 2},
        "web/service.ts": {1},
        "web/App.tsx": {1},
    }
