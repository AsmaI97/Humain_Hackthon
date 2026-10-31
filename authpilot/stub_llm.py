"""Deterministic offline stand-in for the LLM (LLM_MODE=stub).

It reads the same prompts as the real model and answers through the same tool schemas, so the
whole pipeline runs without an API key. It is a sentence-level keyword heuristic written by
the developers, who also wrote the case templates. Its scores show that the plumbing works.
They say nothing about the agent's real accuracy, which must come from a real model run.
"""

import hashlib
import json
import re
from datetime import date
from typing import Any

from authpilot.prompts import APPEAL_TOOL, CHECK_TOOL, EXTRACT_TOOL, LETTER_TOOL, SINGLE_TOOL

STUB_MODEL = "stub-heuristic-v1"

SYNONYMS = {
    "therapy": ["physical therapy", "pt", "nsaid", "nsaids", "naproxen", "ibuprofen", "meloxicam"],
    "red-flag": ["red flag", "red flags", "bowel", "bladder", "saddle", "incontinence", "urinary retention",
                 "cauda equina", "fever", "weight loss", "groin", "cancer"],
    "neurological": ["neurologic", "neuro", "reflexes", "strength", "sensation", "straight-leg raise"],
    "examination": ["exam"],
    "imaging": ["mri", "radiographs"],
    "diagnosis": ["rheumatoid arthritis", "impression", "assessment"],
    "conventional": ["methotrexate", "dmard"],
    "tuberculosis": ["tb", "quantiferon", "igra", "interferon-gamma", "tuberculin"],
    "activity": ["das28"],
}
STOPWORDS = {"no", "prior", "recent", "the", "of", "and", "or", "a", "an", "to", "for"}

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}

OTHER_PERSON = re.compile(r"\b(mother|father|sister|brother|spouse|son|daughter|family history)\b")
HISTORICAL = re.compile(r"\b(?:in|at a) (?:19|20)\d\d\b")
PLAN = re.compile(r"\b(consider|plan|will obtain|ordering|referral|deferred|pending|start)\b")
UNCERTAIN = re.compile(
    r"\b(several|unknown|unclear|not available|short course|indeterminate|versus|not completed|"
    r"limited by|per patient report|in the past|possible)\b"
)
NEGATED_HISTORY = re.compile(r"\b(no prior|not previously|never)\b")
ABSENCE_OK = re.compile(r"\b(no|denies|negative|without)\b")
INTOLERANCE = re.compile(r"\b(intolerance|toxicity|not tolerated)\b")
DURATION = re.compile(r"\b(\d+|" + "|".join(NUMBER_WORDS) + r")[- ](weeks?|months?)\b")
ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
STANDALONE_NUMBER = re.compile(r"(?<![\w.\-/])(\d+(?:\.\d+)?)(?![\w\-/])")


