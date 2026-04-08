"""Format-specific export generators (all sync, called from Celery task).

Each generator queries the database, assembles output, and returns bytes.
"""

from __future__ import annotations

import csv
import io
import json
import tempfile
import zipfile
from datetime import UTC, datetime

import structlog
from sqlalchemy import text

logger = structlog.get_logger(__name__)

# Privilege status to legal basis mapping
_PRIVILEGE_BASIS = {
    "privileged": "Attorney-Client Privilege",
    "work_product": "Work Product Doctrine",
}


def _query_documents(engine, matter_id: str, doc_ids: list[str] | None = None) -> list[dict]:
    """Query documents from the database, optionally filtered by doc_ids."""
    with engine.connect() as conn:
        if doc_ids:
            result = conn.execute(
                text("""
                    SELECT id, filename, document_type, page_count,
                           minio_path, file_size_bytes, bates_begin, bates_end,
                           privilege_status, privilege_reviewed_by,
                           privilege_reviewed_at, created_at, metadata_
                    FROM documents
                    WHERE matter_id = :matter_id AND id = ANY(:doc_ids)
                    ORDER BY created_at ASC
                """),
                {"matter_id": matter_id, "doc_ids": doc_ids},
            )
        else:
            result = conn.execute(
                text("""
                    SELECT id, filename, document_type, page_count,
                           minio_path, file_size_bytes, bates_begin, bates_end,
                           privilege_status, privilege_reviewed_by,
                           privilege_reviewed_at, created_at, metadata_
                    FROM documents
                    WHERE matter_id = :matter_id
                    ORDER BY created_at ASC
                """),
                {"matter_id": matter_id},
            )
        return [dict(r._mapping) for r in result.all()]


def generate_court_ready(
    engine,
    matter_id: str,
    doc_ids: list[str] | None = None,
    production_set_id: str | None = None,
) -> bytes:
    """Generate a court-ready export package as a ZIP archive.

    Contains:
    - privilege_log.csv -- privileged/work_product docs with Bates ranges
    - citation_index.csv -- doc_id, filename, bates_begin, bates_end, page_count
    - manifest.json -- metadata (timestamp, doc count, params)
    - documents/ -- references to files (paths in manifest, not actual file content)
    """
    docs = _query_documents(engine, matter_id, doc_ids)

    buf = tempfile.SpooledTemporaryFile(max_size=10 * 1024 * 1024)
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # citation_index.csv
        csv_buf = io.StringIO()
        writer = csv.writer(csv_buf)
        writer.writerow(["doc_id", "filename", "bates_begin", "bates_end", "page_count"])
        for doc in docs:
            writer.writerow(
                [
                    str(doc["id"]),
                    doc["filename"],
                    doc.get("bates_begin") or "",
                    doc.get("bates_end") or "",
                    doc.get("page_count") or 0,
                ]
            )
        zf.writestr("citation_index.csv", csv_buf.getvalue())

        # privilege_log.csv
        priv_buf = io.StringIO()
        priv_writer = csv.writer(priv_buf)
        priv_writer.writerow(
            [
                "Bates Begin",
                "Bates End",
                "Filename",
                "Doc Type",
                "Date",
                "Privilege Status",
                "Privilege Basis",
                "Reviewed By",
                "Reviewed At",
            ]
        )
        for doc in docs:
            priv_status = doc.get("privilege_status")
            if priv_status in ("privileged", "work_product"):
                priv_writer.writerow(
                    [
                        doc.get("bates_begin") or "",
                        doc.get("bates_end") or "",
                        doc["filename"],
                        doc.get("document_type") or "",
                        doc.get("created_at").isoformat() if doc.get("created_at") else "",
                        priv_status,
                        _PRIVILEGE_BASIS.get(priv_status, ""),
                        str(doc.get("privilege_reviewed_by") or ""),
                        doc.get("privilege_reviewed_at").isoformat() if doc.get("privilege_reviewed_at") else "",
                    ]
                )
        zf.writestr("privilege_log.csv", priv_buf.getvalue())

        # manifest.json
        manifest = {
            "export_type": "court_ready",
            "matter_id": matter_id,
            "generated_at": datetime.now(UTC).isoformat(),
            "document_count": len(docs),
            "documents": [
                {
                    "doc_id": str(doc["id"]),
                    "filename": doc["filename"],
                    "minio_path": doc.get("minio_path") or "",
                    "bates_begin": doc.get("bates_begin"),
                    "bates_end": doc.get("bates_end"),
                }
                for doc in docs
            ],
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, default=str))

    buf.seek(0)
    data = buf.read()
    buf.close()

    logger.info(
        "export.court_ready.generated",
        matter_id=matter_id,
        document_count=len(docs),
        size_bytes=len(data),
    )
    return data


