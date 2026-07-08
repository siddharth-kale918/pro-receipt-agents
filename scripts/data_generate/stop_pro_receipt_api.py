#!/usr/bin/env python3
"""
Stop the pro-receipt API service.

Kills processes started by start_pro_receipt_api.py:
  - bun run dev:api   (API on port 3003)
  - bun run dev:receipts:host  (MFE dev host)

Also kills anything holding those ports as a fallback.

Usage:
    python stop_pro_receipt_api.py
    python stop_pro_receipt_api.py --ports-only   # skip pattern kill, port kill only
    python stop_pro_receipt_api.py --no-ports     # pattern kill only
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent

_KILL_PATTERNS = [
    "bun run dev:api",
    "bun run dev:receipts",
    "bun run dev:host",
    "dev:receipts:host",
]

_KILL_PORTS = [3003]


def _kill_by_pattern(pattern: str) -> bool:
    result = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
    pids = result.stdout.strip().split()
    if not pids:
        print(f"  No process found matching: {pattern!r}")
        return False
    for pid in pids:
        subprocess.run(["kill", "-9", pid], capture_output=True)
    print(f"  Killed {len(pids)} process(es) matching {pattern!r}  (PIDs: {', '.join(pids)})")
    return True


def _kill_by_port(port: int) -> bool:
    result = subprocess.run(["lsof", "-ti", f":{port}"], capture_output=True, text=True)
    pids = result.stdout.strip().split()
    if not pids:
        print(f"  No process found on port {port}")
        return False
    for pid in pids:
        subprocess.run(["kill", "-9", pid], capture_output=True)
    print(f"  Killed {len(pids)} process(es) on port {port}  (PIDs: {', '.join(pids)})")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Stop pro-receipt API")
    parser.add_argument("--ports-only", action="store_true", help="Port kill only")
    parser.add_argument("--no-ports", action="store_true", help="Pattern kill only")
    args = parser.parse_args()

    if not args.ports_only:
        print("Killing by process pattern …")
        for pattern in _KILL_PATTERNS:
            _kill_by_pattern(pattern)

    if not args.no_ports:
        print("Killing by port …")
        for port in _KILL_PORTS:
            _kill_by_port(port)

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
