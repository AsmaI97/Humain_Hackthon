# AuthPilot demo script (5 minutes)

The demo uses the web app. Run it yourself in live mode with `LLM_MODE=live make dashboard`,
then Workbench, **Run agent**.

| Scenario | Case | Expect |
| --- | --- | --- |
| All criteria met | `case_035` | Letter, then you approve, then the payer approves |
| Missing criteria | `case_038` | The agent asks the clinic, then waits for your approval |
| Denied, then appeal | `case_040` | First submission denied, appeal letter, approve it, approved on appeal |
| Contradictory records | `case_002` | Escalates. Open the queue. |
| Ambiguous, clinic cannot help | `case_034` | Escalates |
| Irrelevant extra note | `case_043` | Still approved |
| Unseen procedure | `unseen/case_000` (CLI only) | Escalates instead of inventing criteria |

The timed walkthrough below uses the missing-document MRI and the denial. `case_036` is another
missing-document MRI. On the recorded live run it escalated after the clinic replied, because
red-flag screening stayed unclear. Use `case_038` when you want the missing-document case to
reach the approval button.

## Before going on stage (10 minutes earlier)

1. `make check` passes (tests, demo, quick metrics).
2. Choose the model mode. The scripted story (case 036 reaches Approve, then case 040 deny and appeal) is the stub:
   - `export LLM_MODE=stub`. An unset mode is replay, not stub. Say so if asked; never present stub numbers as Claude's.
   - Replay (`export LLM_MODE=replay`) only after `make record-demo`. On the current live cache, case 040 matches this script (denied, appealed, approved). Case 036 asks the clinic and then escalates, because red-flag screening stays unclear. Use stub when you need the approval click on case 036.
3. Start from a clean runtime so the cases run fresh: `rm -rf runtime`.
4. Pre-run one escalated case so the queue is not empty:
   `python -m authpilot.cli run dev/case_002 --quiet` (contradictory methotrexate records, escalates).
5. Start the app: `make dashboard`, open http://localhost:8501, zoom the browser to 110%.
   If you changed any code since starting it, stop and restart the app; a running Streamlit
   server can keep old modules in memory.
6. Keep open in other tabs: the backup storyboard (`docs/demo_backup/README.md`) and the slides
   (`docs/slides.html`).

## Timeline

| Time | Screen | Do | Say |
| --- | --- | --- | --- |
| 0:00 | Home, hero | Nothing | "Prior authorization takes clinic staff about 45 minutes per request, an estimate we are validating, and every denial restarts it. AuthPilot is one agent that owns the whole process and stops for exactly one human click." |
| 0:30 | Home, challenge cards | Scroll to "The challenge" | "It covers all three example use cases: it reviews the chart against the policy like a contract, chases missing documents like onboarding, and writes and follows up letters like sales development." |
| 1:00 | Workbench | Sidebar: Dev case `case_036`, press **Run agent** | "A lumbar MRI order. The agent fetches the chart and checks every policy criterion." |
| 1:20 | Workbench, criteria and timeline | Scroll to the timeline: 2.2 not met, step 3 request_missing_info with `new_documents: doc_05_progress_addendum`, then 2.2 met; the 2.2 card cites the addendum | "Red-flag screening was missing, so it asked the clinic, got the addendum and checked again. Nobody told it to; it decided from the case state." |
| 1:50 | Workbench, approval panel | Point at a quote and its `source:` line | "Every 'met' cites text copied word for word from the chart, and code checks that. If the model invents a quote, the claim is dropped." |
| 2:10 | Workbench, approval panel | Type `Sara`, press **Approve and submit** | "This is the only human step. The approval is bound to this exact letter; change one character and it is void." |
| 2:30 | Workbench | Status shows approved, payer approved | "Submitted and approved." |
| 2:40 | Workbench | Dev case `case_040`, **Run agent**, approve as `Sara` | "Now a biologic drug. The DAS28 score lives only in a flowsheet." |
| 3:00 | Workbench | Banner: denied with DAS28-SCORE; approval panel shows the appeal letter | "The payer's first-level review ignores flowsheets, so it is denied. The agent writes an appeal that answers that exact reason code, with the flowsheet quote." |
| 3:20 | Workbench | Approve the appeal | "A person approves the appeal too. Approved on appeal." |
| 3:35 | Escalation queue | Open `dev_002` | "When records contradict each other, it does not guess. It escalates with a summary of what is unclear." |
| 4:00 | Results | Expand "Full evaluation" | "We measure it like a product: baselines, ablations, perturbations, an unseen procedure and fault injection, with confidence intervals and a regression check. Removing the evidence loop costs 17 points of final accuracy; every injected fault ended safely." |
| 4:30 | Workbench in Arabic | Sidebar: switch the language to **العربية**, open `dev_040`, scroll to the letter tabs | "It also works in Arabic. Every letter comes with an Arabic version, written by code around the same verbatim quotes, and the approval covers both." |
| 4:45 | Home, future enhancements | Switch back to English, scroll | "Next: a pilot with one clinic on de-identified data, and FHIR and NPHIES integration behind the same approval gate." |
| 5:00 | | | "Thank you." |