def generate_edrm_package(
    engine,
    matter_id: str,
    doc_ids: list[str] | None = None,
) -> bytes:
    """Generate an EDRM XML export package as a ZIP archive.

    Contains:
    - loadfile.xml -- EDRM XML with Document/Tag elements
    - loadfile.dat -- Concordance DAT format
    - manifest.json -- metadata
    """
    from app.edrm.loadfile_parser import LoadFileParser
    from app.edrm.schemas import LoadFileRecord

    docs = _query_documents(engine, matter_id, doc_ids)

    # Build LoadFileRecord objects with BEGBATES/ENDBATES
    records: list[LoadFileRecord] = []
    for doc in docs:
        fields: dict[str, str] = {
            "DOCID": str(doc["id"]),
            "FILENAME": doc["filename"],
            "DOCTYPE": doc.get("document_type") or "",
            "PAGECOUNT": str(doc.get("page_count") or 0),
        }
        if doc.get("bates_begin"):
            fields["BEGBATES"] = doc["bates_begin"]
        if doc.get("bates_end"):
            fields["ENDBATES"] = doc["bates_end"]
        if doc.get("minio_path"):
            fields["File_Path"] = doc["minio_path"]

        records.append(LoadFileRecord(doc_id=str(doc["id"]), fields=fields))

    # Generate EDRM XML
    edrm_xml = LoadFileParser.export_edrm_xml(records)

    # Generate Concordance DAT
    dat_buf = io.StringIO()
    delimiter = "\u0014"
    qualifier = "\u00fe"
    if records:
        # Header
        all_keys = list(records[0].fields.keys())
        dat_buf.write(delimiter.join(f"{qualifier}{k}{qualifier}" for k in all_keys))
        dat_buf.write("\n")
        # Data rows
        for rec in records:
            values = [rec.fields.get(k, "") for k in all_keys]
            dat_buf.write(delimiter.join(f"{qualifier}{v}{qualifier}" for v in values))
            dat_buf.write("\n")

    buf = tempfile.SpooledTemporaryFile(max_size=10 * 1024 * 1024)
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("loadfile.xml", edrm_xml)
        zf.writestr("loadfile.dat", dat_buf.getvalue())

        manifest = {
            "export_type": "edrm_xml",
            "matter_id": matter_id,
            "generated_at": datetime.now(UTC).isoformat(),
            "document_count": len(docs),
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, default=str))

    buf.seek(0)
    data = buf.read()
    buf.close()

    logger.info(
        "export.edrm.generated",
        matter_id=matter_id,
        document_count=len(docs),
        size_bytes=len(data),
    )
    return data


def generate_privilege_log(
    engine,
    matter_id: str,
    production_set_id: str | None = None,
    fmt: str = "csv",
) -> bytes:
    """Generate a privilege log as CSV.

    Columns: Bates Begin, Bates End, Filename, Doc Type, Date, From, To,
             Subject, Privilege Status, Privilege Basis, Reviewed By, Reviewed At
    """
    with engine.connect() as conn:
        if production_set_id:
            result = conn.execute(
                text("""
                    SELECT psd.bates_begin, psd.bates_end,
                           d.filename, d.document_type, d.document_date,
                           d.privilege_status, d.privilege_reviewed_by,
                           d.privilege_reviewed_at, d.metadata_
                    FROM documents d
                    JOIN production_set_documents psd ON psd.document_id = d.id
                    WHERE d.matter_id = :matter_id
                      AND psd.production_set_id = :ps_id
                      AND d.privilege_status IN ('privileged', 'work_product')
                    ORDER BY psd.bates_begin ASC NULLS LAST
                """),
                {"matter_id": matter_id, "ps_id": production_set_id},
            )
        else:
            result = conn.execute(
                text("""
                    SELECT bates_begin, bates_end,
                           filename, document_type, document_date,
                           privilege_status, privilege_reviewed_by,
                           privilege_reviewed_at, metadata_
                    FROM documents
                    WHERE matter_id = :matter_id
                      AND privilege_status IN ('privileged', 'work_product')
                    ORDER BY bates_begin ASC NULLS LAST
                """),
                {"matter_id": matter_id},
            )
        rows = result.all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "Bates Begin",
            "Bates End",
            "Filename",
            "Doc Type",
            "Date",
            "From",
            "To",
            "Subject",
            "Privilege Status",
            "Privilege Basis",
            "Reviewed By",
            "Reviewed At",
        ]
    )

    for row in rows:
        m = dict(row._mapping)
        priv = m.get("privilege_status", "")
        basis = _PRIVILEGE_BASIS.get(priv, "")

        # Extract email metadata if available
        meta = m.get("metadata_") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except (json.JSONDecodeError, TypeError):
                meta = {}

        writer.writerow(
            [
                m.get("bates_begin") or "",
                m.get("bates_end") or "",
                m.get("filename") or "",
                m.get("document_type") or "",
                m.get("document_date").isoformat() if m.get("document_date") else "",
                meta.get("from", ""),
                meta.get("to", ""),
                meta.get("subject", ""),
                priv,
                basis,
                str(m.get("privilege_reviewed_by") or ""),
                m.get("privilege_reviewed_at").isoformat() if m.get("privilege_reviewed_at") else "",
            ]
        )

    data = buf.getvalue().encode("utf-8")

    logger.info(
        "export.privilege_log.generated",
        matter_id=matter_id,
        entry_count=len(rows),
        size_bytes=len(data),
    )
    return data


def generate_result_set(
    engine,
    matter_id: str,
    doc_ids: list[str] | None = None,
    fmt: str = "csv",
) -> bytes:
    """Generate a result set export as CSV.

    Columns: doc_id, filename, doc_type, page_count, bates_begin, bates_end,
             privilege_status
    """
    docs = _query_documents(engine, matter_id, doc_ids)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "doc_id",
            "filename",
            "doc_type",
            "page_count",
            "bates_begin",
            "bates_end",
            "privilege_status",
        ]
    )

    for doc in docs:
        writer.writerow(
            [
                str(doc["id"]),
                doc["filename"],
                doc.get("document_type") or "",
                doc.get("page_count") or 0,
                doc.get("bates_begin") or "",
                doc.get("bates_end") or "",
                doc.get("privilege_status") or "",
            ]
        )

    data = buf.getvalue().encode("utf-8")

    logger.info(
        "export.result_set.generated",
        matter_id=matter_id,
        document_count=len(docs),
        size_bytes=len(data),
    )
    return data
