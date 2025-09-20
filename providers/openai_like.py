from __future__ import annotations
import os
import json
import urllib.request
from typing import Sequence, Optional
from .base import LLM, Message

class OpenAICompatible(LLM):
    """
    Minimal OpenAI-compatible client (no 3rd-party deps) for local/remote servers.
    Works with vLLM's OpenAI API and many gateways.

    Env vars:
      OPENAI_API_BASE   e.g., http://localhost:8000/v1
      OPENAI_API_KEY    any non-empty string (vLLM ignores, but we must send one)
      MODEL_NAME        e.g., Qwen/Qwen2.5-Coder-32B-Instruct or qwen2.5-coder-32b-instruct
    """
    def __init__(
        self,
        model: Optional[str] = None,
        api_base: Optional[str] = None,
        api_key_env: str = "OPENAI_API_KEY",
    ):
        self.model = model or os.getenv("MODEL_NAME") or "Qwen/Qwen2.5-Coder-32B-Instruct"
        self.api_base = api_base or os.getenv("OPENAI_API_BASE") or "http://localhost:8000/v1"
        self.api_key = os.getenv(api_key_env) or "sk-local-placeholder"

    def complete(self, messages: Sequence[Message], **kwargs) -> str:
        url = f"{self.api_base}/chat/completions"
        body = {
            "model": self.model,
            "messages": [m.__dict__ for m in messages],
            "temperature": kwargs.get("temperature", 0.2),
            "max_tokens": kwargs.get("max_tokens", 2000),
        }
        data = json.dumps(body).encode("utf-8")

        req = urllib.request.Request(url, data=data)
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self.api_key}")

        with urllib.request.urlopen(req, timeout=180) as resp:
            payload = json.loads(resp.read().decode("utf-8"))

        # Basic safety against unexpected responses
        choices = payload.get("choices") or []
        if not choices or "message" not in choices[0] or "content" not in choices[0]["message"]:
            raise RuntimeError(f"OpenAI-compatible response malformed: {payload}")

        return choices[0]["message"]["content"]
