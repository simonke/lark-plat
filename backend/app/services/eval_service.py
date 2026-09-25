"""Offline AI evaluation harness (P4 E8).

`run(cases)` executes a deterministic, offline evaluation over `EchoLLMClient`
(no network). A **negative-control** case passes only when the expected pattern is
*absent* from the model output, so the harness itself stays red-able (a hand-wave
"always green" eval is a假绿 the gate must reject).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from app.services.llm_client import EchoLLMClient, LLMClient


@dataclass
class EvalReport:
    """Aggregate result of one offline eval run."""

    total: int = 0
    passed: int = 0
    failed: int = 0
    model_name: str = "echo"
    model_version: str | None = None
    results: list[dict] = field(default_factory=list)

    def ok(self) -> bool:
        return self.failed == 0

    def to_dict(self) -> dict:
        data = asdict(self)
        data["ok"] = self.ok()
        return data


def _contains_case(case: dict) -> bool:
    expected = case.get("expected") or {}
    needle = expected.get("contains")
    if needle is None:
        return True
    return needle in (case.get("_output") or "")


def run(cases: list[dict], *, client: LLMClient | None = None) -> EvalReport:
    """Run `cases` over the stub client and return an `EvalReport`.

    Each case: ``{name, input, expected={contains}, neg_control?}``. A negative
    control passes when the expected pattern is *absent* (proves judging works).
    """
    client = client or EchoLLMClient()
    report = EvalReport(model_name=getattr(client, "model_name", "echo"),
                        model_version=getattr(client, "model_version", None))
    for case in cases or []:
        report.total += 1
        messages = case.get("input") or [{"role": "user", "content": case.get("prompt", "")}]
        result = client.complete(messages, purpose=str(case.get("purpose", "eval")))
        judged = {**case, "_output": result.text}
        matched = _contains_case(judged)
        neg = bool(case.get("neg_control"))
        passed = (not matched) if neg else matched
        report.results.append(
            {"name": case.get("name", f"case-{report.total}"), "neg_control": neg, "passed": passed}
        )
        if passed:
            report.passed += 1
        else:
            report.failed += 1
    return report
