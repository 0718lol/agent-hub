"""File upload and retrieval endpoints."""
import mimetypes
import os

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.file_storage import UPLOAD_DIR, FileStorageManager
from app.core.tenancy import request_user_id
from app.core.upload_security import UploadLimitExceeded, read_upload_limited, safe_upload_extension

router = APIRouter(tags=["uploads"])


SAFE_INLINE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "application/pdf",
}
_FILE_PREFIX = "tenantfile__"


def _tenant_file_prefix(user_id: str) -> str:
    return f"{_FILE_PREFIX}{user_id}__"


def _can_access_file(file_id: str, user_id: str) -> bool:
    if file_id.startswith(_tenant_file_prefix(user_id)):
        return True
    return user_id == "api-client" and not file_id.startswith(_FILE_PREFIX)


def _file_response(path: str, file_id: str) -> FileResponse:
    """Serve only known-safe media inline; force potentially active files to download."""
    content_type, _ = mimetypes.guess_type(file_id)
    content_type = content_type or "application/octet-stream"
    disposition = "inline" if content_type in SAFE_INLINE_TYPES else "attachment"
    return FileResponse(
        path,
        media_type=content_type,
        filename=file_id,
        content_disposition_type=disposition,
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=3600"},
    )


@router.get("/uploads/list")
async def list_uploads(request: Request):
    """列出当前已上传文件。"""
    try:
        files = []
        user_id = request_user_id(request)
        for name in os.listdir(UPLOAD_DIR):
            if name.startswith("."):
                continue
            full = os.path.join(UPLOAD_DIR, name)
            if os.path.isfile(full) and _can_access_file(name, user_id):
                files.append({
                    "id": name,
                    "name": name,
                    "url": f"/uploads/{name}",
                    "size": os.path.getsize(full),
                })
        return {"files": files}
    except Exception:
        return {"files": []}


@router.get("/uploads/{file_id}")
async def get_uploaded_file(file_id: str, request: Request):
    """返回已上传文件（通过 file_id = stored_name 定位）"""
    if ".." in file_id or "/" in file_id or "\\" in file_id:
        raise HTTPException(status_code=400, detail="Invalid file_id")
    if not _can_access_file(file_id, request_user_id(request)):
        raise HTTPException(status_code=404, detail="文件不存在")
    if not FileStorageManager.exists(file_id):
        raise HTTPException(status_code=404, detail="文件不存在")
    path = FileStorageManager.get_absolute_path(file_id)
    real_path = os.path.realpath(path)
    real_upload = os.path.realpath(UPLOAD_DIR)
    if not real_path.startswith(real_upload + os.sep) and real_path != real_upload:
        raise HTTPException(status_code=403, detail="Access denied")
    return _file_response(path, file_id)


@router.post("/upload")
async def upload_file(request: Request, file: UploadFile = File(...)):
    """Upload a file to the server."""
    import uuid as _uuid
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    ext = safe_upload_extension(file.filename)
    stored_name = f"{_tenant_file_prefix(request_user_id(request))}{_uuid.uuid4().hex}{ext}"
    file_path = os.path.join(UPLOAD_DIR, stored_name)
    try:
        content = await read_upload_limited(file, settings.upload_max_bytes)
    except UploadLimitExceeded as exc:
        raise HTTPException(status_code=413, detail=f"File too large (max {exc.max_bytes} bytes)") from exc
    with open(file_path, "wb") as f:
        f.write(content)
    is_image = (file.content_type or "").startswith("image/")
    return {
        "status": "uploaded",
        "original_name": file.filename,
        "stored_name": stored_name,
        "url": f"/uploads/{stored_name}",
        "content_type": file.content_type,
        "size": len(content),
        "is_image": is_image,
    }
