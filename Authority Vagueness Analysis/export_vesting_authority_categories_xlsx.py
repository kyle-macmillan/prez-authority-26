"""Export all vesting-authority categories to an Excel workbook."""

from __future__ import annotations

import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse
from xml.sax.saxutils import escape, quoteattr

from vesting_authority_breakdown import (
    CATEGORIES,
    POSSIBLE_VESTING_RE,
    PRESIDENTIAL_TITLE_INVOCATION_RE,
    classify_authority_category,
    extract_vesting_clauses,
)
from vesting_authority_stats import DEFAULT_DEV, DEFAULT_HOLDOUT, load_corpus


ANALYSIS_DIR = Path(__file__).resolve().parent
OUTPUT = ANALYSIS_DIR / "vesting_authority_all_categories.xlsx"
TARGETS = CATEGORIES
SHEET_NAMES = {
    "generic_constitution_only": "1 Generic Constitution",
    "specific_constitution_only": "2 Specific Constitution",
    "generic_statute_only": "3 Generic Statute",
    "specific_statute_only": "4 Specific Statute",
    "generic_constitution_and_generic_statute": "5 Gen Const + Gen Statute",
    "generic_constitution_and_specific_statute": "6 Gen Const + Spec Statute",
    "specific_constitution_and_generic_statute": "7 Spec Const + Gen Statute",
    "specific_constitution_and_specific_statute": "8 Spec Const + Spec Statute",
    "no_vesting_clause": "No Vesting Clause",
    "other_vesting_authority": "Other Authority",
}
HEADERS = ("Title", "Directive Type", "Year", "Administration", "URL to UCSB Link", "Full Text")
EXCEL_CELL_CHAR_LIMIT = 32_767


def title_from_url(url: str) -> str:
    slug = unquote(urlparse(url).path.rstrip("/").split("/")[-1])
    return slug.replace("-", " ").title()


def sheet_name(category: str) -> str:
    return SHEET_NAMES[category]


def cell_ref(column: int, row: int) -> str:
    letters = ""
    while column:
        column, remainder = divmod(column - 1, 26)
        letters = chr(65 + remainder) + letters
    return f"{letters}{row}"


def inline_cell(column: int, row: int, value: object, style: int = 0) -> str:
    ref = cell_ref(column, row)
    text = "" if value is None else str(value)
    preserve = ' xml:space="preserve"' if text != text.strip() else ""
    return (
        f'<c r="{ref}" s="{style}" t="inlineStr"><is><t{preserve}>'
        f"{escape(text)}</t></is></c>"
    )


def number_cell(column: int, row: int, value: int) -> str:
    return f'<c r="{cell_ref(column, row)}" s="2"><v>{value}</v></c>'


def worksheet_xml(rows: list[tuple[str, str, int, str, str, str]]) -> str:
    xml_rows = []
    header = "".join(inline_cell(column, 1, value, 1) for column, value in enumerate(HEADERS, 1))
    xml_rows.append(f'<row r="1" ht="22" customHeight="1">{header}</row>')
    hyperlinks = []
    for row_number, values in enumerate(rows, 2):
        title, directive_type, year, administration, url, full_text = values
        cells = (
            inline_cell(1, row_number, title)
            + inline_cell(2, row_number, directive_type)
            + number_cell(3, row_number, year)
            + inline_cell(4, row_number, administration)
            + inline_cell(5, row_number, url, 3)
            + inline_cell(6, row_number, full_text)
        )
        xml_rows.append(f'<row r="{row_number}">{cells}</row>')
        hyperlinks.append(f'<hyperlink ref="E{row_number}" r:id="rId{row_number - 1}"/>')

    last_row = max(1, len(rows) + 1)
    hyperlinks_xml = f"<hyperlinks>{''.join(hyperlinks)}</hyperlinks>" if hyperlinks else ""
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
 <sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>
 <cols><col min="1" max="1" width="54" customWidth="1"/><col min="2" max="2" width="19" customWidth="1"/><col min="3" max="3" width="10" customWidth="1"/><col min="4" max="4" width="31" customWidth="1"/><col min="5" max="5" width="72" customWidth="1"/><col min="6" max="6" width="100" customWidth="1"/></cols>
 <sheetData>{''.join(xml_rows)}</sheetData>
 <autoFilter ref="A1:F{last_row}"/>
 {hyperlinks_xml}
</worksheet>'''


def worksheet_relationships(rows: list[tuple[str, str, int, str, str, str]]) -> str:
    relationships = "".join(
        f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target={quoteattr(row[4])} TargetMode="External"/>'
        for index, row in enumerate(rows, 1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{relationships}</Relationships>'''


def write_workbook(path: Path, sheets: list[tuple[str, list[tuple[str, str, int, str, str, str]]]]) -> None:
    sheet_elements = "".join(
        f'<sheet name={quoteattr(name)} sheetId="{index}" r:id="rId{index}"/>'
        for index, (name, _) in enumerate(sheets, 1)
    )
    workbook_rels = "".join(
        f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, len(sheets) + 1)
    )
    workbook_rels += f'<Relationship Id="rId{len(sheets) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    sheet_overrides = "".join(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, len(sheets) + 1)
    )
    created = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    files = {
        "[Content_Types].xml": f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>{sheet_overrides}</Types>''',
        "_rels/.rels": '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>''',
        "docProps/core.xml": f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>All Vesting Authority Categories</dc:title><dc:creator>Prez Authority 26</dc:creator><dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created></cp:coreProperties>''',
        "docProps/app.xml": '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>Prez Authority 26</Application></Properties>''',
        "xl/workbook.xml": f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>{sheet_elements}</sheets></workbook>''',
        "xl/_rels/workbook.xml.rels": f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{workbook_rels}</Relationships>''',
        "xl/styles.xml": '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="3"><font><sz val="11"/><name val="Calibri"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font><font><u/><color rgb="FF0563C1"/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF1F4E78"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="4"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="center"/></xf><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment horizontal="center"/></xf><xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>''',
    }
    for index, (_, rows) in enumerate(sheets, 1):
        files[f"xl/worksheets/sheet{index}.xml"] = worksheet_xml(rows)
        files[f"xl/worksheets/_rels/sheet{index}.xml.rels"] = worksheet_relationships(rows)

    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as workbook:
        for name, content in files.items():
            workbook.writestr(name, content)


def main() -> None:
    categorized = {category: [] for category in TARGETS}
    corpus = load_corpus([DEFAULT_DEV, DEFAULT_HOLDOUT])
    for row in corpus:
        text = row["doc_text"]
        clauses = (
            extract_vesting_clauses(text, row["doc_type"])
            if POSSIBLE_VESTING_RE.search(text) or PRESIDENTIAL_TITLE_INVOCATION_RE.search(text)
            else []
        )
        values = (
            title_from_url(row["url"]),
            row["doc_type"].replace("_", " ").title(),
            int(row["date"][-4:]),
            f'{row["president"]} ({row["term"]})',
            row["url"],
            row["doc_text"][:EXCEL_CELL_CHAR_LIMIT],
        )
        category = classify_authority_category(clauses)
        categorized[category].append(values)

    sheets = [(sheet_name(category), categorized[category]) for category in TARGETS]
    categorized_total = sum(len(rows) for rows in categorized.values())
    if categorized_total != len(corpus):
        raise ValueError("Excel category total does not match the number of exported directives")
    write_workbook(OUTPUT, sheets)
    print(OUTPUT)
    for name, rows in sheets:
        print(f"{name}: {len(rows):,} directives")


if __name__ == "__main__":
    main()
