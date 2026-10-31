"""Slide deck for the pitch, generated from the latest saved evaluation so numbers never go stale.

Usage: python -m authpilot.eval.slides [--mode stub|record|replay|live] [--out docs/slides.html]
Open the HTML file in a browser: arrow keys or space to move, P to print (one slide per page).
"""

import argparse
import json
from html import escape
from pathlib import Path

from authpilot import config
from authpilot.eval.summary import ROBUSTNESS_TARGET_POINTS, TARGETS, latest_report

CSS = """
*{box-sizing:border-box} body{margin:0;font-family:-apple-system,"Segoe UI",Roboto,sans-serif;background:#0B1F1D;color:#0F172A}
.slide{display:none;width:100vw;height:100vh;padding:5vh 7vw;background:#F7F9FC;flex-direction:column;justify-content:center}
.slide.active{display:flex} .slide.dark{background:linear-gradient(135deg,#0F766E,#134E4A 55%,#1E293B);color:#F8FAFC}
h1{font-size:4.2vw;margin:0 0 1.5vh} h2{font-size:2.8vw;margin:0 0 3vh;color:#0F766E} .dark h2{color:#99F6E4}
p,li{font-size:1.6vw;line-height:1.45} .lead{font-size:2vw;color:#CCFBF1;max-width:70vw}
.eyebrow{text-transform:uppercase;letter-spacing:.15em;font-size:1vw;font-weight:700;color:#0F766E;margin-bottom:1vh}
.dark .eyebrow{color:#99F6E4} .grid{display:grid;grid-template-columns:repeat(3,1fr);gap:2vw}
.card{background:#fff;border:1px solid #E2E8F0;border-radius:14px;padding:2vh 1.5vw}
.card h3{margin:0 0 1vh;font-size:1.5vw} .card p{font-size:1.25vw;margin:0;color:#334155}
table{border-collapse:collapse;font-size:1.3vw;width:100%} th,td{padding:1vh .8vw;border-bottom:1px solid #E2E8F0;text-align:left}
th{color:#475569;font-weight:600} .ok{color:#166534;font-weight:700} .bad{color:#9A3412;font-weight:700}
.flow{display:flex;flex-wrap:wrap;gap:.8vw;align-items:center;margin:2vh 0} .node{background:#fff;border:2px solid #99F6E4;border-radius:10px;padding:1vh 1vw;font-weight:600;font-size:1.3vw;color:#134E4A}
.node.gate{background:#EDE9FE;border-color:#C4B5FD;color:#5B21B6} .arrow{color:#94A3B8;font-size:1.5vw}
.warn{background:#FFF7ED;border:1px solid #FED7AA;color:#9A3412;border-radius:10px;padding:1.2vh 1vw;font-size:1.2vw;margin-bottom:2vh}
img{max-height:62vh;max-width:100%;border-radius:12px;border:1px solid #CBD5E1;box-shadow:0 8px 30px rgba(0,0,0,.12)}
.two{display:grid;grid-template-columns:1fr 1.3fr;gap:3vw;align-items:center}
.counter{position:fixed;bottom:2vh;right:2vw;font-size:1vw;color:#64748B} .big{font-size:5vw;font-weight:800;color:#0F766E}
@media print{.slide{display:flex!important;page-break-after:always;height:100vh} .counter{display:none}}
"""

JS = """
const s=[...document.querySelectorAll('.slide')];let i=0;const c=document.querySelector('.counter');
function show(n){i=Math.max(0,Math.min(s.length-1,n));s.forEach((e,k)=>e.classList.toggle('active',k===i));c.textContent=(i+1)+' / '+s.length}
document.addEventListener('keydown',e=>{if(['ArrowRight','ArrowDown',' ','PageDown'].includes(e.key))show(i+1);
if(['ArrowLeft','ArrowUp','PageUp'].includes(e.key))show(i-1);if(e.key==='p')window.print()});
document.addEventListener('click',e=>show(e.clientX>innerWidth/3?i+1:i-1));show(0);
"""


def _pct(v) -> str:
    return "-" if v is None else f"{v * 100:.1f}%"


def _slide(body: str, dark: bool = False) -> str:
    return f'<section class="slide{" dark" if dark else ""}">{body}</section>'


def _cards(items: list[tuple[str, str]]) -> str:
    return '<div class="grid">' + "".join(
        f'<div class="card"><h3>{escape(t)}</h3><p>{escape(b)}</p></div>' for t, b in items) + "</div>"


def _flow(steps: list[tuple[str, bool]]) -> str:
    parts = []
    for n, (label, gate) in enumerate(steps):
        if n:
            parts.append('<span class="arrow">&rarr;</span>')
        parts.append(f'<span class="node{" gate" if gate else ""}">{escape(label)}</span>')
    return '<div class="flow">' + "".join(parts) + "</div>"


