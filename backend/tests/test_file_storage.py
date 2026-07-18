"""Shared file storage regression tests."""

from pathlib import Path

from app.core.file_storage import FileStorageManager


class _Paginator:
    def __init__(self, client):
        self.client = client

    def paginate(self, Bucket, Prefix):
        del Bucket
        yield {
            "Contents": [
                {"Key": key}
                for key in sorted(self.client.objects)
                if key.startswith(Prefix)
            ]
        }


class _FakeS3:
    def __init__(self):
        self.objects = {}

    def upload_file(self, path, bucket, key):
        del bucket
        self.objects[key] = Path(path).read_bytes()

    def download_file(self, bucket, key, path):
        del bucket
        Path(path).write_bytes(self.objects[key])

    def head_object(self, Bucket, Key):
        del Bucket
        return {"ContentLength": len(self.objects[Key])}

    def delete_object(self, Bucket, Key):
        del Bucket
        self.objects.pop(Key, None)

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return _Paginator(self)


def test_local_storage_roundtrip(tmp_path, monkeypatch):
    from app.core import file_storage

    monkeypatch.setattr(file_storage, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(file_storage.settings, "storage_backend", "local")
    stored_name = "tenantfile__user__sample.txt"

    path = FileStorageManager.save(b"hello", stored_name)

    assert Path(path).read_bytes() == b"hello"
    assert FileStorageManager.list_names("tenantfile__user__") == [stored_name]
    assert FileStorageManager.size(stored_name) == 5
    assert FileStorageManager.delete(stored_name)
    assert not FileStorageManager.exists(stored_name)


def test_s3_storage_rebuilds_missing_local_cache(tmp_path, monkeypatch):
    from app.core import file_storage

    fake_s3 = _FakeS3()
    monkeypatch.setattr(file_storage, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(file_storage.settings, "storage_backend", "s3")
    monkeypatch.setattr(file_storage.settings, "s3_bucket", "agenthub-test")
    monkeypatch.setattr(file_storage.settings, "s3_prefix", "agenthub")
    monkeypatch.setattr(FileStorageManager, "_s3_client", fake_s3)
    stored_name = "tenantfile__user__artifact.zip"

    local_path = Path(FileStorageManager.save(b"archive", stored_name))
    local_path.unlink()

    rebuilt = Path(FileStorageManager.get_absolute_path(stored_name))
    assert rebuilt.read_bytes() == b"archive"
    assert FileStorageManager.list_names("tenantfile__user__") == [stored_name]
