"""A-191: every top-level constant, function and class in app/ is referenced in app/ besides its definition.

References from tests do not count (dead app code with a leftover test is still dead), except for test
hooks: functions whose docstring starts with "Test hook". Decorated functions (routes, job handlers) are
registered by their decorator, so they are skipped.
"""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _top_level_names(tree: ast.Module) -> list[str]:
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.decorator_list and not (ast.get_docstring(node) or "").startswith("Test hook"):
                names.append(node.name)
        elif isinstance(node, ast.Assign):
            names += [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.append(node.target.id)
    return [n for n in names if not n.startswith("__")]


def test_no_unreferenced_top_level_names():
    app = {p: p.read_text(encoding="utf-8") for p in (ROOT / "app").rglob("*.py")}
    dead = []
    for path, text in app.items():
        for name in _top_level_names(ast.parse(text)):
            word = re.compile(rf"\b{re.escape(name)}\b")
            if sum(len(word.findall(s)) for s in app.values()) <= 1:
                dead.append(f"{path.relative_to(ROOT)}: {name}")
    assert dead == [], "unused outside tests - delete them (and their tests):\n" + "\n".join(dead)


def test_a_name_used_only_by_tests_is_dead():
    tree = ast.parse('def helper():\n    """Used by its test only."""\n\n\ndef seam():\n    """Test hook: x."""\n')
    assert _top_level_names(tree) == ["helper"]
