#!/usr/bin/env python3
"""Build the presidential-directives workshop deck from the WGPIPL template.

Run with:
    UV_CACHE_DIR=/tmp/prez-authority-uv-cache \
      uv run --offline --with python-pptx \
      python WGPIPL/build_workshop_deck.py [--ecdf PATH]

The optional ECDF asset may be a PDF, PNG, JPEG, or TIFF. When it is omitted,
slide 5 is retained as a clearly marked placeholder so the deck structure and
the other eight slides can still be reviewed.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
from difflib import SequenceMatcher
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml import parse_xml
from pptx.util import Inches, Pt


ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "Nou_Gedid_Lecture.pptx"
OUTPUT = ROOT / "Presidential_Directives_Workshop.pptx"

MAROON = RGBColor(128, 0, 0)
DARK = RGBColor(45, 45, 45)
MID = RGBColor(103, 99, 95)
LIGHT = RGBColor(246, 243, 239)
LIGHT_MAROON = RGBColor(242, 230, 230)
GOLD = RGBColor(166, 124, 0)
OVERLAP_GREEN = RGBColor(15, 110, 70)
WHITE = RGBColor(255, 255, 255)
LINE = RGBColor(205, 199, 193)
FONT = "Garamond"

SLIDE_W = Inches(10)
SLIDE_H = Inches(7.5)


def remove_template_slides(prs: Presentation) -> None:
    """Remove the template's content slides while retaining its masters."""
    for slide_id in list(prs.slides._sldIdLst):
        prs.part.drop_rel(slide_id.rId)
        prs.slides._sldIdLst.remove(slide_id)


def set_text_frame_defaults(text_frame, margin: float = 0.06) -> None:
    text_frame.clear()
    text_frame.word_wrap = True
    text_frame.margin_left = Inches(margin)
    text_frame.margin_right = Inches(margin)
    text_frame.margin_top = Inches(margin)
    text_frame.margin_bottom = Inches(margin)
    text_frame.vertical_anchor = MSO_ANCHOR.TOP


def add_textbox(
    container,
    x: float,
    y: float,
    w: float,
    h: float,
    text: str = "",
    *,
    size: float = 14,
    color: RGBColor = DARK,
    bold: bool = False,
    italic: bool = False,
    align=PP_ALIGN.LEFT,
    font: str = FONT,
    margin: float = 0.06,
):
    box = container.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    set_text_frame_defaults(tf, margin)
    p = tf.paragraphs[0]
    p.alignment = align
    p.space_after = Pt(0)
    run = p.add_run()
    run.text = text
    run.font.name = font
    run.font.size = Pt(size)
    run.font.color.rgb = color
    run.font.bold = bold
    run.font.italic = italic
    return box


def style_run(run, *, size=14, color=DARK, bold=False, italic=False) -> None:
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.color.rgb = color
    run.font.bold = bold
    run.font.italic = italic


def add_mixed_paragraph(text_frame, parts, *, size=14, align=PP_ALIGN.LEFT, after=4):
    p = text_frame.paragraphs[0] if not text_frame.paragraphs[0].text else text_frame.add_paragraph()
    p.alignment = align
    p.space_after = Pt(after)
    for text, kwargs in parts:
        run = p.add_run()
        run.text = text
        style_run(run, size=size, **kwargs)
    return p


def add_title(slide, title: str, subtitle: str | None = None, *, size: float = 25) -> None:
    add_textbox(slide.shapes, 0.55, 0.25, 8.9, 0.48, title, size=size, color=MAROON, bold=True)
    if subtitle:
        add_textbox(slide.shapes, 0.58, 0.73, 8.8, 0.33, subtitle, size=11.5, color=MID, italic=True)


def add_rule(slide, y: float = 1.03) -> None:
    rule = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.58), Inches(y), Inches(8.85), Inches(0.015))
    rule.fill.solid()
    rule.fill.fore_color.rgb = LINE
    rule.line.fill.background()


def add_card(container, x, y, w, h, *, fill=WHITE, line=LINE, radius=False):
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE
    card = container.add_shape(shape_type, Inches(x), Inches(y), Inches(w), Inches(h))
    card.fill.solid()
    card.fill.fore_color.rgb = fill
    card.line.color.rgb = line
    card.line.width = Pt(0.8)
    return card


def add_label(container, x, y, w, text, *, fill=MAROON, color=WHITE):
    tag = container.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(0.28))
    tag.fill.solid()
    tag.fill.fore_color.rgb = fill
    tag.line.fill.background()
    tf = tag.text_frame
    set_text_frame_defaults(tf, 0.02)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = text.upper()
    style_run(r, size=8.5, color=color, bold=True)
    return tag


def add_footer(slide, parts) -> None:
    """Add compact source notes; parts are (text, url-or-None) tuples."""
    box = slide.shapes.add_textbox(Inches(0.58), Inches(6.87), Inches(8.75), Inches(0.25))
    tf = box.text_frame
    set_text_frame_defaults(tf, 0.01)
    p = tf.paragraphs[0]
    p.space_after = Pt(0)
    for text, url in parts:
        r = p.add_run()
        r.text = text
        style_run(r, size=7.6, color=MID, italic=True)
        if url:
            r.hyperlink.address = url


