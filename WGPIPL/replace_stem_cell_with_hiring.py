#!/usr/bin/env python3
"""Replace the stem-cell authority example with two federal-hiring memoranda."""

from pathlib import Path
from io import BytesIO

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Pt


DECK = Path(__file__).with_name("Presidential_Directives_Workshop.pptx")


def replace_text(shape, value, size=None):
    text_frame = shape.text_frame
    while len(text_frame.paragraphs) > 1:
        text_frame._element.remove(text_frame.paragraphs[-1]._element)
    paragraph = text_frame.paragraphs[0]
    run = paragraph.runs[0] if paragraph.runs else paragraph.add_run()
    for extra in list(paragraph.runs[1:]):
        paragraph._element.remove(extra._r)
    run.text = value
    if size is not None:
        run.font.size = Pt(size)


def replace_footer(shape, parts):
    text_frame = shape.text_frame
    text_frame.clear()
    paragraph = text_frame.paragraphs[0]
    for value, url in parts:
        run = paragraph.add_run()
        run.text = value
        run.font.name = "Garamond"
        run.font.size = Pt(8)
        run.font.italic = True
        run.font.color.rgb = RGBColor(0x67, 0x63, 0x5F)
        if url:
            run.hyperlink.address = url


def preserve_master_logo(presentation, slide):
    logo = presentation.slide_masters[0].shapes[5]
    picture = slide.shapes.add_picture(
        BytesIO(logo.image.blob),
        logo.left,
        logo.top,
        logo.width,
        logo.height,
    )
    picture.name = "UChicagoLogoFallback"
    slide.shapes._spTree.remove(picture._element)
    slide.shapes._spTree.insert(2, picture._element)


def main():
    presentation = Presentation(DECK)
    slide = presentation.slides[4]
    shapes = slide.shapes

    replace_text(
        shapes[0],
        "Federal hiring: specific authority, vague authority—and legal effect",
        20.5,
    )

    replace_text(shapes[3], "SPECIFIC")
    replace_text(shapes[4], "Recruitment and Hiring\nMemorandum", 14.5)
    replace_text(shapes[5], "May 11, 2010")

    replace_text(shapes[9], "VAGUE")
    replace_text(shapes[10], "Hiring Freeze\nMemorandum", 14.5)
    replace_text(shapes[11], "January 20, 2025")

    authority_group = shapes[14]
    replace_text(
        authority_group.shapes[0],
        "By the authority vested in me as President by the Constitution and the laws of the United States, including section 3301 of title 5, United States Code, I hereby direct the following:",
        10.7,
    )
    replace_text(
        authority_group.shapes[1],
        "By the authority vested in me as President by the Constitution and the laws of the United States of America, I hereby order a freeze on the hiring of Federal civilian employees, to be applied throughout the executive branch.",
        10.2,
    )

    effect_group = shapes[15]
    replace_text(
        effect_group.shapes[0],
        "Section 1. Directions to Agencies. Agency heads shall take the following actions no later than November 1, 2010: (a) consistent with merit system principles and other requirements of title 5, United States Code, and subject to guidance to be issued by the Office of Personnel Management (OPM), adopt hiring procedures that: (1) eliminate any requirement that applicants respond to essay-style questions when submitting their initial application materials for any Federal job; (2) allow individuals to apply for Federal employment by submitting resumes and cover letters or completing simple, plain language applications, and assess applicants using valid, reliable tools; …",
        8.25,
    )
    replace_text(
        effect_group.shapes[1],
        "As part of this freeze, no Federal civilian position that is vacant at noon on January 20, 2025, may be filled, and no new position may be created except as otherwise provided for in this memorandum or other applicable law. Contracting outside the Federal Government to circumvent the intent of this memorandum is prohibited.",
        9.8,
    )

    replace_text(shapes[16], "Click 1: authority  •  Click 2: hiring rule")
    replace_footer(shapes[17], [
        ("Sources: ", None),
        ("Presidential Memorandum on Federal Recruitment and Hiring", "https://www.presidency.ucsb.edu/documents/memorandum-improving-the-federal-recruitment-and-hiring-process"),
        (" (May 11, 2010); ", None),
        ("Presidential Memorandum on Hiring Freeze", "https://www.presidency.ucsb.edu/documents/memorandum-hiring-freeze"),
        (" (Jan. 20, 2025). Verbatim excerpts; ellipsis marks cropped continuation.", None),
    ])

    preserve_master_logo(presentation, slide)

    presentation.save(DECK)


if __name__ == "__main__":
    main()
