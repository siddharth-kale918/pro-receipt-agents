#!/usr/bin/env python3
"""
Start the pro-receipt API service.

Steps:
  0. Sync .env.prime → <codebase>/.env
  1. Ensure Docker containers (postgres, kafka, kafka-ui, jaeger, localstack)
       — if a port is already bound by something other than our compose project,
         a free alternative port is chosen automatically and docker-compose.override.yml
         is written into the codebase directory.
  2. bun run build          (blocking — waits for completion)
  3. Open Terminal tabs:
       - bun run dev:host   (API on 3003 + MFE receipts dev host)

Required .env.prime:
    PRO_RECEIPT_CODEBASE_PATH  — absolute path to the pro-receipt repo

.env.prime is always copied to <PRO_RECEIPT_CODEBASE_PATH>/.env before any step runs.

Usage:
    python start_pro_receipt_api.py
    python start_pro_receipt_api.py --skip-build       # skip bun run build
    python start_pro_receipt_api.py --skip-docker      # skip docker container step
    python start_pro_receipt_api.py --docker-wait 60   # seconds to wait for healthy (default 90)
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent
_PRIME = _ROOT / ".env.prime"

# Docker compose service ports: {internal_port: (env_var, default_host_port)}
_COMPOSE_PORTS = {
    5432: ("DB_PORT", 5443),
    9392: (None, 9392),
    8086: (None, 8086),
    16686: (None, 16686),
    4319: (None, 4319),
    4577: ("LOCALSTACK_PORT", 4577),
}

_COMPOSE_PROJECT = "pro-receipts"


def _load_prime_manual(path: Path) -> None:
    for raw in path.read_text(errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if not key or not all(c.isalnum() or c == "_" for c in key):
            continue
        val = val.strip()
        if len(val) >= 2 and val[0] in ('"', "'") and val[-1] == val[0]:
            val = val[1:-1]
        os.environ.setdefault(key, val)


def _sync_prime(codebase: str) -> None:
    if not _PRIME.exists():
        print(f"WARNING: .env.prime not found at {_PRIME} — skipping sync.", file=sys.stderr)
        return
    dest = Path(codebase) / ".env"
    dest.write_bytes(_PRIME.read_bytes())
    print(f"  Synced .env.prime → {dest}\n")


def _cfg(key: str, default: str = "") -> str:
    v = os.environ.get(key)
    return str(v).strip() if v and str(v).strip() else default


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def _find_free_port(start: int = 5000) -> int:
    for p in range(start, start + 500):
        if _port_free(p):
            return p
    raise RuntimeError("No free port found")


def _docker_project_owns_port(port: int) -> bool:
    """Check if the port is held by our compose project (not an alien process)."""
    result = subprocess.run(
        ["docker", "compose", "--project-name", _COMPOSE_PROJECT, "ps", "--format", "json"],
        capture_output=True, text=True,
    )
    return str(port) in result.stdout


def _ensure_docker(codebase: str, docker_wait: int) -> None:
    print("Checking Docker containers …")
    overrides: dict[str, int] = {}

    for internal_port, (env_var, default_host) in _COMPOSE_PORTS.items():
        if not _port_free(default_host):
            if _docker_project_owns_port(default_host):
                print(f"  Port {default_host} already owned by {_COMPOSE_PROJECT} — OK")
                continue
            free = _find_free_port(default_host + 1)
            print(f"  Port {default_host} in use by alien process → remapping to {free}")
            overrides[str(internal_port)] = free
            if env_var:
                os.environ[env_var] = str(free)

    if overrides:
        override_content = {"services": {}}
        for svc_name, (svc_internal, svc_env, svc_default) in {
            "postgres": (5432, "DB_PORT", 5443),
            "kafka": (9392, None, 9392),
            "kafka-ui": (8086, None, 8086),
            "jaeger": (16686, None, 16686),
            "localstack": (4577, "LOCALSTACK_PORT", 4577),
        }.items():
            host_port = overrides.get(str(svc_internal))
            if host_port:
                override_content["services"][svc_name] = {
                    "ports": [f"{host_port}:{svc_internal}"]
                }
        override_path = Path(codebase) / "docker-compose.override.yml"
        override_path.write_text(yaml.dump(override_content))
        print(f"  Wrote docker-compose.override.yml → {override_path}")

    result = subprocess.run(
        ["docker", "compose", "--project-name", _COMPOSE_PROJECT, "up", "-d", "--wait"],
        cwd=codebase,
    )
    if result.returncode != 0:
        print("  docker compose up failed.", file=sys.stderr)
        sys.exit(result.returncode)

    print(f"  Waiting up to {docker_wait}s for containers to be healthy …")
    deadline = time.time() + docker_wait
    while time.time() < deadline:
        r = subprocess.run(
            ["docker", "compose", "--project-name", _COMPOSE_PROJECT, "ps", "--format", "json"],
            capture_output=True, text=True, cwd=codebase,
        )
        if '"Health":"healthy"' in r.stdout or "healthy" in r.stdout:
            print("  Containers healthy.")
            break
        time.sleep(3)
    else:
        print("  WARNING: containers may not be fully healthy yet.")


def _open_terminal_tab(title: str, cmd: str, cwd: str) -> None:
    """Open a new Terminal.app tab running cmd in cwd."""
    script = f'''
tell application "Terminal"
    activate
    tell application "System Events" to keystroke "t" using command down
    delay 0.3
    do script "cd {cwd} && echo '=== {title} ===' && {cmd}" in front window
end tell
'''
    subprocess.run(["osascript", "-e", script], capture_output=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Start pro-receipt API")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--skip-docker", action="store_true")
    parser.add_argument("--docker-wait", type=int, default=90)
    args = parser.parse_args()

    if _PRIME.exists():
        _load_prime_manual(_PRIME)

    codebase = _cfg("PRO_RECEIPT_CODEBASE_PATH")
    if not codebase:
        print("ERROR: PRO_RECEIPT_CODEBASE_PATH is required in .env.prime", file=sys.stderr)
        return 1

    _sync_prime(codebase)

    if not args.skip_docker:
        _ensure_docker(codebase, args.docker_wait)

    if not args.skip_build:
        print("Running bun run build …")
        result = subprocess.run(["bun", "run", "build"], cwd=codebase)
        if result.returncode != 0:
            print("  bun run build failed.", file=sys.stderr)
            return result.returncode
        print("  Build complete.\n")

    print("Opening Terminal tab: bun run dev:host …")
    _open_terminal_tab("pro-receipt dev", "bun run dev:host", codebase)

    print("""
Started:
  API  → http://localhost:3003
  MFE  → https://procurement.loc.ogintegration.us/receipts

  (If you see 404: run `bun run setup:hosts` in the pro-receipt repo)
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