def rasterize_pdf(pdf_path: Path, out_stem: Path) -> Path:
    subprocess.run(
        ["pdftocairo", "-png", "-singlefile", "-r", "300", str(pdf_path), str(out_stem)],
        check=True,
    )
    return out_stem.with_suffix(".png")


def add_picture_fit(slide, image_path: Path, x, y, w, h) -> None:
    with Image.open(image_path) as image:
        img_ratio = image.width / image.height
    box_ratio = w / h
    if img_ratio >= box_ratio:
        draw_w = w
        draw_h = w / img_ratio
        draw_x = x
        draw_y = y + (h - draw_h) / 2
    else:
        draw_h = h
        draw_w = h * img_ratio
        draw_x = x + (w - draw_w) / 2
        draw_y = y
    slide.shapes.add_picture(str(image_path), Inches(draw_x), Inches(draw_y), Inches(draw_w), Inches(draw_h))


def figure_slide(prs, pdf_path: Path, scratch: Path) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    png = rasterize_pdf(pdf_path, scratch / pdf_path.stem)
    add_picture_fit(slide, png, 0.42, 0.22, 9.16, 6.47)


def ecdf_slide(prs, ecdf_path: Path | None, scratch: Path) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    if ecdf_path is not None:
        suffix = ecdf_path.suffix.lower()
        if suffix == ".pdf":
            image_path = rasterize_pdf(ecdf_path, scratch / "path_dependency_ecdf")
        elif suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
            image_path = ecdf_path
        else:
            raise ValueError("The ECDF asset must be a PDF, PNG, JPEG, or TIFF file.")
        add_picture_fit(slide, image_path, 0.42, 0.22, 9.16, 6.47)
        return

    add_title(slide, "Path dependency and text reuse")
    add_rule(slide)
    placeholder = add_card(slide.shapes, 0.78, 1.35, 8.45, 4.75, fill=LIGHT, line=LINE, radius=True)
    placeholder.line.dash_style = None
    add_textbox(
        slide.shapes,
        1.35,
        2.72,
        7.3,
        0.55,
        "ECDF figure pending",
        size=24,
        color=MAROON,
        bold=True,
        align=PP_ALIGN.CENTER,
    )
    add_textbox(
        slide.shapes,
        1.55,
        3.34,
        6.9,
        0.8,
        "Insert the definitive path-dependency text-reuse figure here, unchanged.",
        size=15,
        color=MID,
        italic=True,
        align=PP_ALIGN.CENTER,
    )


def add_document_header(slide, x, title, date, directive_type):
    add_card(slide.shapes, x, 1.20, 4.15, 5.23, fill=WHITE, line=LINE, radius=True)
    add_label(slide.shapes, x + 0.18, 1.38, 1.26, directive_type)
    add_textbox(slide.shapes, x + 0.18, 1.77, 3.78, 0.56, title, size=17, color=MAROON, bold=True)
    add_textbox(slide.shapes, x + 0.18, 2.32, 3.78, 0.30, date, size=10.5, color=MID, italic=True)
    add_textbox(slide.shapes, x + 0.18, 2.67, 3.75, 0.34, "Authority clause (verbatim)", size=10, color=MID, bold=True)
    add_textbox(slide.shapes, x + 0.18, 4.32, 3.75, 0.34, "Operative text (verbatim)", size=10, color=MID, bold=True)


def add_reveal_box(group, x, y, w, h, text, *, fill=LIGHT_MAROON, size=12.4):
    box = add_card(group.shapes, x, y, w, h, fill=fill, line=LINE, radius=True)
    tf = box.text_frame
    set_text_frame_defaults(tf, 0.12)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.space_after = Pt(0)
    r = p.add_run()
    r.text = text
    style_run(r, size=size, color=DARK)
    return box


