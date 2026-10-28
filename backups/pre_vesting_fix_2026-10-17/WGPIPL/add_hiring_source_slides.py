#!/usr/bin/env python3
"""Replace the opening hiring comparison with three source-document slides."""

from __future__ import annotations

import shutil
from io import BytesIO
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Inches, Pt


ROOT = Path(__file__).resolve().parent
DECK = ROOT / "Presidential_Directives_Workshop.pptx"
BACKUP = ROOT / "Presidential_Directives_Workshop.before_source_slides.pptx"

MAROON = RGBColor(128, 0, 0)
DARK = RGBColor(45, 45, 45)
MID = RGBColor(103, 99, 95)
LIGHT = RGBColor(246, 243, 239)
LIGHT_MAROON = RGBColor(242, 230, 230)
GOLD = RGBColor(166, 124, 0)
WHITE = RGBColor(255, 255, 255)
LINE = RGBColor(205, 199, 193)
YELLOW = RGBColor(255, 230, 92)
FONT = "Garamond"


DOCUMENTS = [
    {
        "title": "Federal hiring freeze: Reagan memorandum (1981)",
        "subtitle": "An immediate freeze stated without a conventional vesting formula",
        "image": ROOT / "reagan_hiring_freeze_narrow.png",
        "url": "https://www.presidency.ucsb.edu/documents/memorandum-directing-federal-employee-hiring-freeze",
        "badge": "NO EXPRESS VESTING CLAUSE",
        "badge_fill": MID,
        "quote": (
            "“I am ordering today a strict freeze on the hiring of Federal civilian "
            "employees to be applied across the board in the executive branch.”"
        ),
        "analysis": (
            "The opening is operative text—not an ‘authority vested in me’ clause. "
            "It orders an across-the-board freeze and leaves implementation and "
            "exceptions to OMB."
        ),
        "highlight": (278, 671, 344, 64),
        "highlight_dashed": True,
        "source": "Reagan, Memorandum Directing a Federal Employee Hiring Freeze (Jan. 20, 1981).",
    },
    {
        "title": "Federal hiring freeze: Trump memorandum (2025)",
        "subtitle": "A generic constitutional-and-laws vesting clause",
        "image": ROOT / "trump_2025_hiring_freeze_narrow.png",
        "url": "https://www.presidency.ucsb.edu/documents/memorandum-hiring-freeze",
        "badge": "GENERIC VESTING CLAUSE",
        "badge_fill": MAROON,
        "quote": (
            "“By the authority vested in me as President by the Constitution and the "
            "laws of the United States of America …”"
        ),
        "analysis": (
            "No statute is named. The same opening sentence orders an immediate "
            "freeze on vacant and newly created Federal civilian positions, subject "
            "to stated exceptions."
        ),
        "highlight": (278, 635, 344, 66),
        "highlight_dashed": False,
        "source": "Trump, Memorandum on Hiring Freeze (Jan. 20, 2025).",
    },
    {
        "title": "Federal position reductions: Clinton EO 12839 (1993)",
        "subtitle": "A closely related personnel constraint with three specific statutory citations",
        "image": ROOT / "clinton_eo_12839_narrow.png",
        "url": "https://www.presidency.ucsb.edu/documents/executive-order-12839-reduction-100000-federal-positions",
        "badge": "SPECIFIC VESTING CLAUSE",
        "badge_fill": GOLD,
        "quote": (
            "“… including section 301 of title 3, United States Code, section 3301 "
            "of title 5, United States Code, and section 1111 of title 31, United "
            "States Code …”"
        ),
        "analysis": (
            "Functionally similar, but not identical: the order constrains hiring by "
            "requiring a 4% position reduction through attrition or early-out programs, "
            "rather than categorically barring every vacancy from being filled."
        ),
        "highlight": (278, 592, 344, 128),
        "highlight_dashed": False,
        "source": "Clinton, Executive Order 12839 (Feb. 10, 1993).",
    },
]


def set_text_frame_defaults(text_frame, margin: float = 0.06) -> None:
    text_frame.clear()
    text_frame.word_wrap = True
    text_frame.margin_left = Inches(margin)
    text_frame.margin_right = Inches(margin)
    text_frame.margin_top = Inches(margin)
    text_frame.margin_bottom = Inches(margin)
    text_frame.vertical_anchor = MSO_ANCHOR.TOP


def add_textbox(container, x, y, w, h, text="", *, size=14, color=DARK,
                bold=False, italic=False, align=PP_ALIGN.LEFT, margin=0.06):
    box = container.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    set_text_frame_defaults(tf, margin)
    p = tf.paragraphs[0]
    p.alignment = align
    p.space_after = Pt(0)
    run = p.add_run()
    run.text = text
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.color.rgb = color
    run.font.bold = bold
    run.font.italic = italic
    return box


def add_master_logo(prs, slide) -> None:
    logo = prs.slide_masters[0].shapes[5]
    picture = slide.shapes.add_picture(
        BytesIO(logo.image.blob), logo.left, logo.top, logo.width, logo.height
    )
    picture.name = "UChicagoLogoFallback"


