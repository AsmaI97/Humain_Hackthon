"""Case state store. State lives here, not in the prompt history.

Kept in memory and written through to one JSON file per case so the dashboard can read it.
"""

from pathlib import Path

from authpilot import config
from authpilot.schemas import CaseState, Order

_cases: dict[str, CaseState] = {}


def _path(case_id: str) -> Path:
    return Path(config.CASE_STORE_DIR) / f"{case_id}.json"


def save_case(state: CaseState) -> CaseState:
    _cases[state.case_id] = state
    path = _path(state.case_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(state.model_dump_json(indent=2), encoding="utf-8")
    return state


def create_case(case_id: str, order: Order) -> CaseState:
    return save_case(CaseState(case_id=case_id, order=order))


def get_case(case_id: str) -> CaseState:
    if case_id in _cases:
        return _cases[case_id]
    path = _path(case_id)
    if not path.exists():
        raise KeyError(f"unknown case {case_id!r}")
    state = CaseState.model_validate_json(path.read_text(encoding="utf-8"))
    _cases[case_id] = state
    return state


def list_case_ids() -> list[str]:
    on_disk = {p.stem for p in Path(config.CASE_STORE_DIR).glob("*.json")}
    return sorted(on_disk | set(_cases))


def reload(case_id: str) -> CaseState:
    """Drop the in-memory copy and read the case from disk (another process may have changed it)."""
    _cases.pop(case_id, None)
    return get_case(case_id)


def clear() -> None:
    _cases.clear()
