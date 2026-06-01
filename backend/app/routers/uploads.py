"""File upload and retrieval endpoints."""
import os

from fastapi import UploadFile, File, APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.file_storage import FileStorageManager, UPLOAD_DIR

router = APIRouter(prefix="/api", tags=["uploads"])


@router.get("/uploads/{file_id}")
async def get_uploaded_file(file_id: str):
    """返回已上传文件（通过 file_id = stored_name 定位）"""
    if not FileStorageManager.exists(file_id):
        raise HTTPException(status_code=404, detail="文件不存在")
    path = FileStorageManager.get_absolute_path(file_id)
    return FileResponse(path)


@router.get("/uploads/list")
async def list_uploads():
    """列出所有已上传文件（调试用）"""
    try:
        files = []
        for name in os.listdir(UPLOAD_DIR):
            if name.startswith("."):
                continue
            full = os.path.join(UPLOAD_DIR, name)
            if os.path.isfile(full):
                files.append({
                    "id": name,
                    "name": name,
                    "url": f"/uploads/{name}",
                    "size": os.path.getsize(full),
                })
        return {"files": files}
    except Exception:
        return {"files": []}


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload a file to the server."""
    import uuid as _uuid
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    ext = os.path.splitext(file.filename or "")[1]
    stored_name = f"{_uuid.uuid4().hex}{ext}"
    file_path = os.path.join(UPLOAD_DIR, stored_name)
    content = await file.read()
    MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB limit
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail=f"File too large: {len(content)} bytes (max {MAX_UPLOAD_SIZE})")
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
