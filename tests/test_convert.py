"""公共 API 测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from pydoctrans import ConversionError, convert


class TestConvertFunction:
    """测试 convert() 公共 API。"""

    def test_returns_bytes(self) -> None:
        result = convert(b"hello", to="pdf", file_name="test.txt")
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_raises_on_invalid_format(self) -> None:
        with pytest.raises(ConversionError):
            convert(b"data", to="zzz_invalid", file_name="test.txt", timeout=30)

    def test_raises_on_missing_extension(self) -> None:
        with pytest.raises(ValueError, match="须包含扩展名"):
            convert(b"data", to="pdf", file_name="noext")

    def test_default_file_name(self) -> None:
        """无 file_name 时使用默认值 input.bin。"""
        result = convert(b"content", to="pdf")
        assert len(result) > 0


class TestCliConvert:
    """测试 CLI convert 子命令。"""

    def test_convert_with_positional_output(self, tmp_path: Path) -> None:
        import subprocess
        import sys

        input_file = tmp_path / "input.txt"
        output_file = tmp_path / "output.pdf"
        input_file.write_text("CLI test")

        result = subprocess.run(
            [sys.executable, "-m", "pydoctrans", "convert",
             str(input_file), str(output_file)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert output_file.exists()
        assert output_file.stat().st_size > 0

    def test_convert_with_format_flag(self, tmp_path: Path) -> None:
        import subprocess
        import sys

        input_file = tmp_path / "input.txt"
        input_file.write_text("CLI test with flag")

        result = subprocess.run(
            [sys.executable, "-m", "pydoctrans", "convert",
             str(input_file), "-t", "pdf"],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )
        assert result.returncode == 0
        assert "完成:" in result.stdout

    def test_missing_input_file(self, tmp_path: Path) -> None:
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "-m", "pydoctrans", "convert",
             str(tmp_path / "nonexistent.txt"), "-t", "pdf"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "文件不存在" in result.stderr

    def test_missing_format(self, tmp_path: Path) -> None:
        import subprocess
        import sys

        input_file = tmp_path / "input.txt"
        input_file.write_text("no format")

        result = subprocess.run(
            [sys.executable, "-m", "pydoctrans", "convert",
             str(input_file)],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "目标格式" in result.stderr
