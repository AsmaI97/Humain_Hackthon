# AuthPilot: MVP spec and Cursor prompts

How to use this file
1. Create an empty repo. Save the "Project rules" block below as `.cursor/rules/authpilot.md` (or `AGENTS.md`) so Cursor reads it on every request.
2. Paste the "Kickoff prompt" as your first message.
3. Then paste the phase prompts one at a time. Do not ask Cursor to build everything in one go. Commit after each phase.

---

## Model decision

| Role | Model (API string) | Why |
| --- | --- | --- |
| Main agent (criteria checking, letters, appeals) | `claude-sonnet-5-5` | Strong reasoning and tool use at a speed and cost that allow hundreds of evaluation runs |
| Cheap steps (routing, extraction, formatting) | `claude-haiku-5-5` | Fast and cheap for simple structured tasks, and a fallback if the main model is unavailable |
| Escalation / second opinion on hard cases | `claude-opus-5-5` | Use only where the eval shows the main model fails; keep it optional |

All three are set by environment variables, never hard-coded, so you can compare them on your own sealed test set. That comparison is the real justification for the choice.

---

## Project rules (save as `.cursor/rules/authpilot.md`)

```
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
```

---

## Kickoff prompt (paste first)

```
Build the MVP of AuthPilot in phases. Do NOT start coding yet. First, read this spec, then
reply with: (1) the repo layout you will create, (2) any ambiguities or risks, (3) the plan for
Phase 0. Wait for my approval.

GOAL
An agent that takes a physician's order, reads a synthetic patient chart and a payer policy,
decides whether each policy criterion is met (with cited evidence), requests missing evidence,
drafts a medical-necessity letter, waits for human approval, submits to a mock payer, and
drafts an appeal if denied.

SCOPE
- Two procedures: lumbar spine MRI, and a high-cost biologic drug.
- A third procedure with a differently structured policy exists only as an unseen test of
  adaptation. Do not build features for it.
- Payer policies are short markdown files we write ourselves, split into numbered sections.
- The EHR and payer are simulated.

REPO LAYOUT
authpilot/
  config.py            # env vars, model names, thresholds
  schemas.py           # Pydantic models (see below)
  llm.py               # one wrapper around the Anthropic SDK with record/replay cache
  tools/               # one file per tool, each a pure function with a schema
  agent.py             # the loop
  fallback.py          # fallback policy
  audit.py             # append-only audit log in SQLite
  payer_mock/          # FastAPI mock payer
  data/                # generator, policies/, cases/
  eval/                # harness, metrics, baselines, ablations, perturbations
  app/                 # Streamlit multi-page app: landing page, workbench, queue, results
  tests/
Makefile               # make setup | demo | eval | test
README.md

SCHEMAS (schemas.py)
Order: order_id, patient_id, payer_id, procedure_code, procedure_name, ordering_provider
Evidence: doc_id, span_text, start, end            # span_text must equal chart[doc_id][start:end]
Criterion: id, text, section_ref
CriterionResult: criterion_id, status in {met, not_met, unclear}, evidence: list[Evidence],
                 reasoning (max 2 sentences), confidence 0..1
CaseState: case_id, order, results, gaps, letter, status, loop_counts
Status values: intake, checking, needs_evidence, ready_for_approval, submitted, approved,
               denied, appealing, escalated

LLM WRAPPER (llm.py)
- Single function complete(messages, tools, model, temperature=0) using the Anthropic SDK.
- Record/replay: cache every request/response in a local file keyed by a hash of the request.
  Replay mode makes the demo and tests work offline and makes evaluation cheaper.
- Retries with exponential backoff, a timeout, and token and latency logging.

TOOLS (tools/)
get_patient_record(patient_id)            -> chart documents with ids
search_policy(payer_id, procedure_code, query) -> top policy sections (BM25 over sections)
check_criteria(case_id)                   -> list[CriterionResult], validated in code
request_missing_info(case_id, gaps)       -> creates a task and a message to the clinic (logged)
draft_letter(case_id)                     -> letter where every statement maps to an evidence span
submit_request(case_id)                   -> only callable after human approval
check_status(case_id)                     -> payer status
draft_appeal(case_id, denial_reason)      -> appeal that addresses the denial reason

AGENT LOOP (agent.py)
Plain Python loop with Claude tool use. State lives in CaseState, not in the prompt history.
Caps: max 2 gap loops, max 2 appeals, max 12 tool calls per case.
The loop never calls submit_request without an approval flag set by the human gate.

FALLBACKS (fallback.py)
- Invalid structured output: retry with the validation error, max 2, then escalate.
- Evidence span not found in chart: drop the claim, mark "evidence not found".
- Low confidence or unclear status: abstain and set status escalated with a summary.
- Weak retrieval: widen search, then put the full policy in context, then escalate.
- LLM error or timeout: retry with backoff, then switch to CHEAP_MODEL, then queue the case.
- Payer API down: retry, mark pending, never double submit (idempotency key).
- Loop caps reached: escalate to a human.

MOCK PAYER (payer_mock/)
FastAPI: POST /submit, GET /status/{id}. Deterministic rule-based reviewer that applies the
policy to the submitted package and returns approve or deny with a reason code. One scenario
must be denied on first submission and approved after a correct appeal.

SYNTHETIC DATA (data/)
Seeded generator creates cases from templates. Each case has: chart documents (notes with
varied wording), the order, and a label file with the correct criterion results, planted gaps,
and correct final outcome. 100 cases: 60 dev, 40 sealed test (different seed). Include hard
cases: ambiguous notes, contradictory notes, distractor text, and missing evidence.

EVALUATION (eval/)
- Metrics: per-criterion precision, recall, F1; false-"met" rate; citation validity; gap
  recall; final-decision accuracy; letter faithfulness (every statement traces to a span);
  latency, tokens, tool calls, invalid-output rate.
- Run each case 3 times at temperature 0 and report mean and variance, with confidence
  intervals.
- Baselines: single-prompt baseline; keyword/rule baseline.
- Ablations: no retrieval (full policy in prompt), no citation check, no gap loop, no appeal loop.
- Perturbations: changed policy threshold, reworded policy, noisy chart, removed evidence,
  unseen third procedure.
- Fault injection: payer down, corrupted model output, empty retrieval. Report safe-failure rate.
- Coverage vs accuracy curve across confidence thresholds.
- Results saved per run with seed, model name and prompt version. A regression check fails if
  any score drops against the last saved result.
- Never tune on the sealed test set.

FRONTEND (app/)
A multi-page Streamlit app (st.navigation) with a custom theme (.streamlit/config.toml) and a
small shared style module. Pages:
- Landing page: the hackathon challenge and how AuthPilot fits it, the problem (manual prior
  authorization steps and their cost), the solution (one agent that owns the process, two loops,
  one human gate), how it works, safety and trust, success targets (clearly marked as goals, not
  results), future enhancements, and the full technology stack (what is built vs planned).
- Workbench: start or open a case; status badges and counters; criteria cards colored by
  status with evidence quotes and their source documents; gaps; clinic requests; the letter and
  appeal letter; an approval panel (approve or reject, reviewer name) for the exact letter; a
  visual timeline built from the audit log, with the raw table available.
- Escalation queue: every case waiting for a person (approval, escalation, queued retry), with
  the reason and a button to open it in the workbench.
- Results: the latest saved evaluation runs with their seed, model and prompt version, and a
  banner when the numbers come from the offline stub.
- Language switch (English / Arabic): every page in Arabic, right to left; quotes, sources and the
  English letter stay left to right. Letters get a code-templated Arabic version (stretch goal).
Rules: all dynamic text is HTML-escaped before rendering; only the dev split is offered; the UI
calls the same agent, gate and store functions as the CLI (no logic in the pages).

DEFINITION OF DONE
make demo runs the full flow offline from the replay cache. make eval reproduces the results
table. make test passes.
```

