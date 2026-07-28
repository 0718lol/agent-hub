"""Tenant file storage with a local cache and optional S3/MinIO backing."""

import os
import tempfile
import uuid
from pathlib import Path

from app.core.config import settings
from app.core.upload_security import safe_upload_extension

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "uploads")


class FileStorageManager:
    """Keep the historical local API while optionally replicating files to S3."""

    _s3_client = None

    @staticmethod
    def _safe_name(stored_name: str) -> str:
        if not stored_name or Path(stored_name).name != stored_name or "\x00" in stored_name:
            raise ValueError("Invalid stored file name")
        return stored_name

    @classmethod
    def _uses_s3(cls) -> bool:
        return settings.storage_backend == "s3"

    @classmethod
    def _client(cls):
        if cls._s3_client is None:
            import boto3

            cls._s3_client = boto3.client(
                "s3",
                endpoint_url=settings.s3_endpoint_url or None,
                region_name=settings.s3_region or None,
                aws_access_key_id=settings.s3_access_key_id or None,
                aws_secret_access_key=settings.s3_secret_access_key or None,
            )
        return cls._s3_client

    @classmethod
    def _object_key(cls, stored_name: str) -> str:
        name = cls._safe_name(stored_name)
        prefix = settings.s3_prefix.strip("/")
        return f"{prefix}/{name}" if prefix else name

    @staticmethod
    def generate_stored_name(original_name: str) -> str:
        ext = safe_upload_extension(original_name)
        return f"{uuid.uuid4().hex}{ext}"

    @classmethod
    def get_absolute_path(cls, stored_name: str) -> str:
        name = cls._safe_name(stored_name)
        path = os.path.join(UPLOAD_DIR, name)
        if cls._uses_s3() and not os.path.exists(path) and cls.exists(name):
            os.makedirs(UPLOAD_DIR, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(prefix=".download-", dir=UPLOAD_DIR)
            os.close(descriptor)
            try:
                cls._client().download_file(
                    settings.s3_bucket,
                    cls._object_key(name),
                    temporary,
                )
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        return path

    @classmethod
    def save(cls, content: bytes, stored_name: str) -> str:
        name = cls._safe_name(stored_name)
        path = os.path.join(UPLOAD_DIR, name)
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".upload-", dir=UPLOAD_DIR)
        try:
            with os.fdopen(descriptor, "wb") as file_obj:
                file_obj.write(content)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        if cls._uses_s3():
            cls._client().upload_file(path, settings.s3_bucket, cls._object_key(name))
        return path

    @staticmethod
    def get_url(stored_name: str) -> str:
        return f"/uploads/{stored_name}"

    @classmethod
    def exists(cls, stored_name: str) -> bool:
        name = cls._safe_name(stored_name)
        if os.path.isfile(os.path.join(UPLOAD_DIR, name)):
            return True
        if not cls._uses_s3():
            return False
        try:
            cls._client().head_object(
                Bucket=settings.s3_bucket,
                Key=cls._object_key(name),
            )
            return True
        except Exception as exc:
            status = getattr(exc, "response", {}).get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status in {403, 404}:
                return False
            raise

    @classmethod
    def size(cls, stored_name: str) -> int:
        name = cls._safe_name(stored_name)
        path = os.path.join(UPLOAD_DIR, name)
        if os.path.isfile(path):
            return os.path.getsize(path)
        if cls._uses_s3():
            result = cls._client().head_object(
                Bucket=settings.s3_bucket,
                Key=cls._object_key(name),
            )
            return int(result.get("ContentLength", 0))
        return 0

    @classmethod
    def list_names(cls, prefix: str = "") -> list[str]:
        names = set()
        if os.path.isdir(UPLOAD_DIR):
            names = {
                name for name in os.listdir(UPLOAD_DIR)
                if not name.startswith(".") and os.path.isfile(os.path.join(UPLOAD_DIR, name))
            }
        if cls._uses_s3():
            object_prefix = cls._object_key(prefix) if prefix else settings.s3_prefix.strip("/")
            if object_prefix and not object_prefix.endswith("/") and not prefix:
                object_prefix += "/"
            paginator = cls._client().get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=settings.s3_bucket, Prefix=object_prefix):
                for item in page.get("Contents", []):
                    name = item["Key"].rsplit("/", 1)[-1]
                    if name:
                        names.add(name)
        return sorted(name for name in names if name.startswith(prefix))

    @classmethod
    def delete(cls, stored_name: str) -> bool:
        name = cls._safe_name(stored_name)
        deleted = False
        path = os.path.join(UPLOAD_DIR, name)
        if os.path.isfile(path):
            os.remove(path)
            deleted = True
        if cls._uses_s3():
            cls._client().delete_object(
                Bucket=settings.s3_bucket,
                Key=cls._object_key(name),
            )
            deleted = True
        return deleted

    @classmethod
    def healthcheck(cls) -> tuple[bool, str]:
        if not cls._uses_s3():
            return True, f"local:{UPLOAD_DIR}"
        if not settings.s3_bucket:
            return False, "AGENTHUB_S3_BUCKET is required for S3 storage"
        try:
            cls._client().head_bucket(Bucket=settings.s3_bucket)
            return True, f"s3:{settings.s3_bucket}/{settings.s3_prefix.strip('/')}"
        except Exception as exc:
            return False, str(exc)[:240]
