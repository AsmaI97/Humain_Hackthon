from typing import Any

from pydantic import BaseModel

from authpilot import audit


class ToolRefused(Exception):
    """A tool was called in a state where it is not allowed. The case state is unchanged."""


def tool_spec(name: str, description: str, input_model: type[BaseModel]) -> dict[str, Any]:
    schema = input_model.model_json_schema()
    schema.pop("title", None)
    return {"name": name, "description": description, "input_schema": schema}


def log_call(case_id: str, tool: str, args: dict[str, Any]) -> None:
    audit.log_event(case_id, "agent", "tool_call", {"tool": tool, "args": args})


def log_result(case_id: str, tool: str, summary: dict[str, Any]) -> None:
    audit.log_event(case_id, "agent", "tool_result", {"tool": tool, **summary})


def refuse(case_id: str, tool: str, reason: str) -> ToolRefused:
    audit.log_event(case_id, "agent", "error", {"tool": tool, "refused": reason})
    return ToolRefused(f"{tool}: {reason}")