def add_appear_timing(slide, first_shape_id: int, second_shape_id: int) -> None:
    """Append two on-click native Appear effects to a slide."""
    timing_xml = f"""
    <p:timing xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:tnLst>
        <p:par>
          <p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot">
            <p:childTnLst>
              <p:seq concurrent="1" nextAc="seek">
                <p:cTn id="2" dur="indefinite" nodeType="mainSeq">
                  <p:childTnLst>
                    <p:par>
                      <p:cTn id="3" fill="hold" nodeType="clickEffect" grpId="3"
                              presetID="1" presetClass="entr" presetSubtype="0">
                        <p:stCondLst><p:cond delay="0"/></p:stCondLst>
                        <p:childTnLst>
                          <p:set>
                            <p:cBhvr>
                              <p:cTn id="4" dur="1" fill="hold">
                                <p:stCondLst><p:cond delay="0"/></p:stCondLst>
                              </p:cTn>
                              <p:tgtEl><p:spTgt spid="{first_shape_id}"/></p:tgtEl>
                              <p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst>
                            </p:cBhvr>
                            <p:to><p:strVal val="visible"/></p:to>
                          </p:set>
                        </p:childTnLst>
                      </p:cTn>
                    </p:par>
                    <p:par>
                      <p:cTn id="5" fill="hold" nodeType="clickEffect" grpId="5"
                              presetID="1" presetClass="entr" presetSubtype="0">
                        <p:stCondLst><p:cond delay="0"/></p:stCondLst>
                        <p:childTnLst>
                          <p:set>
                            <p:cBhvr>
                              <p:cTn id="6" dur="1" fill="hold">
                                <p:stCondLst><p:cond delay="0"/></p:stCondLst>
                              </p:cTn>
                              <p:tgtEl><p:spTgt spid="{second_shape_id}"/></p:tgtEl>
                              <p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst>
                            </p:cBhvr>
                            <p:to><p:strVal val="visible"/></p:to>
                          </p:set>
                        </p:childTnLst>
                      </p:cTn>
                    </p:par>
                  </p:childTnLst>
                </p:cTn>
                <p:prevCondLst>
                  <p:cond evt="onPrev" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond>
                </p:prevCondLst>
                <p:nextCondLst>
                  <p:cond evt="onNext" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond>
                </p:nextCondLst>
              </p:seq>
            </p:childTnLst>
          </p:cTn>
        </p:par>
      </p:tnLst>
      <p:bldLst>
        <p:bldP spid="{first_shape_id}" grpId="3" animBg="1"/>
        <p:bldP spid="{second_shape_id}" grpId="5" animBg="1"/>
      </p:bldLst>
    </p:timing>
    """
    slide._element.append(parse_xml(timing_xml))


def authority_comparison_slide(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(slide, "Specific authority, vague authority—and legal effect")
    add_rule(slide)

    left_x, right_x = 0.67, 5.18
    add_document_header(slide, left_x, "Executive Order 13224", "September 23, 2001", "EXECUTIVE ORDER")
    add_document_header(slide, right_x, "Executive Order 13505", "March 9, 2009", "EXECUTIVE ORDER")

    authority_group = slide.shapes.add_group_shape()
    authority_group.name = "AuthorityReveal"
    add_reveal_box(
        authority_group,
        left_x + 0.17,
        3.00,
        3.79,
        1.20,
        "By the authority vested in me as President by the Constitution and the laws of the United States of America, including the International Emergency Economic Powers Act (50 U.S.C. 1701 et seq.)(IEEPA), the National Emergencies Act (50 U.S.C. 1601 et seq.), section 5 of the United Nations Participation Act of 1945, as amended (22 U.S.C. 287c) (UNPA), and section 301 of title 3, United States Code, …",
        size=9.0,
    )
    add_reveal_box(
        authority_group,
        right_x + 0.17,
        3.00,
        3.79,
        1.20,
        "By the authority vested in me as President by the Constitution and the laws of the United States of America, it is hereby ordered as follows:",
        size=11.8,
    )

    operative_group = slide.shapes.add_group_shape()
    operative_group.name = "OperativeReveal"
    add_reveal_box(
        operative_group,
        left_x + 0.17,
        4.63,
        3.79,
        1.40,
        "Section 1. Except to the extent required by section 203(b) of IEEPA (50 U.S.C. 1702(b)), or provided in regulations, orders, directives, or licenses that may be issued pursuant to this order, and notwithstanding any contract entered into or any license or permit granted prior to the effective date of this order, all property and interests in property of the following persons that are in the United States or that hereafter come within the United States, or that hereafter come within the possession or control of United States persons are blocked:",
        fill=LIGHT,
        size=8.7,
    )
    add_reveal_box(
        operative_group,
        right_x + 0.17,
        4.63,
        3.79,
        1.40,
        "Sec. 5. Revocations. (a) The Presidential statement of August 9, 2001, limiting Federal funding for research involving human embryonic stem cells, shall have no further effect as a statement of governmental policy. (b) Executive Order 13435 of June 20, 2007, which supplements the August 9, 2001, statement on human embryonic stem cell research, is revoked.",
        fill=LIGHT,
        size=10.0,
    )

    add_textbox(slide.shapes, 3.69, 6.16, 2.65, 0.28, "Click 1: authority  •  Click 2: effect", size=9.5, color=MID, italic=True, align=PP_ALIGN.CENTER)

    add_footer(
        slide,
        [
            ("Sources: ", None),
            ("EO 13224", "https://www.presidency.ucsb.edu/documents/executive-order-13224-blocking-property-and-prohibiting-transactions-with-persons-who"),
            (" (Sept. 23, 2001); ", None),
            ("EO 13505", "https://www.presidency.ucsb.edu/documents/executive-order-13505-removing-barriers-responsible-scientific-research-involving-human"),
            (" (Mar. 9, 2009). Verbatim excerpts; ellipsis marks cropped continuation.", None),
        ],
    )
    add_appear_timing(slide, authority_group.shape_id, operative_group.shape_id)


def comparison_card(slide, x, label, title, date, parts, *, accent=MAROON, body_size=13.2):
    add_card(slide.shapes, x, 1.53, 4.05, 4.78, fill=WHITE, line=LINE, radius=True)
    add_label(slide.shapes, x + 0.18, 1.72, 1.05, label, fill=accent)
    add_textbox(slide.shapes, x + 0.18, 2.12, 3.68, 0.52, title, size=16.5, color=MAROON, bold=True)
    add_textbox(slide.shapes, x + 0.18, 2.62, 3.68, 0.30, date, size=10.5, color=MID, italic=True)
    body = slide.shapes.add_textbox(Inches(x + 0.18), Inches(3.10), Inches(3.68), Inches(2.85))
    tf = body.text_frame
    set_text_frame_defaults(tf, 0.03)
    tf.clear()
    for index, paragraph_parts in enumerate(parts):
        p = tf.paragraphs[0] if index == 0 else tf.add_paragraph()
        p.space_after = Pt(10)
        for text, kwargs in paragraph_parts:
            r = p.add_run()
            r.text = text
            style_run(r, size=body_size, **kwargs)


def shared_word_parts(left_text, right_text, *, min_block_words=1):
    """Return paired run specifications with reused words highlighted."""
    left_tokens = re.findall(r"\S+\s*", left_text)
    right_tokens = re.findall(r"\S+\s*", right_text)

    def match_key(token):
        stripped = token.strip()
        word = re.sub(r"^\W+|\W+$", "", stripped, flags=re.UNICODE)
        return (word or stripped).casefold()

    matcher = SequenceMatcher(
        None,
        [match_key(token) for token in left_tokens],
        [match_key(token) for token in right_tokens],
        autojunk=False,
    )
    left_shared = set()
    right_shared = set()
    for block in matcher.get_matching_blocks():
        if block.size < min_block_words:
            continue
        left_shared.update(range(block.a, block.a + block.size))
        right_shared.update(range(block.b, block.b + block.size))

    def parts(tokens, shared_indices):
        result = []
        for index, token in enumerate(tokens):
            is_shared = index in shared_indices
            kwargs = {"color": OVERLAP_GREEN if is_shared else DARK, "bold": is_shared}
            if result and result[-1][1] == kwargs:
                result[-1] = (result[-1][0] + token, kwargs)
            else:
                result.append((token, kwargs))
        return result

    return parts(left_tokens, left_shared), parts(right_tokens, right_shared)


def add_arrow(slide, x=4.64, y=3.55):
    arrow = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(x), Inches(y), Inches(0.72), Inches(0.46))
    arrow.fill.solid()
    arrow.fill.fore_color.rgb = MAROON
    arrow.line.fill.background()


