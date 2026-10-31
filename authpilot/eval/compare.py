"""Compare the two latest saved evaluation reports for the current mode.

Usage: python -m authpilot.eval.compare
Refuses stub mode. In replay mode, refuses a cache that was not produced by a live run
with the same model and prompt version. Does not call the API.
"""

import json
import sys
from pathlib import Path

from authpilot import config
from authpilot.eval.guard import require_eval_mode
from authpilot.eval.run_all import regression_check


def _saved_reports() -> list[Path]:
    directory = Path(config.RESULTS_DIR) / "eval"
    if not directory.is_dir():
        return []
    return sorted(
        path for path in directory.glob(f"*_{config.LLM_MODE}.json")
        if not path.name.startswith("latest_")
    )


def main() -> None:
    require_eval_mode()
    files = _saved_reports()
    if len(files) < 2:
        raise SystemExit(
            f"Refusing to compare: need two saved {config.LLM_MODE} evaluation files in "
            f"{Path(config.RESULTS_DIR) / 'eval'}. Run make eval twice in live or replay mode first."
        )
    older, newer = files[-2], files[-1]
    old = json.loads(older.read_text(encoding="utf-8"))
    new = json.loads(newer.read_text(encoding="utf-8"))
    result = regression_check(new, old)
    print(f"comparing {older.name} -> {newer.name}")
    print(f"mode {new['meta'].get('llm_mode')} model {new['meta'].get('model')} "
          f"prompt {new['meta'].get('prompt_version')}")
    print(f"status: {result['status']}")
    for drop in result["drops"]:
        print(f"- {drop['metric']}: {drop['previous']} -> {drop['now']}")
    if result["status"] == "regression":
        sys.exit(1)


if __name__ == "__main__":
    main()
