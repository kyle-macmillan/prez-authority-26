#!/usr/bin/env python3
import json
from pathlib import Path
from pptx import Presentation
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches
from pptx.util import Pt
import build_workshop_deck as st

DECK = Path(__file__).with_name("Presidential_Directives_Workshop.pptx")


def text(shape, value, size=None):
    tf = shape.text_frame
    while len(tf.paragraphs) > 1:
        tf._element.remove(tf.paragraphs[-1]._element)
    p = tf.paragraphs[0]
    r = p.runs[0] if p.runs else p.add_run()
    for extra in list(p.runs[1:]):
        p._element.remove(extra._r)
    r.text = value
    if size:
        r.font.size = Pt(size)


def linked_footer(shape, parts):
    tf = shape.text_frame
    tf.clear()
    p = tf.paragraphs[0]
    for value, url in parts:
        r = p.add_run()
        r.text = value
        st.style_run(r, size=7.6, color=st.MID, italic=True)
        if url:
            r.hyperlink.address = url


def revise_covid(slide):
    s = slide.shapes
    text(s[0], "Federal-contractor COVID rules: specific and generic authority", 22)
    s[0].height = Inches(0.72)
    text(s[2], "GENERIC")
    text(s[3], "Executive Order 14099")
    text(s[4], "May 9, 2023")
    text(s[6], "By the authority vested in me as President by the Constitution and the laws of the United States of America, it is hereby ordered as follows:", 11.3)
    text(s[8], "Sec. 2. Revocation of Vaccination Requirements. Executive Order 14042 and Executive Order 14043 are revoked. Agency policies adopted to implement Executive Order 14042 or Executive Order 14043, to the extent such policies are premised on those orders, no longer may be enforced and shall be rescinded consistent with applicable law.", 9.7)
    text(s[9], "SPECIFIC")
    text(s[10], "Executive Order 14042")
    text(s[11], "September 9, 2021")
    text(s[13], "By the authority vested in me as President by the Constitution and the laws of the United States of America, including the Federal Property and Administrative Services Act, 40 U.S.C. 101 et seq., and section 301 of title 3, United States Code, and in order to promote economy and efficiency in procurement by contracting with sources that provide adequate COVID-19 safeguards for their workforce, it is hereby ordered as follows:", 8.5)
    text(s[15], "Executive departments and agencies, including independent establishments subject to the Federal Property and Administrative Services Act, 40 U.S.C. 102(4)(A) (agencies), shall, to the extent permitted by law, ensure that contracts and contract-like instruments (as described in section 5(a) of this order) include a clause that the contractor and any subcontractors (at any tier) shall incorporate into lower-tier subcontracts.", 8.5)
    linked_footer(s[16], [
        ("Sources: ", None),
        ("EO 14099", "https://www.presidency.ucsb.edu/documents/executive-order-14099-moving-beyond-covid-19-vaccination-requirements-for-federal-workers"),
        (" (2023); ", None),
        ("EO 14042", "https://www.presidency.ucsb.edu/documents/executive-order-14042-ensuring-adequate-covid-safety-protocols-for-federal-contractors"),
        (" (2021). Verbatim excerpts.", None),
    ])
    s[16].text_frame.paragraphs[0].alignment = PP_ALIGN.LEFT


def add_paragraph(tf, parts, size=9.0, after=6):
    p = tf.paragraphs[0] if not tf.paragraphs[0].text else tf.add_paragraph()
    p.space_after = Pt(after)
    for value, color, bold in parts:
        r = p.add_run()
        r.text = value
        st.style_run(r, size=size, color=color, bold=bold)


