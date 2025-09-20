#!/usr/bin/env python3
"""
Orchestrator: plan → scaffold → LLM impl (bounded retries) → tests → freeze.
Uses an OpenAI-compatible provider (e.g., vLLM with Qwen2.5-Coder-32B-Instruct).

Env:
  OPENAI_API_BASE, OPENAI_API_KEY, MODEL_NAME
  LLM_MAX_RETRIES (optional, default 2)
"""
from __future__ import annotations
import os, re, json, subprocess
from pathlib import Path
from typing import Tuple, Optional

import yaml
from providers.base import Message
from providers.openai_like import OpenAICompatible

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "planner_out" / "tasks.json"

llm = OpenAICompatible()
MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))

# ----------------- helpers -----------------
def sh(cmd: str) -> int:
    print(f"[orchestrator] $ {cmd}")
    return subprocess.run(cmd, shell=True, cwd=ROOT).returncode

def sh_capture(cmd: str) -> Tuple[int, str]:
    print(f"[orchestrator] $ {cmd}")
    p = subprocess.run(cmd, shell=True, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return p.returncode, p.stdout

def _load_charter() -> dict:
    return yaml.safe_load((ROOT / "project.charter.yaml").read_text(encoding="utf-8"))

def _src_dir(ch: dict) -> Path:
    rl = (ch.get("meta", {}) or {}).get("repo_layout", {})
    return ROOT / rl.get("src_dir", "src")

# ----------------- prompt & parsing -----------------
def render_prompt(charter_text: str, module_path: str, repo_summary: str, mode: str, failure_trace: Optional[str] = None) -> list[Message]:
    sys_msg = Message("system",
        "You are a contract-first software engineer. Obey the Charter strictly. "
        "Prefer minimal, type-safe, testable code. Modify ONLY the target module unless instructed.")
    extra = (f"\n\nPrevious attempt failed. Here is the failure trace:\n```\n{failure_trace}\n```\nFix the root cause." if failure_trace else "")
    user_msg = Message("user", f"""\
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
```""")
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
            ch = _load_charter()
            srcdir = _src_dir(ch)
            charter_text = (ROOT / "project.charter.yaml").read_text(encoding="utf-8")
            repo_files = "\n".join(str(p.relative_to(ROOT)) for p in srcdir.rglob("*.py"))
            mode = t.get("detail", {}).get("mode", "template")

            failure_trace = None
            for attempt in range(1, MAX_RETRIES + 2):  # bounded
                msgs = render_prompt(charter_text, target, f"Files present:\n{repo_files}", mode, failure_trace)
                llm_output = llm.complete(msgs, temperature=0.2, max_tokens=3000)

                # Save raw output for debugging
                (ROOT / ".charter").mkdir(exist_ok=True, parents=True)
                (ROOT / ".charter" / f"llm_{target.replace('.', '_')}_attempt{attempt}.md").write_text(llm_output, encoding="utf-8")

                content = extract_code_block(target, llm_output)
                if not content:
                    print("[orchestrator] LLM did not return a valid code block; aborting impl step.")
                    return 1

                out_path = srcdir / (Path(target.replace(".", "/") + ".py"))
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(content, encoding="utf-8")
                print(f"[orchestrator] wrote {out_path.relative_to(ROOT)} (attempt {attempt})")

                rc, out = sh_capture("python tools/oracle.py --dynamic")
                if rc == 0:
                    print("[orchestrator] Tests passed.")
                    break
                else:
                    print("[orchestrator] Tests failed; preparing retry…" if attempt < (MAX_RETRIES + 1) else "[orchestrator] Final attempt failed.")
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