If numbers come from the stub, add at 4:00: "These numbers are from our offline test model; the
pipeline is ready for the Claude run, and the sealed test set is held back for the final measurement."

## If something goes wrong

| Problem | Fallback |
| --- | --- |
| Claude API slow or down | Restart with `LLM_MODE=replay` if that case is in the cache, or `LLM_MODE=stub`. |
| Web app error | Terminal: `python -m authpilot.cli run dev/case_040 --approve` prints the full audit log, the letters and the final state. |
| Laptop or projector problem | Walk through `docs/demo_backup/README.md` (screenshots of every step), then the slides. |
| A case behaves differently than rehearsed | Say what the agent did and why from the timeline; open the escalation queue if it escalated. That is the safety design working. |

## Likely questions

**How do you stop the model from inventing evidence?**
The model only returns a document id and a quote. Code searches the chart for that exact text and
computes the offsets; anything not found is dropped and a "met" without evidence becomes "unclear".
Letter statements are kept only if their quotes are verbatim and every number appears in them.

**Why not an agent framework?**
A plain loop over a typed case state is easier to inspect, test and audit. The model chooses the
next tool; code decides which tools are allowed in each state and enforces caps.

**How do you know it works? Are these numbers real?**
`make eval` runs 60 dev cases three times plus baselines, ablations, perturbations, an unseen
procedure and fault injection, saved with seeds, model and prompt version. Current numbers are from
an offline stub model and are labeled as such; the same command produces Claude numbers with an API
key. A sealed set of 40 cases with wording never seen in development is held back.

**What happens when the payer or the model is down?**
Model errors retry with backoff, then switch to the cheaper model, then park the case in a retry
queue. Payer outages retry, then mark the submission pending; fixed idempotency keys mean a retry
can never submit twice. All 180 injected-fault runs ended in a safe state.

**What if the policy changes?**
Thresholds are read from the policy text. Changing 6 weeks to 8 weeks flipped exactly the 9
affected verdicts and none of the other 21. Reworded policies and a new procedure are part of the
evaluation; they are where a real model must prove itself.

**Is patient data safe?**
Everything here is synthetic. The design includes data minimization, role-based access and
encryption, and a PDPL and HIPAA-style review before any pilot. Every action is in an append-only
audit log.

**Why keep a human in the loop?**
The clinician stays accountable for what is sent to the payer. The agent does the reading, checking,
chasing and drafting; a person approves the exact letter in one click.

**What does it cost per request?**
About 5,000 tokens per case in the current runs; retrieval cuts that by about a third compared with
sending the whole policy.

**Why does the Arabic letter quote the chart in English?**
The chart is in English, and a translated quote could no longer be checked word for word against
it. Code writes the Arabic sentences from fixed templates, so the Arabic version cannot claim
anything the English one does not. The English letter is the one submitted; Arabic clinical notes
are a future step.

**How would it connect to NPHIES?**
Submissions already go through one client with a typed package; mapping that package to the NPHIES
FHIR message format is the integration step, to be confirmed with a health-IT mentor.
