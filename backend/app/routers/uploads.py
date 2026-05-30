"""
独立上传路由 — GET 文件服务 + 增强上传（POST 见 main.py）
"""
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


@router.get("/api/uploads")
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


@router.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload a file to the server."""
    import uuid as _uuid
    import os as _os
    UPLOAD_DIR = _os.path.join(_os.path.dirname(__file__), "..", "..", "data", "uploads")
    _os.makedirs(UPLOAD_DIR, exist_ok=True)
    ext = _os.path.splitext(file.filename or "")[1]
    stored_name = f"{_uuid.uuid4().hex}{ext}"
    file_path = _os.path.join(UPLOAD_DIR, stored_name)
    content = await file.read()
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
