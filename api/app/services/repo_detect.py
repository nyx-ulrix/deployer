"""Suggest app settings from a repository's files (docs/DEPLOYMENTS.md "Connect a Git repository").

Pure: works on the tree listing (paths) and the contents of the few files `wanted_files` asks for.
`detect` returns a draft for `POST /apps`; nothing here touches the network or the database.
"""

from __future__ import annotations

import json
import re

ENV_FILES = (".env.example", ".env.sample", ".env.template")
_DIR_FILES = (
    "Dockerfile",
    "package.json",
    "package-lock.json",
    "requirements.txt",
    "pyproject.toml",
    "manage.py",
    "index.html",
    "app.py",
    "wsgi.py",
    "main.py",
    "app/__init__.py",
    "app/main.py",
    "next.config.js",
    "next.config.mjs",
    "next.config.ts",
    "svelte.config.js",
    *ENV_FILES,
)
# Files whose presence (not content) is enough.
_PRESENCE_ONLY = {"package-lock.json", "manage.py", "index.html"}
PY_DB_DEPS = {"pymysql", "mysqlclient", "psycopg", "psycopg2", "psycopg2-binary", "pymongo", "sqlalchemy"}
NODE_DB_DEPS = {"mysql2", "pg", "mongodb", "mongoose", "prisma", "@prisma/client"}
_NODE_SERVERS = ("express", "fastify", "koa", "hono")
_ENV_KEY = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


def _join(directory: str, name: str) -> str:
    return f"{directory}/{name}" if directory else name


def _dirs(tree: list[str]) -> list[str]:
    """Root plus first-level directories (monorepo candidates), sorted."""
    return [""] + sorted({p.split("/", 1)[0] for p in tree if "/" in p and not p.startswith(".")})


def wanted_files(tree: list[str]) -> list[str]:
    """Paths (present in the tree) whose contents `detect` reads."""
    present = set(tree)
    out = []
    for directory in _dirs(tree):
        for name in _DIR_FILES:
            path = _join(directory, name)
            if path in present and name not in _PRESENCE_ONLY:
                out.append(path)
    return out


def _python_deps(text: str, pyproject: bool) -> set[str]:
    if pyproject:
        names = re.findall(r"[\"']\s*([A-Za-z0-9][A-Za-z0-9_.\-]*)", text)
    else:
        names = [
            re.split(r"[\s\[<>=!~;@]", line.strip(), maxsplit=1)[0]
            for line in text.splitlines()
            if line.strip() and not line.strip().startswith(("#", "-"))
        ]
    return {n.lower().replace("_", "-") for n in names if n}


def _find_module(
    files: dict[str, str], directory: str, candidates: list[tuple[str, str]], marker: re.Pattern
) -> tuple[str, str]:
    """(module, file) of the first candidate file matching `marker`; ("", "") when none does."""
    for rel, module in candidates:
        text = files.get(_join(directory, rel))
        if text is not None and marker.search(text):
            return module, rel
    return "", ""


