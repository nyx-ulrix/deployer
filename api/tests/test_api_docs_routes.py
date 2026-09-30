"""Every endpoint in the docs' Method | Path tables must exist in the router (A-189).

Tables often give paths relative to a prefix stated above them ("All under /v1/projects/{id}",
".../tables/{table}/rows"), so a documented path matches any route that ends with it. A path
parameter typed as a Literal stands for each of its values (`.../{replica_id}/{action}` is routed
for `.../{rid}/pause`, `resume` and `recopy`).
"""

import re
from pathlib import Path
from typing import Literal, get_args, get_origin

from starlette.routing import WebSocketRoute

from app.main import app

DOCS = Path(__file__).resolve().parents[2] / "docs"
ROW = re.compile(r"^\|\s*(GET|POST|PUT|PATCH|DELETE|WS)\s*\|\s*`([^`]+)`")


def _norm(path: str) -> str:
    return re.sub(r"\{[^}]*\}", "{}", path)


def _paths(route) -> list[str]:
    paths = [route.path]
    for param in getattr(getattr(route, "dependant", None), "path_params", []):
        if get_origin(param.field_info.annotation) is Literal:
            key = "{" + param.name + "}"
            paths = [p.replace(key, str(v)) for p in paths for v in get_args(param.field_info.annotation)]
    return [_norm(p) for p in paths]


def _routes() -> set[tuple[str, str]]:
    out = set()
    for r in app.routes:
        methods = {"WS"} if isinstance(r, WebSocketRoute) else getattr(r, "methods", None) or set()
        out |= {(m, p) for m in methods for p in _paths(r)}
    return out


def _documented():
    for doc in sorted(DOCS.glob("*.md")):
        for n, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            if m := ROW.match(line):
                path = m.group(2).split("?")[0].removeprefix("...")
                head, _, last = path.rpartition("/")
                for alt in last.split("\\|"):  # `.../{rid}/pause\|resume\|recopy`
                    yield f"{doc.name}:{n}", m.group(1), _norm(f"{head}/{alt}")


def test_documented_endpoints_exist():
    routes = _routes()
    rows = list(_documented())
    assert len(rows) > 150  # the parser still finds the tables
    missing = [
        f"{where} {method} {path}"
        for where, method, path in rows
        if not any(m == method and p.endswith(path) for m, p in routes)
    ]
    assert not missing, "documented but not routed:\n" + "\n".join(missing)
