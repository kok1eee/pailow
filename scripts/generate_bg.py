from __future__ import annotations

import json
from pathlib import Path


def generate_bg(out_path: Path) -> None:
    from PIL import Image, ImageDraw

    w, h = 1200, 800
    img = Image.new("RGB", (w, h), (26, 26, 26))
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(1, h - 1)
        r = int(26 + (60 - 26) * t)
        g = int(26 + (20 - 26) * t)
        b = int(26 + (80 - 26) * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)


def main() -> None:
    here = Path(__file__).parent
    examples = here.parent / "examples"
    out = examples / "bg.png"
    generate_bg(out)
    print(f"wrote: {out}")


if __name__ == "__main__":
    main()
