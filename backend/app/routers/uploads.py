"""
独立上传路由 — GET 文件服务 + 增强上传（POST 见 main.py）
"""
import os

from fastapi import APIRouter, HTTPException
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
