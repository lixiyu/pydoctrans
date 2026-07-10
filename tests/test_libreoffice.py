"""LibreOffice 引擎测试。

需要有 LO 环境才能运行，否则 skip。
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

import pytest

from pydoctrans.engine.libreoffice import (
    ConversionError,
    LibreOfficeEngine,
    _get_pool,
)
from pydoctrans.env import detect


def _lo_available() -> bool:
    """检查当前环境是否有 LO。"""
    return detect().found


pytestmark = pytest.mark.skipif(
    not _lo_available(),
    reason="未检测到 LibreOffice 安装",
)


class TestLibreOfficeEngine:
    """集成测试：需要真实 LO 环境。"""

    @pytest.fixture(autouse=True)
    def _reset_pool(self) -> None:
        """每个测试前重置共享池。"""
        import pydoctrans.engine.libreoffice as mod

        mod._pool = None

    def test_health_returns_status(self) -> None:
        engine = LibreOfficeEngine()
        health = engine.health()
        assert health["status"] == "up"
        assert health["engine"] == "libreoffice"
        assert health["version"] is not None
        assert "pool" in health

    def test_convert_txt_to_pdf(self) -> None:
        engine = LibreOfficeEngine()
        result = engine.convert(
            b"Hello pydoctrans!",
            "test.txt",
            "pdf",
            timeout=30,
        )
        assert len(result.data) > 0
        assert result.to == "pdf"
        assert result.engine == "libreoffice"
        assert result.meta["elapsed_s"] > 0

    def test_convert_missing_extension_raises(self) -> None:
        engine = LibreOfficeEngine()
        with pytest.raises(ValueError, match="须包含扩展名"):
            engine.convert(b"data", "noext", "pdf")

    def test_convert_invalid_format_raises(self) -> None:
        engine = LibreOfficeEngine()
        with pytest.raises(ConversionError):
            engine.convert(b"data", "test.txt", "zzz_invalid_format", timeout=30)

    def test_find_output_strategy(self, tmp_path: Path) -> None:
        """验证输出文件查找逻辑。"""
        from pydoctrans.engine.libreoffice import LibreOfficeEngine as LOE

        # 策略 1：直接匹配
        (tmp_path / "report.pdf").write_text("matched")
        result = LOE._find_output(tmp_path, "report.docx", "pdf")
        assert result is not None
        assert result.name == "report.pdf"

        # 策略 2：通配匹配（清理策略1的文件后测试）
        for p in tmp_path.glob("*.pdf"):
            p.unlink()
        (tmp_path / "report_docx.pdf").write_text("variant")
        result = LOE._find_output(tmp_path, "report.docx", "pdf")
        assert result is not None
        assert result.name == "report_docx.pdf"


class TestEngineNotAvailable:
    """无 LO 时的行为测试。"""

    def test_constructor_raises_when_no_lo(self) -> None:
        with mock.patch("pydoctrans.engine.libreoffice.detect") as mock_detect:
            mock_detect.return_value.found = False
            with pytest.raises(RuntimeError, match="未检测到 LibreOffice"):
                LibreOfficeEngine()


class TestPoolShared:
    """共享池的行为测试。"""

    def test_get_pool_singleton(self) -> None:
        import pydoctrans.engine.libreoffice as mod

        mod._pool = None
        p1 = _get_pool()
        p2 = _get_pool()
        assert p1 is p2
