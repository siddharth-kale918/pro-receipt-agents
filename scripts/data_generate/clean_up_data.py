#!/usr/bin/env python3
"""
Reset the pro-receipt database: drop → recreate → migrate.

Steps:
  1. Terminate active connections and DROP DATABASE {target}
  2. CREATE DATABASE {target}
  3. Run `bun run db:migrate` in PRO_RECEIPT_CODEBASE_PATH

Default connection config (override via .env.prime or env vars):
    DB_HOST                   = 127.0.0.1
    DB_PORT                   = 5443
    DB_USERNAME               = pro-receipts
    DB_PASSWORD               = pro-receipts
    DB_DATABASE               = receipts_local
    DB_SSL                    = false
    PRO_RECEIPT_CODEBASE_PATH  (required for migration step)

.env.prime is always copied to <PRO_RECEIPT_CODEBASE_PATH>/.env before migration runs.

Usage:
    python clean_up_data.py
    python clean_up_data.py --yes           # skip confirmation prompt
    python clean_up_data.py --skip-migrate  # drop + recreate only, no migration
    python clean_up_data.py --db my_db      # target a different database name
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

_ROOT = Path(__file__).resolve().parent
_DATA_DIR = _ROOT / "data"
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset pro-receipt database")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    parser.add_argument("--skip-migrate", action="store_true", help="Drop + recreate only, no migration")
    parser.add_argument("--db", default="", help="Target database name (default: DB_DATABASE from env)")
    args = parser.parse_args()

    host = _cfg("DB_HOST", "127.0.0.1")
    port = int(_cfg("DB_PORT", "5443"))
    user = _cfg("DB_USERNAME", "pro-receipts")
    password = _cfg("DB_PASSWORD", "pro-receipts")
    target_db = args.db or _cfg("DB_DATABASE", "receipts_local")
    codebase = _cfg("PRO_RECEIPT_CODEBASE_PATH")

    print(f"  Database: {host}:{port}/{target_db} (user={user})")

    if not args.yes:
        ans = input(f"  Drop and recreate '{target_db}'? This is destructive. [y/N] ").strip().lower()
        if ans not in ("y", "yes"):
            print("  Aborted.")
            return 0

    conn = psycopg2.connect(host=host, port=port, user=user, password=password, dbname="postgres")
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()

    cur.execute(
        sql.SQL(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()"
        ),
        [target_db],
    )
    cur.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(target_db)))
    print(f"  Dropped '{target_db}'.")

    cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target_db)))
    print(f"  Created '{target_db}'.")
    cur.close()
    conn.close()

    if args.skip_migrate:
        print("  Skipping migration (--skip-migrate).")
        return 0

    if not codebase:
        print("  WARNING: PRO_RECEIPT_CODEBASE_PATH not set — skipping migration.", file=sys.stderr)
        return 0

    _sync_prime(codebase)

    print("  Running db:migrate …")
    result = subprocess.run(["bun", "run", "db:migrate"], cwd=codebase)
    if result.returncode != 0:
        print(f"  db:migrate failed (exit {result.returncode}).", file=sys.stderr)
        return result.returncode

    print("  db:migrate complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
