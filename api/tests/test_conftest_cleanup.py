import subprocess
import sys
from pathlib import Path


def test_conftest_removes_its_temp_dir_at_exit():
    # A-193: every test run used to leave a deployer-tests-* dir (with the SQLite DB) behind.
    api_dir = Path(__file__).resolve().parents[1]
    script = "import runpy; print(runpy.run_path('tests/conftest.py')['_tmpdir'])"
    out = subprocess.run([sys.executable, "-c", script], cwd=api_dir, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    tmpdir = Path(out.stdout.strip().splitlines()[-1])
    assert tmpdir.name.startswith("deployer-tests-") and not tmpdir.exists()
