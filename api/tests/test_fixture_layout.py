"""A-192: shared fixtures live in conftest.py or its plugin modules, never imported from another test module."""

import ast
from pathlib import Path

TESTS = Path(__file__).parent


def _is_fixture(node: ast.FunctionDef) -> bool:
    for dec in node.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        if ast.unparse(target) in ("pytest.fixture", "fixture"):
            return True
    return False


def test_no_fixture_is_imported_from_a_test_module():
    trees = {p: ast.parse(p.read_text(encoding="utf-8")) for p in TESTS.rglob("*.py")}
    fixtures = {
        ".".join(p.relative_to(TESTS.parent).with_suffix("").parts): {
            n.name for n in tree.body if isinstance(n, ast.FunctionDef) and _is_fixture(n)
        }
        for p, tree in trees.items()
        if p.name.startswith("test_")
    }
    bad = [
        f"{p.relative_to(TESTS)}: {alias.name} from {node.module}"
        for p, tree in trees.items()
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module in fixtures
        for alias in node.names
        if alias.name in fixtures[node.module]
    ]
    assert bad == [], "move these fixtures to tests/shared_fixtures.py (registered in conftest.py):\n" + "\n".join(bad)
