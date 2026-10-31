"""Load payer policies from markdown and split them into numbered sections."""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from authpilot import config

_HEADING = re.compile(r"^##\s+(\d+)\.\s+(.+)$")
_SUBSECTION = re.compile(r"^(\d+\.\d+)\s+(.*)$", re.S)


@dataclass(frozen=True)
class PolicySection:
    ref: str
    heading: str
    text: str


@dataclass(frozen=True)
class Policy:
    meta: dict[str, str]
    sections: tuple[PolicySection, ...]
    path: Path

    @property
    def policy_id(self) -> str:
        return self.meta["policy_id"]

    def section(self, ref: str) -> PolicySection | None:
        return next((s for s in self.sections if s.ref == ref), None)

    def full_text(self) -> str:
        return "\n\n".join(f"[{s.ref}] {s.heading}: {s.text}" for s in self.sections)


def _parse_front_matter(lines: list[str]) -> tuple[dict[str, str], list[str]]:
    if not lines or lines[0].strip() != "---":
        return {}, lines
    end = lines.index("---", 1)
    meta = {}
    for line in lines[1:end]:
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip().strip('"')
    return meta, lines[end + 1:]


def parse_policy(text: str, path: Path = Path("<memory>")) -> Policy:
    meta, body = _parse_front_matter(text.splitlines())
    sections: list[PolicySection] = []
    heading_ref, heading = "", ""
    paragraph: list[str] = []

    def flush() -> None:
        if not paragraph or not heading_ref:
            paragraph.clear()
            return
        joined = " ".join(line.strip() for line in paragraph)
        match = _SUBSECTION.match(joined)
        if match:
            sections.append(PolicySection(match.group(1), heading, match.group(2)))
        else:
            sections.append(PolicySection(heading_ref, heading, joined))
        paragraph.clear()

    for line in body:
        match = _HEADING.match(line.strip())
        if match:
            flush()
            heading_ref, heading = match.group(1), match.group(2).strip()
        elif not line.strip() or line.startswith("#"):
            flush()
        else:
            paragraph.append(line)
    flush()
    return Policy(meta=meta, sections=tuple(sections), path=path)


@lru_cache(maxsize=None)
def _load_all(policies_dir: str) -> tuple[Policy, ...]:
    return tuple(
        parse_policy(path.read_text(encoding="utf-8"), path)
        for path in sorted(Path(policies_dir).glob("*.md"))
    )


def find_policy(payer_id: str, procedure_code: str, policies_dir: Path | None = None) -> Policy:
    for policy in _load_all(str(policies_dir or config.POLICIES_DIR)):
        if policy.meta.get("payer_id") == payer_id and policy.meta.get("procedure_code") == procedure_code:
            return policy
    raise KeyError(f"no policy for payer {payer_id!r} and procedure {procedure_code!r}")


def clear_cache() -> None:
    _load_all.cache_clear()
