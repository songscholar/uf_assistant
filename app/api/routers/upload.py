"""
UF Stock Assistant — 文件上传接口
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.auth.dependencies import get_current_user
from app.core.logging import get_logger
from app.tools.file_parser import parse_file

logger = get_logger("app.api.upload")

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.post("/upload")
async def upload_file(file: UploadFile = File(..., description="上传的文件")):
    """
    上传文件并解析
    
    支持的格式：PDF、DOCX、XLSX、TXT、PNG、JPG 等
    """
    try:
        # 保存上传的文件到临时目录
        suffix = Path(file.filename or "tmp").suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
        
        try:
            # 解析文件
            parsed_content = parse_file(tmp_path)
            
            logger.info(
                "file_uploaded",
                filename=file.filename,
                size=len(content),
                parsed_length=len(parsed_content),
            )
            
            return {
                "success": True,
                "filename": file.filename,
                "content_type": file.content_type,
                "size": len(content),
                "parsed_content": parsed_content[:5000] if len(parsed_content) > 5000 else parsed_content,
                "truncated": len(parsed_content) > 5000,
            }
        finally:
            # 清理临时文件
            os.unlink(tmp_path)
            
    except Exception as exc:
        logger.error("upload_error", filename=file.filename, error=str(exc))
        raise HTTPException(status_code=500, detail=f"文件处理失败: {exc}")


@router.post("/upload/batch")
async def upload_batch(files: list[UploadFile] = File(..., description="批量上传文件")):
    """批量上传文件"""
    results = []
    
    for file in files:
        try:
            suffix = Path(file.filename or "tmp").suffix
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                content = await file.read()
                tmp.write(content)
                tmp_path = tmp.name
            
            try:
                parsed_content = parse_file(tmp_path)
                results.append({
                    "filename": file.filename,
                    "success": True,
                    "parsed_content": parsed_content[:2000] if len(parsed_content) > 2000 else parsed_content,
                    "truncated": len(parsed_content) > 2000,
                })
            except Exception as exc:
                results.append({
                    "filename": file.filename,
                    "success": False,
                    "error": str(exc),
                })
            finally:
                os.unlink(tmp_path)
                
        except Exception as exc:
            results.append({
                "filename": file.filename,
                "success": False,
                "error": str(exc),
            })
    
    return {
        "success_count": sum(1 for r in results if r["success"]),
        "failed_count": sum(1 for r in results if not r["success"]),
        "results": results,
    }
