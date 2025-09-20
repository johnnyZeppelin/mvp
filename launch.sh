# Spin up an OpenAI-compatible server (vLLM)
# Run this on a GPU machine (A100/80GB recommended for 32B; adjust TP if multi-GPU):
pip install "vllm>=0.6.0"
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-Coder-32B-Instruct \
  --dtype bfloat16 \
  --max-model-len 32768 \
  --port 8000
# Optional flags: --tensor-parallel-size 2 (or more), --gpu-memory-utilization 0.9
# This exposes an OpenAI-compatible endpoint at http://localhost:8000/v1.

# Set environment variables in your shell
export OPENAI_API_BASE="http://localhost:8000/v1"
export OPENAI_API_KEY="sk-local-placeholder"        # vLLM ignores but required
export MODEL_NAME="Qwen/Qwen2.5-Coder-32B-Instruct" # or qwen2.5-coder-32b-instruct

# Install project-side Python deps
# On the machine where you run the scaffolder/orchestrator:
pip install pyyaml ruff mypy pytest
# Optional for property tests:
pip install hypothesis

# Initialize and run the loop
# 1) Create structure and stubs from the Charter
python tools/scaffold.py --init
python tools/scaffold.py --from-charter

# 2) Plan tasks
python planner/planner.py

# 3) Execute (LLM will implement modules during `impl:*`)
python tools/orchestrator.py --run
#--------------------------------------------------------------
# Start vLLM with Qwen on the GPU machine (no browser needed):

pip install "vllm>=0.6.0"
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-Coder-32B-Instruct \
  --dtype bfloat16 \
  --max-model-len 32768 \
  --port 8000

export OPENAI_API_BASE="http://localhost:8000/v1"
export OPENAI_API_KEY="sk-local-placeholder"
export MODEL_NAME="Qwen/Qwen2.5-Coder-32B-Instruct"
export LLM_MAX_RETRIES=2   # optional: change if you want 0/1/2 retries

pip install pyyaml ruff mypy pytest hypothesis
python tools/scaffold.py --init
python tools/scaffold.py --from-charter
python planner/planner.py
python tools/orchestrator.py --run

