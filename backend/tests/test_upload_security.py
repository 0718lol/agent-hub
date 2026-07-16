"""Bounded upload reading and filename normalization tests."""

from io import BytesIO

import pytest
from starlette.datastructures import UploadFile

from app.core.upload_security import UploadLimitExceeded, read_upload_limited, safe_upload_extension


@pytest.mark.asyncio
async def test_upload_at_limit_is_accepted():
    upload = UploadFile(BytesIO(b"12345"), filename="demo.txt")
    assert await read_upload_limited(upload, 5) == b"12345"


@pytest.mark.asyncio
async def test_upload_over_limit_is_rejected_while_reading():
    upload = UploadFile(BytesIO(b"123456"), filename="demo.txt")
    with pytest.raises(UploadLimitExceeded):
        await read_upload_limited(upload, 5)


def test_upload_extension_is_strictly_normalized():
    assert safe_upload_extension("Demo.TXT") == ".txt"
    assert safe_upload_extension("payload.very-long-extension") == ""
    assert safe_upload_extension("no-extension") == ""
