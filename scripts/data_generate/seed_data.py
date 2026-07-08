#!/usr/bin/env python3
"""
Seed reference data into the receipts database.

Runs the following bun seed scripts in order:
  1. bun run db:seed          — seed receipts and shared reference data

Requires PRO_RECEIPT_CODEBASE_PATH in .env.prime.

Usage:
    python seed_data.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_PRIME = _ROOT / ".env.prime"


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


def _load_env() -> None:
    for candidate in [_PRIME, _ROOT / ".env", _ROOT.parent / ".env"]:
        if candidate.exists():
            _load_prime_manual(candidate)
            return


_load_env()


def _sync_prime(codebase: str) -> None:
    if not _PRIME.exists():
        return
    dest = Path(codebase) / ".env"
    dest.write_bytes(_PRIME.read_bytes())
    print(f"  Synced .env.prime → {dest}")


def _cfg(key: str, default: str = "") -> str:
    v = os.environ.get(key)
    return str(v).strip() if v and str(v).strip() else default


def _run(label: str, cmd: list[str], cwd: Path) -> None:
    print(f"  Running: {' '.join(cmd)}  (cwd={cwd})")
    result = subprocess.run(cmd, cwd=str(cwd))
    if result.returncode != 0:
        print(f"  {label} failed (exit {result.returncode}).", file=sys.stderr)
        sys.exit(result.returncode)
    print(f"  {label} complete.")


def main() -> int:
    codebase = _cfg("PRO_RECEIPT_CODEBASE_PATH")
    if not codebase:
        print("PRO_RECEIPT_CODEBASE_PATH is required in .env.prime", file=sys.stderr)
        return 1

    _sync_prime(codebase)
    cwd = Path(codebase)

    _run("db:seed", ["bun", "run", "db:seed"], cwd)
    _run("db:setup:shared", ["bun", "run", "db:setup:shared"], cwd)

    print("\nSeed complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
