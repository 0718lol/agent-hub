"""
文档解析器 — 支持 txt / md / docx / pdf 纯文本提取
"""
import os
from typing import Optional


class DocumentParser:
    """从文档文件中提取纯文本，供 LLM 上下文注入使用"""

    # 支持的文件扩展名
    SUPPORTED_EXTENSIONS = {".txt", ".md", ".docx", ".pdf", ".json", ".csv"}

    @classmethod
    def extract_text(cls, file_path: str, content_type: str = "") -> Optional[str]:
        """
        根据文件扩展名选择合适的解析器提取文本。
        返回提取到的纯文本字符串，失败返回 None。
        """
        ext = os.path.splitext(file_path)[1].lower()

        if ext in (".txt", ".md", ".json", ".csv"):
            return cls._extract_text_file(file_path)

        if ext == ".docx":
            return cls._extract_docx(file_path)

        if ext == ".pdf":
            return cls._extract_pdf(file_path)

        return None

    @classmethod
    def _extract_text_file(cls, file_path: str) -> Optional[str]:
        """从纯文本文件中读取内容"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except UnicodeDecodeError:
            try:
                with open(file_path, "r", encoding="gbk") as f:
                    return f.read()
            except Exception:
                return None
        except Exception:
            return None

    @classmethod
    def _extract_docx(cls, file_path: str) -> Optional[str]:
        """从 .docx 文件中提取纯文本"""
        try:
            import docx
            doc = docx.Document(file_path)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n".join(paragraphs)
        except Exception:
            return None

    @classmethod
    def _extract_pdf(cls, file_path: str) -> Optional[str]:
        """从 .pdf 文件中提取纯文本"""
        try:
            from pypdf import PdfReader
            reader = PdfReader(file_path)
            pages = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    pages.append(text.strip())
            return "\n\n".join(pages) if pages else None
        except Exception:
            return None

    @classmethod
    def is_supported(cls, filename: str) -> bool:
        """判断文件类型是否支持文本提取"""
        ext = os.path.splitext(filename)[1].lower()
        return ext in cls.SUPPORTED_EXTENSIONS
