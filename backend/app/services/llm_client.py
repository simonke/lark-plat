"""LLM gateway (P4 ADR#1): single stub-first outbound seam.

`LLMClient` is the ONLY place AI capabilities talk to a model. The default stub
`EchoLLMClient` is deterministic and offline, so unit/lock suites never touch a
network. A real provider is an add-only subclass in a later batch.

`complete` returns an `LLMResult`; `embed` returns one vector per input text.
All AI *writes* still go through `exec + approval` (§红线) — this gateway only
produces non-authoritative suggestions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Default embedding width for the offline stub / application-side cosine.
EMBEDDING_DIM = 64


@dataclass
class LLMResult:
    """One completion result (non-authoritative; audit single-exit)."""

    text: str
    model_name: str
    model_version: str | None = None
    usage: dict = field(default_factory=dict)
    raw: dict | None = None


class LLMClient:
    """Gateway interface; implementations must never require network in unit runs."""

    model_name = "base"

    def complete(self, messages: list[dict], *, purpose: str = "generic") -> LLMResult:
        raise NotImplementedError

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class EchoLLMClient(LLMClient):
    """Deterministic offline stub: echoes the last user message / hashes text."""

    model_name = "echo"
    model_version = "stub-1"

    def complete(self, messages: list[dict], *, purpose: str = "generic") -> LLMResult:
        last = ""
        for msg in reversed(list(messages or [])):
            if str(msg.get("role", "")) == "user":
                last = str(msg.get("content", ""))
                break
        if not last and messages:
            last = str(messages[-1].get("content", ""))
        text = f"[suggestion:{purpose}] {last}".strip()
        return LLMResult(
            text=text,
            model_name=self.model_name,
            model_version=self.model_version,
            usage={"prompt_tokens": len(last), "completion_tokens": len(text)},
            raw=None,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(str(t)) for t in (texts or [])]

    @staticmethod
    def _one(text: str) -> list[float]:
        vec = [0.0] * EMBEDDING_DIM
        for idx, ch in enumerate(text):
            vec[idx % EMBEDDING_DIM] += float(ord(ch) % 97) / 97.0
        norm = sum(v * v for v in vec) ** 0.5 or 1.0
        return [v / norm for v in vec]
