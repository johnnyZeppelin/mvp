#!/usr/bin/env python3
"""
Compile a task DAG from the Charter and write planner_out/tasks.json.
Distinguishes 'template' vs 'creative' by a simple heuristic.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict, field
from pathlib import Path
import json
import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "project.charter.yaml"
OUT = ROOT / "planner_out/tasks.json"

@dataclass
class Task:
    id: str
    kind: str              # scaffold|impl|test|doc|freeze
    target: str            # module or file path
    deps: list[str] = field(default_factory=list)
    detail: dict = field(default_factory=dict)

def _load_charter() -> dict:
    return yaml.safe_load(CHARTER.read_text(encoding="utf-8"))

def _compile_tasks(ch: dict) -> list[Task]:
    tasks: list[Task] = []
    tasks.append(Task(id="layout:ensure", kind="scaffold", target="layout"))

    apis = (ch.get("interfaces", {}) or {}).get("apis", {})
    for api_name, cfg in apis.items():
        module = cfg.get("module")
        if not module:
            continue
        mode = "creative" if "novel" in json.dumps(cfg).lower() else "template"
        impl = Task(id=f"impl:{api_name}", kind="impl", target=module, deps=["layout:ensure"], detail={"mode": mode})
        tests = Task(id=f"test:{api_name}", kind="test", target=module, deps=[impl.id], detail={"types": ["unit", "property"]})
        tasks.extend([impl, tests])

    gates = (ch.get("governance", {}) or {}).get("freeze_after", [])
    tasks.append(Task(id="freeze:checkpoint", kind="freeze", target="apis", deps=[t.id for t in tasks if t.kind=="test"], detail={"gates": gates}))
    return tasks

def main():
    ch = _load_charter()
    tasks = _compile_tasks(ch)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps([asdict(t) for t in tasks], indent=2), encoding="utf-8")
    print(f"[planner] wrote {OUT.relative_to(ROOT)} with {len(tasks)} tasks")

if __name__ == "__main__":
    main()
