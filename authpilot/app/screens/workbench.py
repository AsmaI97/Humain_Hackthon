"""Workbench: run or open a case, review the evidence, approve or reject, follow the timeline."""

import streamlit as st

from authpilot import config, ehr, gate, store
from authpilot.agent import resume_case, run_case
from authpilot.app import ui, views
from authpilot.app.strings import status_label, t

ui.inject_css()


def needs_label(needs: str) -> str:
    if needs.startswith("approve"):
        return t("needs_approve", kind=t("kind_initial" if "initial" in needs else "kind_appeal"))
    return t("needs_escalated") if needs == "escalated" else t("needs_queued")


def show_letters(versions: list[tuple[str, str]]) -> None:
    for language, text in versions:
        if len(versions) > 1:
            st.caption(t("english_version") if language == "en" else t("arabic_version"))
        ui.html(ui.letter(text, rtl=language == "ar"))


with st.sidebar:
    st.subheader(t("start_case"))
    case_name = st.selectbox(t("dev_case"), ehr.list_cases("dev"), key="case_name")
    if st.button(t("run_agent"), key="run_agent", type="primary", use_container_width=True):
        order, _, label = ehr.load_case_files("dev", case_name)
        with st.spinner(t("agent_working")):
            run_case(label.case_id, order)
        st.session_state["case_id"] = label.case_id
    st.subheader(t("open_case"))
    case_ids = store.list_case_ids()
    if case_ids:
        current = st.session_state.get("case_id")
        index = case_ids.index(current) if current in case_ids else 0
        st.session_state["case_id"] = st.selectbox(t("case"), case_ids, index=index)
    st.button(t("refresh"), key="refresh", use_container_width=True)

case_id = st.session_state.get("case_id")
if not case_id:
    with st.container(key="panel_empty"):
        ui.section_title(t("workbench"), level=1, anchor=True)
        ui.banner(t("workbench_intro"), "info")
    st.stop()

state = store.reload(case_id)
needs = views.needs_human(state)
badges = ui.badge(state.status.value)
if state.payer_status:
    badges += ui.badge(f"{t('payer')} {status_label(state.payer_status)}", state.payer_status)
if needs:
    badges += ui.badge(needs_label(needs), "queued" if needs == "queued" else "ready_for_approval")

with st.container(key="panel_head"):
    ui.html(
        f'<p class="ap-eyebrow">{ui.esc(t("case_label"))} <span class="ap-mono">{ui.esc(case_id)}</span></p>'
        f'<h1 id="ap-main" class="ap-section-title">{ui.esc(state.order.procedure_name)} '
        f'({ui.esc(state.order.procedure_code)})</h1><div>{badges}</div>'
    )
    st.caption(t("patient_line", patient=state.order.patient_id, order=state.order.order_id,
                 provider=state.order.ordering_provider, date=state.order.request_date))
    cols = st.columns(4)
    cols[0].metric(t("tool_calls"), f"{state.loop_counts.tool_calls} / {config.MAX_TOOL_CALLS}")
    cols[1].metric(t("clinic_requests"), f"{state.loop_counts.gap_loops} / {config.MAX_GAP_LOOPS}")
    cols[2].metric(t("appeals"), f"{state.loop_counts.appeals} / {config.MAX_APPEALS}")
    cols[3].metric(t("submissions"), len(state.submissions))
    if state.escalation_reason:
        ui.banner(t("escalated_banner", reason=state.escalation_reason), "warn")
    if state.queued_reason:
        ui.banner(t("queued_banner", reason=state.queued_reason), "warn")
        if st.button(t("retry_now"), key="resume_case"):
            resume_case(case_id)
            st.rerun()
    if state.denial_reason:
        ui.banner(t("denial_banner", reason=state.denial_reason), "warn")

kind = gate.awaiting_approval(state)
criteria, timeline, review = st.columns(3)
with criteria:
    with st.container(key="panel_criteria"):
        ui.section_title(t("criteria_checklist"), compact=True)
        rows = views.checklist_rows(state)
        if not rows:
            st.write(t("not_checked"))
        for row in rows:
            status = row["status_key"]
            accent = ui.STATUS_COLORS.get(status, ("", "#3F7078"))[1]
            body = (
                f'<div>{ui.badge(status)}<span class="ap-chip">{ui.esc(t("confidence"))} '
                f'{row["confidence"]:.2f}</span></div>'
                f'<p dir="auto" style="margin-top:8px">{ui.esc(row["reasoning"])}</p>'
                + "".join(ui.quote(q, f"{t('source')}: {doc}") for doc, q in row["quotes"])
            )
            if row["gap"]:
                body += (
                    f'<div class="ap-gap" dir="auto"><span class="ap-gap-label">{ui.esc(t("gap_label"))}</span>'
                    f'{ui.esc(row["gap"])}</div>'
                )
            st.markdown(ui.card(row["criterion"], body, accent=accent, extra_class="ap-crit"), unsafe_allow_html=True)

with timeline:
    with st.container(key="panel_timeline"):
        ui.section_title(t("agent_timeline"), compact=True)
        show_details = st.toggle(t("show_details"), key="show_llm")
        events = views.timeline_rows(case_id, include_model_calls=show_details, include_tool_calls=show_details)
        with st.container(height=640):
            ui.html(ui.timeline(events))
        with st.expander(t("raw_table")):
            st.dataframe(events, use_container_width=True, hide_index=True)

with review:
    with st.container(key="panel_review"):
        if kind:
            with st.container(key="gate"):
                kind_label = t("kind_initial" if kind == "initial" else "kind_appeal")
                ui.html(
                    f'<p class="ap-eyebrow">{ui.esc(t("approval_required"))}</p>'
                    f'<h2 class="ap-panel-title">{ui.esc(t("review_letter", kind=kind_label))}</h2>'
                )
                st.write(t("approval_note"))
                show_letters(gate.letters_for(state, kind))
                reviewer = st.text_input(t("your_name"), key="reviewer")
                reject_reason = st.text_input(t("reject_reason"), key="reject_reason")
                left, right = st.columns(2)
                if left.button(t("approve"), key="approve", type="primary", disabled=not reviewer):
                    gate.approve(case_id, reviewer)
                    with st.spinner(t("submitting")):
                        resume_case(case_id)
                    st.rerun()
                if right.button(t("reject"), key="reject", disabled=not (reviewer and reject_reason)):
                    gate.reject(case_id, reviewer, reject_reason)
                    st.rerun()
        tabs = st.tabs([t("tab_letter"), t("tab_appeal"), t("tab_requests")])
        with tabs[0]:
            if state.letter:
                show_letters(gate.letters_for(state, "initial"))
            else:
                st.write(t("no_letter"))
        with tabs[1]:
            if state.appeal_letter:
                show_letters(gate.letters_for(state, "appeal"))
            else:
                st.write(t("no_appeal"))
        with tabs[2]:
            if not state.info_requests:
                st.write(t("no_requests"))
            for request in state.info_requests:
                received = ", ".join(request.new_doc_ids) or t("nothing_yet")
                ui.html(ui.card(
                    request.request_id,
                    ui.letter(request.message)
                    + f"<p style='margin-top:8px'>{ui.esc(t('documents_received', docs=received))}</p>",
                ))
