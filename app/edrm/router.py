"""EDRM interop API endpoints.

POST /edrm/import       -- import a load file (Concordance DAT, Opticon OPT, EDRM XML)
GET  /edrm/export        -- export documents as EDRM XML
GET  /edrm/threads       -- list email threads
GET  /edrm/duplicates    -- list duplicate clusters
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.middleware import get_current_user, get_matter_id
from app.auth.schemas import UserRecord
from app.dependencies import get_db
from app.edrm.loadfile_parser import LoadFileParser
from app.edrm.schemas import (
    DuplicateCluster,
    DuplicateClusterListResponse,
    EDRMImportResponse,
    ImportStatus,
    LoadFileFormat,
    LoadFileRecord,
    OpticonRecord,
    ThreadListResponse,
    ThreadResponse,
)
from app.edrm.service import EDRMService

router = APIRouter(prefix="/edrm", tags=["edrm"])


# -----------------------------------------------------------------------
# POST /edrm/import — import a load file
# -----------------------------------------------------------------------


@router.post("/import", response_model=EDRMImportResponse)
async def import_loadfile(
    file: UploadFile = File(...),
    format: LoadFileFormat = Query(..., description="Load file format"),
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """Import an EDRM load file and log the import."""
    content = (await file.read()).decode("utf-8", errors="replace")

    records: list[LoadFileRecord] | list[OpticonRecord] = []
    if format == LoadFileFormat.CONCORDANCE_DAT:
        records = LoadFileParser.parse_dat(content)
    elif format == LoadFileFormat.OPTICON_OPT:
        records = LoadFileParser.parse_opt(content)
    elif format == LoadFileFormat.EDRM_XML:
        records = LoadFileParser.parse_edrm_xml(content)

    # Persist BEGBATES/ENDBATES from parsed records onto documents table
    from app.exports.service import ExportService

    bates_updated = await ExportService.import_bates_from_loadfile(
        db=db,
        matter_id=matter_id,
        records=records,
    )

    log_entry = await EDRMService.create_import_log(
        db=db,
        matter_id=matter_id,
        filename=file.filename or "unknown",
        fmt=format.value,
        record_count=len(records),
        status="complete",
    )

    return EDRMImportResponse(
        import_id=log_entry["id"],
        status=ImportStatus.COMPLETE,
        record_count=len(records),
        message=f"Parsed {len(records)} records from {format.value} ({bates_updated} Bates numbers imported)",
    )


# -----------------------------------------------------------------------
# GET /edrm/export — export documents as EDRM XML
# -----------------------------------------------------------------------


@router.get("/export")
async def export_edrm(
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """Export matter documents as EDRM XML."""
    from sqlalchemy import text

    from app.edrm.schemas import LoadFileRecord

    result = await db.execute(
        text(
            """
            SELECT id, filename, document_type, page_count,
                   content_hash, minio_path
            FROM documents
            WHERE matter_id = :matter_id
            ORDER BY created_at
            """
        ),
        {"matter_id": matter_id},
    )
    rows = result.all()

    records = []
    for row in rows:
        mapping = row._mapping
        records.append(
            LoadFileRecord(
                doc_id=str(mapping["id"]),
                fields={
                    "Filename": mapping["filename"] or "",
                    "DocumentType": mapping["document_type"] or "",
                    "PageCount": str(mapping["page_count"] or 0),
                    "ContentHash": mapping["content_hash"] or "",
                    "MinIOPath": mapping["minio_path"] or "",
                },
            )
        )

    xml_output = LoadFileParser.export_edrm_xml(records)

    from fastapi.responses import Response

    return Response(
        content=xml_output,
        media_type="application/xml",
        headers={"Content-Disposition": f"attachment; filename=edrm_export_{matter_id}.xml"},
    )


# -----------------------------------------------------------------------
# GET /edrm/threads — list email threads
# -----------------------------------------------------------------------


@router.get("/threads", response_model=ThreadListResponse)
async def list_threads(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """List email threads for the current matter."""
    items, total = await EDRMService.list_threads(
        db=db,
        matter_id=matter_id,
        offset=offset,
        limit=limit,
    )
    return ThreadListResponse(
        items=[
            ThreadResponse(
                thread_id=item["thread_id"],
                message_count=item["message_count"],
                earliest=item.get("earliest"),
                latest=item.get("latest"),
            )
            for item in items
        ],
        total=total,
        offset=offset,
        limit=limit,
    )


# -----------------------------------------------------------------------
# GET /edrm/duplicates — list duplicate clusters
# -----------------------------------------------------------------------


@router.get("/duplicates", response_model=DuplicateClusterListResponse)
async def list_duplicates(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: UserRecord = Depends(get_current_user),
    matter_id: UUID = Depends(get_matter_id),
):
    """List duplicate clusters for the current matter."""
    items, total = await EDRMService.list_duplicate_clusters(
        db=db,
        matter_id=matter_id,
        offset=offset,
        limit=limit,
    )
    return DuplicateClusterListResponse(
        items=[
            DuplicateCluster(
                cluster_id=item["cluster_id"],
                document_count=item["document_count"],
                avg_score=item.get("avg_score"),
            )
            for item in items
        ],
        total=total,
        offset=offset,
        limit=limit,
    )
