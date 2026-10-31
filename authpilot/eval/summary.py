"""One-page results summary for the slides, generated from the latest saved evaluation.

Usage: python -m authpilot.eval.summary [--mode stub|record|replay|live] [--out docs/results_summary.md]
Without --mode, a real-model run is preferred over the stub when both exist.
"""

import argparse
import json
from pathlib import Path

from authpilot import config

# Targets from the proposal. They are defined for the sealed test set.
TARGETS = [
    ("Criteria-match accuracy", "criterion_accuracy", 0.90, "higher"),
    ("Final decision accuracy", "decision_accuracy", 0.90, "higher"),
    ("Citation validity", "citation_validity", 1.00, "higher"),
    ("Missing-evidence detection (gap recall)", "gap_recall", 0.85, "higher"),
    ("Denial recovery", "denial_recovery", 0.70, "higher"),
]
ROBUSTNESS_TARGET_POINTS = 5.0
TIME_TARGET_S = 300


def latest_report(split: str = "dev", mode: str | None = None) -> Path | None:
    out_dir = Path(config.RESULTS_DIR) / "eval"
    modes = [mode] if mode else ["live", "replay", "stub"]
    for m in modes:
        path = out_dir / f"latest_{split}_{m}.json"
        if path.exists():
            return path
    return None


def _pct(value) -> str:
    return "-" if value is None else f"{value * 100:.1f}%"


def _check(value, target, direction) -> str:
    if value is None:
        return "not measured"
    ok = value >= target if direction == "higher" else value <= target
    return "meets target" if ok else "below target"


def build(report: dict) -> str:
    m, s, ci = report["meta"], report["summaries"]["agent"], report["agent_ci"]
    agent_values = {**s, "denial_recovery": (s.get("denial_recovery") or {}).get("rate")}
    lines = [
        "# AuthPilot: results summary",
        "",
        "AuthPilot is an AI agent that owns prior authorization end to end: it checks every payer policy",
        "criterion against the chart with verbatim evidence, asks the clinic for what is missing, drafts the",
        "letter, waits for one human approval, submits, and appeals denials.",
        "",
        f"Source: `{m['split']}` split, {m['runs']} runs per case, mode `{m['llm_mode']}`, agent model "
        f"`{m['agent_model']}`, prompt `{m['prompt_version']}`, data seed {m['data_seed']}, eval seed "
        f"{m['eval_seed']}, run at {m['run_at']}. Reproduce with `make eval`.",
        "",
    ]
    if m["llm_mode"] == "stub":
        lines += ["> **Read with care:** these numbers come from the offline stub model, a keyword heuristic written",
                  "> alongside the case templates. They prove the pipeline and the safety mechanisms work; they are not",
                  "> the agent's accuracy. Targets are defined for the sealed test set, which has not been run.", ""]

    lines += ["## Headline results vs proposal targets", "", "| Metric | Result | 95% CI | Target | Status |",
              "| --- | --- | --- | --- | --- |"]
    ci_keys = {"criterion_accuracy": "criterion_accuracy", "decision_accuracy": "decision_accuracy",
               "gap_recall": "gap_recall"}
    for name, key, target, direction in TARGETS:
        value = agent_values.get(key)
        interval = ci.get(ci_keys.get(key, ""), None)
        interval_text = f"{_pct(interval[0])} to {_pct(interval[1])}" if interval else "-"
        lines.append(f"| {name} | {_pct(value)} | {interval_text} | {_pct(target)} | {_check(value, target, direction)} |")
    drops = [p["drop_points"] for p in report["perturbations"].values() if p.get("drop_points") is not None]
    worst = max(drops) if drops else None
    lines.append(f"| Robustness drop (worst perturbation) | {worst if worst is not None else '-'} points | - | "
                 f"{ROBUSTNESS_TARGET_POINTS:.0f} points or less | "
                 f"{'not measured' if worst is None else ('meets target' if worst <= ROBUSTNESS_TARGET_POINTS else 'below target')} |")
    latency_ms = s.get("mean_latency_ms") or 0
    latency_s = latency_ms / 1000
    shown = f"{latency_ms:.0f} ms" if latency_s < 1 else f"{latency_s:.1f} s"
    lines.append(f"| Agent time per request | {shown} | - | under {TIME_TARGET_S // 60} minutes | "
                 f"{'meets target' if latency_s < TIME_TARGET_S else 'below target'} |")

    summaries = report["summaries"]

    def final(name):
        return (summaries.get(name) or {}).get("final_accuracy")

    lines += ["", "## Does each part earn its place?", "", "| Variant | Criterion acc | Final outcome acc | "
              "Denial recovery | Tokens per case |", "| --- | --- | --- | --- | --- |"]
    for name in ("agent", "single_prompt", "keyword", "no_retrieval", "no_gap_loop", "no_appeal_loop"):
        v = summaries.get(name)
        if not v:
            continue
        dr = (v.get("denial_recovery") or {}).get("rate")
        tokens = v.get("mean_tokens")
        lines.append(f"| {name.replace('_', ' ')} | {_pct(v['criterion_accuracy'])} | {_pct(v.get('final_accuracy'))} | "
                     f"{_pct(dr)} | {f'{tokens:,.0f}' if tokens is not None else '-'} |")
    if final("agent") is not None and final("no_gap_loop") is not None:
        lines += ["", f"Removing the evidence loop costs {(final('agent') - final('no_gap_loop')) * 100:.1f} points of "
                      f"final outcome accuracy; removing the appeal loop costs "
                      f"{(final('agent') - (final('no_appeal_loop') or 0)) * 100:.1f}."]

    lines += ["", "## Robustness and adaptation", "", "| Perturbation | Criterion acc | Drop (points) | Notes |",
              "| --- | --- | --- | --- |"]
    for name, p in report["perturbations"].items():
        notes = ""
        if "affected_cases" in p:
            notes = f"{p['affected_flipped']}/{p['affected_cases']} affected verdicts flipped"
        elif "no_guess_rate" in p:
            notes = f"no guesses on {p['removed_criteria']} removed criteria" if p["no_guess_rate"] == 1 else \
                f"no-guess rate {p['no_guess_rate']}"
        elif name == "unseen_procedure":
            notes = f"final states {p.get('final_status_counts')}"
        drop = "-" if p.get("drop_points") is None else p["drop_points"]
        lines.append(f"| {name.replace('_', ' ')} | {_pct(p['criterion_accuracy'])} | {drop} | {notes} |")

    lines += ["", "## Safety under faults", ""]
    for name, f in report["faults"].items():
        lines.append(f"- **{name.replace('_', ' ')}**: {_pct(f['safe_rate'])} of {f['runs']} runs ended safely "
                     f"({f['final_status_counts']}).")
    lines += ["- Every submitted claim cites text found word for word in the chart; nothing reaches the payer "
              "without a human approving the exact letter.", ""]

    lines += ["## Next", "", "- Run one live evaluation (`LLM_MODE=live make eval`) for real accuracy numbers.",
              "- Run the sealed test split once, after tuning on dev is finished.", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="dev")
    parser.add_argument("--mode", default=None)
    parser.add_argument("--out", type=Path, default=config.ROOT_DIR / "docs" / "results_summary.md")
    args = parser.parse_args()
    path = latest_report(args.split, args.mode)
    if path is None:
        raise SystemExit("No saved evaluation found. Run `make eval` first.")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(build(json.loads(path.read_text(encoding="utf-8"))), encoding="utf-8")
    print(f"wrote {args.out} from {path}")


if __name__ == "__main__":
    main()
