"""Results: saved evaluation runs with their seed, model and prompt version."""

import json
from pathlib import Path

import streamlit as st

from authpilot import config
from authpilot.app import ui
from authpilot.app.strings import t
from authpilot.eval import criteria_eval

ui.inject_css()

with st.container(key="panel_results"):
    ui.eyebrow(t("results_eyebrow"))
    ui.section_title(t("results_title"), level=1, anchor=True)
    st.write(t("results_intro"))

    mode_report = Path(config.RESULTS_DIR) / "eval" / f"latest_dev_{config.LLM_MODE}.md"
    live_report = Path(config.RESULTS_DIR) / "eval" / "latest_dev_live.md"
    full = live_report if config.LLM_MODE != "stub" and live_report.exists() else mode_report
    with st.expander(t("full_eval"), expanded=full.exists()):
        if full.exists():
            st.markdown(f'<div dir="ltr">\n\n{full.read_text(encoding="utf-8")}\n\n</div>', unsafe_allow_html=True)
        else:
            st.write(t("no_full_eval"))

    ui.eyebrow(t("criterion_runs"))
    if config.LLM_MODE in ("stub", "replay") and st.button(t("run_eval_button"), key="run_eval"):
        with st.spinner(t("evaluating")):
            criteria_eval.save_report(criteria_eval.run("dev"))
        st.rerun()

    runs = sorted(Path(config.RESULTS_DIR).glob("*.json"))
    if not runs:
        ui.banner(t("no_runs"), "info")
        st.stop()

    choice = st.selectbox(t("run_select"), runs, format_func=lambda p: p.name)
    report = json.loads(Path(choice).read_text(encoding="utf-8"))
    meta, summary = report["meta"], report["summary"]

    if meta["llm_mode"] == "stub":
        ui.banner(t("stub_warning"), "warn")

    st.caption(f"split {meta['split']} · seed {meta['seed']} · mode {meta['llm_mode']} · model {meta['agent_model']} · "
               f"prompt {meta['prompt_version']} · run at {meta['run_at']}")

    cards = [
        (f"{summary['criterion_accuracy']:.3f}", t("m_accuracy")),
        (f"{summary['false_met_rate']:.3f}", t("m_false_met")),
        (f"{summary['citation_validity']:.3f}", t("m_citations")),
        (f"{summary['invalid_output_rate']:.3f}", t("m_invalid")),
        (str(summary["mean_tokens_per_case"]), t("m_tokens")),
    ]
    for col, (value, label) in zip(st.columns(len(cards)), cards):
        col.markdown(f'<div class="ap-stat-box"><div class="ap-stat">{ui.esc(value)}</div>'
                     f'<div class="ap-stat-label">{ui.esc(label)}</div></div>', unsafe_allow_html=True)

    left, right = st.columns(2)
    with left:
        st.subheader(t("per_status"))
        st.dataframe([{"status": s, **m} for s, m in summary["per_status"].items()], hide_index=True,
                     use_container_width=True)
        st.subheader(t("confusion"))
        st.dataframe([{"pair": k, "count": v} for k, v in sorted(summary["confusion"].items())], hide_index=True,
                     use_container_width=True)
    with right:
        st.subheader(t("accuracy_by_type"))
        st.bar_chart(summary["accuracy_by_tag"], horizontal=True)

    st.subheader(t("worst_failures"))
    if not report["worst_failures"]:
        st.write(t("none_in_run"))
    for case in report["worst_failures"]:
        with st.container(key=f"card_{case['case_id']}"):
            st.markdown(
                f'<p><span class="ap-mono">{ui.esc(case["case_id"])}</span> '
                f'({ui.esc(case["procedure"])}, {ui.esc(", ".join(case["tags"]))}): '
                f'{ui.esc(str(case["errors"]))} failed</p>',
                unsafe_allow_html=True,
            )
            for row in case["criteria"]:
                if row["correct"]:
                    continue
                body = (f"<p>{ui.esc(t('expected'))} {ui.badge(row['expected'])} {ui.esc(t('got'))} "
                        f"{ui.badge(row['predicted'])}</p><p dir=\"auto\">{ui.esc(row['reasoning'])}</p>"
                        + "".join(ui.quote(q, t("cited_by_agent")) for q in row["cited"]))
                ui.html(ui.card(f"{row['section_ref']} {row['criterion_id']}", body))
