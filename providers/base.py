from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol, Sequence

@dataclass
class Message:
    role: str   # "system" | "user" | "assistant"
    content: str

class LLM(Protocol):
    def complete(self, messages: Sequence[Message], **kwargs) -> str:
        ...
