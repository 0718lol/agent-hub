"""Bounded multipart upload helpers shared by upload endpoints."""

import re
from pathlib import Path

from fastapi import UploadFile

_CHUNK_SIZE = 1024 * 1024
_SAFE_EXTENSION = re.compile(r"^\.[A-Za-z0-9]{1,12}$")


class UploadLimitExceeded(ValueError):
    def __init__(self, max_bytes: int):
        self.max_bytes = max_bytes
        super().__init__(f"Upload exceeds the {max_bytes}-byte limit")


async def read_upload_limited(file: UploadFile, max_bytes: int) -> bytes:
    """Read an upload incrementally and stop as soon as its limit is exceeded."""
    content = bytearray()
    while chunk := await file.read(_CHUNK_SIZE):
        if len(content) + len(chunk) > max_bytes:
            raise UploadLimitExceeded(max_bytes)
        content.extend(chunk)
    return bytes(content)


def safe_upload_extension(filename: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    return suffix if _SAFE_EXTENSION.fullmatch(suffix) else ""
