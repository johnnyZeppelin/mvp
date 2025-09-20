#!/usr/bin/env python3
"""
Minimal orchestrator to execute planner tasks with our tools.
This does NOT call an LLM yet; it wires scaffold + oracle to validate the loop.

Usage:
  python tools/orchestrator.py --plan           # (re)generate tasks.json
  python tools/orchestrator.py --run            # run tasks sequentially
"""
from __future__ import annotations
import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "planner_out/tasks.json"

def sh(cmd: str) -> int:
    print(f"[orchestrator] $ {cmd}")
    return subprocess.run(cmd, shell=True, cwd=ROOT).returncode

def ensure_plan():
    if not TASKS.exists():
        sh("python planner/planner.py")

def run_tasks():
    data = json.loads(TASKS.read_text(encoding="utf-8"))
    for t in data:
        kind = t["kind"]
        target = t["target"]
        if kind == "scaffold":
            sh("python tools/scaffold.py --init")
            sh("python tools/scaffold.py --from-charter")
        elif kind == "impl":
            # Placeholder: future hook to call an LLM for implementation.
            sh("python tools/scaffold.py --from-charter")
        elif kind == "test":
            rc = sh("python tools/oracle.py --dynamic")
            if rc != 0:
                print(f"[orchestrator] Tests failed for {target}")
                return rc
        elif kind == "freeze":
            sh("python tools/oracle.py --update-apis")
        else:
            print(f"[orchestrator] Unknown task kind: {kind}")
    return 0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--run", action="store_true")
    args = ap.parse_args()

    if args.plan:
        sh("python planner/planner.py")
    if args.run:
        ensure_plan()
        code = run_tasks()
        raise SystemExit(code)

if __name__ == "__main__":
    main()
