from __future__ import annotations

from dataclasses import dataclass
from typing import Any


_MAX_VALUE_LEN = 200
_MAX_ERRORS = 50


def truncate_value(value: Any, max_len: int = _MAX_VALUE_LEN) -> str:
    try:
        s = repr(value)
    except Exception:
        s = "<unrepresentable>"
    if len(s) > max_len:
        return s[:max_len] + "…"
    return s


@dataclass
class SpecError(ValueError):
    code: str
    path: str
    value: Any
    expected: str
    fix: str
    message: str = ""

    def __post_init__(self) -> None:
        if not self.message:
            if self.path:
                self.message = f"{self.path}: {self.fix}"
            else:
                self.message = self.fix
        ValueError.__init__(self, self.message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "path": self.path,
            "value": truncate_value(self.value),
            "expected": self.expected,
            "fix": self.fix,
            "message": self.message,
        }
