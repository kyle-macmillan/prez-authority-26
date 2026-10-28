#!/usr/bin/env python3
"""Highlight reused words, rather than changed words, in the workshop deck."""

import tempfile
from pathlib import Path

from pptx import Presentation

import build_workshop_deck as st


DECK = Path(__file__).with_name("Presidential_Directives_Workshop.pptx")


def replace_paragraph(paragraph, parts, size):
    for run in list(paragraph.runs):
        paragraph._element.remove(run._r)
    for value, style in parts:
        run = paragraph.add_run()
        run.text = value
        st.style_run(run, size=size, **style)


def highlight_pair(left_paragraph, right_paragraph, left_size, right_size, *, min_block_words=1):
    left_parts, right_parts = st.shared_word_parts(
        left_paragraph.text,
        right_paragraph.text,
        min_block_words=min_block_words,
    )
    replace_paragraph(left_paragraph, left_parts, left_size)
    replace_paragraph(right_paragraph, right_parts, right_size)


def require_title(slide, expected):
    actual = slide.shapes[0].text
    if actual != expected:
        raise ValueError(f"Expected slide title {expected!r}, found {actual!r}")


def presentation_text(presentation):
    values = []

    def collect(shape):
        if getattr(shape, "shape_type", None) == 6:
            for child in shape.shapes:
                collect(child)
        elif getattr(shape, "has_text_frame", False):
            values.append(shape.text)

    for slide in presentation.slides:
        for shape in slide.shapes:
            collect(shape)
    return values


def main():
    presentation = Presentation(DECK)
    if len(presentation.slides) != 13:
        raise ValueError(f"Expected 13 slides, found {len(presentation.slides)}")
    original_text = presentation_text(presentation)

    high_confidence = presentation.slides[2]
    require_title(high_confidence, "Example of text re-use in high-confidence category")
    highlight_pair(
        high_confidence.shapes[5].text_frame.paragraphs[0],
        high_confidence.shapes[9].text_frame.paragraphs[0],
        9.0,
        8.7,
    )

    ethics = presentation.slides[3]
    require_title(ethics, "Templating outside of the high-confidence categories")
    highlight_pair(
        ethics.shapes[5].text_frame.paragraphs[0],
        ethics.shapes[9].text_frame.paragraphs[0],
        10.8,
        9.2,
    )
    highlight_pair(
        ethics.shapes[5].text_frame.paragraphs[1],
        ethics.shapes[9].text_frame.paragraphs[2],
        10.8,
        9.2,
    )
    replace_paragraph(
        ethics.shapes[9].text_frame.paragraphs[1],
        [(ethics.shapes[9].text_frame.paragraphs[1].text, {"color": st.DARK, "bold": False})],
        9.2,
    )

    task_force = presentation.slides[4]
    require_title(task_force, "A task-force template reused seven years later")
    for paragraph_index in (1, 3, 5):
        highlight_pair(
            task_force.shapes[5].text_frame.paragraphs[paragraph_index],
            task_force.shapes[9].text_frame.paragraphs[paragraph_index],
            8.9,
            8.9,
            min_block_words=2,
        )

    with tempfile.NamedTemporaryFile(dir=DECK.parent, suffix=".pptx", delete=False) as temporary:
        temporary_path = Path(temporary.name)
    try:
        presentation.save(temporary_path)
        saved = Presentation(temporary_path)
        if presentation_text(saved) != original_text:
            raise ValueError("Text changed while applying reuse highlighting")
        temporary_path.replace(DECK)
    finally:
        temporary_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
