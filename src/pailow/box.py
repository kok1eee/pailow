from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


_ALIGN = {"left", "center", "right"}
_VALIGN = {"top", "middle", "bottom"}
_FIT = {"wrap", "shrink", "truncate"}


@dataclass(frozen=True)
class Box:
    id: str
    x: int
    y: int
    w: int
    h: int
    text: str = ""
    pad: int = 0
    font: Optional[str] = None
    size: int = 24
    color: str = "#FFFFFF"
    align: str = "left"
    valign: str = "middle"
    fit: str = "wrap"
    line_spacing: float = 1.2
    min_size: Optional[int] = None
    char_size_steps: Optional[tuple] = None
    parent: Optional[str] = None
    char_wrap: Optional[int] = None

    def __post_init__(self) -> None:
        if self.align not in _ALIGN:
            raise ValueError(f"align must be one of {sorted(_ALIGN)}, got {self.align!r}")
        if self.valign not in _VALIGN:
            raise ValueError(f"valign must be one of {sorted(_VALIGN)}, got {self.valign!r}")
        if self.fit not in _FIT:
            raise ValueError(f"fit must be one of {sorted(_FIT)}, got {self.fit!r}")
        if self.w < 0 or self.h < 0:
            raise ValueError("w and h must be non-negative")
        if self.pad < 0:
            raise ValueError("pad must be non-negative")
        if self.pad * 2 > self.w or self.pad * 2 > self.h:
            raise ValueError("pad is larger than box dimensions")
        if self.size <= 0:
            raise ValueError("size must be positive")
        if self.line_spacing <= 0:
            raise ValueError("line_spacing must be positive")
        if self.min_size is not None:
            if self.min_size < 1:
                raise ValueError("min_size must be positive if specified")
            if self.min_size > self.size:
                raise ValueError(f"min_size ({self.min_size}) cannot exceed size ({self.size})")
        if self.char_size_steps is not None:
            if not isinstance(self.char_size_steps, (list, tuple)):
                raise ValueError("char_size_steps must be a list of (max_chars, size) tuples")
            prev = -1
            for step in self.char_size_steps:
                if not (isinstance(step, (list, tuple)) and len(step) == 2):
                    raise ValueError(
                        f"each char_size_steps entry must be a 2-tuple (max_chars, size); got {step!r}"
                    )
                max_chars, size = int(step[0]), int(step[1])
                if max_chars <= prev:
                    raise ValueError("char_size_steps max_chars must be strictly increasing")
                if size <= 0:
                    raise ValueError("char_size_steps size must be positive")
                prev = max_chars
        if self.char_wrap is not None and self.char_wrap < 1:
            raise ValueError("char_wrap must be positive if specified")


@dataclass(frozen=True)
class Canvas:
    width: int
    height: int
    background: str = "#FFFFFF"

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("canvas width/height must be positive")


def parse_color(s: str) -> tuple[int, int, int, int]:
    s = s.strip()
    if not s.startswith("#"):
        raise ValueError(f"color must start with '#', got {s!r}")
    hex_part = s[1:]
    if len(hex_part) == 3:
        try:
            r, g, b = (int(c * 2, 16) for c in hex_part)
        except ValueError as e:
            raise ValueError(f"invalid color {s!r}") from e
        return (r, g, b, 255)
    if len(hex_part) == 6:
        try:
            r = int(hex_part[0:2], 16)
            g = int(hex_part[2:4], 16)
            b = int(hex_part[4:6], 16)
        except ValueError as e:
            raise ValueError(f"invalid color {s!r}") from e
        return (r, g, b, 255)
    if len(hex_part) == 8:
        try:
            r = int(hex_part[0:2], 16)
            g = int(hex_part[2:4], 16)
            b = int(hex_part[4:6], 16)
            a = int(hex_part[6:8], 16)
        except ValueError as e:
            raise ValueError(f"invalid color {s!r}") from e
        return (r, g, b, a)
    raise ValueError(f"invalid color {s!r}: must be #RGB, #RRGGBB, or #RRGGBBAA")
