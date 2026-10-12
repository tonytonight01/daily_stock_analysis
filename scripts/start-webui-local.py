#!/usr/bin/env python3
"""Prepare the local Python environment and start the existing Web workspace."""

import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from urllib.request import urlopen
import webbrowser


ROOT = Path(__file__).resolve().parents[1]


def prepare(root: Path) -> Path:
    if sys.version_info < (3, 11):
        raise RuntimeError("Install Python 3.11 or newer before starting the Web workspace.")
    for executable in ("node", "npm"):
        if shutil.which(executable) is None:
            raise RuntimeError("Install Node.js (including npm), then reopen this launcher.")
    node = subprocess.check_output([shutil.which("node"), "--version"], text=True).strip()
    version = tuple(int(part) for part in node.lstrip("v").split(".")[:3])
    if not (version >= (20, 19, 0) and version[0] < 27):
        raise RuntimeError("The current frontend requires Node.js >=20.19 and <27.")

    env_path = root / ".env"
    if not env_path.exists():
        shutil.copyfile(root / "docs/examples/tdx-webui.env.example", env_path)
        print("Created local .env. Add your DeepSeek API Key in Web Settings; do not share it.", flush=True)

    environment = root / ".venv"
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.exists():
        subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True, cwd=root)
    requirements = root / "requirements.txt"
    fingerprint = hashlib.sha256(requirements.read_bytes()).hexdigest()
    stamp = environment / ".local-webui-requirements.sha256"
    if not stamp.exists() or stamp.read_text().strip() != fingerprint:
        print("Installing Python dependencies. First launch can take several minutes.", flush=True)
        subprocess.run([str(python), "-m", "pip", "install", "-r", str(requirements)], check=True, cwd=root)
        stamp.write_text(fingerprint + "\n")
    return python


def local_url(python: Path, root: Path) -> str:
    # Return only non-secret listener settings; never print or copy credentials.
    code = (
        "import json; from src.config import setup_env, get_config; setup_env(); "
        "c=get_config(); print(json.dumps({'host':c.webui_host,'port':c.webui_port}))"
    )
    settings = json.loads(subprocess.check_output([str(python), "-c", code], cwd=root, text=True))
    host = settings["host"]
    if host != "localhost" and not ipaddress.ip_address(host).is_loopback:
        raise RuntimeError("This local launcher requires a loopback WEBUI_HOST in .env.")
    address = f"[{host}]" if ":" in host else host
    return f"http://{address}:{settings['port']}"


def open_when_ready(url: str, process: subprocess.Popen) -> None:
    while process.poll() is None:
        try:
            with urlopen(url + "/api/health", timeout=2) as response:
                if response.status == 200:
                    webbrowser.open(url)
                    return
        except (OSError, ValueError):
            pass
        time.sleep(2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-browser", action="store_true", help="Do not open the browser automatically")
    args = parser.parse_args()
    process = None
    try:
        python = prepare(ROOT)
        url = local_url(python, ROOT)
        print(f"Web workspace: {url}\nKeep this window open. Press Ctrl+C to stop.", flush=True)
        environment = os.environ.copy()
        # Install the locked versions through the official registry, including
        # lockfile entries that originally point to a mirror. Preserve proxies.
        environment["npm_config_registry"] = "https://registry.npmjs.org"
        environment["npm_config_replace_registry_host"] = "always"
        process = subprocess.Popen([str(python), "main.py", "--webui-only"], cwd=ROOT, env=environment)
        if not args.no_browser:
            threading.Thread(target=open_when_ready, args=(url, process), daemon=True).start()
        return process.wait()
    except KeyboardInterrupt:
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait()
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Local startup failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