---

## Phase prompts (paste one at a time)

### Phase 0: scaffolding and data
```
Implement Phase 0. Create the repo layout, config.py, schemas.py, audit.py, and the Makefile.
Write the seeded case generator and two policy files (lumbar spine MRI and biologic drug) with
numbered sections. Generate 100 cases (60 dev, 40 sealed with a different seed) with label
files. Add tests that check the generator is deterministic and that every label's evidence span
is a verbatim substring of the chart. Stop and show me one generated case and its labels.
```

### Phase 1: core agent pieces
```
Implement Phase 1. Build llm.py with record/replay, the tools get_patient_record, search_policy
(BM25 over sections) and check_criteria, and the code that validates evidence spans. Use
structured output through a tool schema and Pydantic validation. Add a minimal eval runner that
scores criterion accuracy and citation validity on the dev set, so we measure from now on.
Show me the dev-set numbers and the three worst failures.
```

### Phase 2: end-to-end flow (milestone)
```
Implement Phase 2. Add gap detection, request_missing_info, draft_letter with the
"every statement maps to a span" check, the mock payer service, submit_request and
check_status, and the agent loop with caps. Provide a CLI that runs one case end to end.
Do not add the approval gate or appeals yet. Show me a full run's audit log.
```

### Phase 3: loops, gate and fallbacks
```
Implement Phase 3. Add the human approval gate (submit_request must refuse without approval),
draft_appeal and the denial loop, and fallback.py with every rule listed in the spec. Write
tests that inject each fault (invalid output, missing span, low confidence, empty retrieval,
LLM timeout, payer down) and assert the case ends in a safe state. Show me the test results.
```

### Phase 4: frontend
```
Implement Phase 4. Build the multi-page Streamlit app described under FRONTEND: a landing page
(challenge, problem, solution, how it works, safety, targets, future enhancements, full tech
stack), the workbench (styled criteria cards with evidence quotes, approval panel, visual
timeline from the audit log), the escalation queue and the results page. Use a custom theme and
one shared style module; escape all dynamic text. Keep data shaping in plain functions with unit
tests, and add a headless Streamlit test that runs a case and approves it through the UI.
```

### Phase 5: full evaluation
```
Implement Phase 5. Build the full evaluation: all metrics, 3 runs per case, confidence
intervals, baselines, ablations, perturbations, fault injection, the coverage vs accuracy
curve, saved run results with seeds and model names, and the regression check. Run on the dev
set only and show me the results table. I will tell you when to run the sealed test set.
```

### Phase 6: packaging
```
Implement Phase 6. Write the README (setup, architecture, results, limitations), pin
dependencies, add a Dockerfile, make sure make setup, make demo, make eval and make test work
from a clean clone, and produce a one-page results summary for the slides.
```
