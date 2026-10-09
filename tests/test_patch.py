"""patch.py: an apply_patch input as the calls rules know."""

from agentltl_codex import patch

PATCH = """*** Begin Patch
*** Add File: docs/new.md
+# Title
+text
*** Update File: src/app.py
@@ def main():
     keep
-    old()
+    new()
*** Update File: a.txt
*** Move to: b.txt
@@
-x
+y
*** Delete File: old.txt
*** End Patch
"""


def test_calls():
    assert patch.calls(PATCH) == [
        ("Write", {"file_path": "docs/new.md", "content": "# Title\ntext\n"}),
        ("Edit", {"file_path": "src/app.py", "old_string": "    old()", "new_string": "    new()"}),
        ("Edit", {"file_path": "a.txt", "old_string": "x", "new_string": "y"}),
        ("Write", {"file_path": "b.txt", "content": "y"}),
        ("Bash", {"command": "rm -- old.txt"}),
    ]
    assert patch.paths(PATCH) == ["docs/new.md", "src/app.py", "a.txt", "b.txt", "old.txt"]


def test_odd_patches():
    assert patch.calls("") == []
    assert patch.calls("not a patch") == []
    assert patch.calls("*** Begin Patch\n*** Delete File: it's here.txt\n*** End Patch") == [
        ("Bash", {"command": "rm -- 'it'\"'\"'s here.txt'"})]
    assert patch.calls("*** Begin Patch\n*** Add File: empty.txt\n*** End Patch") == [
        ("Write", {"file_path": "empty.txt", "content": ""})]
