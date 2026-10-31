from pathlib import Path

import pytest

from authpilot import config, store
from authpilot.agent import auto_approver, run_case
from authpilot.app import ui, views
from authpilot.eval import criteria_eval
from authpilot.schemas import Status
from helpers import clean_case, unsupplied_gap_case

DASHBOARD = str(Path(__file__).resolve().parents[1] / "authpilot" / "app" / "dashboard.py")


def _app():
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    return AppTest.from_file(DASHBOARD, default_timeout=30)


def _all_markdown(at) -> str:
    return "\n".join(m.value for m in at.markdown)


# Data shaping ------------------------------------------------------------------------------


def test_checklist_shows_every_criterion_with_quotes():
    order, chart, label = clean_case()
    state, _ = run_case(label.case_id, order)
    rows = views.checklist_rows(state)
    assert [r["criterion"].split(":")[-1] for r in rows] == ["2.1", "2.2", "2.3", "2.4"]
    for row in rows:
        assert row["status_key"] == "met" and row["quotes"]
        for doc_id, quote in row["quotes"]:
            assert quote in chart[doc_id]


def test_timeline_has_tool_calls_verdicts_and_human_actions():
    order, _, label = clean_case()
    run_case(label.case_id, order, approver=auto_approver("Sara"))
    rows = views.timeline_rows(label.case_id)
    kinds = {r["kind"] for r in rows}
    assert {"verdict", "step", "human", "event"} <= kinds
    assert not kinds & {"model", "tool call", "tool result"}
    assert any("submission_id" in r["detail"] for r in rows if r["kind"] == "step")
    detailed = {r["kind"] for r in views.timeline_rows(label.case_id, include_model_calls=True, include_tool_calls=True)}
    assert {"model", "tool call", "tool result"} <= detailed


def test_timeline_shows_only_the_latest_run_including_resumes():
    from authpilot import gate
    from authpilot.agent import resume_case

    order, _, label = clean_case()
    run_case(label.case_id, order, approver=auto_approver("First"))
    run_case(label.case_id, order)
    gate.approve(label.case_id, "Second")
    resume_case(label.case_id)
    rows = views.timeline_rows(label.case_id)
    humans = [r["detail"] for r in rows if r["kind"] == "human"]
    assert len(humans) == 1 and humans[0].startswith("Second")
    assert sum(r["detail"].startswith("run_started") for r in rows) == 1
    assert any(r["detail"].startswith("run_resumed") for r in rows)


def test_queue_lists_cases_waiting_for_a_person():
    waiting = clean_case()
    escalated = unsupplied_gap_case()
    run_case(waiting[2].case_id, waiting[0])
    run_case(escalated[2].case_id, escalated[0])
    rows = {r["case"]: r for r in views.queue_rows()}
    assert rows[waiting[2].case_id]["needs"] == "approve initial letter"
    assert rows[escalated[2].case_id]["needs"] == "escalated" and rows[escalated[2].case_id]["reason"]


def test_list_case_ids_reads_the_store_directory():
    order, _, label = clean_case()
    run_case(label.case_id, order)
    store.clear()
    assert label.case_id in store.list_case_ids()


def test_ui_components_escape_dynamic_text():
    hostile = '<script>alert("x")</script>'
    for markup in (ui.quote(hostile, hostile), ui.card(hostile, ""), ui.badge(hostile),
                   ui.timeline([{"time": "1", "kind": "step", "detail": hostile}])):
        assert "<script>" not in markup and "&lt;script&gt;" in markup


# Pages -------------------------------------------------------------------------------------


def test_landing_page_covers_challenge_problem_solution_future_and_stack():
    at = _app().run()
    assert not at.exception
    text = _all_markdown(at)
    for heading in ("The challenge", "The problem", "The solution", "Safety and trust", "Success targets",
                    "Future enhancements", "Full technology stack"):
        assert heading in text, heading
    assert config.AGENT_MODEL in text
    assert "Stub mode: results are not real" in text


def test_queue_and_results_pages_render(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RESULTS_DIR", tmp_path / "results")
    order, _, label = unsupplied_gap_case()
    run_case(label.case_id, order)
    at = _app().run()
    at.switch_page("screens/queue.py").run()
    assert not at.exception and label.case_id in _all_markdown(at)

    at.switch_page("screens/results.py").run()
    assert not at.exception and "No saved runs yet" in _all_markdown(at)

    criteria_eval.save_report(criteria_eval.run("dev"))
    at.switch_page("screens/results.py").run()
    assert not at.exception and "offline stub model" in _all_markdown(at)


def test_workbench_runs_a_case_and_approves_it_from_the_ui():
    _, _, label = clean_case()
    at = _app().run()
    at.switch_page("screens/workbench.py").run()
    assert not at.exception
    at.selectbox(key="case_name").select(label.case_id.replace("dev_", "case_")).run()
    at.button(key="run_agent").click().run()
    assert not at.exception
    assert store.reload(label.case_id).status is Status.ready_for_approval
    assert "Human approval required" in _all_markdown(at)

    at.text_input(key="reviewer").input("Sara").run()
    at.button(key="approve").click().run()
    assert not at.exception
    state = store.reload(label.case_id)
    assert state.status is Status.approved and state.approval.reviewer == "Sara"
    assert "payer approved" in _all_markdown(at)
