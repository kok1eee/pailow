"""pailow — container-based text overlay CLI for images. Bridge between Pillow and LLMs."""

from __future__ import annotations

__version__ = "0.1.0"

from pailow.box import Box, Canvas, parse_color
from pailow.errors import SpecError
from pailow.inspect import inspect_canvas, inspect_from_mapping, inspect_spec
from pailow.gallery import (
    GALLERY,
    GALLERY_IDS,
    get_gallery_item,
    render_gallery_example,
)
from pailow.layout import (
    load_spec,
    load_spec_from_mapping,
    validate_spec,
)
from pailow.render import (
    analyze,
    analyze_from_mapping,
    layout_box,
    render,
    render_from_mapping,
)
from pailow.schema import build_schema, schema_version

__all__ = [
    "Box",
    "Canvas",
    "SpecError",
    "parse_color",
    "GALLERY",
    "GALLERY_IDS",
    "get_gallery_item",
    "render_gallery_example",
    "load_spec",
    "load_spec_from_mapping",
    "validate_spec",
    "render",
    "render_from_mapping",
    "analyze",
    "analyze_from_mapping",
    "layout_box",
    "inspect_canvas",
    "inspect_from_mapping",
    "inspect_spec",
    "build_schema",
    "schema_version",
    "__version__",
]
