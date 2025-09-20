#!/usr/bin/env bash
set -euo pipefail

# ---------- CONFIG ----------
export MODEL_NAME="${MODEL_NAME:-Qwen/Qwen2.5-Coder-32B-Instruct}"
export OPENAI_API_BASE="${OPENAI_API_BASE:-http://localhost:8000/v1}"
export OPENAI_API_KEY="${OPENAI_API_KEY:-sk-local-placeholder}"
export LLM_MAX_RETRIES="${LLM_MAX_RETRIES:-2}"

# If you want this script to also launch vLLM locally, set START_VLLM=1
export START_VLLM="${START_VLLM:-0}"
export VLLM_PORT="${VLLM_PORT:-8000}"

# ---------- CHECK PYTHON & TOOLS ----------
python -c "import sys; assert sys.version_info[:2] >= (3,10)" || {
  echo "Python >=3.10 required"; exit 1; }

pip install -U pip
pip install pyyaml ruff mypy pytest hypothesis || true

# ---------- (Optional) START vLLM LOCALLY ----------
if [[ "$START_VLLM" == "1" ]]; then
  python -c "import importlib; assert importlib.util.find_spec('vllm'), 'Install vLLM first: pip install vllm>=0.6.0'" || exit 1
  if ! ss -ltn | grep -q ":${VLLM_PORT}"; then
    echo "[boot] starting vLLM on port ${VLLM_PORT} ..."
    nohup python -m vllm.entrypoints.openai.api_server \
      --model "${MODEL_NAME}" \
      --dtype bfloat16 \
      --max-model-len 32768 \
      --port "${VLLM_PORT}" \
      > .vllm_stdout.log 2>&1 &
    # Wait for server to accept connections
    echo -n "[boot] waiting for vLLM to be ready"
    for i in {1..30}; do
      sleep 2
      if curl -s "${OPENAI_API_BASE}/models" >/dev/null; then
        echo " OK"
        break
      else
        echo -n "."
      fi
      if [[ $i -eq 30 ]]; then
        echo " timeout waiting for vLLM"; exit 1
      fi
    done
  else
    echo "[boot] vLLM port ${VLLM_PORT} already in use; assuming server is up."
  fi
fi

# ---------- SCAFFOLD → PLAN → RUN ----------
echo "[run] scaffolding..."
python tools/scaffold.py --init
python tools/scaffold.py --from-charter

echo "[run] planning..."
python planner/planner.py

echo "[run] orchestrating (LLM impl + tests + freeze)..."
python tools/orchestrator.py --run

# ---------- PREDICTED RESULTS ----------
echo
echo "[done] If tests passed, you should now see:"
echo " - Generated/updated implementation files under \$(yq '.meta.repo_layout.src_dir' project.charter.yaml)"
echo " - Test results printed above by the Oracle"
echo " - API docs: docs/PUBLIC_APIS.md"
echo " - API fingerprint: .charter/api_fingerprint.json"
echo " - LLM attempt logs: .charter/llm_*_attempt*.md"


# ----------- ONE MORE THING ------------
## Usage examples:
### If you already run vLLM elsewhere (recommended):
# bash```
# chmod +x run_qwen_mvp.sh
# ./run_qwen_mvp.sh
# ```
### If you want the script to spin up vLLM locally too (same box):
# bash```
# pip install "vllm>=0.6.0"
# START_VLLM=1 ./run_qwen_mvp.sh
# ```
## What you will see:
# What you’ll see:

## Terminal-only logs; no browser required.

## On success: code written to src/..., tests pass, then PUBLIC_APIS.md and the API fingerprint are generated (progressive freeze).

## On failure: the orchestrator retries up to LLM_MAX_RETRIES, feeding pytest traces back to Qwen. Raw LLM outputs are saved in .charter/ for inspection.
# --------- END ONE MORE THING ----------
