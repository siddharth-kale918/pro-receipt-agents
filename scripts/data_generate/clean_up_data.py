#!/usr/bin/env python3
"""
Reset the pro-receipt database: drop all tables → re-migrate → re-seed.

Runs these root-level bun scripts in sequence:
  1. db:reset        — drop all rcp_* tables, enums, and drizzle migration schema
  2. db:migrate      — re-run all migrations
  3. db:seed         — re-seed reference data
  4. db:setup:shared — set up shared tables

Each step is run from the repo root so it picks up --env-file=.env (drizzle-kit
needs this; db:reset:full's internal call does not re-pass --env-file).

No superuser credentials needed — works with the app DB user.

.env.prime is always synced to <PRO_RECEIPT_CODEBASE_PATH>/.env before running.

Usage:
    python clean_up_data.py
    python clean_up_data.py --yes           # skip confirmation prompt
    python clean_up_data.py --skip-seed     # reset + migrate only, skip seed
"""

from __future__ import annotations

import argparse
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


def _run(label: str, cmd: list[str], cwd: str) -> None:
    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        print(f"  {label} failed (exit {result.returncode}).", file=sys.stderr)
        sys.exit(result.returncode)
    print(f"  {label} complete.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset pro-receipt database")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    parser.add_argument("--skip-seed", action="store_true", help="Reset + migrate only, skip seed")
    args = parser.parse_args()

    codebase = _cfg("PRO_RECEIPT_CODEBASE_PATH")
    if not codebase:
        print("ERROR: PRO_RECEIPT_CODEBASE_PATH is required in .env.prime", file=sys.stderr)
        return 1

    if not args.yes:
        ans = input("  Drop all receipt tables and reseed? This is destructive. [y/N] ").strip().lower()
        if ans not in ("y", "yes"):
            print("  Aborted.")
            return 0

    _sync_prime(codebase)

    # Run each step from the repo root so every command picks up --env-file via
    # the root package.json scripts (db:reset:full's internal bun run db:migrate
    # does NOT re-pass --env-file, so env vars may not propagate to drizzle-kit).
    _run("db:reset", ["bun", "run", "db:reset"], codebase)
    _run("db:migrate", ["bun", "run", "db:migrate"], codebase)
    if not args.skip_seed:
        _run("db:seed", ["bun", "run", "db:seed"], codebase)
        _run("db:setup:shared", ["bun", "run", "db:setup:shared"], codebase)

    return 0


if __name__ == "__main__":
    sys.exit(main())
