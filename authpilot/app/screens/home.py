"""Landing page: the challenge, the problem, the solution, safety, targets, roadmap, tech stack."""

import streamlit as st

from authpilot import config, ehr
from authpilot.agent import TOOLS
from authpilot.app import ui
from authpilot.app.content import HOME
from authpilot.app.strings import lang

ui.inject_css()
c = HOME[lang()]


def grid(items_html: list[str], columns: str) -> str:
    return f'<div class="ap-grid {columns}">' + "".join(items_html) + "</div>"


with st.container(key="panel_hero"):
    left, right = st.columns([1.15, 0.85], vertical_alignment="top")
    with left:
        chips = []
        for i, step in enumerate(c["flow"][:6]):
            chips.append(f'<span class="ap-chip{" lime" if i == 5 else ""}">{ui.esc(step)}</span>')
        ui.html(
            ui.wordmark(38)
            + f'<p class="ap-eyebrow">{ui.esc(c["hero_eyebrow"])}</p>'
            + f'<h1 id="ap-main" class="ap-hero-title">{ui.esc(c["hero_lead"])} '
            + f'<span class="ap-accent">{ui.esc(c["hero_accent"])}</span></h1>'
            + f'<p class="ap-lead">{ui.esc(c["hero_text"])}</p>'
            + '<div class="ap-chips">' + "".join(chips) + "</div>"
        )
        primary, secondary = st.columns(2)
        with primary:
            with st.container(key="cta_primary"):
                st.page_link("screens/workbench.py", label=c["link_workbench"], icon=":material/play_circle:",
                             width="content")
        with secondary:
            with st.container(key="cta_secondary"):
                st.page_link("screens/results.py", label=c["link_results"], icon=":material/monitoring:",
                             width="content")
    with right:
        ui.html(
            '<div class="ap-mock">'
            f'<p class="ap-kicker">{ui.esc(c["illustration"])}</p>'
            f'<div class="ap-mono">DEV-SAMPLE</div>'
            f'<h3>{ui.esc(c["sample_procedure"])}</h3>'
            f'{ui.badge("met")}'
            f'{ui.quote(c["sample_quote"], c["illustration"])}'
            f'<p class="ap-overlay">{ui.esc(c["overlay"])}</p>'
            "</div>"
        )
    values = [str(len(ehr.list_cases("dev")) + len(ehr.list_cases("sealed"))), "2", str(len(TOOLS)), "2 + 1",
              str(config.MAX_TOOL_CALLS)]
    ui.html(grid([
        f'<div class="ap-stat-box"><div class="ap-stat">{ui.esc(value)}</div>'
        f'<div class="ap-stat-label">{ui.esc(label)}</div></div>'
        for value, label in zip(values, c["stats"])
    ], "five"))

with st.container(key="panel_challenge"):
    ui.eyebrow(c["challenge_eyebrow"])
    ui.section_title(c["challenge_title"])
    st.write(c["challenge_text"])
    ui.html("".join(
        f'<div class="ap-rule"><h3>{ui.esc(title)}</h3><p>{ui.esc(body)}</p></div>'
        for title, body in c["challenge_cards"]
    ))

with st.container(key="panel_problem"):
    ui.eyebrow(c["problem_eyebrow"])
    ui.section_title(c["problem_title"])
    ui.html(grid([
        f'<div class="ap-tall"><div class="num">{i:02d}</div><p>{ui.esc(step)}</p></div>'
        for i, step in enumerate(c["problem_steps"], start=1)
    ], "five"))
    ui.html(
        f'<h3 class="ap-section-title" style="font-size:28px">{ui.esc(c["problem_cost_title"])}</h3>'
        + grid([
            f'<div class="ap-card"><p>{ui.esc(item)}</p></div>' for item in c["problem_costs"]
        ], "three")
    )
    ui.banner(c["problem_estimate"], "info")

