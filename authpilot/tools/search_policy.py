"""BM25 over the numbered sections of one payer policy."""

import math
import re
from collections import Counter

from pydantic import Field

from authpilot import config
from authpilot.policies import Policy, PolicySection, find_policy
from authpilot.schemas import Strict
from authpilot.tools._common import log_call, log_result, tool_spec

K1 = 1.5
B = 0.75
_STOP = {"the", "a", "an", "of", "and", "or", "to", "in", "is", "be", "by", "for", "with", "that", "this",
         "on", "as", "at", "are", "was", "has", "have", "must", "when", "which", "member"}


class SearchPolicyInput(Strict):
    payer_id: str
    procedure_code: str
    query: str = Field(min_length=1)
    k: int = Field(default=config.RETRIEVAL_K, ge=1, le=10)


class PolicyHit(Strict):
    ref: str
    heading: str
    text: str
    score: float


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOP]


def bm25_rank(sections: tuple[PolicySection, ...], query: str) -> list[tuple[PolicySection, float]]:
    docs = [tokenize(f"{s.heading} {s.text}") for s in sections]
    if not docs:
        return []
    avgdl = sum(len(d) for d in docs) / len(docs)
    df = Counter(term for d in docs for term in set(d))
    n = len(docs)
    scored = []
    for section, doc in zip(sections, docs):
        tf = Counter(doc)
        score = 0.0
        for term in set(tokenize(query)):
            if term not in tf:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            score += idf * tf[term] * (K1 + 1) / (tf[term] + K1 * (1 - B + B * len(doc) / avgdl))
        scored.append((section, score))
    return sorted(scored, key=lambda pair: (-pair[1], pair[0].ref))


def search_sections(policy: Policy, query: str, k: int) -> list[PolicyHit]:
    return [
        PolicyHit(ref=s.ref, heading=s.heading, text=s.text, score=round(score, 4))
        for s, score in bm25_rank(policy.sections, query)[:k]
        if score > 0
    ]


def search_policy(payer_id: str, procedure_code: str, query: str, k: int = config.RETRIEVAL_K,
                  case_id: str = "-") -> list[PolicyHit]:
    log_call(case_id, "search_policy", {"payer_id": payer_id, "procedure_code": procedure_code, "query": query, "k": k})
    hits = search_sections(find_policy(payer_id, procedure_code), query, k)
    log_result(case_id, "search_policy", {"refs": [h.ref for h in hits], "scores": [h.score for h in hits]})
    return hits


TOOL_SPEC = tool_spec(
    "search_policy",
    "Search the payer policy for the procedure and return the most relevant numbered sections.",
    SearchPolicyInput,
)
