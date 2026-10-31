"""Command line entry point.

  python -m authpilot.cli run dev/case_005             run until done or the approval gate
  python -m authpilot.cli run dev/case_005 --approve   approve letters as a simulated reviewer
  python -m authpilot.cli approve dev_005 --by "Sara"  approve the waiting letter and continue
  python -m authpilot.cli resume dev_005               continue a queued case

Across separate processes, use a running payer (make payer, PAYER_URL=http://127.0.0.1:8100);
the in-process payer forgets submissions when the process exits.
"""

import argparse
import json

from authpilot import audit, config, ehr, gate
from authpilot.agent import auto_approver, resume_case, run_case


def _short(value, limit: int = 160) -> str:
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def format_event(event: dict) -> str | None:
    p, kind = event["payload"], event["event_type"]
    ts = event["ts"][11:23]
    if kind == "tool_call":
        return f"{ts}  CALL    {p['tool']}({_short(p.get('args', {}), 100)})"
    if kind == "tool_result":
        body = {k: v for k, v in p.items() if k not in ("tool", "letter", "message")}
        return f"{ts}  RESULT  {p['tool']}: {_short(body)}"
    if kind == "llm_call":
        tokens = f"{p.get('input_tokens', 0)}/{p.get('output_tokens', 0)} tok"
        served = p.get("served_by", p["model"])
        return f"{ts}  LLM     {p['purpose']} model={served} source={p['source']} {p['latency_ms']}ms {tokens}"
    if kind == "decision":
        if p.get("event") == "step":
            return f"{ts}  STEP {p['step']:>2} {p['tool']} -> status={p['status_after']}"
        if "criterion_id" in p:
            quotes = [e["span_text"] for e in p.get("evidence", [])]
            return f"{ts}  VERDICT {p['criterion_id']} = {p['status']} ({p['confidence']}) evidence={_short(quotes, 120)}"
        return f"{ts}  EVENT   {p.get('event')}: {_short({k: v for k, v in p.items() if k != 'event'})}"
    if kind == "error":
        return f"{ts}  ERROR   {_short(p)}"
    return f"{ts}  {kind.upper():7s} {_short(p)}"


def print_timeline(case_id: str, run_id: str) -> None:
    for event in audit.read_events(case_id, run_id=run_id):
        line = format_event(event)
        if line:
            print(line)


def print_outcome(state, quiet: bool, case_id: str, run_ids: list[str]) -> None:
    if not quiet:
        for run_id in run_ids:
            print(f"=== audit log: case {case_id}, run {run_id}, LLM_MODE={config.LLM_MODE} ===")
            print_timeline(case_id, run_id)
        if state.info_requests:
            print("\n=== message to clinic ===")
            print(state.info_requests[-1].message)
        if state.letter:
            print("\n=== medical-necessity letter ===")
            print(state.letter)
        if state.letter_ar:
            print("\n=== medical-necessity letter (Arabic) ===")
            print(state.letter_ar)
        if state.appeal_letter:
            print("\n=== appeal letter ===")
            print(state.appeal_letter)
        if state.appeal_letter_ar:
            print("\n=== appeal letter (Arabic) ===")
            print(state.appeal_letter_ar)
    print("\n=== state ===")
    print(f"status: {state.status.value}")
    print(f"tool calls: {state.loop_counts.tool_calls}, gap loops: {state.loop_counts.gap_loops}, "
          f"appeals: {state.loop_counts.appeals}")
    if gate.awaiting_approval(state):
        print(f"waiting for human approval of the {gate.awaiting_approval(state)} letter: "
              f"python -m authpilot.cli approve {case_id} --by <name>")
    if state.approval:
        print(f"approved by: {state.approval.reviewer} ({state.approval.kind})")
    if state.submissions:
        print(f"submissions: {', '.join(state.submissions)} payer_status={state.payer_status}")
    if state.denial_reason:
        print(f"last denial: {state.denial_reason}")
    if state.escalation_reason:
        print(f"escalated: {state.escalation_reason}")
    if state.queued_reason:
        print(f"queued: {state.queued_reason}")


def cmd_run(args: argparse.Namespace) -> None:
    split, case_name = args.case.split("/")
    order, _, label = ehr.load_case_files(split, case_name)
    approver = auto_approver(args.reviewer) if args.approve else None
    state, run_id = run_case(label.case_id, order, approver=approver)
    print_outcome(state, args.quiet, label.case_id, [run_id])
    print(f"label: expected_outcome={label.expected_outcome} expected_final={label.expected_final} ({label.notes})")


def cmd_approve(args: argparse.Namespace) -> None:
    gate.approve(args.case_id, args.by)
    state, run_id = resume_case(args.case_id)
    print_outcome(state, args.quiet, args.case_id, [run_id])


def cmd_resume(args: argparse.Namespace) -> None:
    state, run_id = resume_case(args.case_id)
    print_outcome(state, args.quiet, args.case_id, [run_id])


def main() -> None:
    parser = argparse.ArgumentParser(prog="authpilot")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run one case until it finishes or needs a human")
    run.add_argument("case", help="split/case_name, e.g. dev/case_005")
    run.add_argument("--approve", action="store_true", help="approve letters automatically as --reviewer")
    run.add_argument("--reviewer", default="cli-reviewer")
    run.add_argument("--quiet", action="store_true")
    run.set_defaults(func=cmd_run)
    approve = sub.add_parser("approve", help="approve the waiting letter of a case and continue it")
    approve.add_argument("case_id")
    approve.add_argument("--by", required=True)
    approve.add_argument("--quiet", action="store_true")
    approve.set_defaults(func=cmd_approve)
    resume = sub.add_parser("resume", help="continue a paused or queued case")
    resume.add_argument("case_id")
    resume.add_argument("--quiet", action="store_true")
    resume.set_defaults(func=cmd_resume)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