def _detect_dir(files: dict[str, str], present: set[str], d: str) -> dict | None:
    """Settings for the app in directory `d`, or None when nothing is recognised there."""

    def has(name: str) -> bool:
        return _join(d, name) in present

    def src(*names: str) -> str:
        return ", ".join(_join(d, n) for n in names)

    if has("Dockerfile"):
        text = files.get(_join(d, "Dockerfile"), "")
        m = re.search(r"^\s*EXPOSE\s+(\d+)", text, re.I | re.M)
        out = {"preset": "dockerfile", "what": "Dockerfile", "from": src("Dockerfile"), "warnings": []}
        if m:
            out["container_port"] = int(m.group(1))
        else:
            out["container_port"] = 8080
            out["warnings"].append("The Dockerfile has no EXPOSE line; assumed port 8080 - check the container port.")
        return out

    if has("package.json"):
        try:
            pkg = json.loads(files.get(_join(d, "package.json"), "") or "{}")
        except ValueError:
            pkg = {}
        pkg = pkg if isinstance(pkg, dict) else {}
        deps = {**(pkg.get("devDependencies") or {}), **(pkg.get("dependencies") or {})}
        scripts = pkg.get("scripts") or {}
        scripts = scripts if isinstance(scripts, dict) else {}
        install = "npm ci" if has("package-lock.json") else "npm install"
        build = "npm run build" if scripts.get("build") else ""
        server = any(s in deps for s in _NODE_SERVERS)
        db = bool(NODE_DB_DEPS & set(deps))

        def static(what: str, output: str) -> dict:
            return {
                "preset": "static",
                "what": what,
                "from": src("package.json"),
                "install_command": install,
                "build_command": build or "npm run build",
                "output_dir": output,
                "db": db,
                "warnings": [],
            }

        next_config = "".join(files.get(_join(d, f"next.config.{ext}"), "") for ext in ("js", "mjs", "ts"))
        if "next" in deps and (
            re.search(r"output\s*:\s*[\"']export[\"']", next_config) or "next export" in str(scripts.get("build", ""))
        ):
            return static("Next.js static export", "out")
        if not server:
            if "vite" in deps or any(k.startswith("@vitejs/") for k in deps):
                return static("Vite site", "dist")
            if "react-scripts" in deps:
                return static("Create React App", "build")
            if "astro" in deps:
                return static("Astro site", "dist")
            if "@sveltejs/kit" in deps and "@sveltejs/adapter-static" in deps:
                return static("SvelteKit static site", "build")
        framework = next((f for f in ("next", "nuxt", *_NODE_SERVERS) if f in deps), None)
        if scripts.get("start") or framework:
            warnings = []
            if scripts.get("start"):
                start = "npm start"
            elif framework == "next":
                start = "npx next start"
            elif framework == "nuxt":
                start = "node .output/server/index.mjs"
            else:
                start = f"node {pkg.get('main') or 'index.js'}"
                warnings.append(f"package.json has no start script; guessed `{start}` - check the start command.")
            names = {"next": "Next.js", "nuxt": "Nuxt", "express": "Express", "fastify": "Fastify"}
            return {
                "preset": "node",
                "what": f"{names.get(framework or '', 'Node.js')} app",
                "from": src("package.json"),
                "install_command": install,
                "build_command": build,
                "start_command": start,
                "db": db,
                "warnings": warnings,
            }

    if has("requirements.txt") or has("pyproject.toml"):
        deps: set[str] = set()
        sources = []
        for name, pyproject in (("requirements.txt", False), ("pyproject.toml", True)):
            if has(name):
                deps |= _python_deps(files.get(_join(d, name), ""), pyproject)
                sources.append(name)
        install = "" if has("requirements.txt") else "pip install --no-cache-dir ."
        db = bool(PY_DB_DEPS & deps)
        base = {"preset": "python", "install_command": install, "db": db, "warnings": []}
        if "flask" in deps:
            module, where = _find_module(
                files,
                d,
                [("app.py", "app"), ("wsgi.py", "wsgi"), ("app/__init__.py", "app")],
                re.compile(r"def\s+create_app\s*\(|^\s*app\s*=", re.M),
            )
            if not module:
                module = "app"
                base["warnings"].append("Couldn't find the Flask app; assumed module `app` - check the start command.")
            return {
                **base,
                "what": "Flask app",
                "from": src(*sources, *([where] if where else [])),
                "start_command": f"python -m flask --app {module} run --host 0.0.0.0 --port 8000",
            }
        if "fastapi" in deps:
            module, _ = _find_module(
                files,
                d,
                [("main.py", "main"), ("app.py", "app"), ("app/main.py", "app.main")],
                re.compile(r"^\s*app\s*=\s*FastAPI\(", re.M),
            )
            if not module:
                module = "main"
                base["warnings"].append("Couldn't find `app = FastAPI()`; assumed main.py - check the start command.")
            if "uvicorn" not in deps:
                base["warnings"].append("uvicorn is not in your requirements; add it or the app won't start.")
            return {
                **base,
                "what": "FastAPI app",
                "from": src(*sources),
                "start_command": f"uvicorn {module}:app --host 0.0.0.0 --port 8000",
            }
        if "django" in deps or has("manage.py"):
            base["warnings"].append(
                "Django's runserver is a development server; for production use gunicorn "
                "(e.g. gunicorn <project>.wsgi --bind 0.0.0.0:8000)."
            )
            return {
                **base,
                "what": "Django app",
                "from": src(*sources, *(["manage.py"] if has("manage.py") else [])),
                "start_command": "python manage.py runserver 0.0.0.0:8000",
            }

    if has("index.html") and not has("package.json"):
        return {
            "preset": "static",
            "what": "Static site",
            "from": src("index.html"),
            "install_command": "",
            "build_command": "",
            "output_dir": ".",
            "warnings": [],
        }
    return None


def env_keys(files: dict[str, str], directory: str) -> list[str]:
    """Variable names (never values) from the first .env example file in `directory` (then the root)."""
    for d in dict.fromkeys([directory, ""]):
        for name in ENV_FILES:
            text = files.get(_join(d, name))
            if text is not None:
                return list(dict.fromkeys(m.group(1) for line in text.splitlines() if (m := _ENV_KEY.match(line))))
    return []


def detect(files: dict[str, str], tree: list[str], *, name: str = "", branch: str = "main") -> dict:
    """App draft (never persisted): see `POST /projects/{pid}/apps/detect` in docs/API.md."""
    present = set(tree) | set(files)
    root_dir = "."
    found = _detect_dir(files, present, "")
    warnings: list[str] = []
    if found is None:
        subdirs = [(d, r) for d in _dirs(tree)[1:] if (r := _detect_dir(files, present, d)) is not None]
        if len(subdirs) == 1:
            root_dir, found = subdirs[0]
        elif subdirs:
            warnings.append(
                "Several apps found (" + ", ".join(d for d, _ in subdirs) + "); pick one with Root directory."
            )
    if found is None and not warnings:
        warnings.append("Couldn't recognise the app type; choose a preset and fill in the commands.")
    found = found or {}
    return {
        "name": name,
        "branch": branch,
        "root_dir": root_dir,
        "preset": found.get("preset", "static"),
        "install_command": found.get("install_command") or None,
        "build_command": found.get("build_command") or None,
        "start_command": found.get("start_command") or None,
        "output_dir": found.get("output_dir") or None,
        "container_port": found.get("container_port"),
        "env_keys": env_keys(files, "" if root_dir == "." else root_dir),
        "database_access_suggested": bool(found.get("db")),
        "detected": [{"what": found["what"], "from": found["from"]}] if found else [],
        "warnings": warnings + found.get("warnings", []),
    }
