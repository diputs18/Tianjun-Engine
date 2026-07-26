from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import venv
import zipfile
from pathlib import Path


REQUIRED_ASSETS = {
    "tianjun/interfaces/dashboard/static/index.html",
    "tianjun/interfaces/dashboard/static/css/base.css",
    "tianjun/interfaces/dashboard/static/js/router.js",
    "tianjun/interfaces/dashboard/static/js/request.js",
    "tianjun/interfaces/dashboard/static/js/topology-data.js",
    "tianjun/interfaces/dashboard/static/js/topology-resource.js",
}


INSTALLED_SMOKE_PROGRAM = r"""
import json
import threading
import urllib.request

from tianjun.application.bootstrap import build_control_plane
from tianjun.interfaces.http.server import build_http_server

control_plane = build_control_plane()
server = build_http_server(control_plane, "127.0.0.1", 0)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
base_url = f"http://127.0.0.1:{server.server_address[1]}"
try:
    with urllib.request.urlopen(base_url + "/dashboard", timeout=5) as response:
        dashboard = response.read().decode("utf-8")
    with urllib.request.urlopen(base_url + "/css/base.css", timeout=5) as response:
        stylesheet = response.read().decode("utf-8")
    with urllib.request.urlopen(base_url + "/css/tokens.css", timeout=5) as response:
        tokens = response.read().decode("utf-8")
    with urllib.request.urlopen(base_url + "/js/router.js", timeout=5) as response:
        javascript = response.read().decode("utf-8")
    assert "<!doctype html>" in dashboard.lower()
    assert "box-sizing" in stylesheet
    assert ":root" in tokens
    assert "navigate" in javascript.lower()
    print(json.dumps({"status": "ok", "dashboard_bytes": len(dashboard)}))
finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
"""


def _venv_python(environment: Path) -> Path:
    if sys.platform == "win32":
        return environment / "Scripts" / "python.exe"
    return environment / "bin" / "python"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify dashboard assets in a wheel and start the installed HTTP server."
    )
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    wheel = args.wheel.resolve()
    if not wheel.is_file():
        raise FileNotFoundError(wheel)

    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
    missing = sorted(REQUIRED_ASSETS - names)
    if missing:
        raise RuntimeError(f"wheel is missing dashboard assets: {missing}")

    with tempfile.TemporaryDirectory(prefix="tianjun-wheel-smoke-") as temp_dir:
        environment = Path(temp_dir) / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = _venv_python(environment)
        subprocess.run(
            [str(python), "-m", "pip", "install", "--no-deps", str(wheel)],
            check=True,
        )
        completed = subprocess.run(
            [str(python), "-c", INSTALLED_SMOKE_PROGRAM],
            capture_output=True,
            text=True,
        )
        if completed.returncode:
            raise RuntimeError(
                "installed wheel smoke test failed\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            )
        print(completed.stdout.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