with st.container(key="deep_solution"):
    ui.eyebrow(c["solution_eyebrow"])
    ui.section_title(c["solution_title"])
    steps = []
    for i, step in enumerate(c["flow"], start=1):
        gate = i == 6
        steps.append(
            f'<div class="ap-step{" gate" if gate else ""}"><div class="num">{i:02d}</div>'
            f"<h3>{ui.esc(step)}</h3></div>"
        )
    ui.html('<div class="ap-steps">' + "".join(steps) + "</div>")
    st.write(c["solution_text"])
    ui.html(grid([
        f'<div class="ap-safe"><h3>{ui.esc(title)}</h3><p>{ui.esc(body)}</p></div>'
        for title, body in c["autonomy"]
    ], "four"))

with st.container(key="panel_safety"):
    ui.eyebrow(c["safety_eyebrow"])
    ui.section_title(c["safety_title"])
    ui.html(grid([
        ui.card(title, f"<p>{ui.esc(body)}</p>") for title, body in c["safety"]
    ], "three"))

with st.container(key="panel_targets"):
    ui.eyebrow(c["targets_eyebrow"])
    ui.section_title(c["targets_title"])
    ui.banner(c["targets_note"], "info")
    ui.html(grid([
        f'<div class="ap-target"><div class="ap-kicker">{ui.esc(c["goal"])}</div>'
        f"<h3>{ui.esc(metric)}</h3><p>{ui.esc(how)}</p>"
        f'<div class="ap-target-value">{ui.esc(target)}</div>'
        f'<div class="ap-pending">{ui.esc(c["pending"])}</div></div>'
        for metric, how, target in c["targets"]
    ], "three"))

with st.container(key="panel_stack"):
    ui.eyebrow(c["stack_eyebrow"])
    ui.section_title(c["stack_title"])
    st.write(c["stack_note"])
    stack = [
        ([f"Claude agent model ({config.AGENT_MODEL})", f"Cheap model for extraction and fallback ({config.CHEAP_MODEL})",
          f"Escalation model, optional ({config.ESCALATION_MODEL})", "Anthropic SDK with tool use",
          "Structured outputs validated with Pydantic", "Record and replay cache", "Offline stub model for tests"], []),
        (["Python 3.11", "Plain-Python agent loop (no framework)", "Pydantic v2 schemas", "BM25 policy retrieval",
          "FastAPI mock payer", "httpx client", "Uvicorn", "Dockerfile and fully locked dependencies"], ["Hosted deployment"]),
        (["SQLite append-only audit log", "JSON case store", "Seeded synthetic case generator",
          "Markdown payer policies with numbered sections"], ["Synthea FHIR records", "Postgres", "NPHIES message format"]),
        (["Streamlit multi-page app", "Custom theme and components", "English and Arabic interface (RTL)",
          "Bilingual letters with verbatim quotes"], ["React or Next.js portal"]),
        (["pytest with fault injection", "Headless UI tests", "Deterministic seeds", "Makefile commands",
          "Baselines and ablations", "Perturbations and an unseen procedure", "Bootstrap confidence intervals",
          "Regression check on every run"], ["Sealed test run with Claude"]),
    ]
    cards = []
    for title, (built, planned) in zip(c["stack_titles"], stack):
        chips = []
        for item in built:
            kind = "lime" if config.AGENT_MODEL in item else "solid"
            chips.append(f'<span class="ap-chip {kind}">{ui.esc(item)}</span>')
        chips += [f'<span class="ap-chip line">{ui.esc(item)}</span>' for item in planned]
        cards.append(ui.card(title, "".join(chips)))
    ui.html(grid(cards, "three"))

with st.container(key="panel_future"):
    ui.eyebrow(c["future_eyebrow"])
    ui.section_title(c["future_title"])
    ui.html(grid([
        ui.card(title, ui.bullet_list(items)) for title, items in c["future"]
    ], "three"))
    ui.html(f'<p><a class="ap-pill" href="#ap-main">{ui.esc(c["back_top"])}</a></p>')

with st.container(key="panel_footer"):
    ui.html(ui.wordmark(28) + f'<p class="ap-footer">{ui.esc(c["footer"].format(mode=config.LLM_MODE))}</p>')
