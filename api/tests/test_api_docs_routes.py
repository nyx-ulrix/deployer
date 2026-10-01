"""Every endpoint the docs name must exist in the router (A-189).

Checked: `| METHOD | path |` table rows in docs/*.md, and inline `METHOD [<url>]/v1/...` references in
docs/*.md, README.md and the deploy-website skill.

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

ROOT = Path(__file__).resolve().parents[2]
DOCS = [*sorted((ROOT / "docs").glob("*.md")), ROOT / "README.md", ROOT / "skills/deploy-website/SKILL.md"]
ROW = re.compile(r"^\|\s*(GET|POST|PUT|PATCH|DELETE|WS)\s*\|\s*`([^`]+)`")
# `GET /v1/...`, and `GET <url>/v1/...` as the skill writes its availability probes
INLINE = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE|WS) +`?(?:<\w+>)?(/v1/[^\s`)\"',;]+)")


def _norm(path: str) -> str:
    return re.sub(r"\{[^}]*\}|<\w+>", "{}", path)  # `{id}` and `<project_id>` placeholders


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
    for doc in DOCS:
        for n, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            for m in filter(None, [ROW.match(line), *INLINE.finditer(line)]):
                path = m.group(2).split("?")[0].rstrip(".:").removeprefix("...")
                head, _, last = path.rpartition("/")
                for alt in last.split("\\|"):  # `.../{rid}/pause\|resume\|recopy`
                    yield f"{doc.name}:{n}", m.group(1), _norm(f"{head}/{alt}")


def test_documented_endpoints_exist():
    routes = _routes()
    rows = list(_documented())
    assert len(rows) > 150  # the parser still finds the tables
    assert sum(w.startswith("SKILL.md") for w, _, _ in rows) > 10  # ...and the inline references
    missing = [
        f"{where} {method} {path}"
        for where, method, path in rows
        if not any(m == method and p.endswith(path) for m, p in routes)
    ]
    assert not missing, "documented but not routed:\n" + "\n".join(missing)
