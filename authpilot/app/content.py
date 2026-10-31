"""Landing page content in English and Arabic. Product, model and technology names stay as they are."""

HOME = {
    "en": {
        "hero_eyebrow": "Hackathon project · Autonomous AI agents",
        "hero_lead": "Prior authorization, owned by an",
        "hero_accent": "AI agent.",
        "overlay": "Every claim cited. Every submission approved by a person.",
        "illustration": "Illustration",
        "sample_procedure": "Lumbar MRI · 72148",
        "sample_quote": "Evidence quote, copied from the chart",
        "pending": "pending sealed run",
        "goal": "Goal",
        "back_top": "Back to top",
        "hero_text": "An autonomous agent that owns prior authorization from the physician's order to the payer's "
                     "decision. It reads the chart and the payer policy, proves every criterion with cited evidence, "
                     "chases what is missing, writes the letter and the appeal, and stops only for one human approval.",
        "link_workbench": "Open the workbench", "link_results": "See the results",
        "stats": ["synthetic cases (dev + sealed)", "procedures: lumbar MRI and a biologic drug", "agent tools",
                  "loops (evidence, appeal) and one human gate", "tool calls at most per case"],
        "challenge_eyebrow": "The challenge",
        "challenge_title": "An agent that owns a whole business process, not one that answers questions",
        "challenge_text": "The brief asks for an AI agent that takes ownership of a complete process end to end. "
                          "AuthPilot does that for prior authorization and combines the three example use cases of the challenge.",
        "challenge_cards": [
            ("Contract review", "Compares the patient chart against the payer's policy clauses, flags unmet criteria "
                                "and cites the exact evidence for each one."),
            ("Employee onboarding", "Creates tasks and requests for missing documents, sends them to the clinic and "
                                    "tracks them until the evidence arrives."),
            ("Sales development", "Drafts personalized, evidence-based letters and appeals and follows up on each "
                                  "submission until the payer decides."),
        ],
        "problem_eyebrow": "The problem",
        "problem_title": "Prior authorization is slow, manual and restarts after every denial",
        "problem_steps_title": "What clinic staff do by hand, for every request",
        "problem_steps": [
            "Find out whether the payer requires authorization for the procedure or drug",
            "Locate the current payer policy and read its criteria",
            "Dig through the chart for notes, imaging, labs and therapy history",
            "Fill the payer form and write a medical-necessity letter",
            "Submit, wait, call for status, and rewrite the request after a denial",
        ],
        "problem_cost_title": "Why it is costly",
        "problem_costs": [
            "Policies are long, differ by payer and change often",
            "Evidence is scattered across the chart, so items are missed and requests are denied",
            "Every denial restarts the work, delaying care by days",
        ],
        "problem_estimate": "About 45 minutes of staff time per request is our working estimate, to be validated with "
                            "a clinic administrator.",
        "solution_eyebrow": "The solution",
        "solution_title": "One agent, two loops, one human gate",
        "flow": ["Physician order", "Read chart", "Check every policy criterion", "Request missing evidence",
                 "Draft letter", "Human approval", "Submit to payer", "Appeal if denied", "Decision"],
        "solution_text": "If evidence is missing, the agent asks the clinic and checks again. If the payer denies, it "
                         "writes an appeal that answers the denial reason. Approving the submission is the only step "
                         "that needs a person.",
        "autonomy": [
            ("Decides its next step", "From the current case state, not from a fixed script."),
            ("Loops on its own", "When evidence is missing and when a request is denied."),
            ("Uses real tools", "Chart lookup, policy search, criteria checks, letters, submission, status, appeals."),
            ("Stops at one gate", "A human approves the exact letter before anything reaches the payer."),
        ],
        "safety_eyebrow": "Safety and trust",
        "safety_title": "Every claim can be checked, and every step can be stopped",
        "safety": [
            ("No invented facts", "Every 'criterion met' cites text that code confirms is copied word for word from "
                                  "the chart. Unverifiable claims are dropped as 'evidence not found'."),
            ("Faithful letters", "A letter statement is kept only if its quotes are verbatim and every number in it "
                                 "appears in those quotes."),
            ("Human approval gate", "Submission is refused unless a person approved that exact letter. Any edit "
                                    "afterwards voids the approval. The agent cannot approve itself."),
            ("Abstains when unsure", "Unclear criteria or low confidence go to a person with a summary, instead of a guess."),
            ("Full audit trail", "Every tool call, model call, decision, fallback and human action is logged in an "
                                 "append-only log and replayed in the workbench timeline."),
            ("Synthetic data only", "All patients are generated. Data minimization, role-based access and encryption "
                                    "are part of the design for any pilot."),
        ],
        "targets_eyebrow": "Success targets",
        "targets_title": "What we will measure on a sealed test set",
        "targets_note": "These are goals, not results. They are measured on cases never used for tuning, alongside "
                        "baselines, ablations and robustness tests.",
        "targets_columns": ("Metric", "How it is measured", "Target"),
        "targets": [
            ("Criteria-match accuracy", "Agent verdict per criterion vs label", "90% or higher"),
            ("Final decision accuracy", "Submit or needs-evidence call vs label", "90% or higher"),
            ("Citation validity", "Cited spans that exist in the chart", "100%"),
            ("Missing-evidence detection", "Gaps found vs gaps planted", "85% or higher"),
            ("Robustness drop", "Perturbed vs unperturbed accuracy", "5 points or less"),
            ("Denial recovery", "Denied cases appealed successfully", "70% or higher"),
            ("Time per request", "Agent run time vs manual estimate", "Under 5 minutes"),
        ],
        "future_eyebrow": "Future enhancements",
        "future_title": "From hackathon build to clinic pilot",
        "future": [
            ("Pilot with one clinic", ["De-identified data", "Compliance review against Saudi PDPL and HIPAA-style principles",
                                       "Measure real time saved per request"]),
            ("More procedures and payers", ["Policy ingestion for new payers", "Automatic monitoring of policy changes",
                                            "The unseen third procedure as the first adaptation test"]),
            ("Real integrations", ["FHIR patient records instead of synthetic charts", "NPHIES-aligned submission messages",
                                   "Real fax and email delivery behind the approval gate"]),
            ("Smarter over time", ["Learn from payer outcomes to predict approval likelihood",
                                   "Improve letters from past appeals", "Arabic clinical notes, not only Arabic letters"]),
            ("Enterprise readiness", ["Role-based access and single sign-on", "Encryption at rest and in transit",
                                      "Multi-user workbench with assignment"]),
            ("Richer frontend", ["React or Next.js staff portal", "Clinic-facing upload portal for requested documents",
                                 "Live notifications when a case needs a person"]),
        ],
        "stack_eyebrow": "Full technology stack",
        "stack_title": "What it is built with",
        "stack_note": "Filled chips are running today. Outlined chips are planned. The lime chip is the main model.",
        "stack_titles": ["AI and reasoning", "Agent and backend", "Data and audit", "Frontend", "Quality and evaluation"],
        "footer": "AuthPilot is a hackathon prototype. All patient data is synthetic. LLM mode for this session: {mode}.",
    },
    "ar": {
        "hero_eyebrow": "مشروع هاكاثون · وكلاء الذكاء الاصطناعي المستقلون",
        "hero_lead": "الموافقة المسبقة، يتولاها",
        "hero_accent": "وكيل ذكي.",
        "overlay": "كل ادعاء موثّق. وكل إرسال توافق عليه شخص.",
        "illustration": "مثال",
        "sample_procedure": "رنين مغناطيسي للفقرات القطنية · 72148",
        "sample_quote": "اقتباس من السجل الطبي",
        "pending": "بانتظار التشغيل المحجوب",
        "goal": "هدف",
        "back_top": "العودة إلى الأعلى",
        "hero_text": "وكيل ذكي مستقل يتولى الموافقة المسبقة من أمر الطبيب حتى قرار الجهة الدافعة. يقرأ السجل الطبي "
                     "وسياسة الجهة الدافعة، ويُثبت كل معيار بدليل مقتبس، ويتابع المستندات الناقصة، ويكتب خطاب الضرورة "
                     "الطبية وخطاب التظلم، ولا يتوقف إلا لموافقة بشرية واحدة.",
        "link_workbench": "افتح منصة العمل", "link_results": "اطّلع على النتائج",
        "stats": ["حالة اصطناعية (تطوير ومحجوبة)", "إجراءان: رنين مغناطيسي للفقرات القطنية ودواء بيولوجي",
                  "أداة للوكيل", "حلقتان (الأدلة والتظلم) وبوابة بشرية واحدة", "حد أقصى لاستدعاءات الأدوات لكل حالة"],
        "challenge_eyebrow": "التحدي",
        "challenge_title": "وكيل يتولى عملية كاملة، لا مجرد الإجابة عن الأسئلة",
        "challenge_text": "يطلب التحدي وكيلًا ذكيًا يتولى مسؤولية عملية كاملة من بدايتها إلى نهايتها. ويقوم AuthPilot "
                          "بذلك للموافقة المسبقة، جامعًا حالات الاستخدام الثلاث الواردة في التحدي.",
        "challenge_cards": [
            ("مراجعة العقود", "يقارن السجل الطبي ببنود سياسة الجهة الدافعة، ويحدد المعايير غير المستوفاة، ويستشهد "
                              "بالدليل الدقيق لكل معيار."),
            ("تهيئة الموظفين", "ينشئ المهام وطلبات المستندات الناقصة، ويرسلها إلى العيادة، ويتابعها حتى وصول الأدلة."),
            ("تطوير المبيعات", "يكتب خطابات وتظلمات مخصصة مبنية على الأدلة، ويتابع كل طلب حتى صدور قرار الجهة الدافعة."),
        ],
        "problem_eyebrow": "المشكلة",
        "problem_title": "الموافقة المسبقة بطيئة ويدوية، وتبدأ من جديد بعد كل رفض",
        "problem_steps_title": "ما يفعله موظفو العيادة يدويًا لكل طلب",
        "problem_steps": [
            "التحقق مما إذا كانت الجهة الدافعة تشترط موافقة مسبقة على الإجراء أو الدواء",
            "إيجاد السياسة الحالية للجهة الدافعة وقراءة معاييرها",
            "البحث في السجل الطبي عن الملاحظات والتصوير والتحاليل وتاريخ العلاج",
            "تعبئة نموذج الجهة الدافعة وكتابة خطاب الضرورة الطبية",
            "الإرسال والانتظار والاتصال لمعرفة الحالة، ثم إعادة كتابة الطلب بعد الرفض",
        ],
        "problem_cost_title": "لماذا هي مكلفة",
        "problem_costs": [
            "السياسات طويلة، وتختلف من جهة دافعة لأخرى، وتتغير كثيرًا",
            "الأدلة متفرقة في السجل الطبي، فتُغفل بعض البنود وتُرفض الطلبات",
            "كل رفض يعيد العمل من البداية ويؤخر العلاج أيامًا",
        ],
        "problem_estimate": "نقدّر الوقت بنحو 45 دقيقة من وقت الموظف لكل طلب، وهو تقدير أولي سنتحقق منه مع إداري في عيادة.",
        "solution_eyebrow": "الحل",
        "solution_title": "وكيل واحد، حلقتان، وبوابة بشرية واحدة",
        "flow": ["أمر الطبيب", "قراءة السجل", "التحقق من كل معيار", "طلب الأدلة الناقصة", "كتابة الخطاب",
                 "موافقة بشرية", "الإرسال إلى الجهة الدافعة", "التظلم عند الرفض", "القرار"],
        "solution_text": "إذا نقص دليل، يطلبه الوكيل من العيادة ثم يتحقق مجددًا. وإذا رفضت الجهة الدافعة، يكتب تظلمًا "
                         "يعالج سبب الرفض. والموافقة على الإرسال هي الخطوة الوحيدة التي تحتاج إلى إنسان.",
        "autonomy": [
            ("يقرر خطوته التالية", "بناءً على حالة الطلب الحالية، لا وفق نص ثابت."),
            ("يكرر من تلقاء نفسه", "عند نقص الأدلة وعند رفض الطلب."),
            ("يستخدم أدوات حقيقية", "قراءة السجل، والبحث في السياسة، والتحقق من المعايير، والخطابات، والإرسال، "
                                    "ومتابعة الحالة، والتظلمات."),
            ("يتوقف عند بوابة واحدة", "يوافق إنسان على الخطاب نفسه قبل أن يصل أي شيء إلى الجهة الدافعة."),
        ],
        "safety_eyebrow": "الأمان والثقة",
        "safety_title": "كل ادعاء قابل للتحقق، وكل خطوة قابلة للإيقاف",
        "safety": [
            ("لا حقائق مختلقة", "كل معيار «مستوفى» يستشهد بنص يتحقق الكود من أنه منقول حرفيًا من السجل. "
                                "وتُحذف الادعاءات غير القابلة للتحقق بوصفها «دليلًا غير موجود»."),
            ("خطابات أمينة", "لا تُقبل عبارة في الخطاب إلا إذا كانت اقتباساتها حرفية وكل رقم فيها موجودًا في تلك الاقتباسات."),
            ("بوابة الموافقة البشرية", "يُرفض الإرسال ما لم يوافق شخص على هذا الخطاب تحديدًا، وأي تعديل لاحق يُبطل "
                                       "الموافقة، ولا يستطيع الوكيل الموافقة بنفسه."),
            ("يمتنع عند عدم اليقين", "تُحال المعايير غير الواضحة أو منخفضة الثقة إلى موظف مع ملخص، بدلًا من التخمين."),
            ("سجل تدقيق كامل", "يُسجَّل كل استدعاء أداة ونموذج وكل قرار وإجراء احتياطي وإجراء بشري في سجل لا يقبل "
                               "التعديل، ويُعرض في الخط الزمني لمنصة العمل."),
            ("بيانات اصطناعية فقط", "جميع المرضى مُولَّدون. وتقليل البيانات والصلاحيات حسب الأدوار والتشفير جزء من "
                                    "التصميم لأي تجربة فعلية."),
        ],
        "targets_eyebrow": "مؤشرات النجاح",
        "targets_title": "ما سنقيسه على مجموعة اختبار محجوبة",
        "targets_note": "هذه أهداف وليست نتائج، وتُقاس على حالات لم تُستخدم في الضبط، إلى جانب خطوط الأساس والتجارب "
                        "الإقصائية واختبارات المتانة.",
        "targets_columns": ("المؤشر", "طريقة القياس", "الهدف"),
        "targets": [
            ("دقة مطابقة المعايير", "حكم الوكيل لكل معيار مقارنة بالتصنيف", "90% أو أعلى"),
            ("دقة القرار النهائي", "قرار الإرسال أو طلب الأدلة مقارنة بالتصنيف", "90% أو أعلى"),
            ("صحة الاقتباسات", "الاقتباسات الموجودة فعلًا في السجل", "100%"),
            ("اكتشاف الأدلة الناقصة", "الثغرات المكتشفة مقارنة بالثغرات المزروعة", "85% أو أعلى"),
            ("انخفاض المتانة", "الدقة بعد التغيير مقارنة بالدقة قبله", "5 نقاط أو أقل"),
            ("استعادة الطلبات المرفوضة", "الطلبات المرفوضة التي نجح التظلم فيها", "70% أو أعلى"),
            ("الوقت لكل طلب", "مدة عمل الوكيل مقارنة بالتقدير اليدوي", "أقل من 5 دقائق"),
        ],
        "future_eyebrow": "التطويرات المستقبلية",
        "future_title": "من نموذج الهاكاثون إلى تجربة في عيادة",
        "future": [
            ("تجربة في عيادة واحدة", ["بيانات مُجهّلة الهوية", "مراجعة الامتثال لنظام حماية البيانات الشخصية السعودي "
                                      "ومبادئ مماثلة لـ HIPAA", "قياس الوقت الفعلي الموفَّر لكل طلب"]),
            ("إجراءات وجهات دافعة أكثر", ["إدخال سياسات جهات دافعة جديدة", "مراقبة تغييرات السياسات تلقائيًا",
                                          "الإجراء الثالث غير المرئي كأول اختبار للتكيف"]),
            ("تكاملات حقيقية", ["سجلات المرضى بمعيار FHIR بدلًا من السجلات الاصطناعية", "رسائل إرسال متوافقة مع نفيس (NPHIES)",
                                "إرسال فعلي بالفاكس والبريد الإلكتروني خلف بوابة الموافقة"]),
            ("أذكى مع الوقت", ["التعلم من قرارات الجهات الدافعة للتنبؤ باحتمال الموافقة", "تحسين الخطابات من التظلمات السابقة",
                               "ملاحظات سريرية عربية، لا الخطابات العربية فقط"]),
            ("جاهزية المؤسسات", ["صلاحيات حسب الأدوار وتسجيل دخول موحد", "التشفير أثناء التخزين والنقل",
                                 "منصة عمل متعددة المستخدمين مع إسناد المهام"]),
            ("واجهة أغنى", ["بوابة موظفين بتقنية React أو Next.js", "بوابة للعيادات لرفع المستندات المطلوبة",
                            "تنبيهات فورية عندما تحتاج حالة إلى موظف"]),
        ],
        "stack_eyebrow": "التقنيات المستخدمة",
        "stack_title": "مكوّنات النظام",
        "stack_note": "الرقائق المملوءة تعمل اليوم، والرقائق المحددة بخط مخطط لها، والرقاقة الليمونية هي النموذج الرئيسي.",
        "stack_titles": ["الذكاء الاصطناعي والاستدلال", "الوكيل والخادم", "البيانات والتدقيق", "الواجهة", "الجودة والتقييم"],
        "footer": "AuthPilot نموذج أولي لهاكاثون، وجميع بيانات المرضى اصطناعية. وضع النموذج في هذه الجلسة: {mode}.",
    },
}
