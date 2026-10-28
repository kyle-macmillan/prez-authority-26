"""Insert the vesting-authority figure at the beginning of manuscript section III."""

from __future__ import annotations

import copy
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent.parent
DOCUMENT = ROOT / "paper" / "pres claims of legal authority, WGPIPL, jn.docx"
IMAGE = ROOT / "WGPIPL" / "authority_category_distribution_by_administration.png"
MEDIA_NAME = "authority_category_distribution_by_administration.png"
CAPTION = "Number of directives by vesting-authority category and administration"
BOOKMARK_NAME = "_RefAuthorityCategoryFigure"
AUTHOR = "Codex"

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
PIC_NS = "http://schemas.openxmlformats.org/drawingml/2006/picture"
W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"
WP14_NS = "http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

for prefix, namespace in (
    ("w", W_NS),
    ("r", R_NS),
    ("a", A_NS),
    ("wp", WP_NS),
    ("pic", PIC_NS),
    ("w14", W14_NS),
    ("wp14", WP14_NS),
):
    ET.register_namespace(prefix, namespace)
ET.register_namespace("", REL_NS)


def q(namespace: str, tag: str) -> str:
    return f"{{{namespace}}}{tag}"


def paragraph_text(paragraph: ET.Element) -> str:
    return "".join(node.text or "" for node in paragraph.iter(q(W_NS, "t"))).strip()


def next_numeric_id(root: ET.Element, attribute: str) -> int:
    values = []
    for node in root.iter():
        value = node.get(attribute)
        if value and value.isdigit():
            values.append(int(value))
    return max(values, default=0) + 1


def run(text: str | None = None) -> ET.Element:
    element = ET.Element(q(W_NS, "r"))
    properties = ET.SubElement(element, q(W_NS, "rPr"))
    fonts = ET.SubElement(properties, q(W_NS, "rFonts"))
    fonts.set(q(W_NS, "ascii"), "Times New Roman")
    fonts.set(q(W_NS, "hAnsi"), "Times New Roman")
    fonts.set(q(W_NS, "cs"), "Times New Roman")
    if text is not None:
        text_element = ET.SubElement(element, q(W_NS, "t"))
        text_element.text = text
    return element


def revision(tag: str, revision_id: int, when: str, children: list[ET.Element]) -> ET.Element:
    element = ET.Element(q(W_NS, tag))
    element.set(q(W_NS, "id"), str(revision_id))
    element.set(q(W_NS, "author"), AUTHOR)
    element.set(q(W_NS, "date"), when)
    for child in children:
        element.append(child)
    return element