def task_force_column(slide, x, label, title_value, date, sections):
    st.add_label(slide.shapes, x, 1.48, 1.05, label)
    st.add_textbox(slide.shapes, x, 1.87, 3.76, 0.54, title_value, size=16.0, color=st.MAROON, bold=True)
    st.add_textbox(slide.shapes, x, 2.39, 3.76, 0.28, date, size=10.3, color=st.MID, italic=True)
    box = slide.shapes.add_textbox(Inches(x), Inches(2.86), Inches(3.76), Inches(3.43))
    tf = box.text_frame
    st.set_text_frame_defaults(tf, 0.02)
    tf.clear()
    for heading, parts in sections:
        add_paragraph(tf, [(heading, st.MAROON, True)], size=9.5, after=2)
        add_paragraph(tf, parts, size=8.9, after=7)


def revise_task_force(slide):
    for shape in list(slide.shapes):
        shape._element.getparent().remove(shape._element)
    st.add_title(slide, "A task-force template reused seven years later")
    st.add_textbox(slide.shapes, 0.59, 0.76, 8.8, 0.27, "Outside the automatic-parent set • matched verbatim clauses aligned in the same rows", size=11.3, color=st.MID, italic=True)
    st.add_rule(slide, 1.08)
    corpus = DECK.parent.parent / "data/parent_analysis_full/directive_similarity_documents.jsonl"
    urls = {
        "earlier": "memorandum-the-white-house-task-force-middle-class-working-families",
        "later": "memorandum-the-white-house-cancer-moonshot-task-force",
    }
    docs = {}
    with corpus.open() as source:
        for line in source:
            item = json.loads(line)
            for key, suffix in urls.items():
                if item["url"].endswith(suffix):
                    docs[key] = item["cleaned_masked_text"]

    def excerpt(value, start, end):
        return value[value.index(start):value.index(end)].strip()

    def sections(value, admin_start):
        return [
            ("Section 1. Establishment", excerpt(value, "There is established", "(a) Membership")),
            ("(a) Membership", excerpt(value, "such other executive branch", "(b) Administration")),
            ("(b) Administration", excerpt(value, admin_start, "Sec. 2.")),
        ]

    earlier_sections = sections(docs["earlier"], "The Department of Labor")
    later_sections = sections(docs["later"], "The NIH")
    highlighted_earlier = []
    highlighted_later = []
    for (earlier_heading, earlier_text), (later_heading, later_text) in zip(earlier_sections, later_sections):
        earlier_parts, later_parts = st.shared_word_parts(earlier_text, later_text, min_block_words=2)
        highlighted_earlier.append((earlier_heading, [(value, style["color"], style["bold"]) for value, style in earlier_parts]))
        highlighted_later.append((later_heading, [(value, style["color"], style["bold"]) for value, style in later_parts]))

    task_force_column(slide, 0.72, "EARLIER", "Middle-Class Working Families", "January 30, 2009", highlighted_earlier)
    task_force_column(slide, 5.48, "LATER", "Cancer Moonshot", "January 28, 2016", highlighted_later)
    st.add_arrow(slide, 4.64, 4.10)
    st.add_footer(slide, [
        ("Sources: Obama, ", None),
        ("Middle-Class Working Families Task Force", "https://www.presidency.ucsb.edu/documents/memorandum-the-white-house-task-force-middle-class-working-families"),
        (" (2009) → ", None),
        ("Cancer Moonshot Task Force", "https://www.presidency.ucsb.edu/documents/memorandum-the-white-house-cancer-moonshot-task-force"),
        (" (2016). Verbatim excerpts.", None),
    ])
    slide.shapes[-1].text_frame.paragraphs[0].alignment = PP_ALIGN.LEFT


def delete_slide(prs, index):
    slide_id = prs.slides._sldIdLst[index]
    prs.part.drop_rel(slide_id.rId)
    prs.slides._sldIdLst.remove(slide_id)


def main():
    prs = Presentation(DECK)
    revise_covid(prs.slides[8])
    revise_task_force(prs.slides[12])
    if len(prs.slides) > 13:
        delete_slide(prs, 13)
    prs.save(DECK)


if __name__ == "__main__":
    main()
