"""Arabic versions of the letters, written by code from fixed templates.

Clinical evidence is never translated: every quote stays verbatim in the language of the chart,
with its source document, so the Arabic letter carries exactly the facts the English one does and
both can be checked against the chart. Only the framing text is Arabic.
"""

from authpilot.schemas import CaseState, LetterStatement

# Arabic names for the criteria of the policies in this repository, keyed by the English name
# (the first sentence of the policy section). Unknown names fall back to the English name.
CRITERION_NAMES_AR = {
    "Conservative therapy": "العلاج التحفظي",
    "Red-flag screening": "فحص العلامات التحذيرية",
    "Neurological examination": "الفحص العصبي",
    "No recent imaging": "عدم وجود تصوير حديث",
    "Confirmed diagnosis": "تشخيص مؤكد",
    "Prior conventional therapy": "العلاج التقليدي السابق",
    "Tuberculosis screening": "فحص السل",
    "Disease activity": "نشاط المرض",
    "Body mass index": "مؤشر كتلة الجسم",
    "Lifestyle program": "برنامج نمط الحياة",
    "Thyroid cancer screening": "فحص سرطان الغدة الدرقية",
}

STATUS_AR = {
    "intake": "استلام",
    "checking": "قيد التحقق",
    "needs_evidence": "بحاجة إلى مستندات",
    "ready_for_approval": "بانتظار الموافقة",
    "submitted": "مُرسل",
    "approved": "تمت الموافقة",
    "denied": "مرفوض",
    "appealing": "قيد التظلم",
    "escalated": "مُحال إلى موظف",
    "met": "مستوفى",
    "not_met": "غير مستوفى",
    "unclear": "غير واضح",
    "queued": "بانتظار إعادة المحاولة",
}

TRANSLATION_NOTE = ("ملاحظة: هذه نسخة عربية من الرسالة الإنجليزية. الاقتباسات من السجل الطبي منقولة حرفيًا "
                    "بلغتها الأصلية دون ترجمة، مع ذكر مصدر كل اقتباس.")


def criterion_name_ar(name: str) -> str:
    return CRITERION_NAMES_AR.get(name, name)


def _statement_ar(statement: LetterStatement, name: str) -> str:
    quotes = " ".join(f'"{e.span_text}"' for e in statement.evidence)
    sources = "، ".join(sorted({e.doc_id for e in statement.evidence}))
    return f"{criterion_name_ar(name)}: ورد في السجل الطبي ما يلي: {quotes} [المصدر: {sources}]"


def render_letter_ar(state: CaseState, policy_id: str, statements: list[LetterStatement],
                     names: dict[str, str]) -> str:
    """names: criterion_id -> English criterion name."""
    order = state.order
    lines = [
        f"التاريخ: {order.request_date.isoformat()}",
        f"إلى: إدارة المراجعة الطبية لدى {order.payer_id}",
        f"الموضوع: طلب موافقة مسبقة على {order.procedure_name} ({order.procedure_code})",
        f"المريض: {order.patient_id}    رقم الطلب: {order.order_id}",
        f"الطبيب المعالج: {order.ordering_provider}",
        "",
        f"نطلب الموافقة على {order.procedure_name} وفقًا للسياسة {policy_id}. "
        "ويوثّق السجل الطبي للمريض كل معيار من معايير التغطية على النحو التالي:",
        "",
    ]
    for i, statement in enumerate(statements, 1):
        lines.append(f"{i}. {_statement_ar(statement, names.get(statement.criterion_id, statement.criterion_id))}")
    lines += [
        "",
        "كل ما ورد أعلاه مقتبس حرفيًا من السجلات الطبية المرفقة.",
        "",
        "مع خالص التحية،",
        f"{order.ordering_provider} (مسودة أعدّها AuthPilot لمراجعة الموظفين)",
        "",
        TRANSLATION_NOTE,
    ]
    return "\n".join(lines)


def render_appeal_ar(state: CaseState, statements: list[LetterStatement], names: dict[str, str],
                     attachments: list[str]) -> str:
    order = state.order
    lines = [
        f"التاريخ: {order.request_date.isoformat()}",
        f"إلى: قسم التظلمات لدى {order.payer_id}",
        f"الموضوع: تظلّم على الطلب {state.submission_id} بشأن {order.procedure_name} ({order.procedure_code})",
        f"المريض: {order.patient_id}    رقم الطلب: {order.order_id}",
        f"سبب الرفض كما ورد من الجهة الدافعة: {state.denial_reason}",
        "",
        f"نتظلّم على قرار الرفض ذي الرمز {state.denial_code} المتعلق بالبند {state.denial_ref} من السياسة. "
        "ويوثّق السجل الطبي هذا المعيار على النحو التالي:",
        "",
    ]
    for i, statement in enumerate(statements, 1):
        lines.append(f"{i}. {_statement_ar(statement, names.get(statement.criterion_id, statement.criterion_id))}")
    lines += [
        "",
        f"السجلات الداعمة مرفقة: {'، '.join(attachments)}. ونطلب إعادة النظر وفقًا لأحكام التظلّم في السياسة.",
        "",
        "مع خالص التحية،",
        f"{order.ordering_provider} (مسودة أعدّها AuthPilot لمراجعة الموظفين)",
        "",
        TRANSLATION_NOTE,
    ]
    return "\n".join(lines)