def image_paragraph(relationship_id: str, drawing_id: int, revision_id: int, when: str) -> ET.Element:
    paragraph = ET.Element(q(W_NS, "p"))
    properties = ET.SubElement(paragraph, q(W_NS, "pPr"))
    ET.SubElement(properties, q(W_NS, "keepNext"))
    spacing = ET.SubElement(properties, q(W_NS, "spacing"))
    spacing.set(q(W_NS, "after"), "120")
    spacing.set(q(W_NS, "line"), "240")
    spacing.set(q(W_NS, "lineRule"), "auto")

    image_run = run()
    no_proof = ET.SubElement(image_run.find(q(W_NS, "rPr")), q(W_NS, "noProof"))
    drawing = ET.SubElement(image_run, q(W_NS, "drawing"))
    inline = ET.SubElement(drawing, q(WP_NS, "inline"), {"distT": "0", "distB": "0", "distL": "0", "distR": "0"})
    ET.SubElement(inline, q(WP_NS, "extent"), {"cx": "5702300", "cy": "3543300"})
    ET.SubElement(inline, q(WP_NS, "effectExtent"), {"l": "0", "t": "0", "r": "0", "b": "0"})
    ET.SubElement(inline, q(WP_NS, "docPr"), {"id": str(drawing_id), "name": "Authority category figure"})
    frame_properties = ET.SubElement(inline, q(WP_NS, "cNvGraphicFramePr"))
    ET.SubElement(frame_properties, q(A_NS, "graphicFrameLocks"), {"noChangeAspect": "1"})
    graphic = ET.SubElement(inline, q(A_NS, "graphic"))
    graphic_data = ET.SubElement(graphic, q(A_NS, "graphicData"), {"uri": PIC_NS})
    picture = ET.SubElement(graphic_data, q(PIC_NS, "pic"))
    nonvisual = ET.SubElement(picture, q(PIC_NS, "nvPicPr"))
    ET.SubElement(nonvisual, q(PIC_NS, "cNvPr"), {"id": str(drawing_id), "name": MEDIA_NAME})
    ET.SubElement(nonvisual, q(PIC_NS, "cNvPicPr"))
    fill = ET.SubElement(picture, q(PIC_NS, "blipFill"))
    ET.SubElement(fill, q(A_NS, "blip"), {q(R_NS, "embed"): relationship_id})
    stretch = ET.SubElement(fill, q(A_NS, "stretch"))
    ET.SubElement(stretch, q(A_NS, "fillRect"))
    shape = ET.SubElement(picture, q(PIC_NS, "spPr"))
    transform = ET.SubElement(shape, q(A_NS, "xfrm"))
    ET.SubElement(transform, q(A_NS, "off"), {"x": "0", "y": "0"})
    ET.SubElement(transform, q(A_NS, "ext"), {"cx": "5702300", "cy": "3543300"})
    geometry = ET.SubElement(shape, q(A_NS, "prstGeom"), {"prst": "rect"})
    ET.SubElement(geometry, q(A_NS, "avLst"))
    paragraph.append(revision("ins", revision_id, when, [image_run]))
    return paragraph


def caption_paragraph(bookmark_id: int, revision_id: int, when: str) -> ET.Element:
    paragraph = ET.Element(q(W_NS, "p"))
    properties = ET.SubElement(paragraph, q(W_NS, "pPr"))
    ET.SubElement(properties, q(W_NS, "pStyle"), {q(W_NS, "val"): "Caption"})
    ET.SubElement(paragraph, q(W_NS, "bookmarkStart"), {q(W_NS, "id"): str(bookmark_id), q(W_NS, "name"): BOOKMARK_NAME})

    children = [run("Figure ")]
    begin = run()
    ET.SubElement(begin, q(W_NS, "fldChar"), {q(W_NS, "fldCharType"): "begin"})
    children.append(begin)
    instruction = run()
    instruction_text = ET.SubElement(instruction, q(W_NS, "instrText"))
    instruction_text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    instruction_text.text = " SEQ Figure \\* ARABIC "
    children.append(instruction)
    separate = run()
    ET.SubElement(separate, q(W_NS, "fldChar"), {q(W_NS, "fldCharType"): "separate"})
    children.append(separate)
    children.append(run("1"))
    end = run()
    ET.SubElement(end, q(W_NS, "fldChar"), {q(W_NS, "fldCharType"): "end"})
    children.extend([end, run(f": {CAPTION}")])
    paragraph.append(revision("ins", revision_id, when, children))
    ET.SubElement(paragraph, q(W_NS, "bookmarkEnd"), {q(W_NS, "id"): str(bookmark_id)})
    return paragraph


def tracked_field_result_change(paragraph: ET.Element, old: str, new: str, revision_id: int, when: str) -> int:
    """Replace a cached field result, splitting an existing insertion when necessary."""
    direct_children = list(paragraph)
    for direct_index, direct_child in enumerate(direct_children):
        candidates = list(direct_child) if direct_child.tag == q(W_NS, "ins") else [direct_child]
        for child_index, candidate in enumerate(candidates):
            texts = list(candidate.iter(q(W_NS, "t")))
            if len(texts) != 1 or texts[0].text != old:
                continue
            old_run = copy.deepcopy(candidate)
            old_text = next(old_run.iter(q(W_NS, "t")))
            old_text.tag = q(W_NS, "delText")
            new_run = copy.deepcopy(candidate)
            next(new_run.iter(q(W_NS, "t"))).text = new
            replacement = [
                revision("del", revision_id, when, [old_run]),
                revision("ins", revision_id + 1, when, [new_run]),
            ]
            if direct_child.tag == q(W_NS, "ins"):
                before = copy.deepcopy(direct_child)
                after = copy.deepcopy(direct_child)
                before[:] = candidates[:child_index]
                after[:] = candidates[child_index + 1 :]
                replacement = ([before] if len(before) else []) + replacement + ([after] if len(after) else [])
            paragraph.remove(direct_child)
            for offset, element in enumerate(replacement):
                paragraph.insert(direct_index + offset, element)
            return revision_id + 2
    raise ValueError(f"could not find cached field result {old!r}")


