# #!/usr/bin/env python3
# """
# Minimal orchestrator to execute planner tasks with our tools.
# This does NOT call an LLM yet; it wires scaffold + oracle to validate the loop.

# Usage:
#   python tools/orchestrator.py --plan           # (re)generate tasks.json
#   python tools/orchestrator.py --run            # run tasks sequentially
# """
# from __future__ import annotations
# import argparse
# import json
# import subprocess
# from pathlib import Path
# import os, re
# from providers.base import Message
# from providers.openai_like import OpenAICompatible

# ROOT = Path(__file__).resolve().parents[1]
# TASKS = ROOT / "planner_out/tasks.json"

# llm = OpenAICompatible()  # picks env vars set above # uses OPENAI_API_BASE / OPENAI_API_KEY / MODEL_NAME envs
# MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))

# def sh(cmd: str) -> int:
#     print(f"[orchestrator] $ {cmd}")
#     return subprocess.run(cmd, shell=True, cwd=ROOT).returncode

# def ensure_plan():
#     if not TASKS.exists():
#         sh("python planner/planner.py")

# def run_tasks():
#     data = json.loads(TASKS.read_text(encoding="utf-8"))
#     for t in data:
#         kind = t["kind"]
#         target = t["target"]
#         if kind == "scaffold":
#             sh("python tools/scaffold.py --init")
#             sh("python tools/scaffold.py --from-charter")
#         elif kind == "impl":
#             # Placeholder: future hook to call an LLM for implementation.
#             sh("python tools/scaffold.py --from-charter")
#         elif kind == "test":
#             rc = sh("python tools/oracle.py --dynamic")
#             if rc != 0:
#                 print(f"[orchestrator] Tests failed for {target}")
#                 return rc
#         elif kind == "freeze":
#             sh("python tools/oracle.py --update-apis")
#         else:
#             print(f"[orchestrator] Unknown task kind: {kind}")
#     return 0

# def main():
#     ap = argparse.ArgumentParser()
#     ap.add_argument("--plan", action="store_true")
#     ap.add_argument("--run", action="store_true")
#     args = ap.parse_args()

#     if args.plan:
#         sh("python planner/planner.py")
#     if args.run:
#         ensure_plan()
#         code = run_tasks()
#         raise SystemExit(code)

# if __name__ == "__main__":
#     main()



#!/usr/bin/env python3
"""
Orchestrator: plan → scaffold → LLM impl (with bounded retries) → tests → freeze.
Uses an OpenAI-compatible provider (e.g., vLLM with Qwen2.5-Coder-32B-Instruct).

Env:
  OPENAI_API_BASE, OPENAI_API_KEY, MODEL_NAME
  LLM_MAX_RETRIES       (optional, default 2)
"""
from __future__ import annotations
import os, re, json, subprocess
from pathlib import Path
from typing import Tuple, Optional

from providers.base import Message
from providers.openai_like import OpenAICompatible

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "planner_out" / "tasks.json"

# LLM client (reads env for endpoint/model)
llm = OpenAICompatible()
MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))

# ----------------- shell helpers -----------------
def sh(cmd: str) -> int:
    print(f"[orchestrator] $ {cmd}")
    return subprocess.run(cmd, shell=True, cwd=ROOT).returncode

def sh_capture(cmd: str) -> Tuple[int, str]:
    """Run a command and capture stdout+stderr as text."""
    print(f"[orchestrator] $ {cmd}")
    p = subprocess.run(
        cmd, shell=True, cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    return p.returncode, p.stdout

# ----------------- prompt & parsing -----------------
def render_prompt(
    charter_text: str,
    module_path: str,
    repo_summary: str,
    mode: str,
    failure_trace: Optional[str] = None
) -> list[Message]:
    sys_msg = Message(
        "system",
        "You are a contract-first software engineer. Obey the Charter strictly. "
        "Prefer minimal, type-safe, testable code. Modify ONLY the target module unless instructed."
    )
    extra = (
        f"\n\nPrevious attempt failed. Here is the failure trace:\n```\n{failure_trace}\n```\n"
        "Fix the root cause."
        if failure_trace else ""
    )
    user_msg = Message(
        "user",
        f"""\
Charter:
{charter_text}

Task: Implement or update the module `{module_path}` so unit/property tests pass.

Repo summary:
{repo_summary}

Mode: {mode}{extra}

Output requirements:
1) Provide the full updated file content for `{module_path}` only.
2) No extra commentary before or after the code block.
3) Use Python.

Return exactly:
```python
# {module_path}
<file content>
```"""
    )
    return [sys_msg, user_msg]

def extract_code_block(module_path: str, llm_output: str) -> Optional[str]:
    pat = rf"```python\s*#\s*{re.escape(module_path)}\s*(.*?)```"
    m = re.search(pat, llm_output, flags=re.S)
    return m.group(1).lstrip("\n") if m else None

# ----------------- plan/run -----------------
def ensure_plan():
    if not TASKS.exists():
        sh("python planner/planner.py")

def run_tasks() -> int:
    data = json.loads(TASKS.read_text(encoding="utf-8"))
    for t in data:
        kind = t["kind"]
        target = t["target"]

        if kind == "scaffold":
            sh("python tools/scaffold.py --init")
            sh("python tools/scaffold.py --from-charter")

        elif kind == "impl":
            charter_text = (ROOT / "project.charter.yaml").read_text(encoding="utf-8")
            repo_files = "\n".join(str(p.relative_to(ROOT)) for p in (ROOT / "src").rglob("*.py"))
            mode = t.get("detail", {}).get("mode", "template")

            failure_trace = None
            # attempts = 1 + MAX_RETRIES (bounded; no dead loop)
            for attempt in range(1, MAX_RETRIES + 2):
                msgs = render_prompt(
                    charter_text, target, f"Files present:\n{repo_files}", mode, failure_trace
                )
                llm_output = llm.complete(msgs, temperature=0.2, max_tokens=3000)

                # Save raw output for debugging
                (ROOT / ".charter").mkdir(exist_ok=True, parents=True)
                (ROOT / ".charter" / f"llm_{target.replace('.', '_')}_attempt{attempt}.md") \
                    .write_text(llm_output, encoding="utf-8")

                content = extract_code_block(target, llm_output)
                if not content:
                    print("[orchestrator] LLM did not return a valid code block; aborting impl step.")
                    return 1

                out_path = ROOT / "src" / (target.replace(".", "/") + ".py")
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(content, encoding="utf-8")
                print(f"[orchestrator] wrote {out_path.relative_to(ROOT)} (attempt {attempt})")

                # run tests
                rc, out = sh_capture("python tools/oracle.py --dynamic")
                if rc == 0:
                    print("[orchestrator] Tests passed.")
                    break
                else:
                    print(
                        "[orchestrator] Tests failed; preparing retry…"
                        if attempt < (MAX_RETRIES + 1)
                        else "[orchestrator] Final attempt failed."
                    )
                    failure_trace = out
                    if attempt >= (MAX_RETRIES + 1):
                        return rc

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
    import argparse
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
