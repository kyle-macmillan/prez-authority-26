#!/usr/bin/env python3
"""Change gold text-overlap emphasis to green on the reuse slides."""

import shutil
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor


ROOT = Path(__file__).resolve().parent
DECK = ROOT / "Presidential_Directives_Workshop.pptx"
BACKUP = ROOT / "Presidential_Directives_Workshop.before_green_overlap.pptx"
GOLD = "A67C00"
OVERLAP_GREEN = RGBColor(15, 110, 70)
REUSE_TITLES = {
    "Example of text re-use in high-confidence category",
    "A task-force template reused seven years later",
}


def main() -> None:
    if not BACKUP.exists():
        shutil.copy2(DECK, BACKUP)

    presentation = Presentation(DECK)
    changed = 0
    found_titles = set()
    for slide in presentation.slides:
        slide_text = {
            shape.text.strip()
            for shape in slide.shapes
            if getattr(shape, "has_text_frame", False) and shape.text.strip()
        }
        matches = REUSE_TITLES & slide_text
        if not matches:
            continue
        found_titles.update(matches)
        for shape in slide.shapes:
            if not getattr(shape, "has_text_frame", False):
                continue
            for paragraph in shape.text_frame.paragraphs:
                for run in paragraph.runs:
                    try:
                        is_gold = str(run.font.color.rgb) == GOLD
                    except (AttributeError, TypeError):
                        is_gold = False
                    if is_gold:
                        run.font.color.rgb = OVERLAP_GREEN
                        changed += 1

    if found_titles != REUSE_TITLES:
        missing = ", ".join(sorted(REUSE_TITLES - found_titles))
        raise RuntimeError(f"Could not find expected reuse slide(s): {missing}")
    if changed != 32:
        raise RuntimeError(f"Expected to recolor 32 overlap runs; found {changed}")

    presentation.save(DECK)
    print(f"Changed {changed} overlap runs from gold to green.")


if __name__ == "__main__":
    main()
