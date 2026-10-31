"""Simulated EHR backed by the generated case files.

A patient's chart is its base chart (the case file, or an in-memory override used by
perturbation tests) plus any documents received later from the clinic. Received documents are
saved under the runtime directory so a paused case can resume in another process.
"""

import json
from functools import lru_cache
from pathlib import Path

from authpilot import config
from authpilot.schemas import CaseLabel, Chart, Order

_overrides: dict[str, Chart] = {}


@lru_cache(maxsize=None)
def _index(cases_dir: str) -> dict[str, Path]:
    index = {}
    for order_path in sorted(Path(cases_dir).glob("*/case_*/order.json")):
        patient_id = json.loads(order_path.read_text(encoding="utf-8"))["patient_id"]
        index[patient_id] = order_path.parent
    return index


def refresh_index() -> None:
    _index.cache_clear()


def _case_dir(patient_id: str) -> Path:
    try:
        return _index(str(config.CASES_DIR))[patient_id]
    except KeyError:
        raise KeyError(f"unknown patient {patient_id!r}") from None


def _received_path(patient_id: str) -> Path:
    return Path(config.RUNTIME_DIR) / "ehr" / f"{patient_id}.json"


def load_chart(patient_id: str) -> Chart:
    if patient_id in _overrides:
        chart = dict(_overrides[patient_id])
    else:
        chart = json.loads((_case_dir(patient_id) / "chart.json").read_text(encoding="utf-8"))
    received = _received_path(patient_id)
    if received.exists():
        chart.update(json.loads(received.read_text(encoding="utf-8")))
    return chart


def set_chart_override(patient_id: str, chart: Chart) -> None:
    _overrides[patient_id] = dict(chart)


def clear_chart_override(patient_id: str) -> None:
    _overrides.pop(patient_id, None)


def append_documents(patient_id: str, documents: Chart) -> None:
    """Simulates new documents arriving in the EHR, e.g. after a request to the clinic."""
    path = _received_path(patient_id)
    received = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    received.update(documents)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(received, indent=2), encoding="utf-8")


def clear_patient(patient_id: str) -> None:
    """Forget documents received during earlier runs. The base chart and overrides stay."""
    _received_path(patient_id).unlink(missing_ok=True)


def load_supplemental(patient_id: str) -> dict:
    """Simulation only: documents the clinic holds but has not yet sent. The agent never calls this."""
    path = _case_dir(patient_id) / "supplemental.json"
    if not path.exists():
        return {"documents": {}, "provides": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def clear_overrides() -> None:
    _overrides.clear()


def load_case_files(split: str, case_name: str) -> tuple[Order, Chart, CaseLabel]:
    """Evaluation helper: read one generated case. The agent never reads labels."""
    case_dir = Path(config.CASES_DIR) / split / case_name
    order = Order.model_validate_json((case_dir / "order.json").read_text(encoding="utf-8"))
    chart = json.loads((case_dir / "chart.json").read_text(encoding="utf-8"))
    label = CaseLabel.model_validate_json((case_dir / "labels.json").read_text(encoding="utf-8"))
    return order, chart, label


def list_cases(split: str) -> list[str]:
    split_dir = Path(config.CASES_DIR) / split
    if not split_dir.exists():
        return []
    return sorted(p.name for p in split_dir.iterdir() if p.is_dir())
