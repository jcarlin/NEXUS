"""EDRM load file parsers for Concordance DAT, Opticon OPT, and EDRM XML.

Handles the three most common load file formats used in e-discovery:
- Concordance DAT: Delimited text (U+00014 field separator, U+00FE text qualifier)
- Opticon OPT: Comma-separated image cross-reference
- EDRM XML: Standard XML format with Document/File/Tag elements
"""

from __future__ import annotations

import csv
import io
import xml.etree.ElementTree as ET
from pathlib import Path

import structlog

from app.edrm.schemas import LoadFileRecord, OpticonRecord

logger = structlog.get_logger(__name__)

# Concordance delimiters
_CONCORDANCE_DELIMITER = "\u0014"  # Unicode "information separator four"
_CONCORDANCE_QUALIFIER = "\u00fe"  # Latin small letter thorn (Concordance text qualifier)


class LoadFileParser:
    """Parse EDRM load files into structured records."""

    # ------------------------------------------------------------------
    # Concordance DAT
    # ------------------------------------------------------------------

    @staticmethod
    def parse_dat(content: str) -> list[LoadFileRecord]:
        """Parse a Concordance DAT file into LoadFileRecords.

        Concordance DAT uses U+0014 as the field delimiter and U+00FE as
        the text qualifier (wrapping field values that may contain the
        delimiter or newlines).
        """
        records: list[LoadFileRecord] = []

        lines = content.split("\n")
        if not lines:
            return records

        # Parse header
        header_line = lines[0].strip()
        headers = LoadFileParser._split_concordance_line(header_line)

        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue
            values = LoadFileParser._split_concordance_line(line)

            fields: dict[str, str] = {}
            for i, header in enumerate(headers):
                if i < len(values):
                    fields[header] = values[i]
                else:
                    fields[header] = ""

            # Use first field as doc_id, or look for common ID field names
            doc_id = ""
            for id_field in ("DOCID", "DocID", "doc_id", "ID", "BEGDOC"):
                if id_field in fields:
                    doc_id = fields[id_field]
                    break
            if not doc_id and fields:
                doc_id = next(iter(fields.values()))

            records.append(LoadFileRecord(doc_id=doc_id, fields=fields))

        logger.info("loadfile.dat.parsed", record_count=len(records))
        return records

    @staticmethod
    def _split_concordance_line(line: str) -> list[str]:
        """Split a Concordance DAT line on the field delimiter.

        Handles the U+00FE text qualifier by stripping it from field values.
        """
        parts = line.split(_CONCORDANCE_DELIMITER)
        result: list[str] = []
        for part in parts:
            # Strip text qualifier from both ends
            value = part.strip(_CONCORDANCE_QUALIFIER).strip()
            result.append(value)
        return result

    # ------------------------------------------------------------------
    # Opticon OPT
    # ------------------------------------------------------------------

    @staticmethod
    def parse_opt(content: str) -> list[OpticonRecord]:
        """Parse an Opticon OPT file into OpticonRecords.

        Opticon OPT is a comma-separated format with fields:
        DocID, Volume, ImagePath, DocumentBreak, BoxOrFolder, Pages
        """
        records: list[OpticonRecord] = []

        reader = csv.reader(io.StringIO(content))
        for row in reader:
            if not row or not row[0].strip():
                continue

            record = OpticonRecord(
                doc_id=row[0].strip() if len(row) > 0 else "",
                volume=row[1].strip() if len(row) > 1 else "",
                image_path=row[2].strip() if len(row) > 2 else "",
                document_break=row[3].strip() if len(row) > 3 else "",
                box_or_folder=row[4].strip() if len(row) > 4 else "",
                pages=row[5].strip() if len(row) > 5 else "",
            )
            records.append(record)

        logger.info("loadfile.opt.parsed", record_count=len(records))
        return records

    # ------------------------------------------------------------------
    # EDRM XML
    # ------------------------------------------------------------------

    @staticmethod
    def parse_edrm_xml(content: str) -> list[LoadFileRecord]:
        """Parse an EDRM XML file into LoadFileRecords.

        Expects the standard EDRM XML structure with Document elements
        containing File and Tag children.
        """
        records: list[LoadFileRecord] = []

        root = ET.fromstring(content)

        # Handle namespaced or non-namespaced XML
        ns = ""
        if root.tag.startswith("{"):
            ns = root.tag.split("}")[0] + "}"

        # Find all Document elements
        doc_elements = root.findall(f".//{ns}Document")
        if not doc_elements:
            # Try without namespace
            doc_elements = root.findall(".//Document")

        for doc_elem in doc_elements:
            doc_id = doc_elem.get("DocID", "") or doc_elem.get("docid", "")
            fields: dict[str, str] = {}

            # Extract attributes
            for attr_name, attr_value in doc_elem.attrib.items():
                fields[attr_name] = attr_value

            # Extract File elements
            files = doc_elem.findall(f"{ns}File") or doc_elem.findall("File")
            for i, file_elem in enumerate(files):
                prefix = f"File_{i}" if i > 0 else "File"
                for attr_name, attr_value in file_elem.attrib.items():
                    fields[f"{prefix}_{attr_name}"] = attr_value
                if file_elem.text and file_elem.text.strip():
                    fields[f"{prefix}_Path"] = file_elem.text.strip()

            # Extract Tag elements
            tags = doc_elem.findall(f"{ns}Tag") or doc_elem.findall("Tag")
            for tag_elem in tags:
                tag_name = tag_elem.get("TagName", "") or tag_elem.get("name", "")
                tag_value = tag_elem.get("TagValue", "") or tag_elem.get("value", "")
                if not tag_value and tag_elem.text:
                    tag_value = tag_elem.text.strip()
                if tag_name:
                    fields[tag_name] = tag_value

            records.append(LoadFileRecord(doc_id=doc_id, fields=fields))

        logger.info("loadfile.edrm_xml.parsed", record_count=len(records))
        return records

    @staticmethod
    def export_edrm_xml(records: list[LoadFileRecord]) -> str:
        """Export LoadFileRecords as EDRM XML.

        Produces a well-formed XML document with Document/Tag elements.
        """
        root = ET.Element("EDRMExport")

        for record in records:
            doc_elem = ET.SubElement(root, "Document", DocID=record.doc_id)

            # Separate file-related fields from tag fields
            file_fields: dict[str, str] = {}
            tag_fields: dict[str, str] = {}

            for key, value in record.fields.items():
                if key.startswith("File_") or key == "File_Path":
                    file_fields[key] = value
                elif key in ("DocID",):
                    continue  # Already in the Document element attribute
                else:
                    tag_fields[key] = value

            # Write File element if there are file fields
            if file_fields:
                file_elem = ET.SubElement(doc_elem, "File")
                for key, value in file_fields.items():
                    clean_key = key.replace("File_", "")
                    file_elem.set(clean_key, value)

            # Write Tag elements
            for tag_name, tag_value in tag_fields.items():
                ET.SubElement(doc_elem, "Tag", TagName=tag_name, TagValue=tag_value)

        ET.indent(root, space="  ")
        return ET.tostring(root, encoding="unicode", xml_declaration=True)
