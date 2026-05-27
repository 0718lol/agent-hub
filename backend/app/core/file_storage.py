"""
文件存储管理器 — 负责生成唯一文件名、保存到本地磁盘
"""
import os
import uuid

# 上传文件存储根目录
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


class FileStorageManager:
    """管理文件存储：唯一命名、目录组织、路径解析"""

    @staticmethod
    def generate_stored_name(original_name: str) -> str:
        """生成唯一文件名，保留原始扩展名"""
        _, ext = os.path.splitext(original_name)
        return f"{uuid.uuid4().hex}{ext}"

    @staticmethod
    def get_absolute_path(stored_name: str) -> str:
        """返回文件的绝对磁盘路径"""
        return os.path.join(UPLOAD_DIR, stored_name)

    @staticmethod
    def save(content: bytes, stored_name: str) -> str:
        """将字节内容保存到磁盘，返回绝对路径"""
        path = FileStorageManager.get_absolute_path(stored_name)
        with open(path, "wb") as f:
            f.write(content)
        return path

    @staticmethod
    def get_url(stored_name: str) -> str:
        """返回文件对外访问 URL"""
        return f"/uploads/{stored_name}"

    @staticmethod
    def exists(stored_name: str) -> bool:
        """检查文件是否存在"""
        return os.path.isfile(FileStorageManager.get_absolute_path(stored_name))

    @staticmethod
    def delete(stored_name: str) -> bool:
        """删除文件，返回是否成功"""
        path = FileStorageManager.get_absolute_path(stored_name)
        if os.path.isfile(path):
            os.remove(path)
            return True
        return False
