import io
import hashlib
import logging
from typing import Optional, Tuple
from datetime import datetime, timedelta
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class StorageService:
    def __init__(self):
        self._client = None
        self._bucket = settings.s3_bucket
        self._available = False
        try:
            self._init_client()
            self._ensure_bucket()
            self._available = True
        except Exception as e:
            logger.warning(f"Storage service initialization failed: {e}. Uploads will be skipped.")

    def _init_client(self):
        config_kwargs = {
            "aws_access_key_id": settings.s3_access_key,
            "aws_secret_access_key": settings.s3_secret_key,
            "region_name": settings.s3_region,
            "config": Config(signature_version="s3v4"),
        }
        if settings.s3_endpoint_url:
            config_kwargs["endpoint_url"] = settings.s3_endpoint_url
            config_kwargs["use_ssl"] = settings.s3_use_ssl
        self._client = boto3.client("s3", **config_kwargs)

    def _ensure_bucket(self):
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError as e:
            if e.response["Error"]["Code"] in ("404", "NoSuchBucket"):
                try:
                    self._client.create_bucket(Bucket=self._bucket)
                    logger.info(f"Created bucket: {self._bucket}")
                except Exception as ce:
                    logger.warning(f"Could not create bucket: {ce}")
            else:
                logger.warning(f"Bucket check failed: {e}")

    def upload_pdf(self, pdf_bytes: bytes, job_id: str) -> Tuple[str, str, int]:
        if not self._available or self._client is None:
            raise RuntimeError("Storage service is not available")
        object_key = f"pdfs/{datetime.utcnow().strftime('%Y/%m/%d')}/{job_id}.pdf"
        sha256_hash = hashlib.sha256(pdf_bytes).hexdigest()
        size_bytes = len(pdf_bytes)

        file_obj = io.BytesIO(pdf_bytes)
        self._client.upload_fileobj(
            file_obj,
            self._bucket,
            object_key,
            ExtraArgs={
                "ContentType": "application/pdf",
                "Metadata": {
                    "sha256": sha256_hash,
                    "job-id": job_id,
                },
            },
        )
        return object_key, sha256_hash, size_bytes

    def generate_presigned_url(self, object_key: str, expires_in_seconds: Optional[int] = None) -> str:
        if not self._available or self._client is None:
            raise RuntimeError("Storage service is not available")
        if expires_in_seconds is None:
            expires_in_seconds = settings.pdf_ttl_days * 24 * 3600
        try:
            url = self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": object_key},
                ExpiresIn=expires_in_seconds,
            )
            return url
        except ClientError as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            raise

    def delete_pdf(self, object_key: str) -> bool:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=object_key)
            return True
        except ClientError as e:
            logger.error(f"Failed to delete PDF {object_key}: {e}")
            return False

    def cleanup_expired(self):
        cutoff = datetime.utcnow() - timedelta(days=settings.pdf_ttl_days)
        prefix = "pdfs/"
        try:
            paginator = self._client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    last_mod = obj["LastModified"].replace(tzinfo=None)
                    if last_mod < cutoff:
                        self.delete_pdf(obj["Key"])
        except Exception as e:
            logger.error(f"Cleanup expired failed: {e}")