def high_confidence_path_slide(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(slide, "Path dependency: policy text travels forward")
    add_textbox(slide.shapes, 0.59, 0.76, 8.8, 0.27, "High-confidence parent–child relationship • verbatim paragraph (1) from each proclamation", size=11.3, color=MID, italic=True)
    add_rule(slide, 1.08)

    parent_text = "(1) In order to provide generally for the preferential tariff treatment being accorded under the Agreement to Honduras and Nicaragua, to provide certain other treatment to originating goods for the purposes of the Agreement, to provide tariff-rate quotas with respect to certain goods, to reflect the removal of Honduras and Nicaragua from the enumeration of designated beneficiary developing countries for purposes of the GSP, to reflect the removal of Honduras and Nicaragua from the enumeration of designated beneficiary countries for purposes of the CBERA and the CBTPA, and to make technical and conforming changes in the general notes to the HTS, the HTS is modified as set forth in Annex I of Publication 3845 of the United States International Trade Commission, entitled Modifications to the Harmonized Tariff Schedule of the United States to Implement the Dominican Republic-Central America-United States Free Trade Agreement With Respect to Honduras and Nicaragua (Publication 3845), which is incorporated by reference into this proclamation."
    child_text = "(1) In order to provide generally for the preferential tariff treatment being accorded under the Agreement to Guatemala, to provide certain other treatment to originating goods for the purposes of the Agreement, to provide tariff-rate quotas with respect to certain goods, to reflect the removal of Guatemala from the enumeration of designated beneficiary developing countries for purposes of the GSP, to reflect the removal of Guatemala from the enumeration of designated beneficiary countries for purposes of the CBERA and the CBTPA, to implement statistical monitoring relating to tariff provisions that the President previously proclaimed to implement the Agreement, and to make technical and conforming changes in the general notes to the HTS, the HTS is modified as set forth in the Annex of Publication 3861 of the United States International Trade Commission, entitled \"Modifications to the Harmonized Tariff Schedule of the United States to Implement the Dominican Republic-Central America-United States Free Trade Agreement With Respect to Guatemala\" (Publication 3861), which is incorporated by reference into this proclamation."
    parent_parts, child_parts = shared_word_parts(parent_text, child_text)
    comparison_card(
        slide,
        0.66,
        "PARENT",
        "Proclamation 7996",
        "March 31, 2006",
        [parent_parts],
        body_size=9.0,
    )
    comparison_card(
        slide,
        5.29,
        "CHILD",
        "Proclamation 8034",
        "June 30, 2006",
        [child_parts],
        body_size=8.7,
    )
    add_arrow(slide)
    add_textbox(slide.shapes, 1.07, 6.39, 7.85, 0.32, "0.802 normalized 5-word reuse  •  0.99 parent-selection confidence", size=12.5, color=MAROON, bold=True, align=PP_ALIGN.CENTER)
    add_footer(
        slide,
        [
            ("Sources: ", None),
            ("Proclamation 7996", "https://www.presidency.ucsb.edu/documents/proclamation-7996-implement-the-dominican-republic-central-america-united-states-free"),
            (" (Mar. 31, 2006) → ", None),
            ("Proclamation 8034", "https://www.presidency.ucsb.edu/documents/proclamation-8034-implement-the-dominican-republic-central-america-united-states-free"),
            (" (June 30, 2006). Verbatim excerpts; vesting clauses excluded from matching.", None),
        ],
    )


def suggestive_path_slide(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(slide, "Path dependency beyond the high-confidence set", size=22)
    add_textbox(slide.shapes, 0.59, 0.76, 8.8, 0.27, "Verbatim ethics-pledge excerpts • substantial reuse, but not a validated parent–child classification", size=11.3, color=MID, italic=True)
    add_rule(slide, 1.08)

    earlier_heading = "Section 1. Ethics Pledge. Every appointee in every executive agency appointed on or after January 20, 2009, shall sign, and upon signing shall be contractually committed to, the following pledge upon becoming an appointee:"
    later_heading = "Section 1. Ethics Pledge. Every appointee in every executive agency appointed on or after January 20, 2021, shall sign, and upon signing shall be contractually committed to, the following pledge upon becoming an appointee:"
    earlier_pledge = "\"As a condition, and in consideration, of my employment in the United States Government in a position invested with the public trust, I commit myself to the following obligations, which I understand are binding on me and are enforceable under law:"
    later_pledge = "\"Accordingly, as a condition, and in consideration, of my employment in the United States Government in a position invested with the public trust, I commit myself to the following obligations, which I understand are binding on me and are enforceable under law:"
    earlier_heading_parts, later_heading_parts = shared_word_parts(earlier_heading, later_heading)
    earlier_pledge_parts, later_pledge_parts = shared_word_parts(earlier_pledge, later_pledge)
    comparison_card(
        slide,
        0.66,
        "EARLIER",
        "Executive Order 13490",
        "January 21, 2009",
        [earlier_heading_parts, earlier_pledge_parts],
        body_size=10.8,
    )
    comparison_card(
        slide,
        5.29,
        "LATER",
        "Executive Order 13989",
        "January 20, 2021",
        [
            later_heading_parts,
            [
                ("\"I recognize that this pledge is part of a broader ethics in government plan designed to restore and maintain public trust in government, and I commit myself to conduct consistent with that plan. I commit to decision-making on the merits and exclusively in the public interest, without regard to private gain or personal benefit. I commit to conduct that upholds the independence of law enforcement and precludes improper interference with investigative or prosecutorial decisions of the Department of Justice.", {"color": DARK, "bold": False}),
            ],
            later_pledge_parts,
        ],
        body_size=9.2,
    )
    add_arrow(slide)
    add_textbox(slide.shapes, 1.17, 6.39, 7.65, 0.32, "656 reused words in the earlier full-corpus alignment measure", size=12.5, color=MAROON, bold=True, align=PP_ALIGN.CENTER)
    add_footer(
        slide,
        [
            ("Sources: ", None),
            ("EO 13490", "https://www.presidency.ucsb.edu/documents/executive-order-13490-ethics-commitments-executive-branch-personnel"),
            (" (Jan. 21, 2009) → ", None),
            ("EO 13989", "https://www.presidency.ucsb.edu/documents/executive-order-13989-ethics-commitments-executive-branch-personnel"),
            (" (Jan. 20, 2021). Verbatim excerpts; score is suggestive, not a validated genealogy.", None),
        ],
    )


def authority_example_card(slide, x, label, title, date, authority, operative, *, authority_size=10.2, operative_size=10.2):
    add_card(slide.shapes, x, 1.34, 4.15, 5.18, fill=WHITE, line=LINE, radius=True)
    add_label(slide.shapes, x + 0.18, 1.53, 1.42, label)
    add_textbox(slide.shapes, x + 0.18, 1.92, 3.78, 0.54, title, size=16.2, color=MAROON, bold=True)
    add_textbox(slide.shapes, x + 0.18, 2.43, 3.78, 0.27, date, size=10.3, color=MID, italic=True)
    add_textbox(slide.shapes, x + 0.18, 2.77, 3.75, 0.26, "Authority clause (verbatim)", size=9.5, color=MID, bold=True)
    add_reveal_box(slide, x + 0.18, 3.05, 3.78, 1.25, authority, size=authority_size)
    add_textbox(slide.shapes, x + 0.18, 4.39, 3.75, 0.26, "Operative text (verbatim)", size=9.5, color=MID, bold=True)
    add_reveal_box(slide, x + 0.18, 4.67, 3.78, 1.48, operative, fill=LIGHT, size=operative_size)


def golan_slide(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(slide, "Consequential action under boilerplate authority")
    add_textbox(slide.shapes, 0.59, 0.76, 8.8, 0.27, "A substantive proclamation with no named constitutional or statutory provision", size=11.3, color=MID, italic=True)
    add_rule(slide, 1.08)
    add_card(slide.shapes, 0.83, 1.42, 8.34, 4.93, fill=WHITE, line=LINE, radius=True)
    add_label(slide.shapes, 1.08, 1.69, 1.45, "PROCLAMATION")
    add_textbox(slide.shapes, 1.08, 2.10, 7.82, 0.72, "Proclamation 9852 — Recognizing the Golan Heights as Part of the State of Israel", size=18.5, color=MAROON, bold=True)
    add_textbox(slide.shapes, 1.08, 2.83, 7.82, 0.28, "March 25, 2019", size=10.8, color=MID, italic=True)
    box = add_card(slide.shapes, 1.08, 3.25, 7.82, 2.38, fill=LIGHT_MAROON, line=LINE, radius=True)
    tf = box.text_frame
    set_text_frame_defaults(tf, 0.18)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.space_after = Pt(0)
    for text, kwargs in [
        ("Now, Therefore, I, Donald J. Trump, President of the United States of America, ", {"color": DARK, "bold": False}),
        ("by virtue of the authority vested in me by the Constitution and the laws of the United States", {"color": GOLD, "bold": True}),
        (", do hereby proclaim that, the United States recognizes that the Golan Heights are part of the State of Israel.", {"color": DARK, "bold": False}),
    ]:
        r = p.add_run()
        r.text = text
        style_run(r, size=18, **kwargs)
    add_footer(slide, [("Source: ", None), ("Proclamation 9852", "https://www.presidency.ucsb.edu/documents/proclamation-9852-recognizing-the-golan-heights-part-the-state-israel"), (" (Mar. 25, 2019). Full operative paragraph reproduced verbatim.", None)])


def trade_authority_slide(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(slide, "Trade policy: generic authority versus statutory detail")
    add_rule(slide)
    authority_example_card(
        slide, 0.67, "GENERIC", "TPP withdrawal memorandum", "January 23, 2017",
        "Based on these principles, and by the authority vested in me as President by the Constitution and the laws of the United States of America,",
        "I hereby direct you to withdraw the United States as a signatory to the Trans-Pacific Partnership (TPP), to permanently withdraw the United States from TPP negotiations, and to begin pursuing, wherever possible, bilateral trade negotiations to promote American industry, protect American workers, and raise American wages.",
        authority_size=11.2, operative_size=10.2,
    )
    authority_example_card(
        slide, 5.18, "SPECIFIC", "Proclamation 10053 — USMCA", "June 29, 2020",
        "Now, Therefore, I, Donald J. Trump, President of the United States of America, by virtue of the authority vested in me by the Constitution and the laws of the United States of America, including sections 103(c), 105(a), 207, 324, and 611(a) of the USMCA Implementation Act; section 1206(a) of the 1988 Act; … section 604 of the 1974 Act; and section 301 of title 3, United States Code, do hereby proclaim:",
        "(1) In order to provide generally for the preferential tariff treatment being accorded under the USMCA … the HTS is modified as set forth in Annex I of Publication 5060 of the United States International Trade Commission.",
        authority_size=8.5, operative_size=10.2,
    )
    add_footer(slide, [("Sources: ", None), ("TPP memorandum", "https://www.presidency.ucsb.edu/documents/memorandum-withdrawal-the-united-states-from-the-trans-pacific-partnership-negotiations"), (" (Jan. 23, 2017); ", None), ("Proclamation 10053", "https://www.presidency.ucsb.edu/documents/proclamation-10053-take-certain-actions-under-the-united-states-mexico-canada-agreement"), (" (June 29, 2020). Verbatim excerpts; ellipses mark cropped continuation.", None)])


def employment_authority_slide(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(slide, "The same provision, supported differently")
    add_textbox(slide.shapes, 0.59, 0.76, 8.8, 0.27, "Both orders amend the first sentence of Executive Order 11478", size=11.3, color=MID, italic=True)
    add_rule(slide, 1.08)
    authority_example_card(
        slide, 0.67, "GENERIC", "Executive Order 13087", "May 28, 1998",
        "By the authority vested in me as President by the Constitution and the laws of the United States, and in order to provide for a uniform policy for the Federal Government to prohibit discrimination based on sexual orientation, it is hereby ordered that Executive Order 11478, as amended, is further amended as follows:",
        "Section 1. The first sentence of section 1 is amended by substituting “age, or sexual orientation” for “or age”.",
        authority_size=10.1, operative_size=12.0,
    )
    authority_example_card(
        slide, 5.18, "SPECIFIC", "Executive Order 13672", "July 21, 2014",
        "By the authority vested in me as President by the Constitution and the laws of the United States of America, including 40 U.S.C. 121, and in order to provide for a uniform policy for the Federal Government to prohibit discrimination and take further steps to promote economy and efficiency in Federal Government procurement by prohibiting discrimination based on sexual orientation and gender identity, it is hereby ordered as follows:",
        "Section 1. Amending Executive Order 11478. The first sentence of section 1 of Executive Order 11478 of August 8, 1969, as amended, is revised by substituting “sexual orientation, gender identity” for “sexual orientation”.",
        authority_size=8.8, operative_size=10.4,
    )
    add_footer(slide, [("Sources: ", None), ("EO 13087", "https://www.presidency.ucsb.edu/documents/executive-order-13087-further-amendment-executive-order-11478-equal-employment-opportunity"), (" (May 28, 1998); ", None), ("EO 13672", "https://www.presidency.ucsb.edu/documents/executive-order-13672-further-amendments-executive-order-11478-equal-employment"), (" (July 21, 2014). Verbatim excerpts.", None)])


def immigration_authority_slide(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(slide, "Immigration policy: generic authority versus a named statute")
    add_rule(slide)
    authority_example_card(
        slide, 0.67, "GENERIC", "DACA preservation memorandum", "January 20, 2021",
        "By the authority vested in me as President by the Constitution and the laws of the United States, it is hereby ordered as follows:",
        "The Secretary of Homeland Security, in consultation with the Attorney General, shall take all actions he deems appropriate, consistent with applicable law, to preserve and fortify DACA.",
        authority_size=11.3, operative_size=11.6,
    )
    authority_example_card(
        slide, 5.18, "SPECIFIC", "Executive Order 13768", "January 25, 2017",
        "By the authority vested in me as President by the Constitution and the laws of the United States of America, including the Immigration and Nationality Act (INA) (8 U.S.C. 1101 et seq.), and in order to ensure the public safety of the American people in communities across the United States, as well as to ensure that our Nation's immigration laws are faithfully executed, I hereby declare the policy of the executive branch to be, and order, as follows:",
        "It is the policy of the executive branch to: (a) Ensure the faithful execution of the immigration laws of the United States, including the INA, against all removable aliens, consistent with Article II, Section 3 of the United States Constitution and with the INA;",
        authority_size=8.8, operative_size=10.0,
    )
    add_footer(slide, [("Sources: ", None), ("DACA memorandum", "https://www.presidency.ucsb.edu/documents/memorandum-preserving-and-fortifying-deferred-action-for-childhood-arrivals-daca"), (" (Jan. 20, 2021); ", None), ("EO 13768", "https://www.presidency.ucsb.edu/documents/executive-order-13768-enhancing-public-safety-the-interior-the-united-states"), (" (Jan. 25, 2017). Verbatim excerpts.", None)])


def truman_commission_path_slide(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(slide, "One commission template, two policy destinations")
    add_textbox(slide.shapes, 0.59, 0.76, 8.8, 0.27, "Outside the automatic-parent set • verbatim institutional clauses", size=11.3, color=MID, italic=True)
    add_rule(slide, 1.08)
    comparison_card(slide, 0.55, "EARLIER", "EO 9981 — Military equality", "July 26, 1948", [[("All executive departments and agencies of the Federal Government are authorized and directed to cooperate with the Committee in its work, and to furnish the Committee such information or the services of such persons as the Committee may require in the performance of its duties.", {"color": DARK, "bold": False})], [("The Committee shall continue to exist until such time as the President shall terminate its existence by Executive order.", {"color": DARK, "bold": False})]], body_size=11.0)
    add_arrow(slide, 4.49, 3.44)
    add_card(slide.shapes, 5.23, 1.38, 4.22, 2.38, fill=WHITE, line=LINE, radius=True)
    add_label(slide.shapes, 5.42, 1.57, 1.05, "LATER")
    add_textbox(slide.shapes, 5.42, 1.94, 3.78, 0.38, "EO 10005 — Puerto Rico", size=15.2, color=MAROON, bold=True)
    add_textbox(slide.shapes, 5.42, 2.31, 3.78, 1.16, "All executive departments and agencies of the Federal Government are authorized and directed to cooperate with the Commission in its work and to furnish the Commission such information as the Commission may require in the performance of its duties.", size=10.2, color=DARK)
    add_card(slide.shapes, 5.23, 3.94, 4.22, 2.38, fill=WHITE, line=LINE, radius=True)
    add_label(slide.shapes, 5.42, 4.13, 1.05, "LATER")
    add_textbox(slide.shapes, 5.42, 4.50, 3.78, 0.38, "EO 10013 — Military welfare", size=15.2, color=MAROON, bold=True)
    add_textbox(slide.shapes, 5.42, 4.87, 3.78, 1.10, "The Committee shall … confer and advise with the Secretary of Defense and the Secretaries of the Army, Navy, and Air Force … and make such recommendations to the President and the said Secretaries as it shall deem appropriate.", size=10.2, color=DARK)
    add_footer(slide, [("Sources: ", None), ("EO 9981", "https://www.presidency.ucsb.edu/documents/executive-order-9981-establishing-the-presidents-committee-equality-treatment-and"), (" → ", None), ("EO 10005", "https://www.presidency.ucsb.edu/documents/executive-order-10005-establishing-the-presidents-advisory-commission-the-relation-federal"), (" and ", None), ("EO 10013", "https://www.presidency.ucsb.edu/documents/executive-order-10013-establishing-the-presidents-committee-religious-and-moral-welfare"), (". Verbatim excerpts; ellipses mark cropped continuation.", None)])


def eisenhower_committee_path_slide(prs) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(slide, "Suggestive reuse in committee-establishment letters")
    add_textbox(slide.shapes, 0.59, 0.76, 8.8, 0.27, "Outside the automatic-parent set • different policy fields, parallel drafting sequence", size=11.3, color=MID, italic=True)
    add_rule(slide, 1.08)
    shared = {"color": DARK, "bold": False}
    comparison_card(slide, 0.66, "EARLIER", "Cabinet Committee on Water Resources", "May 26, 1954", [[("To meet the needs to which I have referred above, ", shared), ("I am establishing", {"color": OVERLAP_GREEN, "bold": True}), (" a Cabinet Committee on Water Resources Policy. ", shared), ("I am designating you the Chairman", {"color": OVERLAP_GREEN, "bold": True}), (" of the Cabinet Committee on Water Resources Policy.", shared)], [("The Secretary of Commerce, the Secretary of Health, Education and Welfare and the Director of the Bureau of the Budget will participate on an ad hoc basis.", shared)]], body_size=11.2)
    comparison_card(slide, 5.29, "LATER", "Interdepartmental Committee on Migratory Labor", "August 26, 1954", [[("As you have suggested, ", shared), ("I am establishing", {"color": OVERLAP_GREEN, "bold": True}), (" an Interdepartmental Committee on Migratory Labor … ", shared), ("I am designating you as Chairman", {"color": OVERLAP_GREEN, "bold": True}), (".", shared)], [("There are other departments and agencies which have major interests in specific areas, and I shall expect you, as Chairman, to keep them informed and to invite their participation as needed.", shared)]], body_size=10.8)
    add_arrow(slide)
    add_footer(slide, [("Sources: Eisenhower letters establishing the ", None), ("Cabinet Committee on Water Resources Policy", "https://www.presidency.ucsb.edu/documents/letter-secretary-mckay-establishing-cabinet-committee-water-resources-policy"), (" (May 26, 1954) and the ", None), ("Interdepartmental Committee on Migratory Labor", "https://www.presidency.ucsb.edu/documents/letter-secretary-mitchell-establishing-interdepartmental-committee-migratory-labor"), (" (Aug. 26, 1954). Verbatim excerpts.", None)])


def build(ecdf_path: Path | None, output_path: Path) -> None:
    prs = Presentation(str(TEMPLATE))
    remove_template_slides(prs)
    if prs.slide_width != SLIDE_W or prs.slide_height != SLIDE_H:
        raise ValueError("Template is not the expected 10 × 7.5 inch (4:3) format.")

    figure_pdfs = [
        ROOT / "vc_shares_all_directives_with_counts.pdf",
        ROOT / "vc_shares_executive_orders_with_counts.pdf",
        ROOT / "vc_shares_memos_with_counts.pdf",
        ROOT / "vc_shares_proclamations_with_counts.pdf",
    ]
    for path in figure_pdfs:
        if not path.exists():
            raise FileNotFoundError(path)
    if ecdf_path is not None and not ecdf_path.exists():
        raise FileNotFoundError(ecdf_path)

    with tempfile.TemporaryDirectory(prefix="workshop_deck_") as scratch_dir:
        scratch = Path(scratch_dir)
        for pdf_path in figure_pdfs:
            figure_slide(prs, pdf_path, scratch)
        ecdf_slide(prs, ecdf_path, scratch)
        authority_comparison_slide(prs)
        high_confidence_path_slide(prs)
        suggestive_path_slide(prs)
        golan_slide(prs)
        trade_authority_slide(prs)
        employment_authority_slide(prs)
        immigration_authority_slide(prs)
        truman_commission_path_slide(prs)
        eisenhower_committee_path_slide(prs)
        prs.save(str(output_path))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ecdf", type=Path, default=ROOT / "word5_reuse_distribution_ecdf.pdf", help="Path to the definitive ECDF figure")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    build(args.ecdf, args.output)
    print(args.output)
