# Demo backup storyboard

Use this if the live demo cannot run. Every screenshot was captured from the real web app running
the two demo cases (`dev/case_036`, `dev/case_040`) with the offline stub model, following
[DEMO_SCRIPT.md](../DEMO_SCRIPT.md).

## 1. MRI request: the agent stops for one human approval

After fetching the chart, checking every criterion, asking the clinic for the missing red-flag
screening and re-checking, the agent has drafted the letter and waits. The letter is shown exactly
as it will be sent; approving binds the reviewer's name to this text.

![MRI approval needed](01_mri_approval_needed.jpg)

## 2. Evidence for every criterion, and the agent's own timeline

Each criterion cites a sentence copied word for word from the chart, with its source document.
Red-flag screening (2.2) is supported by `doc_05_progress_addendum`, the document the clinic sent
after the agent asked. The timeline shows the decision path: 2.2 not met, request to the clinic,
addendum received, all criteria met.

![Evidence and timeline](02_mri_evidence_and_timeline.jpg)

## 3. Approved

After Sara approves, the agent submits and checks the status: approved by the payer, 7 tool calls,
1 request to the clinic.

![MRI approved](03_mri_approved.jpg)

## 4. Biologic request: denied, appeal drafted

The DAS28 score exists only in a flowsheet, which the payer's first-level review does not accept.
The request is denied with reason code DAS28-SCORE. The agent drafts an appeal that answers that
code with the flowsheet quote, and waits for a person to approve the appeal too.

![Denied, appeal drafted](04_biologic_denied_appeal_drafted.jpg)

## 5. Approved on appeal

![Approved on appeal](05_biologic_approved_on_appeal.jpg)

## 6. When records conflict, the agent escalates instead of guessing

The escalation queue lists every case waiting for a person. `dev_002` has contradictory
methotrexate records, so the agent abstained and escalated with a summary.

![Escalation queue](06_escalation_queue.jpg)

## 7. Measured like a product

The Results page shows the full evaluation: agent vs baselines and ablations with confidence
intervals, robustness, fault injection and the regression check. These numbers come from the
offline stub model and are labeled as such.

![Results](07_results.jpg)
