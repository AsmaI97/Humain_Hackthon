---
description: AuthPilot project rules
alwaysApply: true
---

You are helping build AuthPilot, a hackathon project: an autonomous prior authorization agent.
It is judged on: accuracy on unseen test cases, robustness to changed inputs, systematic
evaluation with ablations and regression checks, technical judgment, engineering quality, and
clear communication.

Hard rules
- Synthetic data only. Never use or invent real patient data.
- Python 3.11, FastAPI, Pydantic v2, pytest, SQLite. Pinned versions in requirements.txt.
- Every LLM output that drives a decision must be validated against a Pydantic schema.
- No fabricated clinical facts: every "criterion met" claim needs an evidence span that is a
  verbatim substring of the chart. This is checked in code, not by the model.
- Models come from environment variables (AGENT_MODEL, CHEAP_MODEL, ESCALATION_MODEL).
- All randomness is seeded. Evaluation must be reproducible with one command.
- Every tool call, decision and error is written to the audit log.
- Keep it simple and inspectable. No agent frameworks. Prefer small functions and clear names.
- Write tests for each tool. Do not move to the next phase while tests fail.
- Ask before adding a dependency that is not in the spec.
