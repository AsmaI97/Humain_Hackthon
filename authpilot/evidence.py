"""Turn model quotes into verified evidence spans. This check runs in code, never in the model.

The model returns (doc_id, quote). Models are unreliable at character offsets, so offsets are
computed here by exact substring search. A quote that is not a verbatim substring of the named
document is dropped.
"""

from dataclasses import dataclass, field

from authpilot.schemas import Chart, Evidence


@dataclass
class CitationCheck:
    valid: list[Evidence] = field(default_factory=list)
    invalid: list[dict[str, str]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.valid) + len(self.invalid)


def locate(chart: Chart, doc_id: str, quote: str) -> Evidence | None:
    doc = chart.get(doc_id)
    quote = quote.strip()
    if doc is None or not quote:
        return None
    start = doc.find(quote)
    if start < 0:
        return None
    return Evidence(doc_id=doc_id, span_text=quote, start=start, end=start + len(quote))


def check_citations(chart: Chart, quotes: list[dict[str, str]]) -> CitationCheck:
    result = CitationCheck()
    seen: set[tuple[str, int, int]] = set()
    for item in quotes:
        evidence = locate(chart, item.get("doc_id", ""), item.get("quote", ""))
        if evidence is None:
            result.invalid.append(item)
            continue
        key = (evidence.doc_id, evidence.start, evidence.end)
        if key not in seen:
            seen.add(key)
            result.valid.append(evidence)
    return result


def unchecked_evidence(chart: Chart, quotes: list[dict[str, str]]) -> list[Evidence]:
    """Ablation only: accept quotes without checking them against the chart."""
    out = []
    for item in quotes:
        quote = item.get("quote", "").strip() or "?"
        doc = chart.get(item.get("doc_id", ""), "")
        start = max(doc.find(quote), 0)
        out.append(Evidence(doc_id=item.get("doc_id", "?"), span_text=quote, start=start, end=start + len(quote)))
    return out
