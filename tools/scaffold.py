#!/usr/bin/env python3
"""
Scaffolder that reads the Project Charter and keeps the repo layout consistent.

Usage:
  python tools/scaffold.py --init                 # create layout + package + cli
  python tools/scaffold.py --from-charter         # stub APIs & tests from Charter
  python tools/scaffold.py --module user_service --kind service
  python tools/scaffold.py --tests-only           # regenerate tests for all APIs
"""
from __future__ import annotations
import argparse
import sys
import textwrap
from pathlib import Path

try:
    import yaml  # PyYAML
except ImportError:
    print("Install PyYAML: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "project.charter.yaml"

# ---------- Charter helpers ----------
def _load_charter() -> dict:
    if CHARTER.exists():
        return yaml.safe_load(CHARTER.read_text(encoding="utf-8")) or {}
    return {}

def _package_name(ch: dict) -> str:
    name = (ch.get("meta", {}) or {}).get("name", "your_project")
    return name.lower().replace("-", "_").replace(" ", "_")

def _layout_paths(ch: dict) -> tuple[Path, Path, Path]:
    repo_layout = (ch.get("meta", {}) or {}).get("repo_layout", {})
    src_dir = ROOT / repo_layout.get("src_dir", "src")
    tests_dir = ROOT / repo_layout.get("test_dir", "tests")
    docs_dir = ROOT / repo_layout.get("docs_dir", "docs")
    return src_dir, tests_dir, docs_dir

# ---------- File templates ----------
PKG_INIT = "# package\n"
CLI_TEMPLATE = textwrap.dedent(
    """
    def main():
        print("{pkg} CLI ready")

    if __name__ == "__main__":
        main()
    """
)
SERVICE_TEMPLATE = textwrap.dedent(
    """
    \"\"\"Service: {name}

    Auto-generated stub from Charter. Replace pass with real logic.\"\"\"

    {functions}
    """
)
FUNCTION_STUB = textwrap.dedent(
    """
    def {fname}{signature}:
        \"\"\"{doc}\"\"\"
        raise NotImplementedError("TODO: implement {fname}")
    """
)
UNIT_TEST_TEMPLATE = textwrap.dedent(
    """
    import pytest

    {imports}

    {tests}
    """
)
UNIT_TEST_CALL = textwrap.dedent(
    """
    def test_{fname}_signature_runs():
        # Smoke test to ensure the function is importable/callable with dummy args.
        {call}
    """
)
PROPERTY_TEST_TEMPLATE = textwrap.dedent(
    """
    import pytest
    try:
        from hypothesis import given, strategies as st
    except Exception:
        pytest.skip("hypothesis not installed")

    @pytest.mark.property
    @pytest.mark.skip(reason="replace with real property invariants")
    @given(st.text())
    def test_placeholder_property(s):
        assert isinstance(s, str)
    """
)

# ---------- Writers ----------
def _ensure_layout(ch: dict) -> tuple[str, Path, Path, Path]:
    src_dir, tests_dir, docs_dir = _layout_paths(ch)
    pkg = _package_name(ch)
    pkg_dir = src_dir / pkg
    for d in [src_dir, tests_dir, docs_dir, ROOT / "tools", ROOT / "planner", ROOT / ".charter",
              pkg_dir, pkg_dir / "services", pkg_dir / "pipelines", pkg_dir / "adapters", pkg_dir / "utils"]:
        d.mkdir(parents=True, exist_ok=True)
    for p in [pkg_dir, pkg_dir / "services", pkg_dir / "pipelines", pkg_dir / "adapters", pkg_dir / "utils"]:
        init = p / "__init__.py"
        if not init.exists():
            init.write_text(PKG_INIT, encoding="utf-8")
    cli_py = pkg_dir / "cli.py"
    if not cli_py.exists():
        cli_py.write_text(CLI_TEMPLATE.format(pkg=pkg), encoding="utf-8")
    return pkg, pkg_dir, src_dir, tests_dir

def _write_service_stub(pkg: str, pkg_dir: Path, module_path: str, functions: list[dict]):
    rel = Path(module_path.replace(".", "/") + ".py")
    py_path = (ROOT / "src" / rel)
    py_path.parent.mkdir(parents=True, exist_ok=True)

    funcs_code = []
    for f in functions:
        fname = f.get("name")
        sig = f.get("signature", "()")
        doc = f.get("description", f"{fname} stub")
        funcs_code.append(FUNCTION_STUB.format(fname=fname, signature=sig, doc=doc))
    body = SERVICE_TEMPLATE.format(name=module_path.split(".")[-1], functions="\n".join(funcs_code) or "pass\n")

    if not py_path.exists():
        py_path.write_text(body, encoding="utf-8")
        print(f"[scaffold] wrote {py_path.relative_to(ROOT)}")
    else:
        print(f"[scaffold] exists {py_path.relative_to(ROOT)} (skipped)")

def _write_tests(tests_dir: Path, module_path: str, functions: list[dict]):
    mod_import = module_path
    imports = f"from {mod_import} import " + ", ".join(f["name"] for f in functions) if functions else f"import {mod_import}"
    tests = []
    for f in functions:
        fname = f["name"]
        sig = f.get("signature", "()").strip()
        dummy_call = f"{fname}()" if sig == "()" else f"# TODO: call {fname}{sig} with dummy args"
        tests.append(UNIT_TEST_CALL.format(fname=fname, call=dummy_call))
    unit_py = tests_dir / f"test_{module_path.split('.')[-1]}_unit.py"
    unit_py.write_text(UNIT_TEST_TEMPLATE.format(imports=imports, tests="\n\n".join(tests) or "def test_import():\n    assert True\n"), encoding="utf-8")
    print(f"[scaffold] wrote {unit_py.relative_to(ROOT)}")

    prop_py = tests_dir / f"test_{module_path.split('.')[-1]}_property.py"
    prop_py.write_text(PROPERTY_TEST_TEMPLATE, encoding="utf-8")
    print(f"[scaffold] wrote {prop_py.relative_to(ROOT)}")

# ---------- Commands ----------
def cmd_init():
    ch = _load_charter()
    _ensure_layout(ch)

def cmd_from_charter():
    ch = _load_charter()
    pkg, pkg_dir, _, tests_dir = _ensure_layout(ch)
    apis = (ch.get("interfaces", {}) or {}).get("apis", {})
    for api_name, cfg in apis.items():
        module = cfg.get("module")
        if not module:
            continue
        fns = []
        for fname, spec in (cfg.get("functions", {}) or {}).items():
            fns.append({
                "name": fname,
                "signature": spec.get("signature", "()"),
                "description": spec.get("description", ""),
            })
        _write_service_stub(pkg, pkg_dir, module, fns)
        _write_tests(tests_dir, module, fns)

def cmd_module(name: str, kind: str):
    ch = _load_charter()
    pkg, pkg_dir, _, tests_dir = _ensure_layout(ch)
    if kind not in {"service", "pipeline", "adapter", "util"}:
        print("kind must be one of: service|pipeline|adapter|util")
        sys.exit(1)
    module = f"{pkg}.{kind}s.{name}"
    _write_service_stub(pkg, pkg_dir, module, [])
    _write_tests(tests_dir, module, [])

def cmd_tests_only():
    ch = _load_charter()
    _, _, _, tests_dir = _ensure_layout(ch)
    apis = (ch.get("interfaces", {}) or {}).get("apis", {})
    for _, cfg in apis.items():
        module = cfg.get("module")
        if module:
            fns = []
            for fname, spec in (cfg.get("functions", {}) or {}).items():
                fns.append({"name": fname, "signature": spec.get("signature", "()"), "description": spec.get("description", "")})
            _write_tests(tests_dir, module, fns)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--from-charter", action="store_true")
    ap.add_argument("--tests-only", action="store_true")
    ap.add_argument("--module", type=str)
    ap.add_argument("--kind", type=str, default="service")
    args = ap.parse_args()

    if args.init:
        cmd_init()
    elif args.from_charter:
        cmd_from_charter()
    elif args.tests_only:
        cmd_tests_only()
    elif args.module:
        cmd_module(args.module, args.kind)
    else:
        ap.print_help()

if __name__ == "__main__":
    main()
