# ---------------------------------------------------------------
# File: planner/controller.py
# Purpose: Read Charter → compile a task DAG → emit actionable steps for the agent.
# For MVP this prints a plan and writes planner_out/tasks.json. Hook it to your orchestrator.

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import json
import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "project.charter.yaml"
OUT = ROOT / "planner_out/tasks.json"

@dataclass
class Task:
    id: str
    kind: str              # scaffold|impl|test|doc|refactor|freeze
    target: str            # module or file path
    deps: list[str] = field(default_factory=list)
    detail: dict = field(default_factory=dict)


def load_charter():
    return yaml.safe_load(CHARTER.read_text(encoding="utf-8"))


def compile_tasks(ch: dict) -> list[Task]:
    tasks: list[Task] = []
    layout = ch.get("meta", {}).get("repo_layout", {})
    src_dir = layout.get("src_dir", "src")

    # 1) Ensure repo layout
    tasks.append(Task(id="layout:ensure", kind="scaffold", target=src_dir))

    # 2) For each API, create impl+tests
    apis = ch.get("interfaces", {}).get("apis", {})
    for api_name, cfg in apis.items():
        module = cfg.get("module")
        if not module:
            continue
        t1 = Task(id=f"impl:{api_name}", kind="impl", target=module,
                  deps=["layout:ensure"], detail={"mode": "template"})
        t2 = Task(id=f"test:{api_name}", kind="test", target=module,
                  deps=[t1.id], detail={"types": ["unit", "property"]})
        tasks.extend([t1, t2])

    # 3) Add freeze checkpoint aligned with Charter gates
    gates = ch.get("governance", {}).get("freeze_after", [])
    tasks.append(Task(id="freeze:checkpoint", kind="freeze", target="apis", detail={"gates": gates}))

    return tasks


def main():
    ch = load_charter()
    tasks = compile_tasks(ch)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps([t.__dict__ for t in tasks], indent=2), encoding="utf-8")
    print(f"[planner] wrote {OUT.relative_to(ROOT)} with {len(tasks)} tasks")

if __name__ == "__main__":
    main()
