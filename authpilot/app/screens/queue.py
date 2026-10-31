"""Escalation queue: every case that is waiting for a person."""

import streamlit as st

from authpilot.app import ui, views
from authpilot.app.strings import t

ui.inject_css()


def needs_label(needs: str) -> str:
    if needs.startswith("approve"):
        return t("needs_approve", kind=t("kind_initial" if "initial" in needs else "kind_appeal"))
    return t("needs_escalated") if needs == "escalated" else t("needs_queued")


with st.container(key="panel_queue"):
    ui.eyebrow(t("queue_eyebrow"))
    ui.section_title(t("queue_title"), level=1, anchor=True)
    st.write(t("queue_intro"))

    rows = views.queue_rows()
    if not rows:
        ui.banner(t("queue_empty"), "info")

    counts: dict[str, int] = {}
    for row in rows:
        counts[needs_label(row["needs"])] = counts.get(needs_label(row["needs"]), 0) + 1
    if counts:
        for col, (need, count) in zip(st.columns(len(counts)), sorted(counts.items())):
            col.metric(need, count)

    for row in rows:
        with st.container(key=f"q_{row['case']}"):
            left, right = st.columns([5, 1])
            status_key = "ready_for_approval" if row["needs"].startswith("approve") else row["needs"]
            badges = ui.badge(row["status"]) + (
                ui.badge(needs_label(row["needs"]), status_key) if row["needs"] != row["status"] else ""
            )
            left.markdown(
                f'<div><span class="ap-mono">{ui.esc(row["case"])}</span> · {ui.esc(row["procedure"])}</div>'
                f'<div style="margin:6px 0">{badges}</div>'
                f'<div class="ap-muted" dir="auto">{ui.esc(row["reason"]) or ui.esc(t("waiting_review"))}</div>',
                unsafe_allow_html=True,
            )
            if right.button(t("open"), key=f"open_{row['case']}", use_container_width=True):
                st.session_state["case_id"] = row["case"]
                st.switch_page("screens/workbench.py")
