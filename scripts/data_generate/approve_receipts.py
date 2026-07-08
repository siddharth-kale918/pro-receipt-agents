#!/usr/bin/env python3
"""
Approve receipts submitted by submit_receipts.py.

Reads receipt IDs from data/{scenario}_state_submit.json and calls
  POST http://localhost:{API_PORT}/api/v1/entities/{ENTITY_ID}/receipts/{id}/approve

Note: approve calls the PO API to validate and sync received quantities.
      Ensure the PO API (PO_API_BASE_URL in .env.prime) is reachable.

Saves approved receipt IDs to data/{scenario}_state_approve.json.

Usage:
    python approve_receipts.py --scenario s1
    python approve_receipts.py --all
    python approve_receipts.py --scenario s1 --verbose
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests
import yaml

_ROOT = Path(__file__).resolve().parent
_DATA_DIR = _ROOT / "data"
_SCENARIOS_FILE = _DATA_DIR / "scenarios.yml"
_PRIME = _ROOT / ".env.prime"

_DEFAULT_ENTITY_ID = "04eb277c-f9cd-42b0-9610-0f068f6aaea1"
_STUB_TOKEN = "stub-token"


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


def _cfg(key: str, default: str = "") -> str:
    v = os.environ.get(key)
    return str(v).strip() if v and str(v).strip() else default


def _api_base() -> str:
    port = _cfg("API_PORT", "3003")
    entity_id = _cfg("ENTITY_ID", _DEFAULT_ENTITY_ID)
    return f"http://localhost:{port}/api/v1/entities/{entity_id}"


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_STUB_TOKEN}",
        "Content-Type": "application/json",
    }


def _approve_receipt(rid: str, verbose: bool) -> dict:
    url = f"{_api_base()}/receipts/{rid}/approve"
    if verbose:
        print(f"    POST {url}")
    resp = requests.post(url, headers=_headers(), timeout=30)
    if not resp.ok:
        print(f"    APPROVE ERROR {resp.status_code}: {resp.text}", file=sys.stderr)
        sys.exit(1)
    return resp.json()


def _run_scenario(name: str, verbose: bool) -> list[dict]:
    state_file = _DATA_DIR / f"{name}_state_submit.json"
    if not state_file.exists():
        print(f"  No submit state for {name} — run submit_receipts.py first.", file=sys.stderr)
        return []

    receipts = json.loads(state_file.read_text())
    if not receipts:
        print(f"  Scenario {name}: no receipts in submit state — skipping.")
        return []

    print(f"  Approving {len(receipts)} receipt(s) for scenario {name} …")
    approved = []

    for i, entry in enumerate(receipts):
        rid = str(entry["id"])
        rnum = entry.get("receiptNumber", "?")

        data = _approve_receipt(rid, verbose)
        receipt = data.get("data", data)
        status = receipt.get("status", "?")
        print(f"    [{i+1}] Approved receipt #{rnum}  (id={rid}, status={status})")
        approved.append({"id": rid, "receiptNumber": rnum, "status": status})

    state_out = _DATA_DIR / f"{name}_state_approve.json"
    state_out.write_text(json.dumps(approved, indent=2))
    print(f"  State saved → {state_out}")
    return approved


def main() -> int:
    parser = argparse.ArgumentParser(description="Approve receipts")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--scenario", metavar="NAME")
    group.add_argument("--all", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    scenarios = yaml.safe_load(_SCENARIOS_FILE.read_text())

    if args.all:
        for name in scenarios:
            _run_scenario(name, args.verbose)
    else:
        name = args.scenario
        if name not in scenarios:
            print(f"Unknown scenario: {name!r}. Available: {list(scenarios)}", file=sys.stderr)
            return 1
        _run_scenario(name, args.verbose)

    return 0


if __name__ == "__main__":
    sys.exit(main())
