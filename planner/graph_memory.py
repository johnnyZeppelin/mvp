"""
Lightweight repo graph: modules → imports, function defs (names only).
Uses Python AST; safe (does not import/execute user code).
"""
from __future__ import annotations
import ast
from pathlib import Path
from typing import Dict, List

def build_repo_graph(src_dir: Path) -> Dict[str, dict]:
    graph: Dict[str, dict] = {}
    for py in src_dir.rglob("*.py"):
        try:
            text = py.read_text(encoding="utf-8")
            tree = ast.parse(text)
        except Exception:
            continue
        # best-effort module name relative to src_dir
        try:
            rel = py.relative_to(src_dir).with_suffix("")
            module = ".".join(rel.parts)
        except ValueError:
            # fallback: absolute-ish
            module = ".".join(py.with_suffix("").parts[-3:])

        imports: List[str] = []
        funcs: List[str] = []
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                imports += [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom):
                if n.module:
                    imports.append(n.module)
            elif isinstance(n, ast.FunctionDef) and not n.name.startswith("_"):
                funcs.append(n.name)
        graph[module] = {"imports": sorted(set(imports)), "defs": sorted(funcs)}
    return graph
