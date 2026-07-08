#!/usr/bin/env python3
"""
Create draft receipts via the pro-receipt API.

Reads receipt definitions from data/scenarios.yml, POSTs each one to
  POST http://localhost:{API_PORT}/api/v1/entities/{ENTITY_ID}/receipts

Saves created receipt IDs to data/{scenario}_state_create.json.

Required .env.prime keys:
    ENTITY_ID               — Platform entity UUID (default: 04eb277c-f9cd-42b0-9610-0f068f6aaea1)
    API_PORT                — API port (default: 3003)

Auth: runs in stub mode — any Bearer token is accepted.

Usage:
    python create_receipts.py --scenario s1
    python create_receipts.py --all
    python create_receipts.py --scenario s1 --verbose
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


def _create_receipt(payload: dict, verbose: bool) -> dict:
    url = f"{_api_base()}/receipts"
    if verbose:
        print(f"    POST {url}")
        print(f"    Body: {json.dumps(payload, indent=2)}")
    resp = requests.post(url, json=payload, headers=_headers(), timeout=30)
    if not resp.ok:
        print(f"    ERROR {resp.status_code}: {resp.text}", file=sys.stderr)
        sys.exit(1)
    return resp.json()


def _run_scenario(name: str, scenario: dict, verbose: bool) -> list[dict]:
    receipts_cfg = scenario.get("receipts", [])
    if not receipts_cfg:
        print(f"  Scenario {name}: no receipts defined — skipping.")
        return []

    print(f"  Creating {len(receipts_cfg)} receipt(s) for scenario {name} …")
    created = []

    for i, r in enumerate(receipts_cfg, 1):
        payload = {
            "receiptDate": r.get("receiptDate"),
            "receivedBy": r.get("receivedBy"),
            "receivingDepartment": r.get("receivingDepartment"),
            "referenceNumber": r.get("referenceNumber"),
            "description": r.get("description"),
            "deliveryCode": r.get("deliveryCode"),
            "deliveryCodeId": r.get("deliveryCodeId"),
            "locationName": r.get("locationName"),
            "locationType": r.get("locationType"),
            "addressLine1": r.get("addressLine1"),
            "addressLine2": r.get("addressLine2"),
            "city": r.get("city"),
            "state": r.get("state"),
            "zip": r.get("zip"),
            "countryCode": r.get("countryCode"),
            "vendorDisplayId": r.get("vendorDisplayId", ""),
            "eVendorId": r.get("eVendorId", 0),
            "vendorName": r.get("vendorName", ""),
        }
        # Strip nulls for cleaner payload (server accepts missing optional fields)
        payload = {k: v for k, v in payload.items() if v is not None}

        data = _create_receipt(payload, verbose)
        receipt = data.get("data", data)
        rid = receipt.get("id") or receipt.get("receiptId") or data.get("id")
        rnum = receipt.get("receiptNumber", "?")
        print(f"    [{i}] Created receipt #{rnum}  (id={rid})")
        created.append({"id": rid, "receiptNumber": rnum, "description": r.get("description"), "lineItems": r.get("lineItems", [])})

    state_file = _DATA_DIR / f"{name}_state_create.json"
    state_file.write_text(json.dumps(created, indent=2))
    print(f"  State saved → {state_file}")
    return created


def main() -> int:
    parser = argparse.ArgumentParser(description="Create draft receipts")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--scenario", metavar="NAME")
    group.add_argument("--all", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    scenarios = yaml.safe_load(_SCENARIOS_FILE.read_text())

    if args.all:
        for name, scenario in scenarios.items():
            _run_scenario(name, scenario, args.verbose)
    else:
        name = args.scenario
        if name not in scenarios:
            print(f"Unknown scenario: {name!r}. Available: {list(scenarios)}", file=sys.stderr)
            return 1
        _run_scenario(name, scenarios[name], args.verbose)

    return 0


if __name__ == "__main__":
    sys.exit(main())