def _tokens_count(text: str) -> int:
    return max(1, len(text) // 4)


def _tool_response(request: dict[str, Any], tool: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    digest = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()[:16]
    prompt_len = len(json.dumps(request.get("messages", [])))
    return {
        "content": [{"type": "tool_use", "id": f"stub_{digest}", "name": tool, "input": tool_input}],
        "stop_reason": "tool_use",
        "model": STUB_MODEL,
        "usage": {"input_tokens": _tokens_count("x" * prompt_len), "output_tokens": _tokens_count(json.dumps(tool_input))},
    }


def _first_user_text(request: dict[str, Any]) -> str:
    for message in request.get("messages", []):
        if message["role"] == "user" and isinstance(message["content"], str):
            return message["content"]
    return ""


def respond(request: dict[str, Any]) -> dict[str, Any]:
    tool = (request.get("tool_choice") or {}).get("name")
    prompt = _first_user_text(request)
    if tool == EXTRACT_TOOL:
        return _tool_response(request, tool, _extract(prompt))
    if tool == CHECK_TOOL:
        return _tool_response(request, tool, _check(prompt))
    if tool in (LETTER_TOOL, APPEAL_TOOL):
        return _tool_response(request, tool, _letter(prompt))
    if tool == SINGLE_TOOL:
        return _tool_response(request, tool, _single(prompt))
    if "<case_state>" in prompt:
        return _plan(request, prompt)
    return {
        "content": [{"type": "text", "text": "stub model: unsupported request"}],
        "stop_reason": "end_turn",
        "model": STUB_MODEL,
        "usage": {"input_tokens": 0, "output_tokens": 0},
    }


# Criteria extraction ------------------------------------------------------------------------


def _extract(prompt: str) -> dict[str, Any]:
    criteria = []
    for ref, heading, text in re.findall(r'<section ref="([^"]+)" heading="([^"]*)">(.*?)</section>', prompt, re.S):
        if re.fullmatch(r"\d+\.\d+", ref) and "criteria" in heading.lower():
            criteria.append({"section_ref": ref, "name": text.split(". ")[0].strip()[:120]})
    return {"criteria": criteria}


def _single(prompt: str) -> dict[str, Any]:
    """Single-prompt baseline: find criteria the same way as extraction, then check each one."""
    head = prompt.split("<chart>", 1)[0]
    chart_part = "<chart>" + prompt.split("<chart>", 1)[1] if "<chart>" in prompt else ""
    rd = re.search(r"<request_date>[^<]*</request_date>", head)
    results = []
    for ref, heading, text in re.findall(r'<section ref="([^"]+)" heading="([^"]*)">(.*?)</section>', head, re.S):
        if re.fullmatch(r"\d+\.\d+", ref) and "criteria" in heading.lower():
            pseudo = f"{rd.group(0) if rd else ''}\n<criterion section_ref=\"{ref}\">{text}</criterion>\n{chart_part}"
            results.append({"section_ref": ref, **_check(pseudo)})
    return {"results": results}


# Letter drafting --------------------------------------------------------------------------


def _letter(prompt: str) -> dict[str, Any]:
    statements = []
    pattern = r'<criterion id="([^"]+)" section_ref="[^"]*" name="([^"]*)">(.*?)</criterion>'
    for cid, name, body in re.findall(pattern, prompt, re.S):
        quotes = re.findall(r'<evidence doc_id="([^"]+)">(.*?)</evidence>', body, re.S)
        if quotes:
            doc_id, quote = quotes[0]
            statements.append({"criterion_id": cid, "text": f'{name} is documented in the record: "{quote}"',
                               "quotes": [{"doc_id": doc_id, "quote": quote}]})
    return {"statements": statements}


# Agent planning ---------------------------------------------------------------------------


def next_action(state: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """A fixed decision policy over the case state summary. Also used as the fallback planner."""
    case = {"case_id": state["case_id"]}
    allowed = set(state.get("allowed_tools", []))

    def choose(name: str, args: dict[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
        return (name, args if args is not None else case) if name in allowed else ("escalate", {
            **case, "reason": f"planner wanted {name} but it is not allowed"})

    if state["status"] == "submitted":
        return choose("check_status")
    if state["status"] == "denied":
        refused = "draft_appeal" in (state.get("last_error") or "")
        if state["appeals"] < state["max_appeals"] and not refused:
            return choose("draft_appeal", {**case, "denial_reason": state["denial_reason"]})
        reason = f"denial cannot be appealed further: {state['denial_reason']}"
        return choose("escalate", {**case, "reason": reason[:290]})
    if state["status"] in ("appealing", "ready_for_approval"):
        return choose("submit_request")
    if not state["record_fetched"]:
        return choose("get_patient_record", {"patient_id": state["patient_id"]})
    if not state["criteria_checked"] or state["new_documents_since_check"]:
        return choose("check_criteria")
    if state["gaps"]:
        last = state.get("last_info_request")
        if state["gap_loops"] < state["max_gap_loops"] and not (last and last["new_documents"] == 0):
            return choose("request_missing_info")
        return choose("escalate", {**case, "reason": "open gaps could not be resolved with the clinic"})
    if not state["letter_drafted"]:
        return choose("draft_letter")
    if not state["submitted"]:
        return choose("submit_request")
    return choose("check_status")


def _plan(request: dict[str, Any], prompt: str) -> dict[str, Any]:
    match = re.search(r"<case_state>(.*?)</case_state>", prompt, re.S)
    state = json.loads(match.group(1))
    name, args = next_action(state)
    return _tool_response(request, name, args)


# Criterion check --------------------------------------------------------------------------


def _anchors(criterion_text: str) -> list[str]:
    title = criterion_text.split(". ")[0].lower()
    words = [w.strip(".,;:()") for w in title.split()]
    anchors = []
    for word in words:
        if word and word not in STOPWORDS:
            anchors.append(word)
            anchors.extend(SYNONYMS.get(word, []))
    return anchors


def _sentences(chart: dict[str, str]):
    for doc_id, text in chart.items():
        for line in text.splitlines():
            line = line.strip()
            if not line or line.isupper() or re.match(r"^(Date|Author|Patient):", line):
                continue
            for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", line):
                if len(sentence.split()) >= 4:
                    yield doc_id, sentence


def _durations_days(sentence: str) -> list[int]:
    out = []
    for amount, unit in DURATION.findall(sentence.lower()):
        n = int(amount) if amount.isdigit() else NUMBER_WORDS[amount]
        out.append(n * (7 if unit.startswith("week") else 30))
    return out


def _dates(sentence: str) -> list[date]:
    out = []
    for y, m, d in ISO_DATE.findall(sentence):
        try:
            out.append(date(int(y), int(m), int(d)))
        except ValueError:
            pass
    return out


def _classify(sentence: str, criterion: str, request_date: date | None) -> str | None:
    """Return 'positive', 'contradicting', 'ambiguous', or None to ignore the sentence."""
    low = sentence.lower()
    if OTHER_PERSON.search(low) or HISTORICAL.search(low) or PLAN.search(low):
        return None
    if UNCERTAIN.search(low):
        return "ambiguous"

    crit = criterion.lower()
    window = re.search(r"within the (\d+) months", crit)
    window_days = int(int(window.group(1)) * 365 / 12) if window else None

    def in_window(d: date) -> bool:
        return request_date is not None and window_days is not None and 0 <= (request_date - d).days <= window_days

    if "none are present" in crit or "has not had" in crit:
        if ABSENCE_OK.search(low):
            return "positive"
        dates = _dates(sentence)
        if window_days and dates:
            return "contradicting" if any(in_window(d) for d in dates) else "positive"
        return "contradicting"

    if NEGATED_HISTORY.search(low):
        return "contradicting"
    if "intolerance" in crit and INTOLERANCE.search(low):
        return "positive"
    threshold = re.search(r"at least (\d+|" + "|".join(NUMBER_WORDS) + r") (weeks?|months?)", crit)
    if threshold:
        amount, unit = threshold.groups()
        n = int(amount) if amount.isdigit() else NUMBER_WORDS[amount]
        required = n * (7 if unit.startswith("week") else 30)
        found = _durations_days(sentence)
        if not found:
            return "ambiguous"
        return "positive" if max(found) >= required else "contradicting"
    if window_days:
        dates = _dates(sentence)
        if not dates:
            return "ambiguous"
        return "positive" if any(in_window(d) for d in dates) else "contradicting"
    greater = re.search(r"greater than (\d+(?:\.\d+)?)", crit)
    if greater:
        numbers = [float(n) for n in STANDALONE_NUMBER.findall(sentence)]
        if not numbers:
            return "ambiguous"
        return "positive" if any(n > float(greater.group(1)) for n in numbers) else "contradicting"
    return "positive"


def _check(prompt: str) -> dict[str, Any]:
    rd = re.search(r"<request_date>(\d{4}-\d{2}-\d{2})</request_date>", prompt)
    request_date = date.fromisoformat(rd.group(1)) if rd else None
    crit = re.search(r"<criterion[^>]*>(.*?)</criterion>", prompt, re.S)
    criterion = crit.group(1) if crit else ""
    chart = dict(re.findall(r'<document id="([^"]+)">\n(.*?)</document>', prompt, re.S))
    anchors = _anchors(criterion)

    buckets: dict[str, list[tuple[int, str, str]]] = {"positive": [], "contradicting": [], "ambiguous": []}
    for doc_id, sentence in _sentences(chart):
        low = sentence.lower()
        score = sum(1 for a in anchors if re.search(r"\b" + re.escape(a) + r"\b", low))
        if score == 0:
            continue
        label = _classify(sentence, criterion, request_date)
        if label:
            buckets[label].append((score, doc_id, sentence))

    def quotes(items: list[tuple[int, str, str]], limit: int = 2, best_only: bool = False) -> list[dict[str, str]]:
        items = sorted(items, key=lambda t: -t[0])
        if best_only and items:
            items = [t for t in items if t[0] == items[0][0]]
        return [{"doc_id": d, "quote": s} for _, d, s in items[:limit]]

    pos, con, amb = buckets["positive"], buckets["contradicting"], buckets["ambiguous"]
    if pos and con:
        return {"status": "unclear", "evidence": quotes(pos, 1) + quotes(con, 2), "confidence": 0.55,
                "reasoning": "The chart contains conflicting statements about this criterion."}
    if pos:
        return {"status": "met", "evidence": quotes(pos, best_only=True), "confidence": 0.9,
                "reasoning": "The chart explicitly documents this criterion."}
    if con:
        return {"status": "not_met", "evidence": quotes(con), "confidence": 0.7,
                "reasoning": "The chart documents that this criterion is not satisfied."}
    if amb:
        return {"status": "unclear", "evidence": quotes(amb), "confidence": 0.5,
                "reasoning": "The documentation for this criterion is vague or incomplete."}
    return {"status": "not_met", "evidence": [], "confidence": 0.85,
            "reasoning": "No documentation for this criterion was found in the chart."}
