"""
UF Stock Assistant — 文件/图片解析工具
支持 PDF、DOCX、XLSX、TXT、图片等格式
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.core.exceptions import FileParseError
from app.core.logging import get_logger

logger = get_logger("app.tools.file_parser")


# =============================================================================
# 文件类型检测
# =============================================================================

def detect_file_type(file_path: str) -> str:
    """
    检测文件类型
    
    Args:
        file_path: 文件路径
        
    Returns:
        MIME 类型或文件类型标识
    """
    suffix = Path(file_path).suffix.lower()
    
    type_map = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".doc": "application/msword",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls": "application/vnd.ms-excel",
        ".txt": "text/plain",
        ".csv": "text/csv",
        ".md": "text/markdown",
        ".json": "application/json",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    
    return type_map.get(suffix, "application/octet-stream")


# =============================================================================
# 文本文件解析
# =============================================================================

def parse_text_file(file_path: str) -> str:
    """解析文本文件"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return content
    except UnicodeDecodeError:
        # 尝试其他编码
        with open(file_path, "r", encoding="gbk") as f:
            content = f.read()
        return content
    except Exception as exc:
        raise FileParseError(f"读取文本文件失败: {exc}") from exc


# =============================================================================
# PDF 解析
# =============================================================================

def parse_pdf(file_path: str) -> str:
    """解析 PDF 文件"""
    try:
        from unstructured.partition.pdf import partition_pdf
        
        elements = partition_pdf(filename=file_path)
        text = "\n\n".join([str(el) for el in elements])
        
        logger.info("pdf_parsed", file=file_path, length=len(text))
        return text
        
    except ImportError:
        logger.warning("unstructured_not_installed", file=file_path)
        # fallback：尝试 PyPDF2
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(file_path)
            text = "\n\n".join([page.extract_text() or "" for page in reader.pages])
            return text
        except ImportError:
            raise FileParseError("未安装 PDF 解析库，请安装 unstructured 或 PyPDF2")
    except Exception as exc:
        raise FileParseError(f"解析 PDF 失败: {exc}") from exc


# =============================================================================
# Word 文档解析
# =============================================================================

def parse_docx(file_path: str) -> str:
    """解析 Word 文档"""
    try:
        from unstructured.partition.docx import partition_docx
        
        elements = partition_docx(filename=file_path)
        text = "\n\n".join([str(el) for el in elements])
        
        logger.info("docx_parsed", file=file_path, length=len(text))
        return text
        
    except ImportError:
        logger.warning("unstructured_not_installed", file=file_path)
        try:
            import docx
            doc = docx.Document(file_path)
            text = "\n\n".join([para.text for para in doc.paragraphs if para.text.strip()])
            return text
        except ImportError:
            raise FileParseError("未安装 DOCX 解析库，请安装 unstructured 或 python-docx")
    except Exception as exc:
        raise FileParseError(f"解析 DOCX 失败: {exc}") from exc


# =============================================================================
# Excel 解析
# =============================================================================

def parse_excel(file_path: str) -> str:
    """解析 Excel 文件"""
    try:
        import pandas as pd
        
        # 读取所有 sheet
        xls = pd.ExcelFile(file_path)
        parts = []
        
        for sheet_name in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet_name)
            parts.append(f"=== Sheet: {sheet_name} ===\n")
            parts.append(df.to_string(index=False))
            parts.append("\n")
        
        text = "\n".join(parts)
        logger.info("excel_parsed", file=file_path, sheets=len(xls.sheet_names))
        return text
        
    except ImportError:
        raise FileParseError("未安装 Excel 解析库，请安装 pandas 和 openpyxl")
    except Exception as exc:
        raise FileParseError(f"解析 Excel 失败: {exc}") from exc


# =============================================================================
# 图片解析（OCR 或多模态）
# =============================================================================

def parse_image(file_path: str, use_ocr: bool = True) -> str:
    """
    解析图片内容
    
    Args:
        file_path: 图片路径
        use_ocr: 是否使用 OCR，否则返回图片描述
        
    Returns:
        图片中的文本内容或描述
    """
    try:
        if use_ocr:
            try:
                from PIL import Image
                import pytesseract
                
                image = Image.open(file_path)
                text = pytesseract.image_to_string(image, lang="chi_sim+eng")
                
                logger.info("image_ocr_parsed", file=file_path, length=len(text))
                return text.strip() or "图片中未识别到文本内容"
                
            except ImportError:
                logger.warning("ocr_not_available", file=file_path)
                return f"[图片文件: {file_path}]\n注意：OCR 功能未安装，无法提取图片中的文字。"
        else:
            return f"[图片文件: {file_path}]"
            
    except Exception as exc:
        raise FileParseError(f"解析图片失败: {exc}") from exc


# =============================================================================
# 统一解析入口
# =============================================================================

def parse_file(file_path: str, mime_type: str | None = None) -> str:
    """
    统一文件解析入口
    
    Args:
        file_path: 文件路径
        mime_type: MIME 类型（可选，自动检测）
        
    Returns:
        文件文本内容
    """
    if not os.path.exists(file_path):
        raise FileParseError(f"文件不存在: {file_path}")
    
    file_type = mime_type or detect_file_type(file_path)
    
    logger.info("parsing_file", file=file_path, type=file_type)
    
    # 根据类型分发
    if file_type == "text/plain" or file_type == "text/csv" or file_type == "text/markdown" or file_type == "application/json":
        return parse_text_file(file_path)
    
    elif file_type == "application/pdf":
        return parse_pdf(file_path)
    
    elif file_type in ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/msword"):
        return parse_docx(file_path)
    
    elif file_type in ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/vnd.ms-excel"):
        return parse_excel(file_path)
    
    elif file_type.startswith("image/"):
        return parse_image(file_path)
    
    else:
        # 未知类型，尝试作为文本读取
        try:
            return parse_text_file(file_path)
        except Exception:
            raise FileParseError(f"不支持的文件类型: {file_type}")


# =============================================================================
# 批量解析
# =============================================================================

def parse_files(file_paths: list[str]) -> str:
    """
    批量解析文件
    
    Args:
        file_paths: 文件路径列表
        
    Returns:
        合并后的文本内容
    """
    results = []
    
    for path in file_paths:
        try:
            content = parse_file(path)
            results.append(f"=== 文件: {path} ===\n{content}\n")
        except Exception as exc:
            results.append(f"=== 文件: {path} ===\n解析失败: {exc}\n")
    
    return "\n".join(results)
