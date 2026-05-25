"""
图片处理工具 — 预留 OCR 接口，当前为占位实现
"""
import os
from typing import Optional


class ImageProcessor:
    """图片处理器：缩略图生成、OCR 文本提取（未来扩展）"""

    @staticmethod
    def get_thumbnail_path(stored_name: str) -> str:
        """返回缩略图存放路径（预留）"""
        name, ext = os.path.splitext(stored_name)
        return f"{name}_thumb{ext}"

    @staticmethod
    def extract_text(stored_name: str) -> Optional[str]:
        """
        OCR 文本提取（占位实现）
        未来可接入 Tesseract / EasyOCR / Cloud Vision API
        """
        return None  # 当前不尝试 OCR

    @staticmethod
    def can_process(content_type: str) -> bool:
        """判断是否为可处理的图片类型"""
        supported = ("image/png", "image/jpeg", "image/webp", "image/gif", "image/bmp")
        return content_type.startswith("image/") or content_type in supported
