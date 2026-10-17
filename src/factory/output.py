"""JSON envelope, exit codes and human formatting shared by every command."""

from __future__ import annotations

import json
from typing import Any

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_PRECONDITION = 3
EXIT_CONFLICT = 4
EXIT_UNAVAILABLE = 5


class FactoryError(Exception):
    """An expected failure: short snake_case code, message for the person, exit code."""

    def __init__(self, code: str, message: str, exit_code: int = EXIT_ERROR) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code


def ok_envelope(data: dict[str, Any], warnings: list[str] | None = None) -> dict[str, Any]:
    return {"ok": True, "data": data, "warnings": list(warnings or [])}


def error_envelope(error: FactoryError, warnings: list[str] | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {"code": error.code, "message": error.message},
        "warnings": list(warnings or []),
    }


def render(envelope: dict[str, Any], as_json: bool) -> str:
    if as_json:
        return json.dumps(envelope, ensure_ascii=False)
    if envelope["ok"]:
        lines = _human(envelope["data"], 0)
    else:
        error = envelope["error"]
        lines = [f"error ({error['code']}): {error['message']}"]
    lines += [f"warning: {w}" for w in envelope["warnings"]]
    return "\n".join(lines)


def _human(value: Any, indent: int) -> list[str]:
    pad = "  " * indent
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            if isinstance(item, dict | list) and item:
                lines.append(f"{pad}{key}:")
                lines += _human(item, indent + 1)
            else:
                lines.append(f"{pad}{key}: {_scalar(item)}")
        return lines
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, dict | list) and item:
                lines.append(f"{pad}-")
                lines += _human(item, indent + 1)
            else:
                lines.append(f"{pad}- {_scalar(item)}")
        return lines
    return [f"{pad}{_scalar(value)}"]


def _scalar(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, dict | list):
        return "none"
    return str(value)