def build(report: dict) -> str:
    m, s, ci = report["meta"], report["summaries"]["agent"], report["agent_ci"]
    stub = m["llm_mode"] == "stub"
    warn = ('<div class="warn">Numbers from the offline stub model (a keyword heuristic written alongside the case '
            'templates). They show the pipeline and safety mechanisms work; the Claude run and the sealed test set '
            'give the real accuracy.</div>') if stub else ""
    source = escape(f"{m['split']} split, {m['runs']} runs per case, model {m['agent_model']}, "
                    f"prompt {m['prompt_version']}, seeds {m['data_seed']}/{m['eval_seed']}, {m['run_at']}")
    values = {**s, "denial_recovery": (s.get("denial_recovery") or {}).get("rate")}
    ci_for = {"criterion_accuracy": ci.get("criterion_accuracy"), "decision_accuracy": ci.get("decision_accuracy"),
              "gap_recall": ci.get("gap_recall")}
    rows = []
    for name, key, target, _ in TARGETS:
        value = values.get(key)
        interval = ci_for.get(key)
        ok = value is not None and value >= target
        rows.append(f"<tr><td>{escape(name)}</td><td>{_pct(value)}"
                    f"{f' <small>({_pct(interval[0])} to {_pct(interval[1])})</small>' if interval else ''}</td>"
                    f"<td>{_pct(target)}</td><td class=\"{'ok' if ok else 'bad'}\">{'meets' if ok else 'below'}</td></tr>")
    drops = [p["drop_points"] for p in report["perturbations"].values() if p.get("drop_points") is not None]
    worst = max(drops) if drops else None
    if worst is not None:
        ok = worst <= ROBUSTNESS_TARGET_POINTS
        rows.append(f"<tr><td>Robustness drop (worst perturbation)</td><td>{worst} points</td>"
                    f"<td>{ROBUSTNESS_TARGET_POINTS:.0f} points or less</td>"
                    f"<td class=\"{'ok' if ok else 'bad'}\">{'meets' if ok else 'below'}</td></tr>")

    summaries = report["summaries"]
    ablation_rows = "".join(
        f"<tr><td>{escape(name.replace('_', ' '))}</td><td>{_pct(v['criterion_accuracy'])}</td>"
        f"<td>{_pct(v.get('final_accuracy'))}</td><td>{_pct((v.get('denial_recovery') or {}).get('rate'))}</td>"
        f"<td>{v['mean_tokens']:,.0f}</td></tr>"
        for name in ("agent", "single_prompt", "keyword", "no_retrieval", "no_gap_loop", "no_appeal_loop")
        if (v := summaries.get(name)))
    pert_rows = "".join(
        f"<tr><td>{escape(name.replace('_', ' '))}</td><td>{_pct(p['criterion_accuracy'])}</td>"
        f"<td>{'-' if p.get('drop_points') is None else p['drop_points']}</td></tr>"
        for name, p in report["perturbations"].items())
    fault_rows = "".join(f"<tr><td>{escape(name.replace('_', ' '))}</td><td>{f['runs']}</td><td>{_pct(f['safe_rate'])}</td></tr>"
                         for name, f in report["faults"].items())

    slides = [
        _slide('<div class="eyebrow">Hackathon &middot; Autonomous AI agents</div><h1>AuthPilot</h1>'
               '<p class="lead">An AI agent that owns prior authorization from the physician\'s order to the payer\'s '
               'decision, and stops for exactly one human approval.</p>', dark=True),
        _slide('<div class="eyebrow">The problem</div><h2>Prior authorization is slow, manual and restarts after every denial</h2>'
               "<ul><li>Staff check whether authorization is needed, find the policy, read its criteria</li>"
               "<li>Dig through the chart for notes, imaging, labs and therapy history</li>"
               "<li>Write the letter, submit, chase status, rewrite after a denial</li>"
               "<li>About 45 minutes per request (our estimate, being validated) and days of delay for patients</li></ul>"),
        _slide('<div class="eyebrow">The challenge</div><h2>One agent that owns a whole business process</h2>' + _cards([
            ("Contract review", "Checks the chart against every payer policy clause, with cited evidence."),
            ("Employee onboarding", "Requests missing documents from the clinic and tracks them until they arrive."),
            ("Sales development", "Drafts evidence-based letters and appeals and follows up until a decision."),
        ])),
        _slide('<div class="eyebrow">The solution</div><h2>One agent, two loops, one human gate</h2>' + _flow([
            ("Order", False), ("Read chart", False), ("Check every criterion", False), ("Request missing evidence", False),
            ("Draft letter", False), ("Human approval", True), ("Submit", False), ("Appeal if denied", False),
            ("Decision", False)]) +
            "<p>The model picks the next tool from a compact case state; code decides which tools are allowed, "
            "validates every output, enforces caps and logs everything.</p>"),
        _slide('<div class="eyebrow">Safety and trust</div><h2>Every claim can be checked; every step can be stopped</h2>' + _cards([
            ("No invented facts", "Every 'met' cites text that code confirms is copied word for word from the chart."),
            ("Human approval gate", "Bound to the exact letter. Any edit voids it. The agent cannot approve itself."),
            ("Abstains when unsure", "Unclear or low-confidence criteria go to a person with a summary."),
            ("Faithful letters", "Statements kept only if quotes are verbatim and every number is in them."),
            ("Safe under faults", "Retries, model fallback, retry queue, idempotent submissions."),
            ("Full audit trail", "Every tool call, model call, decision and human action, append-only."),
        ])),
        _slide('<div class="eyebrow">Live demo</div><h2>Gap filled by the clinic; denial, appeal, approval</h2>'
               '<div class="two"><ol><li>MRI order: red-flag screening missing</li><li>Agent asks the clinic, '
               'gets the addendum, re-checks</li><li>Human approves the exact letter: approved</li>'
               '<li>Biologic: denied for DAS28 (flowsheet), agent appeals with the quote</li><li>Approved on appeal</li>'
               '<li>The same flow in Arabic: every letter has an Arabic version, covered by the same approval</li></ol>'
               '<img src="screenshots/workbench_approved.jpg" alt="Workbench"></div>'),
        _slide('<div class="eyebrow">Evaluation</div><h2>Measured like a product, not a prototype</h2>' + _cards([
            ("Held-out data", "100 synthetic cases; 40 sealed with wording never seen in development."),
            ("Baselines and ablations", "Single prompt, keyword rules; no retrieval, citations, gap or appeal loop."),
            ("Robustness", "Policy threshold change, reworded policy, noisy chart, removed evidence, unseen procedure."),
            ("Safety", "Payer down, corrupted model output and empty retrieval on every case."),
            ("Statistics", "Three runs per case, bootstrap confidence intervals, coverage vs accuracy."),
            ("Regression check", "Every run is saved with seeds, model and prompt; any drop fails the build."),
        ])),
        _slide(f'<div class="eyebrow">Results</div><h2>Headline results vs targets</h2>{warn}'
               "<table><tr><th>Metric</th><th>Result</th><th>Target</th><th>Status</th></tr>" + "".join(rows) +
               f"</table><p><small>{source}</small></p>"),
        _slide('<div class="eyebrow">Results</div><h2>Each part earns its place</h2>' + warn +
               "<table><tr><th>Variant</th><th>Criterion acc</th><th>Final outcome acc</th><th>Denial recovery</th>"
               "<th>Tokens per case</th></tr>" + ablation_rows + "</table>"),
        _slide('<div class="eyebrow">Results</div><h2>Robustness and safety</h2>' + warn +
               '<div class="two"><table><tr><th>Perturbation</th><th>Criterion acc</th><th>Drop (points)</th></tr>' +
               pert_rows + '</table><table><tr><th>Injected fault</th><th>Runs</th><th>Safe</th></tr>' + fault_rows +
               "</table></div>"),
        _slide('<div class="eyebrow">Engineering</div><h2>Built to be checked and reproduced</h2>'
               "<ul><li>Typed schemas for every tool and model output; plain-Python agent loop</li>"
               "<li>Tests for every tool, every fallback, the gate, the UI and the evaluation</li>"
               "<li>One command each: <code>make setup</code>, <code>make demo</code>, <code>make eval</code>, "
               "<code>make test</code>; verified from a clean clone</li>"
               "<li>Locked dependencies, fixed seeds, record-and-replay model cache, Dockerfile</li></ul>"),
        _slide('<div class="eyebrow">Roadmap</div><h2>From hackathon build to clinic pilot</h2>' + _cards([
            ("Pilot", "One clinic, de-identified data, PDPL and HIPAA-style compliance review."),
            ("Integrations", "FHIR records, NPHIES-aligned submissions, real fax and email behind the gate."),
            ("Scale", "More procedures and payers, policy-change monitoring, Arabic clinical notes."),
        ])),
        _slide('<h1>Thank you</h1><p class="lead">AuthPilot: the agent does the reading, checking, chasing and '
               'drafting. A person approves in one click.</p>', dark=True),
    ]
    return (f"<!doctype html><html><head><meta charset=\"utf-8\"><title>AuthPilot</title><style>{CSS}</style></head>"
            f"<body>{''.join(slides)}<div class=\"counter\"></div><script>{JS}</script></body></html>\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="dev")
    parser.add_argument("--mode", default=None)
    parser.add_argument("--out", type=Path, default=config.ROOT_DIR / "docs" / "slides.html")
    args = parser.parse_args()
    path = latest_report(args.split, args.mode)
    if path is None:
        raise SystemExit("No saved evaluation found. Run `make eval` first.")
    args.out.write_text(build(json.loads(path.read_text(encoding="utf-8"))), encoding="utf-8")
    print(f"wrote {args.out} from {path}")


if __name__ == "__main__":
    main()
