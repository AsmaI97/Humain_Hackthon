"""Deterministic rule-based payer reviewer.

For every coverage criterion in the policy, the package must mark it met and cite at least one
evidence span that appears verbatim in an attached record. Some payers restrict which records
first-level review accepts (see the policy's review section); those restrictions are lifted on
appeal. The first failing criterion decides the denial reason code.
"""

import re
from datetime import date

from authpilot.policies import Policy, find_policy
from authpilot.schemas import SubmissionPackage

CLINICAL_SOURCE = re.compile(r"CONSULTATION|CLINIC NOTE|PROGRESS NOTE|VISIT NOTE|ADDENDUM|LABORATORY|LAB REPORT")

# policy_id -> pattern a record's title must match for first-level review to accept it.
FIRST_LEVEL_SOURCES = {"PA-RX-207": CLINICAL_SOURCE}

_CODE = re.compile(r"([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+) \((\d+\.\d+)\)")


# The payer knows its own policies; this one puts its criteria under requirement headings.
CRITERIA_REFS = {"PA-RX-310": ["3.1", "3.2", "4.1"]}


def criteria_refs(policy: Policy) -> list[str]:
    if policy.policy_id in CRITERIA_REFS:
        return CRITERIA_REFS[policy.policy_id]
    return [s.ref for s in policy.sections if re.fullmatch(r"\d+\.\d+", s.ref) and "criteria" in s.heading.lower()]


def reason_codes(policy: Policy) -> dict[str, str]:
    codes = {}
    for section in policy.sections:
        for code, ref in _CODE.findall(section.text):
            codes[ref] = code
    return codes


# Content rules: the payer reads the cited evidence, not just its presence. Thresholds are
# parsed from the policy text so a policy change changes the rule.

_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
          "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}
_NUM = r"(\d+|" + "|".join(_WORDS) + r")"
_DURATION = re.compile(_NUM + r"[- ]?(weeks?|wks?|months?|mo)\b", re.I)
_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def _days(text: str) -> list[int]:
    out = []
    for amount, unit in _DURATION.findall(text):
        n = int(amount) if amount.isdigit() else _WORDS[amount.lower()]
        out.append(n * (30 if unit.lower().startswith("mo") else 7))
    return out


def _threshold_days(policy_text: str) -> int | None:
    match = re.search(r"at least " + _NUM + r" (weeks?|months?)", policy_text)
    if not match:
        return None
    amount, unit = match.groups()
    n = int(amount) if amount.isdigit() else _WORDS[amount]
    return n * (30 if unit.startswith("month") else 7)


def _duration_rule(text: str, policy_text: str, request_date: date, alt: str | None = None) -> bool:
    if alt and re.search(alt, text, re.I):
        return True
    needed = _threshold_days(policy_text)
    return needed is None or any(d >= needed for d in _days(text))


def _das28_rule(text: str, policy_text: str, request_date: date) -> bool:
    limit = re.search(r"greater than (\d+(?:\.\d+)?)", policy_text)
    match = re.search(r"DAS28\D{0,30}?(\d+(?:\.\d+)?)(?![\d-])", text)
    if not match or not limit:
        return False
    return float(match.group(1)) > float(limit.group(1))


def _tb_rule(text: str, policy_text: str, request_date: date) -> bool:
    window = re.search(r"within the (\d+) months", policy_text)
    days = int(int(window.group(1)) * 365 / 12) if window else 365
    negative = re.search(r"\bneg(ative)?\b|\b0 mm\b", text, re.I)
    dates = [date(int(y), int(m), int(d)) for y, m, d in _DATE.findall(text)]
    return bool(negative) and any(0 <= (request_date - d).days <= days for d in dates)


CONTENT_RULES = {
    ("PA-RAD-014", "2.1"): _duration_rule,
    ("PA-RX-207", "2.2"): lambda t, p, d: _duration_rule(
        t, p, d, alt=r"intoleran|toxicit|nausea|transaminase|LFT|not tolerated"),
    ("PA-RX-207", "2.3"): _tb_rule,
    ("PA-RX-207", "2.4"): _das28_rule,
}


def review(package: SubmissionPackage, level: str) -> tuple[str, str | None, str | None]:
    policy = find_policy(package.order.payer_id, package.order.procedure_code)
    codes = reason_codes(policy)
    by_ref = {c.section_ref: c for c in package.criteria}
    source_rule = FIRST_LEVEL_SOURCES.get(policy.policy_id) if level == "first" else None

    for ref in criteria_refs(policy):
        code = codes.get(ref, f"CRIT-{ref}")
        item = by_ref.get(ref)
        if item is None or item.status != "met":
            return "denied", code, f"Section {ref} is not documented as met."
        supported = [e for e in item.evidence if e.span_text and e.span_text in package.attachments.get(e.doc_id, "")]
        if not supported:
            return "denied", code, f"Section {ref}: the cited evidence is not in the attached records."
        rule = CONTENT_RULES.get((policy.policy_id, ref))
        if rule:
            policy_text = policy.section(ref).text
            supported = [e for e in supported if rule(e.span_text, policy_text, package.order.request_date)]
            if not supported:
                return "denied", code, f"Section {ref}: the cited evidence does not satisfy the policy requirement."
        if source_rule and not any(source_rule.search(package.attachments[e.doc_id].split("\n", 1)[0])
                                   for e in supported):
            return "denied", code, (f"Section {ref}: first-level review accepts evidence only from clinical "
                                    "notes and laboratory reports; other records are considered on appeal.")
    return "approved", None, None
