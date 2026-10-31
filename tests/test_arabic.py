import re
from pathlib import Path

import pytest

from authpilot import config, gate, i18n, store
from authpilot.agent import auto_approver, run_case
from authpilot.payer_mock import app as payer_app
from authpilot.schemas import Status
from authpilot.tools._common import ToolRefused
from authpilot.tools.check_criteria import check_criteria
from authpilot.tools.draft_letter import draft_letter
from authpilot.tools.submit_request import submit_request
from helpers import appeal_case, clean_case, start

DASHBOARD = str(Path(__file__).resolve().parents[1] / "authpilot" / "app" / "dashboard.py")
NUMBER = re.compile(r"\d+(?:\.\d+)?")
ARABIC = re.compile(r"[\u0600-\u06FF]")


def _ready(case):
    case_id = start(case)
    check_criteria(case_id)
    draft_letter(case_id)
    return store.get_case(case_id)


def test_arabic_letter_quotes_every_statement_verbatim_and_adds_no_numbers():
    order, chart, label = case = clean_case()
    state = _ready(case)
    assert state.letter_ar and ARABIC.search(state.letter_ar)
    for statement in state.letter_statements:
        for evidence in statement.evidence:
            assert f'"{evidence.span_text}"' in state.letter_ar
            assert evidence.doc_id in state.letter_ar
            assert evidence.verify(chart)
    assert set(NUMBER.findall(state.letter_ar)) <= set(NUMBER.findall(state.letter))
    for name in ("العلاج التحفظي", "فحص العلامات التحذيرية", "الفحص العصبي", "عدم وجود تصوير حديث"):
        assert name in state.letter_ar
    assert i18n.TRANSLATION_NOTE in state.letter_ar


def test_approval_covers_both_versions():
    state = _ready(clean_case())
    gate.approve(state.case_id, "Sara")
    state = store.get_case(state.case_id)
    state.letter_ar += "\nتعديل بعد الموافقة"
    store.save_case(state)
    with pytest.raises(ToolRefused, match="human approval"):
        submit_request(state.case_id)


def test_submitted_package_carries_the_arabic_letter():
    state = _ready(clean_case())
    gate.approve(state.case_id, "Sara")
    submission_id = submit_request(state.case_id)
    package = payer_app._packages[submission_id]
    assert package.letter == state.letter and package.letter_ar == state.letter_ar


def test_english_only_mode(monkeypatch):
    monkeypatch.setattr(config, "LETTER_LANGUAGES", ["en"])
    state = _ready(clean_case())
    assert state.letter_ar is None
    assert gate.letter_for(state, "initial") == state.letter
    assert gate.letters_for(state, "initial") == [("en", state.letter)]


def test_arabic_appeal_answers_the_denial_with_the_flowsheet_quote():
    order, chart, label = appeal_case()
    state, _ = run_case(label.case_id, order, approver=auto_approver("Sara"))
    assert state.status is Status.approved
    assert state.appeal_letter_ar and "DAS28-SCORE" in state.appeal_letter_ar and "تظلّم" in state.appeal_letter_ar
    for statement in state.appeal_statements:
        for evidence in statement.evidence:
            assert f'"{evidence.span_text}"' in state.appeal_letter_ar


def test_unknown_criterion_names_fall_back_to_english():
    assert i18n.criterion_name_ar("Something new") == "Something new"
    assert i18n.criterion_name_ar("Disease activity") == "نشاط المرض"


def _app():
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    return AppTest.from_file(DASHBOARD, default_timeout=30)


def _markdown(at) -> str:
    return "\n".join(m.value for m in at.markdown)


def test_landing_page_in_arabic_is_right_to_left():
    at = _app().run()
    at.radio(key="lang_choice").set_value("العربية").run()
    assert not at.exception
    text = _markdown(at)
    for heading in ("التحدي", "المشكلة", "الحل", "الأمان والثقة", "التطويرات المستقبلية", "التقنيات المستخدمة"):
        assert heading in text, heading
    assert "direction: rtl" in text


def test_workbench_in_arabic_runs_and_approves_a_case():
    _, _, label = clean_case()
    at = _app().run()
    at.radio(key="lang_choice").set_value("العربية").run()
    at.switch_page("screens/workbench.py").run()
    at.selectbox(key="case_name").select(label.case_id.replace("dev_", "case_")).run()
    at.button(key="run_agent").click().run()
    assert not at.exception
    text = _markdown(at)
    assert "مطلوب موافقة بشرية" in text and 'dir="rtl"' in text and 'dir="ltr"' in text
    at.text_input(key="reviewer").input("سارة").run()
    at.button(key="approve").click().run()
    assert not at.exception
    state = store.reload(label.case_id)
    assert state.status is Status.approved and state.approval.reviewer == "سارة"
    assert "تمت الموافقة" in _markdown(at)
