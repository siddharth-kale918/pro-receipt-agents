#!/usr/bin/env python3
"""
Run the full receipt lifecycle for one or all scenarios.

Lifecycle steps (in order):
  stop_receipt   — stop_pro_receipt_api.py     kill running pro-receipt processes/ports
  cleanup        — clean_up_data.py            db:reset:full (drop tables → migrate → seed) --yes auto-confirms
  start_receipt  — start_pro_receipt_api.py    bun build (blocking), then open dev:host terminal
  create         — create_receipts.py          create draft receipts
  submit         — submit_receipts.py          submit receipts (attaches line items then submits)
  approve        — approve_receipts.py         approve receipts

Usage:
    python run_lifecycle.py --list
    python run_lifecycle.py --scenario s1
    python run_lifecycle.py --scenario s1 --from create        # skip stop/cleanup/start/seed
    python run_lifecycle.py --scenario s1 --stop-after submit
    python run_lifecycle.py --scenario s1 --skip-setup
    python run_lifecycle.py --all
    python run_lifecycle.py --all --stop-after submit --verbose
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent
_DATA_DIR = _ROOT / "data"
_SCENARIOS_FILE = _DATA_DIR / "scenarios.yml"
_PRIME = _ROOT / ".env.prime"

_BOLD  = "\033[1m"
_CYAN  = "\033[96m"
_GREEN = "\033[92m"
_RESET = "\033[0m"

# Ordered lifecycle steps: (step_name, script_file, takes_scenario_arg)
_STEPS: list[tuple[str, str, bool]] = [
    ("stop_receipt",  "stop_pro_receipt_api.py",  False),
    ("cleanup",       "clean_up_data.py",          False),
    ("start_receipt", "start_pro_receipt_api.py",  False),
    ("create",        "create_receipts.py",        True),
    ("submit",        "submit_receipts.py",        True),
    ("approve",       "approve_receipts.py",       True),
]

_STEP_NAMES = [s[0] for s in _STEPS]


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


def _sync_prime() -> None:
    if not _PRIME.exists():
        print(f"WARNING: .env.prime not found at {_PRIME} — skipping sync.", file=sys.stderr)
        return
    _load_prime_manual(_PRIME)
    codebase = os.environ.get("PRO_RECEIPT_CODEBASE_PATH", "").strip()
    if not codebase:
        print("WARNING: PRO_RECEIPT_CODEBASE_PATH not set in .env.prime — skipping sync.", file=sys.stderr)
        return
    dest = Path(codebase) / ".env"
    dest.write_bytes(_PRIME.read_bytes())
    print(f"  Synced .env.prime → {dest}\n")


def _git_branch(repo: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(repo), capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else "(unknown)"
    except Exception:
        return "(unknown)"


def _run_step(step_name: str, script: str, scenario: str | None, verbose: bool) -> None:
    script_path = _ROOT / script
    cmd = [sys.executable, str(script_path)]

    # Infrastructure steps that take no scenario arg
    if step_name == "cleanup":
        cmd.append("--yes")
    elif step_name in ("stop_receipt", "start_receipt", "seed"):
        pass  # no extra args
    elif scenario:
        cmd += ["--scenario", scenario]
    else:
        cmd.append("--all")

    if verbose and "--verbose" not in cmd:
        cmd.append("--verbose")

    print(f"\n{_BOLD}{_CYAN}▶ [{step_name}]{_RESET}  {' '.join(cmd)}")
    t0 = time.time()
    result = subprocess.run(cmd)
    elapsed = time.time() - t0

    if result.returncode != 0:
        print(f"\n{_BOLD}FAILED{_RESET}: step '{step_name}' exited {result.returncode}", file=sys.stderr)
        sys.exit(result.returncode)
    print(f"{_GREEN}✓ {step_name}{_RESET}  ({elapsed:.1f}s)")


def _list_scenarios(scenarios: dict) -> None:
    print("\nAvailable scenarios:")
    for name, cfg in scenarios.items():
        print(f"  {name}  — {cfg.get('description', '')}")
    print(f"\nLifecycle steps: {', '.join(_STEP_NAMES)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run full receipt lifecycle")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--scenario", metavar="NAME", help="Run a single scenario")
    group.add_argument("--all", action="store_true", help="Run all scenarios")
    parser.add_argument("--list", action="store_true", help="List scenarios and steps")
    parser.add_argument("--from", dest="from_step", metavar="STEP", choices=_STEP_NAMES,
                        help="Start from this step (skip earlier steps)")
    parser.add_argument("--stop-after", metavar="STEP", choices=_STEP_NAMES,
                        help="Stop after this step")
    parser.add_argument("--skip-setup", action="store_true",
                        help="Skip stop_receipt, cleanup, start_receipt, seed")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    scenarios = yaml.safe_load(_SCENARIOS_FILE.read_text())

    if args.list:
        _list_scenarios(scenarios)
        return 0

    if not args.scenario and not args.all:
        parser.print_help()
        return 1

    if args.scenario and args.scenario not in scenarios:
        print(f"Unknown scenario: {args.scenario!r}. Available: {list(scenarios)}", file=sys.stderr)
        return 1

    _sync_prime()

    # Determine which steps to run
    active_steps = list(_STEPS)

    if args.skip_setup:
        setup = {"stop_receipt", "cleanup", "start_receipt"}
        active_steps = [(n, s, t) for n, s, t in active_steps if n not in setup]

    if args.from_step:
        idx = _STEP_NAMES.index(args.from_step)
        active_steps = [(n, s, t) for n, s, t in active_steps if _STEP_NAMES.index(n) >= idx]

    if args.stop_after:
        idx = _STEP_NAMES.index(args.stop_after)
        active_steps = [(n, s, t) for n, s, t in active_steps if _STEP_NAMES.index(n) <= idx]

    scenario_arg = args.scenario if not args.all else None

    print(f"\n{_BOLD}Receipt lifecycle{_RESET}  scenario={'ALL' if args.all else args.scenario}")
    print(f"Steps: {', '.join(n for n, _, _ in active_steps)}\n")

    for step_name, script, takes_scenario in active_steps:
        sc = scenario_arg if takes_scenario else None
        _run_step(step_name, script, sc, args.verbose)

    print(f"\n{_BOLD}{_GREEN}Lifecycle complete.{_RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
