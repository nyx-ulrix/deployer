"""services.repo_detect: every detection rule, the HawkerHub fixture, monorepos and .env keys."""

import json

from app.services.repo_detect import detect, wanted_files


def run(files: dict[str, str], extra: tuple[str, ...] = (), **kw) -> dict:
    tree = [*files, *extra]
    wanted = set(wanted_files(tree))
    assert wanted <= set(files)  # only files that exist are asked for
    return detect({p: t for p, t in files.items() if p in wanted}, tree, **kw)


def pkg(deps=None, dev=None, scripts=None, **extra) -> str:
    return json.dumps({"dependencies": deps or {}, "devDependencies": dev or {}, "scripts": scripts or {}, **extra})


def test_hawkerhub_flask_app():
    files = {
        "requirements.txt": "Flask==3.0.3\nPyMySQL==1.1.1\npymongo>=4.6  # mongo\npython-dotenv\n",
        "app/__init__.py": "from flask import Flask\n\ndef create_app():\n    app = Flask(__name__)\n    return app\n",
        "app/routes.py": "",
        ".env.example": "# Database\nHH_SQL_HOST=localhost\nHH_SQL_PASSWORD=change-me\nexport HH_MONGO_URI=mongodb://x\n\n",
        "README.md": "",
    }
    d = run(files, name="HawkerHub")
    assert d["preset"] == "python" and d["root_dir"] == "."
    assert d["start_command"] == "python -m flask --app app run --host 0.0.0.0 --port 8000"
    assert d["install_command"] is None  # the preset's pip install -r requirements.txt
    assert d["database_access_suggested"] is True
    assert d["env_keys"] == ["HH_SQL_HOST", "HH_SQL_PASSWORD", "HH_MONGO_URI"]
    assert d["detected"] == [{"what": "Flask app", "from": "requirements.txt, app/__init__.py"}]
    assert d["name"] == "HawkerHub" and d["warnings"] == []
    assert "change-me" not in json.dumps(d)


def test_flask_module_from_app_py_and_wsgi():
    base = {"requirements.txt": "flask\n"}
    assert "--app app " in run({**base, "app.py": "app = Flask(__name__)\n"})["start_command"]
    assert "--app wsgi " in run({**base, "wsgi.py": "from x import create_app\napp = create_app()\n"})["start_command"]
    missing = run(base)
    assert "--app app " in missing["start_command"] and missing["warnings"]


def test_fastapi_and_django():
    d = run({"requirements.txt": "fastapi\nuvicorn[standard]\nsqlalchemy\n", "main.py": "app = FastAPI()\n"})
    assert d["start_command"] == "uvicorn main:app --host 0.0.0.0 --port 8000"
    assert d["warnings"] == [] and d["database_access_suggested"] is True
    d = run({"requirements.txt": "fastapi\n", "app/main.py": "app = FastAPI(title='x')\n"})
    assert (
        d["start_command"].startswith("uvicorn app.main:app")
        and "uvicorn is not in your requirements" in d["warnings"][0]
    )
    d = run({"pyproject.toml": '[project]\ndependencies = ["Django>=5", "psycopg[binary]"]\n'}, ("manage.py",))
    assert d["start_command"] == "python manage.py runserver 0.0.0.0:8000"
    assert d["install_command"] == "pip install --no-cache-dir ." and d["database_access_suggested"] is True
    assert "development server" in d["warnings"][0]


def test_dockerfile_wins_and_expose():
    d = run({"Dockerfile": "FROM python\nEXPOSE 5000\n", "requirements.txt": "flask\n"})
    assert (d["preset"], d["container_port"]) == ("dockerfile", 5000)
    d = run({"Dockerfile": "FROM nginx\n"})
    assert d["container_port"] == 8080 and "EXPOSE" in d["warnings"][0]


def test_static_frameworks():
    export = {"next.config.mjs": "export default { output: 'export' }"}
    cases = [
        (pkg({"next": "15"}, scripts={"build": "next build"}), export, "out"),
        (pkg({"next": "13"}, scripts={"build": "next build && next export"}), {}, "out"),
        (pkg(dev={"vite": "5"}, scripts={"build": "vite build"}), {}, "dist"),
        (pkg(dev={"@vitejs/plugin-react": "4"}), {}, "dist"),
        (pkg({"react-scripts": "5"}, scripts={"build": "react-scripts build"}), {}, "build"),
        (pkg({"astro": "4"}), {}, "dist"),
        (pkg(dev={"@sveltejs/kit": "2", "@sveltejs/adapter-static": "3"}), {}, "build"),
    ]  # fmt: skip
    for package, more, output in cases:
        d = run({"package.json": package, **more}, ("package-lock.json",))
        assert (d["preset"], d["output_dir"]) == ("static", output), (package, d)
        assert d["install_command"] == "npm ci" and d["build_command"] == "npm run build"
    assert run({"package.json": pkg(dev={"vite": "5"})})["install_command"] == "npm install"  # no lockfile


def test_node_servers():
    d = run({"package.json": pkg({"express": "4", "mongoose": "8", "vite": "5"}, scripts={"start": "node s.js"})})
    assert (d["preset"], d["start_command"], d["build_command"]) == ("node", "npm start", None)
    assert d["database_access_suggested"] is True and d["detected"][0]["what"] == "Express app"
    d = run({"package.json": pkg({"next": "15"}, scripts={"build": "next build"})})
    assert (d["preset"], d["start_command"], d["build_command"]) == ("node", "npx next start", "npm run build")
    d = run({"package.json": pkg({"fastify": "4"}, main="server.js")})
    assert d["start_command"] == "node server.js" and d["warnings"]
    assert run({"package.json": pkg({"nuxt": "3"})})["start_command"] == "node .output/server/index.mjs"


def test_plain_html_and_unknown():
    d = run({"index.html": "<h1>hi</h1>"})
    assert (d["preset"], d["output_dir"], d["build_command"]) == ("static", ".", None)
    d = run({"README.md": "hello"})
    assert d["detected"] == [] and "Couldn't recognise" in d["warnings"][0]


def test_monorepo():
    d = run({"docs/README.md": "", "web/package.json": pkg(dev={"vite": "5"}), "web/.env.sample": "VITE_API=\n"})
    assert d["root_dir"] == "web" and d["preset"] == "static"
    assert d["detected"] == [{"what": "Vite site", "from": "web/package.json"}] and d["env_keys"] == ["VITE_API"]
    d = run({"api/requirements.txt": "flask\n", "web/package.json": pkg(dev={"vite": "5"})})
    assert d["root_dir"] == "." and d["detected"] == [] and "api, web" in d["warnings"][0]


def test_env_template_and_root_fallback():
    assert run({"index.html": "", ".env.template": "A=1\nnot a var\nB =2\n"})["env_keys"] == ["A", "B"]