def set_fill_opacity(shape, opacity_percent: int) -> None:
    """Set solid-fill opacity through DrawingML; python-pptx has no public API."""
    color = shape.fill._xPr.solidFill.srgbClr
    alpha = OxmlElement("a:alpha")
    alpha.set("val", str(opacity_percent * 1000))
    color.append(alpha)


def add_footer(slide, source: str, url: str) -> None:
    box = slide.shapes.add_textbox(Inches(0.58), Inches(6.91), Inches(8.76), Inches(0.22))
    tf = box.text_frame
    set_text_frame_defaults(tf, 0.01)
    p = tf.paragraphs[0]
    for text, link in (("Source: ", None), (source, url),
                       (" Screenshot: The American Presidency Project; emphasis added.", None)):
        run = p.add_run()
        run.text = text
        run.font.name = FONT
        run.font.size = Pt(7.4)
        run.font.italic = True
        run.font.color.rgb = MID
        if link:
            run.hyperlink.address = link


def add_document_slide(prs: Presentation, document: dict):
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    add_textbox(slide.shapes, 0.55, 0.40, 8.9, 0.40, document["title"],
                size=23, color=MAROON, bold=True)
    add_textbox(slide.shapes, 0.58, 0.78, 8.75, 0.24, document["subtitle"],
                size=10.8, color=MID, italic=True)
    rule = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.58), Inches(1.02),
                                  Inches(8.85), Inches(0.015))
    rule.fill.solid()
    rule.fill.fore_color.rgb = LINE
    rule.line.fill.background()

    picture = slide.shapes.add_picture(str(document["image"]), Inches(0.58), Inches(1.10),
                                       Inches(5.0), Inches(5.62))
    picture.crop_bottom = 0.25
    picture.line.color.rgb = LINE
    picture.line.width = Pt(0.8)

    px, py, pw, ph = document["highlight"]
    highlight = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(0.58 + px / 900 * 5.0),
        Inches(1.10 + py / 1050 * 5.62),
        Inches(pw / 900 * 5.0),
        Inches(ph / 1050 * 5.62),
    )
    highlight.fill.solid()
    highlight.fill.fore_color.rgb = YELLOW
    set_fill_opacity(highlight, 42)
    highlight.line.color.rgb = MAROON
    highlight.line.width = Pt(1.6)
    if document["highlight_dashed"]:
        highlight.line.dash_style = 4

    card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(5.79), Inches(1.10),
                                  Inches(3.64), Inches(5.20))
    card.fill.solid()
    card.fill.fore_color.rgb = LIGHT
    card.line.color.rgb = LINE
    card.line.width = Pt(0.8)

    badge = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(6.02), Inches(1.30),
                                   Inches(3.18), Inches(0.34))
    badge.fill.solid()
    badge.fill.fore_color.rgb = document["badge_fill"]
    badge.line.fill.background()
    tf = badge.text_frame
    set_text_frame_defaults(tf, 0.025)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    run = p.add_run()
    run.text = document["badge"]
    run.font.name = FONT
    run.font.size = Pt(9)
    run.font.bold = True
    run.font.color.rgb = WHITE

    quote_box = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(6.02), Inches(1.82),
                                       Inches(3.18), Inches(1.88))
    quote_box.fill.solid()
    quote_box.fill.fore_color.rgb = LIGHT_MAROON
    quote_box.line.color.rgb = MAROON
    quote_box.line.width = Pt(1.0)
    tf = quote_box.text_frame
    set_text_frame_defaults(tf, 0.14)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = document["quote"]
    run.font.name = FONT
    run.font.size = Pt(15.2)
    run.font.italic = True
    run.font.color.rgb = DARK

    add_textbox(slide.shapes, 6.02, 3.94, 3.15, 0.27, "HOW CLOSE IS THE ANALOGY?",
                size=9, color=MAROON, bold=True)
    add_textbox(slide.shapes, 6.02, 4.25, 3.16, 1.52, document["analysis"],
                size=12.6, color=DARK)
    add_textbox(slide.shapes, 6.02, 5.92, 3.16, 0.24,
                "Highlighted on the published-page capture", size=8.6,
                color=MID, italic=True, align=PP_ALIGN.CENTER)

    add_footer(slide, document["source"], document["url"])
    add_master_logo(prs, slide)
    return slide


def remove_slide(prs: Presentation, slide_id) -> None:
    prs.part.drop_rel(slide_id.rId)
    prs.slides._sldIdLst.remove(slide_id)


def main() -> None:
    missing = [str(doc["image"]) for doc in DOCUMENTS if not doc["image"].exists()]
    if missing:
        raise FileNotFoundError("Missing page capture(s): " + ", ".join(missing))

    if not BACKUP.exists():
        shutil.copy2(DECK, BACKUP)

    prs = Presentation(BACKUP if BACKUP.exists() else DECK)
    old_opening = prs.slides._sldIdLst[0]
    new_ids = []
    for document in DOCUMENTS:
        add_document_slide(prs, document)
        new_ids.append(prs.slides._sldIdLst[-1])

    remove_slide(prs, old_opening)
    for slide_id in reversed(new_ids):
        prs.slides._sldIdLst.remove(slide_id)
        prs.slides._sldIdLst.insert(0, slide_id)

    prs.save(DECK)


if __name__ == "__main__":
    main()