def main() -> None:
    if not IMAGE.exists():
        raise FileNotFoundError(f"generate the figure first: {IMAGE}")

    with zipfile.ZipFile(DOCUMENT) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}

    document = ET.fromstring(files["word/document.xml"])
    body = document.find(f".//{q(W_NS, 'body')}")
    if body is None:
        raise ValueError("document body not found")
    paragraphs = body.findall(q(W_NS, "p"))
    if any(BOOKMARK_NAME == node.get(q(W_NS, "name")) for node in document.iter(q(W_NS, "bookmarkStart"))):
        raise ValueError("authority-category figure is already present")
    section_three = next((p for p in paragraphs if paragraph_text(p) == "III.Data and Preliminary Results"), None)
    if section_three is None:
        raise ValueError("section III heading not found")

    relationships = ET.fromstring(files["word/_rels/document.xml.rels"])
    relationship_numbers = [
        int(node.get("Id")[3:])
        for node in relationships
        if (node.get("Id") or "").startswith("rId") and (node.get("Id") or "")[3:].isdigit()
    ]
    relationship_id = f"rId{max(relationship_numbers, default=0) + 1}"
    ET.SubElement(
        relationships,
        q(REL_NS, "Relationship"),
        {
            "Id": relationship_id,
            "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
            "Target": f"media/{MEDIA_NAME}",
        },
    )

    content_types = ET.fromstring(files["[Content_Types].xml"])
    if not any(node.get("Extension") == "png" for node in content_types):
        ET.SubElement(content_types, q(CT_NS, "Default"), {"Extension": "png", "ContentType": "image/png"})

    when = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    revision_id = next_numeric_id(document, q(W_NS, "id"))
    bookmark_id = revision_id + 10
    drawing_id = max(
        [int(node.get("id")) for node in document.iter(q(WP_NS, "docPr")) if (node.get("id") or "").isdigit()],
        default=0,
    ) + 1

    insert_at = list(body).index(section_three) + 1
    body.insert(insert_at, image_paragraph(relationship_id, drawing_id, revision_id, when))
    body.insert(insert_at + 1, caption_paragraph(bookmark_id, revision_id + 1, when))
    revision_id += 2

    existing_caption = next(
        p for p in body.findall(q(W_NS, "p"))
        if paragraph_text(p).startswith("Figure 1: Distribution of directives")
    )
    revision_id = tracked_field_result_change(existing_caption, "1", "2", revision_id, when)
    reference_paragraph = next(
        p for p in body.findall(q(W_NS, "p"))
        if "Figure 1 in the Appendix shows" in paragraph_text(p)
    )
    tracked_field_result_change(reference_paragraph, "1", "2", revision_id, when)

    files["word/document.xml"] = ET.tostring(document, encoding="utf-8", xml_declaration=True)
    files["word/_rels/document.xml.rels"] = ET.tostring(relationships, encoding="utf-8", xml_declaration=True)
    files["[Content_Types].xml"] = ET.tostring(content_types, encoding="utf-8", xml_declaration=True)
    files[f"word/media/{MEDIA_NAME}"] = IMAGE.read_bytes()

    with tempfile.NamedTemporaryFile(dir=DOCUMENT.parent, suffix=".docx", delete=False) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with zipfile.ZipFile(temporary_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, content in files.items():
                archive.writestr(name, content)
        temporary_path.replace(DOCUMENT)
    finally:
        temporary_path.unlink(missing_ok=True)
    print(DOCUMENT)


if __name__ == "__main__":
    main()
