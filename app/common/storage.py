"""MinIO / S3-compatible object storage wrapper.

boto3 is synchronous so heavy operations are pushed to ``asyncio.to_thread``
to keep the event loop responsive.  For small localhost payloads the overhead
is negligible.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import boto3
import structlog
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

if TYPE_CHECKING:
    from app.config import Settings

logger = structlog.get_logger(__name__)


class StorageClient:
    """Thin async wrapper around boto3 S3 client pointed at MinIO."""

    def __init__(self, settings: Settings) -> None:
        scheme = "https" if settings.minio_use_ssl else "http"
        self._endpoint_url = f"{scheme}://{settings.minio_endpoint}"
        self._bucket = settings.minio_bucket

        # Public endpoint for presigned URLs (browser-reachable).
        # Falls back to internal endpoint when not configured.
        if settings.minio_public_endpoint:
            self._public_endpoint_url = f"{scheme}://{settings.minio_public_endpoint}"
        else:
            self._public_endpoint_url = self._endpoint_url

        self._client = boto3.client(
            "s3",
            endpoint_url=self._endpoint_url,
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
            config=BotoConfig(signature_version="s3v4"),
            region_name="us-east-1",  # MinIO ignores this but boto3 requires it
        )

    # ------------------------------------------------------------------
    # Bucket management
    # ------------------------------------------------------------------

    async def ensure_bucket(self) -> None:
        """Create the configured bucket if it does not already exist."""

        def _ensure() -> None:
            try:
                self._client.head_bucket(Bucket=self._bucket)
                logger.info("minio.bucket_exists", bucket=self._bucket)
            except ClientError:
                self._client.create_bucket(Bucket=self._bucket)
                logger.info("minio.bucket_created", bucket=self._bucket)

        await asyncio.to_thread(_ensure)

    # ------------------------------------------------------------------
    # Object CRUD
    # ------------------------------------------------------------------

    async def upload_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        """Upload raw bytes and return the object key."""

        def _upload() -> None:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )

        await asyncio.to_thread(_upload)
        logger.info("minio.uploaded", key=key, size=len(data))
        return key

    async def download_bytes(self, key: str) -> bytes:
        """Download an object and return its bytes."""

        def _download() -> bytes:
            resp = self._client.get_object(Bucket=self._bucket, Key=key)
            return bytes(resp["Body"].read())

        return await asyncio.to_thread(_download)

    def _rewrite_presigned_url(self, url: str) -> str:
        """Replace internal MinIO endpoint with public endpoint in presigned URLs."""
        if self._public_endpoint_url != self._endpoint_url:
            return url.replace(self._endpoint_url, self._public_endpoint_url, 1)
        return url

    async def get_presigned_url(self, key: str, expires: int = 3600) -> str:
        """Generate a presigned GET URL for the given object."""

        def _presign() -> str:
            url = self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expires,
            )
            return self._rewrite_presigned_url(str(url))

        return await asyncio.to_thread(_presign)

    async def get_presigned_put_url(
        self, key: str, content_type: str = "application/octet-stream", expires: int = 3600
    ) -> str:
        """Generate a presigned PUT URL for direct upload."""

        def _presign() -> str:
            url = self._client.generate_presigned_url(
                "put_object",
                Params={"Bucket": self._bucket, "Key": key, "ContentType": content_type},
                ExpiresIn=expires,
            )
            return self._rewrite_presigned_url(str(url))

        return await asyncio.to_thread(_presign)

    async def list_objects(self, prefix: str = "") -> list[dict]:
        """List objects under *prefix*. Returns list of ``{"key": ..., "size": ..., "last_modified": ...}``."""

        def _list() -> list[dict]:
            resp = self._client.list_objects_v2(Bucket=self._bucket, Prefix=prefix)
            contents = resp.get("Contents", [])
            return [
                {
                    "key": obj["Key"],
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat(),
                }
                for obj in contents
            ]

        return await asyncio.to_thread(_list)

    async def delete_object(self, key: str) -> None:
        """Delete a single object by key."""

        def _delete() -> None:
            self._client.delete_object(Bucket=self._bucket, Key=key)

        await asyncio.to_thread(_delete)
        logger.info("minio.deleted", key=key)
