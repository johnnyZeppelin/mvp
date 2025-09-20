#!/usr/bin/env python3
"""
Minimal Oracle runner: runs lint/type/tests per Charter and updates PUBLIC_APIS.md
and .charter/api_fingerprint.json when freeze gates pass.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

try:
    import yaml  # PyYAML
except ImportError:
    print("[oracle] Missing dependency: PyYAML. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHARTER = ROOT / "project.charter.yaml"

# ------------------------- util -------------------------
def sh(cmd: str, timeout: int | None = None) -> int:
    print(f"\n[oracle] $ {cmd}")
    try:
        proc = subprocess.run(cmd, shell=True, cwd=ROOT, timeout=timeout)
        return proc.returncode
    except subprocess.TimeoutExpired:
        print(f"[oracle] TIMEOUT: {cmd}", file=sys.stderr)
        return 124

def load_charter(path: Path = DEFAULT_CHARTER) -> dict:
    if not path.exists():
        print(f"[oracle] Charter not found: {path}", file=sys.stderr)
        sys.exit(2)
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)

# ------------------ API doc & fingerprint ------------------
def discover_public_apis(src_dir: Path) -> dict:
    """Very lightweight Python API discovery: scan .py and find top-level defs."""
    apis: dict[str, list[str]] = {}
    for py in src_dir.rglob("*.py"):
        rel = py.relative_to(ROOT)
        try:
            text = py.read_text(encoding="utf-8")
        except Exception:
            continue
        module = str(rel).replace(os.sep, ".").removesuffix(".py")
        funcs = []
        for m in re.finditer(r"^def\s+([a-zA-Z_][\w]*)\s*\(([^)]*)\):", text, flags=re.M):
            name = m.group(1)
            sig = m.group(2)
            funcs.append(f"{name}({sig})")
        if funcs:
            apis[module] = sorted(funcs)
    return apis

def write_public_api_doc(apis: dict, out_md: Path):
    out_md.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Public Python APIs\n"]
    for module, funcs in sorted(apis.items()):
        lines.append(f"\n## {module}\n")
        for f in funcs:
            lines.append(f"- `{f}`")
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"[oracle] Wrote {out_md}")

def write_fingerprint(apis: dict, fp_path: Path):
    fp_path.parent.mkdir(parents=True, exist_ok=True)
    fp_path.write_text(json.dumps(apis, indent=2, sort_keys=True), encoding="utf-8")
    print(f"[oracle] Wrote API fingerprint {fp_path}")

# ------------------------- runners -------------------------
def run_step(name: str, cmd: str, timeout: int | None) -> bool:
    rc = sh(cmd, timeout=timeout)
    ok = (rc == 0)
    print(f"[oracle] step={name} => {'OK' if ok else 'FAIL'}")
    return ok

def run_plan(charter: dict, which: list[str] | None = None) -> bool:
    plan = charter.get("oracle_plan", {}).get("steps", [])
    timeouts = charter.get("oracle_plan", {}).get("timeouts", {})
    per_step_timeout = int(timeouts.get("per_step_seconds", 600))

    # map generic step names to concrete commands from runtime.envs
    envs = charter.get("runtime", {}).get("envs", {})
    commands = {}
    for env in envs.values():
        cmds = env.get("commands", {})
        commands |= cmds  # later envs can override

    selected = plan if which is None else which
    fail_fast = charter.get("oracle_plan", {}).get("fail_fast", True)

    all_ok = True
    for step in selected:
        cmd = commands.get(step)
        if not cmd:
            print(f"[oracle] WARN: no command for step '{step}' in charter.runtime.envs.*.commands")
            all_ok = False
            if fail_fast:
                break
            continue
        ok = run_step(step, cmd, per_step_timeout)
        all_ok = all_ok and ok
        if fail_fast and not ok:
            break
    return all_ok

# --------------------- progressive freeze ---------------------
def progressive_freeze(charter: dict) -> None:
    if not charter.get("governance", {}).get("progressive_freeze", False):
        print("[oracle] progressive_freeze disabled in charter")
        return

    src_rel = (charter.get("meta", {}) or {}).get("repo_layout", {}).get("src_dir", "src")
    src_dir = ROOT / src_rel
    apis = discover_public_apis(src_dir)

    gov = charter.get("governance", {})
    api_doc = ROOT / gov.get("public_api_doc", "docs/PUBLIC_APIS.md")
    fp_path = ROOT / gov.get("api_fingerprint_file", ".charter/api_fingerprint.json")

    write_public_api_doc(apis, api_doc)
    write_fingerprint(apis, fp_path)

# ------------------------- main -------------------------
def main():
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--static", action="store_true", help="run lint + typecheck")
    g.add_argument("--dynamic", action="store_true", help="run unit + integration tests")
    g.add_argument("--all", action="store_true", help="run full oracle_plan")
    g.add_argument("--update-apis", action="store_true", help="generate PUBLIC_APIS.md and API fingerprint")
    args = p.parse_args()

    charter = load_charter()

    if args.update_apis:
        progressive_freeze(charter)
        return 0

    if args.static:
        ok = run_plan(charter, ["lint", "typecheck"])
    elif args.dynamic:
        ok = run_plan(charter, ["unit_test", "integration_test"])
    else:  # --all
        ok = run_plan(charter, None)

    gates = charter.get("governance", {}).get("freeze_after", [])
    if args.all and gates:
        print("[oracle] Checking freeze gates …")
        gates_ok = run_plan(charter, gates)
        if gates_ok:
            progressive_freeze(charter)
            print("[oracle] Interfaces frozen (docs + fingerprint updated).")
        else:
            print("[oracle] Freeze skipped: gates not all green.")

    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
