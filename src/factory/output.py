"""JSON envelope, exit codes and human formatting shared by every command."""

from __future__ import annotations

import json
import re
from pathlib import PurePath
from typing import Any

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_PRECONDITION = 3
EXIT_CONFLICT = 4
EXIT_UNAVAILABLE = 5


class FactoryError(Exception):
    """An expected failure: short snake_case code, message for the person, exit code and, when
    there are several problems, one line per problem in `details`."""

    def __init__(
        self, code: str, message: str, exit_code: int = EXIT_ERROR, details: list[str] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code
        self.details = details or []


def ok_envelope(data: dict[str, Any], warnings: list[str] | None = None) -> dict[str, Any]:
    return {"ok": True, "data": data, "warnings": list(warnings or [])}


def error_envelope(error: FactoryError, warnings: list[str] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"code": error.code, "message": error.message}
    if error.details:
        body["details"] = error.details
    return {"ok": False, "error": body, "warnings": list(warnings or [])}


def render(envelope: dict[str, Any], as_json: bool) -> str:
    if as_json:
        return json.dumps(envelope, ensure_ascii=False)
    if envelope["ok"]:
        lines = _human(envelope["data"], 0)
    else:
        error = envelope["error"]
        lines = [f"error ({error['code']}): {error['message']}"]
        lines += [f"  - {d}" for d in error.get("details", [])]
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


# Common secret shapes (design §10.1, A-26). Values stop at quotes, commas and backslashes so that
# masking JSON text keeps it valid.
SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
]
SECRET_ASSIGNMENT = re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key)(\s*[=:]\s*)[^\s\"',\\]+")
SECRET_FILES = (".env", "*.pem", "*.key", "*.p12", "*.pfx", "id_rsa", "id_ecdsa", "id_ed25519", ".env.*")
MASK = "[redacted]"


def mask_secrets(text: str) -> str:
    for pattern in SECRET_PATTERNS:
        text = pattern.sub(MASK, text)
    return SECRET_ASSIGNMENT.sub(lambda m: f"{m.group(1)}{m.group(2)}{MASK}", text)


def is_secret_file(path: str) -> bool:
    name = PurePath(path).name
    return any(PurePath(name).match(pattern) for pattern in SECRET_FILES)
