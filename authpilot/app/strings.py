"""Interface strings in English and Arabic. Pages call t(key) with the language chosen in the sidebar.
Chart text, quotes, case ids and technical names are never translated."""

import streamlit as st

from authpilot.i18n import STATUS_AR

LANGUAGES = {"English": "en", "العربية": "ar"}

STRINGS = {
    "en": {
        "nav_home": "Home", "nav_workbench": "Workbench", "nav_queue": "Escalation queue", "nav_results": "Results",
        "language": "Language", "skip": "Skip to content", "gap_label": "GAP",
        "start_case": "Start a case", "dev_case": "Dev case", "run_agent": "Run agent", "open_case": "Open a case",
        "case": "Case", "refresh": "Refresh", "agent_working": "Agent working...", "submitting": "Submitting...",
        "workbench": "Workbench",
        "workbench_intro": "Pick a dev case in the sidebar and press Run agent. The agent works until the case is "
                           "finished or needs a person.",
        "case_label": "Case", "patient_line": "Patient {patient} · order {order} · ordered by {provider} · request date {date}",
        "tool_calls": "Tool calls", "clinic_requests": "Clinic requests", "appeals": "Appeals", "submissions": "Submissions",
        "payer": "payer", "escalated_banner": "Escalated to a person: {reason}", "queued_banner": "Queued for retry: {reason}",
        "retry_now": "Retry now", "denial_banner": "Last payer denial: {reason}",
        "approval_required": "Human approval required", "review_letter": "Review the {kind} letter",
        "kind_initial": "initial", "kind_appeal": "appeal",
        "approval_note": "Approving binds your name to this exact text, in every language shown. The agent submits it "
                         "to the payer right after.",
        "english_version": "English (submitted letter)", "arabic_version": "Arabic version",
        "your_name": "Your name", "reject_reason": "Reason, if rejecting", "approve": "Approve and submit",
        "reject": "Reject", "criteria_checklist": "Criteria checklist", "not_checked": "Criteria have not been checked yet.",
        "confidence": "confidence", "source": "source", "agent_timeline": "Agent timeline",
        "show_details": "Show tool and model calls", "raw_table": "Raw audit table",
        "tab_letter": "Medical-necessity letter", "tab_appeal": "Appeal letter", "tab_requests": "Requests to the clinic",
        "no_letter": "No letter yet. It is drafted once every criterion is met.",
        "no_appeal": "No appeal. One is drafted only after a payer denial.", "no_requests": "No requests were needed.",
        "documents_received": "Documents received: {docs}", "nothing_yet": "nothing yet",
        "needs_approve": "approve {kind} letter", "needs_escalated": "escalated", "needs_queued": "queued",
        "queue_eyebrow": "Escalation queue", "queue_title": "Cases waiting for a person",
        "queue_intro": "Approvals, escalations and cases queued after an outage. Open one to act on it in the workbench.",
        "queue_empty": "Nothing is waiting. Cases appear here when they need approval, are escalated, or are queued.",
        "open": "Open", "waiting_review": "Waiting for review.",
        "results_eyebrow": "Results", "results_title": "Saved evaluation runs (dev split)",
        "results_intro": "Every run is saved with its seed, model names and prompt version so any number can be "
                         "reproduced. The sealed test split is run only once, at the end.",
        "full_eval": "Full evaluation (make eval): agent vs baselines, ablations, robustness, faults, coverage",
        "no_full_eval": "No full evaluation saved for this mode yet. Run `make eval`.",
        "criterion_runs": "Criterion-level runs", "run_eval_button": "Run the criteria evaluation on dev now",
        "evaluating": "Evaluating 60 dev cases...", "no_runs": "No saved runs yet. Run `make eval-criteria` or press the button above.",
        "run_select": "Run",
        "stub_mode_banner": "Stub mode: results are not real",
        "stub_warning": "These numbers come from the offline stub model, a keyword heuristic written alongside the case "
                        "templates. They show the pipeline works; they do not measure the agent's accuracy.",
        "per_status": "Per status", "confusion": "Confusion (expected -> predicted)",
        "accuracy_by_type": "Accuracy by case type", "worst_failures": "Worst failures", "none_in_run": "None in this run.",
        "expected": "expected", "got": "got", "cited_by_agent": "cited by the agent",
        "m_accuracy": "criterion accuracy", "m_false_met": "false-met rate", "m_citations": "citation validity",
        "m_invalid": "invalid output rate", "m_tokens": "tokens per case",
    },
    "ar": {
        "nav_home": "الرئيسية", "nav_workbench": "منصة العمل", "nav_queue": "قائمة الإحالة", "nav_results": "النتائج",
        "language": "اللغة", "skip": "تخطي إلى المحتوى", "gap_label": "فجوة",
        "start_case": "بدء حالة", "dev_case": "حالة تطوير", "run_agent": "تشغيل الوكيل", "open_case": "فتح حالة",
        "case": "الحالة", "refresh": "تحديث", "agent_working": "الوكيل يعمل...", "submitting": "جارٍ الإرسال...",
        "workbench": "منصة العمل",
        "workbench_intro": "اختر حالة من القائمة الجانبية واضغط «تشغيل الوكيل». يعمل الوكيل حتى تكتمل الحالة "
                           "أو تحتاج إلى قرار من موظف.",
        "case_label": "الحالة", "patient_line": "المريض {patient} · الطلب {order} · الطبيب {provider} · تاريخ الطلب {date}",
        "tool_calls": "استدعاءات الأدوات", "clinic_requests": "طلبات العيادة", "appeals": "التظلمات", "submissions": "الإرسالات",
        "payer": "الجهة الدافعة", "escalated_banner": "أُحيلت الحالة إلى موظف: {reason}",
        "queued_banner": "بانتظار إعادة المحاولة: {reason}", "retry_now": "أعد المحاولة الآن",
        "denial_banner": "آخر رفض من الجهة الدافعة: {reason}",
        "approval_required": "مطلوب موافقة بشرية", "review_letter": "مراجعة خطاب {kind}",
        "kind_initial": "الطلب", "kind_appeal": "التظلم",
        "approval_note": "تربط الموافقة اسمك بهذا النص تحديدًا بكل اللغات المعروضة، ثم يرسله الوكيل إلى الجهة الدافعة مباشرة.",
        "english_version": "النسخة الإنجليزية (الخطاب المُرسل)", "arabic_version": "النسخة العربية",
        "your_name": "اسمك", "reject_reason": "سبب الرفض (عند الرفض)", "approve": "الموافقة والإرسال",
        "reject": "رفض", "criteria_checklist": "قائمة المعايير", "not_checked": "لم يتم التحقق من المعايير بعد.",
        "confidence": "درجة الثقة", "source": "المصدر", "agent_timeline": "الخط الزمني للوكيل",
        "show_details": "إظهار استدعاءات الأدوات والنموذج", "raw_table": "جدول سجل التدقيق",
        "tab_letter": "خطاب الضرورة الطبية", "tab_appeal": "خطاب التظلم", "tab_requests": "الطلبات المرسلة إلى العيادة",
        "no_letter": "لا يوجد خطاب بعد. يُكتب الخطاب عند استيفاء جميع المعايير.",
        "no_appeal": "لا يوجد تظلم. يُكتب التظلم فقط بعد رفض الجهة الدافعة.", "no_requests": "لم تكن هناك حاجة إلى طلبات.",
        "documents_received": "المستندات المستلمة: {docs}", "nothing_yet": "لا شيء بعد",
        "needs_approve": "الموافقة على خطاب {kind}", "needs_escalated": "مُحال إلى موظف", "needs_queued": "بانتظار إعادة المحاولة",
        "queue_eyebrow": "قائمة الإحالة", "queue_title": "حالات بانتظار قرار من موظف",
        "queue_intro": "الموافقات والحالات المُحالة والحالات المؤجلة بعد انقطاع الخدمة. افتح أي حالة للتعامل معها في منصة العمل.",
        "queue_empty": "لا توجد حالات بانتظار. تظهر الحالات هنا عند حاجتها إلى موافقة أو إحالتها أو تأجيلها.",
        "open": "فتح", "waiting_review": "بانتظار المراجعة.",
        "results_eyebrow": "النتائج", "results_title": "نتائج التقييم المحفوظة (بيانات التطوير)",
        "results_intro": "يُحفظ كل تشغيل مع البذرة العشوائية وأسماء النماذج وإصدار التعليمات، لإمكانية إعادة إنتاج أي رقم. "
                         "أما مجموعة الاختبار المحجوبة فتُشغَّل مرة واحدة فقط في النهاية.",
        "full_eval": "التقييم الكامل (make eval): الوكيل مقابل خطوط الأساس والتجارب الإقصائية والمتانة والأعطال والتغطية",
        "no_full_eval": "لا يوجد تقييم كامل محفوظ لهذا الوضع بعد. شغّل `make eval`.",
        "criterion_runs": "تقييمات المعايير", "run_eval_button": "شغّل تقييم المعايير على بيانات التطوير الآن",
        "evaluating": "جارٍ تقييم 60 حالة...", "no_runs": "لا توجد نتائج محفوظة بعد. شغّل `make eval-criteria` أو اضغط الزر أعلاه.",
        "run_select": "التشغيل",
        "stub_mode_banner": "وضع تجريبي: النتائج ليست حقيقية",
        "stub_warning": "هذه الأرقام صادرة عن النموذج التجريبي غير المتصل، وهو قواعد كلمات مفتاحية كُتبت مع قوالب الحالات. "
                        "تُثبت أن المنظومة تعمل، لكنها لا تقيس دقة الوكيل الفعلية.",
        "per_status": "حسب الحالة", "confusion": "مصفوفة الالتباس (المتوقع -> المتنبأ به)",
        "accuracy_by_type": "الدقة حسب نوع الحالة", "worst_failures": "أسوأ الأخطاء", "none_in_run": "لا يوجد في هذا التشغيل.",
        "expected": "المتوقع", "got": "النتيجة", "cited_by_agent": "اقتباس الوكيل",
        "m_accuracy": "دقة المعايير", "m_false_met": "نسبة الاستيفاء الخاطئ", "m_citations": "صحة الاقتباسات",
        "m_invalid": "نسبة المخرجات غير الصالحة", "m_tokens": "الرموز لكل حالة",
    },
}


def lang() -> str:
    return st.session_state.get("lang", "en")


def t(key: str, **kwargs) -> str:
    text = STRINGS[lang()].get(key, STRINGS["en"][key])
    return text.format(**kwargs) if kwargs else text


def status_label(status: str) -> str:
    """Display name for a status or verdict key in the current language."""
    if lang() == "ar":
        return STATUS_AR.get(status, status.replace("_", " "))
    return status.replace("_", " ")
