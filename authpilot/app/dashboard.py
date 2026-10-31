"""AuthPilot web app (Streamlit, multi-page). Run with: make dashboard

Pages: landing page, workbench, escalation queue, results, in English or Arabic (sidebar switch).
The pages call the same agent, gate and store functions as the CLI; no business logic lives in the UI.
"""

import sys
from pathlib import Path

# Streamlit runs this file as a script, so the repository root is not on sys.path by default.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st  # noqa: E402

from authpilot.app import ui  # noqa: E402
from authpilot.app.strings import LANGUAGES, t  # noqa: E402

st.set_page_config(page_title="AuthPilot", page_icon=":material/verified_user:", layout="wide")

with st.sidebar:
    st.markdown(ui.wordmark(38), unsafe_allow_html=True)
    choice = st.radio("Language / اللغة", list(LANGUAGES), horizontal=True, key="lang_choice")
st.session_state["lang"] = LANGUAGES[choice]
ui.inject_theme()
st.markdown(ui.skip_link(t("skip")), unsafe_allow_html=True)

pages = [
    st.Page("screens/home.py", title=t("nav_home"), icon=":material/home:", default=True),
    st.Page("screens/workbench.py", title=t("nav_workbench"), icon=":material/clinical_notes:"),
    st.Page("screens/queue.py", title=t("nav_queue"), icon=":material/assignment_late:"),
    st.Page("screens/results.py", title=t("nav_results"), icon=":material/monitoring:"),
]
st.navigation(pages).run()
