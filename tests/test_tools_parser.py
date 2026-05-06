"""
测试文件解析工具模块
"""

import tempfile

import pytest

from app.core.exceptions import FileParseError
from app.tools.file_parser import detect_file_type, parse_file, parse_text_file


class TestDetectFileType:
    """测试文件类型检测"""

    def test_pdf(self):
        assert detect_file_type("test.pdf") == "application/pdf"

    def test_docx(self):
        assert detect_file_type("test.docx") == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    def test_xlsx(self):
        assert detect_file_type("test.xlsx") == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    def test_txt(self):
        assert detect_file_type("test.txt") == "text/plain"

    def test_png(self):
        assert detect_file_type("test.png") == "image/png"

    def test_jpg(self):
        assert detect_file_type("test.jpg") == "image/jpeg"

    def test_unknown(self):
        assert detect_file_type("test.xyz") == "application/octet-stream"


class TestParseTextFile:
    """测试文本文件解析"""

    def test_parse_utf8(self, tmp_path):
        """测试 UTF-8 编码"""
        file = tmp_path / "test.txt"
        file.write_text("你好，世界", encoding="utf-8")
        
        result = parse_text_file(str(file))
        assert result == "你好，世界"

    def test_parse_gbk(self, tmp_path):
        """测试 GBK 编码"""
        file = tmp_path / "test_gbk.txt"
        file.write_text("你好，世界", encoding="gbk")
        
        result = parse_text_file(str(file))
        assert result == "你好，世界"


class TestParseFile:
    """测试统一解析入口"""

    def test_parse_txt(self, tmp_path):
        """测试解析 txt"""
        file = tmp_path / "test.txt"
        file.write_text("测试内容", encoding="utf-8")
        
        result = parse_file(str(file))
        assert "测试内容" in result

    def test_parse_json(self, tmp_path):
        """测试解析 json"""
        file = tmp_path / "test.json"
        file.write_text('{"key": "value"}', encoding="utf-8")
        
        result = parse_file(str(file))
        assert '"key": "value"' in result

    def test_file_not_found(self):
        """测试文件不存在"""
        with pytest.raises(FileParseError):
            parse_file("/nonexistent/file.txt")
