"""Full evaluation: python -m authpilot.eval.run_all --split dev   (make eval)

Runs the agent (several times per case), the baselines, the ablations, the perturbations and the
fault injections; computes every metric with bootstrap confidence intervals and the coverage
curve; saves the run with its seed, models and prompt version; and fails if any tracked score
dropped against the last saved run for the same split, mode and model.

The sealed split is refused unless --allow-sealed is passed. Never tune on it.
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from authpilot import config
from authpilot.eval.guard import dump_report, require_eval_mode
from authpilot.data.generator import SPLITS
from authpilot.eval import baselines, faults, metrics, perturb
from authpilot.eval.harness import load_split, run_agent_cases, settings

VARIANTS = {
    "agent": {},
    "no_retrieval": {"USE_RETRIEVAL": False},
    "no_citation_check": {"VERIFY_CITATIONS": False},
    "no_gap_loop": {"MAX_GAP_LOOPS": 0},
    "no_appeal_loop": {"MAX_APPEALS": 0},
}
COVERAGE_THRESHOLDS = [0.0, 0.3, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95]
HIGHER_IS_BETTER = ["criterion_accuracy", "citation_validity", "gap_recall", "decision_accuracy",
                    "final_accuracy", "letter_faithfulness", "letter_support", "safe_rate"]
LOWER_IS_BETTER = ["false_met_rate", "invalid_output_rate"]


def _agent_variant(name: str, cases: list, runs: int = 1) -> list[dict]:
    with settings(**VARIANTS[name]):
        return run_agent_cases(cases, name, runs)


def _subset(records: list[dict], case_ids: set[str], run: int = 0) -> list[dict]:
    return [r for r in records if r["case_id"] in case_ids and r["run"] == run]


def run_perturbations(split: str, limit: int | None, agent_records: list[dict], log) -> dict:
    out = {}

    def compare(name: str, records: list[dict], extra: dict | None = None) -> None:
        ids = {r["case_id"] for r in records}
        base = _subset(agent_records, ids)
        pert = metrics.summarize(records)
        unpert = metrics.summarize(base) if base else None
        acc, base_acc = pert["criterion_accuracy"], unpert["criterion_accuracy"] if unpert else None
        out[name] = {
            "cases": pert["cases"],
            "criterion_accuracy": acc,
            "unperturbed_criterion_accuracy": base_acc,
            "drop_points": round((base_acc - acc) * 100, 1) if acc is not None and base_acc is not None else None,
            "decision_accuracy": pert["decision_accuracy"],
            "unperturbed_decision_accuracy": unpert["decision_accuracy"] if unpert else None,
            "final_accuracy": pert["final_accuracy"],
            "citation_validity": pert["citation_validity"],
            "false_met_rate": pert["false_met_rate"],
            **(extra or {}),
        }
        log(f"  perturbation {name}: acc {acc} (unperturbed {base_acc})")

    cases, tmp, affected = perturb.threshold(split, limit)
    with perturb.policy_dir(tmp):
        records = run_agent_cases(cases, "threshold")
    perturb.cleanup(tmp)
    base = {r["case_id"]: r for r in _subset(agent_records, {c[2].case_id for c in cases})}
    flipped = sum(r["predicted"].get("2.1") != "met" for r in records if r["case_id"] in affected)
    unaffected = [r for r in records if r["case_id"] not in affected and r["case_id"] in base]
    stable = sum(r["predicted"].get("2.1") == base[r["case_id"]]["predicted"].get("2.1") for r in unaffected)
    compare("threshold_6_to_8_weeks", records, {
        "affected_cases": len(affected), "affected_flipped": flipped,
        "unaffected_cases": len(unaffected), "unaffected_unchanged": stable,
    })

    cases, path = perturb.reworded(split, limit)
    with perturb.policy_dir(path):
        compare("reworded_policy", run_agent_cases(cases, "reworded"))

    compare("noisy_chart", run_agent_cases(perturb.noisy(split, limit), "noisy"))

    cases, removed = perturb.removed_evidence(split, limit)
    records = run_agent_cases(cases, "removed_evidence")
    guessed = sum(r["predicted"].get(key.split(":")[-1]) == "met"
                  for r in records for key in removed if key.startswith(r["case_id"] + ":"))
    compare("removed_evidence", records, {"removed_criteria": len(removed),
                                          "no_guess_rate": round(1 - guessed / len(removed), 4) if removed else None})

    unseen_records = run_agent_cases(perturb.unseen(limit), "unseen")
    s = metrics.summarize(unseen_records)
    out["unseen_procedure"] = {
        "cases": s["cases"], "criterion_accuracy": s["criterion_accuracy"], "unperturbed_criterion_accuracy": None,
        "drop_points": None, "decision_accuracy": s["decision_accuracy"], "unperturbed_decision_accuracy": None,
        "final_accuracy": s["final_accuracy"], "citation_validity": s["citation_validity"],
        "false_met_rate": s["false_met_rate"], "final_status_counts": s["final_status_counts"],
    }
    log(f"  perturbation unseen_procedure: acc {s['criterion_accuracy']}")
    return out


def run_faults(cases: list, log) -> dict:
    out = {}
    for name, fault in faults.FAULTS.items():
        with fault():
            records = run_agent_cases(cases, f"fault_{name}")
        s = metrics.summarize(records)
        out[name] = {"runs": len(records), "safe_rate": s["safe_rate"], "final_accuracy": s["final_accuracy"],
                     "final_status_counts": s["final_status_counts"], "errors": s["errors"]}
        log(f"  fault {name}: safe {s['safe_rate']} {s['final_status_counts']}")
    return out


def _row(name: str, s: dict) -> dict:
    dr = s.get("denial_recovery") or {}
    return {"variant": name, **{k: s.get(k) for k in (
        "criterion_accuracy", "false_met_rate", "citation_validity", "gap_recall", "decision_accuracy",
        "final_accuracy", "letter_faithfulness", "mean_tool_calls", "mean_tokens", "mean_latency_ms",
        "invalid_output_rate")}, "denial_recovery": dr.get("rate")}


def tracked_scores(report: dict) -> dict[str, float]:
    scores = {}
    agent = report["summaries"]["agent"]
    for key in HIGHER_IS_BETTER + LOWER_IS_BETTER:
        if agent.get(key) is not None:
            scores[f"agent.{key}"] = agent[key]
    for name, p in report.get("perturbations", {}).items():
        if p.get("criterion_accuracy") is not None:
            scores[f"perturbation.{name}.criterion_accuracy"] = p["criterion_accuracy"]
    for name, f in report.get("faults", {}).items():
        if f.get("safe_rate") is not None:
            scores[f"fault.{name}.safe_rate"] = f["safe_rate"]
    return scores


def regression_check(new: dict, old: dict | None) -> dict:
    if old is None:
        return {"status": "no baseline", "compared_with": None, "drops": []}
    same = all(new["meta"][k] == old["meta"].get(k) for k in ("split", "llm_mode", "agent_model"))
    if not same:
        return {"status": "no comparable baseline", "compared_with": old["meta"].get("run_at"), "drops": []}
    new_scores, old_scores = tracked_scores(new), tracked_scores(old)
    drops = []
    for key, value in new_scores.items():
        if key not in old_scores:
            continue
        lower_better = key.split(".")[-1] in LOWER_IS_BETTER
        worse = value > old_scores[key] + 1e-9 if lower_better else value < old_scores[key] - 1e-9
        if worse:
            drops.append({"metric": key, "previous": old_scores[key], "now": value})
    return {"status": "regression" if drops else "pass", "compared_with": old["meta"].get("run_at"), "drops": drops}


def _fmt(value, ci=None) -> str:
    if value is None:
        return "-"
    text = f"{value:.3f}" if isinstance(value, float) else str(value)
    return f"{text} [{ci[0]:.3f}, {ci[1]:.3f}]" if ci else text


def to_markdown(report: dict) -> str:
    m = report["meta"]
    lines = [
        f"# AuthPilot evaluation: {m['split']} split",
        "",
        f"Run at {m['run_at']} | mode `{m['llm_mode']}` | agent model `{m['agent_model']}` | "
        f"prompt `{m['prompt_version']}` | data seed {m['data_seed']} | eval seed {m['eval_seed']} | "
        f"{m['runs']} runs per case | {m['duration_s']} s",
        "",
    ]
    if m["llm_mode"] == "stub":
        lines += ["> These numbers come from the offline stub model, a keyword heuristic written alongside the case",
                  "> templates. They show the evaluation pipeline works; they do not measure the agent's accuracy.", ""]
    ci = report["agent_ci"]
    lines += ["## Main results (95% bootstrap confidence intervals for the agent)", "",
              "| Variant | Criterion acc | False-met | Citation validity | Gap recall | Decision acc | Final outcome acc | "
              "Denial recovery | Letter faithfulness | Tool calls | Tokens | Latency ms | Invalid output |",
              "| --- | " + " | ".join(["---"] * 12) + " |"]
    for row in report["table"]:
        is_agent = row["variant"] == "agent"
        lines.append("| " + " | ".join([
            row["variant"],
            _fmt(row["criterion_accuracy"], ci.get("criterion_accuracy") if is_agent else None),
            _fmt(row["false_met_rate"]), _fmt(row["citation_validity"]),
            _fmt(row["gap_recall"], ci.get("gap_recall") if is_agent else None),
            _fmt(row["decision_accuracy"], ci.get("decision_accuracy") if is_agent else None),
            _fmt(row["final_accuracy"], ci.get("final_accuracy") if is_agent else None),
            _fmt(row["denial_recovery"]), _fmt(row["letter_faithfulness"]), _fmt(row["mean_tool_calls"]),
            _fmt(row["mean_tokens"]), _fmt(row["mean_latency_ms"]), _fmt(row["invalid_output_rate"]),
        ]) + " |")
    spread = report["agent_run_spread"]
    lines += ["", f"Agent spread across {spread['criterion_accuracy']['runs']} runs: criterion accuracy std "
              f"{spread['criterion_accuracy']['std']}, final outcome accuracy std {spread['final_accuracy']['std']}.", ""]
    lines += ["## Robustness and adaptation", "",
              "| Perturbation | Cases | Criterion acc | Unperturbed | Drop (points) | Decision acc | Final outcome acc | "
              "Citation validity | Notes |", "| --- | " + " | ".join(["---"] * 8) + " |"]
    for name, p in report["perturbations"].items():
        notes = ""
        if "affected_cases" in p:
            notes = (f"{p['affected_flipped']}/{p['affected_cases']} affected verdicts flipped; "
                     f"{p['unaffected_unchanged']}/{p['unaffected_cases']} unaffected unchanged")
        elif "no_guess_rate" in p:
            notes = f"no-guess rate {p['no_guess_rate']} on {p['removed_criteria']} removed criteria"
        elif "final_status_counts" in p:
            notes = f"final: {p['final_status_counts']}"
        lines.append("| " + " | ".join([name, str(p["cases"]), _fmt(p["criterion_accuracy"]),
                                         _fmt(p["unperturbed_criterion_accuracy"]), _fmt(p["drop_points"]),
                                         _fmt(p["decision_accuracy"]), _fmt(p["final_accuracy"]),
                                         _fmt(p["citation_validity"]), notes]) + " |")
    lines += ["", "## Fault injection", "", "| Fault | Runs | Safe-failure rate | Final outcome acc | Final states |",
              "| --- | --- | --- | --- | --- |"]
    for name, f in report["faults"].items():
        lines.append(f"| {name} | {f['runs']} | {_fmt(f['safe_rate'])} | {_fmt(f['final_accuracy'])} | "
                     f"{f['final_status_counts']} |")
    lines += ["", "## Coverage vs accuracy (agent, initial verdicts)", "",
              "| Confidence threshold | Coverage | Criterion acc on covered | Decision acc on covered |",
              "| --- | --- | --- | --- |"]
    for row in report["coverage_curve"]:
        lines.append(f"| {row['threshold']} | {_fmt(row['coverage'])} | {_fmt(row['criterion_accuracy'])} | "
                     f"{_fmt(row['decision_accuracy'])} |")
    reg = report["regression"]
    lines += ["", f"## Regression check: {reg['status']}", ""]
    if reg["compared_with"]:
        lines.append(f"Compared with the run at {reg['compared_with']}.")
    for drop in reg["drops"]:
        lines.append(f"- {drop['metric']}: {drop['previous']} -> {drop['now']}")
    return "\n".join(lines) + "\n"


def evaluate(split: str = "dev", runs: int = 3, limit: int | None = None, skip: set[str] | None = None,
             log=print) -> dict:
    skip = skip or set()
    started = time.perf_counter()
    cases = load_split(split, limit)
    log(f"evaluating {len(cases)} {split} cases, {runs} runs per case, mode {config.LLM_MODE}")

    records = {"agent": _agent_variant("agent", cases, runs)}
    log("  agent done")
    if "baselines" not in skip:
        for name in ("single_prompt", "keyword"):
            records[name] = baselines.run_baseline(name, cases)
        log("  baselines done")
    if "ablations" not in skip:
        for name in ("no_retrieval", "no_citation_check", "no_gap_loop", "no_appeal_loop"):
            records[name] = _agent_variant(name, cases)
        log("  ablations done")

    summaries = {name: metrics.summarize(recs) for name, recs in records.items()}
    agent = records["agent"]
    ci = {name: metrics.bootstrap_ci(agent, fn, seed=config.EVAL_SEED) for name, fn in {
        "criterion_accuracy": metrics.criterion_accuracy,
        "decision_accuracy": metrics.decision_accuracy,
        "final_accuracy": metrics.final_accuracy,
        "gap_recall": lambda recs: metrics.gap_scores(recs)["gap_recall"],
    }.items()}
    spread = {name: metrics.per_run_spread(agent, fn) for name, fn in {
        "criterion_accuracy": metrics.criterion_accuracy, "final_accuracy": metrics.final_accuracy}.items()}

    report = {
        "meta": {
            "split": split, "data_seed": SPLITS.get(split, (None, config.UNSEEN_SEED))[1],
            "eval_seed": config.EVAL_SEED, **config.result_provenance(),
            "runs": runs, "limit": limit,
            "confidence_threshold": config.CONFIDENCE_THRESHOLD,
            "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        "summaries": summaries,
        "agent_ci": ci,
        "agent_run_spread": spread,
        "table": [_row(name, s) for name, s in summaries.items()],
        "perturbations": {} if "perturbations" in skip else run_perturbations(split, limit, agent, log),
        "faults": {} if "faults" in skip else run_faults(cases, log),
        "coverage_curve": metrics.coverage_curve(agent, COVERAGE_THRESHOLDS),
        "agent_records": agent,
    }
    report["meta"]["duration_s"] = round(time.perf_counter() - started, 1)
    return report


def save(report: dict, out_dir: Path | None = None) -> tuple[Path, dict]:
    out_dir = Path(out_dir or Path(config.RESULTS_DIR) / "eval")
    out_dir.mkdir(parents=True, exist_ok=True)
    m = report["meta"]
    latest = out_dir / f"latest_{m['split']}_{m['llm_mode']}.json"
    previous = json.loads(latest.read_text(encoding="utf-8")) if latest.exists() else None
    report["regression"] = regression_check(report, previous)
    stamp = m["run_at"].replace(":", "").replace("-", "").replace("+0000", "Z")
    body = dump_report(report)
    (out_dir / f"{stamp}_{m['split']}_{m['llm_mode']}.json").write_text(body, encoding="utf-8")
    latest.write_text(body, encoding="utf-8")
    (out_dir / f"latest_{m['split']}_{m['llm_mode']}.md").write_text(to_markdown(report), encoding="utf-8")
    return latest, report["regression"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full AuthPilot evaluation.")
    parser.add_argument("--split", choices=["dev", "sealed"], default="dev")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--limit", type=int, default=None, help="only the first N cases (smoke runs)")
    parser.add_argument("--skip", nargs="*", default=[], choices=["baselines", "ablations", "perturbations", "faults"])
    parser.add_argument("--allow-sealed", action="store_true")
    parser.add_argument("--no-fail", action="store_true", help="do not exit non-zero on a regression")
    args = parser.parse_args()
    if args.split == "sealed" and not args.allow_sealed:
        raise SystemExit("Refusing to run on the sealed split without --allow-sealed.")
    require_eval_mode()
    report = evaluate(args.split, args.runs, args.limit, set(args.skip))
    path, regression = save(report)
    print(to_markdown(report))
    print(f"saved {path}")
    if regression["status"] == "regression" and not args.no_fail:
        print("REGRESSION: a tracked score dropped against the last saved run.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
