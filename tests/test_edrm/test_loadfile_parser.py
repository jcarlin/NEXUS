"""Tests for EDRM load file parsers: Concordance DAT, Opticon OPT, EDRM XML."""

from __future__ import annotations

from app.edrm.loadfile_parser import LoadFileParser


# ---------------------------------------------------------------------------
# Concordance DAT (1)
# ---------------------------------------------------------------------------

def test_parse_dat_basic():
    """Parse a simple Concordance DAT file with standard delimiters."""
    # U+00FE = text qualifier, U+0014 = field separator
    q = "\u00fe"
    d = "\u0014"
    content = (
        f"{q}DOCID{q}{d}{q}BEGDOC{q}{d}{q}ENDDOC{q}{d}{q}CUSTODIAN{q}\n"
        f"{q}DOC001{q}{d}{q}DOC001{q}{d}{q}DOC001{q}{d}{q}John Smith{q}\n"
        f"{q}DOC002{q}{d}{q}DOC002{q}{d}{q}DOC003{q}{d}{q}Jane Doe{q}\n"
    )

    records = LoadFileParser.parse_dat(content)

    assert len(records) == 2
    assert records[0].doc_id == "DOC001"
    assert records[0].fields["CUSTODIAN"] == "John Smith"
    assert records[1].doc_id == "DOC002"
    assert records[1].fields["CUSTODIAN"] == "Jane Doe"


# ---------------------------------------------------------------------------
# Opticon OPT (1)
# ---------------------------------------------------------------------------

def test_parse_opt_basic():
    """Parse a simple Opticon OPT file."""
    content = (
        "DOC001,VOL001,IMAGES\\DOC001\\001.tif,Y,,2\n"
        "DOC002,VOL001,IMAGES\\DOC002\\001.tif,Y,,1\n"
    )

    records = LoadFileParser.parse_opt(content)

    assert len(records) == 2
    assert records[0].doc_id == "DOC001"
    assert records[0].volume == "VOL001"
    assert records[0].image_path == "IMAGES\\DOC001\\001.tif"
    assert records[0].document_break == "Y"
    assert records[0].pages == "2"
    assert records[1].doc_id == "DOC002"


# ---------------------------------------------------------------------------
# EDRM XML (1)
# ---------------------------------------------------------------------------

def test_parse_edrm_xml_basic():
    """Parse a simple EDRM XML file with Document and Tag elements."""
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<EDRMExport>
  <Document DocID="DOC001">
    <File FileType="native" FileName="contract.pdf">documents/contract.pdf</File>
    <Tag TagName="Custodian" TagValue="John Smith"/>
    <Tag TagName="DateCreated" TagValue="2024-01-15"/>
  </Document>
  <Document DocID="DOC002">
    <File FileType="native" FileName="email.eml">documents/email.eml</File>
    <Tag TagName="Custodian" TagValue="Jane Doe"/>
  </Document>
</EDRMExport>"""

    records = LoadFileParser.parse_edrm_xml(xml_content)

    assert len(records) == 2
    assert records[0].doc_id == "DOC001"
    assert records[0].fields["Custodian"] == "John Smith"
    assert records[0].fields["DateCreated"] == "2024-01-15"
    assert records[0].fields["File_Path"] == "documents/contract.pdf"
    assert records[1].doc_id == "DOC002"
    assert records[1].fields["Custodian"] == "Jane Doe"


# ---------------------------------------------------------------------------
# EDRM XML round-trip (1)
# ---------------------------------------------------------------------------

def test_edrm_xml_round_trip():
    """Export records as EDRM XML, then re-parse and verify consistency."""
    from app.edrm.schemas import LoadFileRecord

    original_records = [
        LoadFileRecord(
            doc_id="DOC001",
            fields={"Custodian": "Alice", "Subject": "Contract Review"},
        ),
        LoadFileRecord(
            doc_id="DOC002",
            fields={"Custodian": "Bob", "Subject": "Financial Summary"},
        ),
    ]

    xml_output = LoadFileParser.export_edrm_xml(original_records)
    assert "DOC001" in xml_output
    assert "DOC002" in xml_output

    # Re-parse
    parsed_records = LoadFileParser.parse_edrm_xml(xml_output)

    assert len(parsed_records) == 2
    assert parsed_records[0].doc_id == "DOC001"
    assert parsed_records[0].fields["Custodian"] == "Alice"
    assert parsed_records[0].fields["Subject"] == "Contract Review"
    assert parsed_records[1].doc_id == "DOC002"
    assert parsed_records[1].fields["Custodian"] == "Bob"
