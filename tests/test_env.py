"""Env 模块测试。"""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

from pydoctrans.env import (
    _detect_version,
    _find_by_scanning,
    _find_from_env,
    _find_from_path,
    _pick_exe,
    _program_dir_from_exe,
    _scan_roots,
    detect,
)


class TestPickExe:
    """测试可执行文件选择逻辑。"""

    def test_prefers_soffice(self, tmp_path: Path) -> None:
        (tmp_path / "soffice").touch(mode=0o755)
        (tmp_path / "libreoffice").touch(mode=0o755)
        result = _pick_exe(str(tmp_path))
        assert result.endswith("soffice")

    def test_falls_back_to_libreoffice(self, tmp_path: Path) -> None:
        (tmp_path / "libreoffice").touch(mode=0o755)
        result = _pick_exe(str(tmp_path))
        assert result.endswith("libreoffice")

    def test_returns_none_when_neither_found(self, tmp_path: Path) -> None:
        assert _pick_exe(str(tmp_path)) is None


class TestProgramDirFromExe:
    """测试从可执行文件推导 program 目录。"""

    def test_soffice_in_program(self) -> None:
        assert _program_dir_from_exe("/opt/libreoffice26.2/program/soffice") == \
            "/opt/libreoffice26.2/program"

    def test_no_program_parent(self) -> None:
        assert _program_dir_from_exe("/usr/bin/soffice") is None


class TestFindFromEnv:
    """测试环境变量查找。"""

    def test_lo_executable(self, tmp_path: Path, monkeypatch) -> None:
        exe = tmp_path / "program" / "soffice"
        exe.parent.mkdir()
        exe.touch(mode=0o755)
        monkeypatch.setenv("LO_EXECUTABLE", str(exe))
        result = _find_from_env()
        assert result is not None
        assert result[0] == str(exe)

    def test_lo_program_dir(self, tmp_path: Path, monkeypatch) -> None:
        prog = tmp_path / "program"
        prog.mkdir()
        (prog / "soffice").touch(mode=0o755)
        monkeypatch.setenv("LO_PROGRAM_DIR", str(prog))
        result = _find_from_env()
        assert result is not None
        assert "program" in result[1]

    def test_returns_none_when_not_set(self, monkeypatch) -> None:
        monkeypatch.delenv("LO_EXECUTABLE", raising=False)
        monkeypatch.delenv("LO_PROGRAM_DIR", raising=False)
        assert _find_from_env() is None


class TestFindFromPath:
    """测试 PATH 查找。"""

    def test_returns_none_when_not_found(self) -> None:
        with mock.patch("shutil.which", return_value=None):
            assert _find_from_path() is None

    def test_finds_libreoffice26_2(self) -> None:
        def fake_which(name):
            return "/opt/libreoffice26.2/program/soffice" if name == "libreoffice26.2" else None

        with mock.patch("shutil.which", side_effect=fake_which):
            result = _find_from_path()
            assert result is not None


class TestScanRoots:
    """测试目录扫描。"""

    def test_finds_program_dir(self, tmp_path: Path) -> None:
        prog = tmp_path / "opt" / "libreoffice26.2" / "program"
        prog.mkdir(parents=True)
        (prog / "soffice").touch(mode=0o755)

        found = _scan_roots([str(tmp_path / "opt")], "libreoffice*/program")
        assert len(found) == 1


class TestDetect:
    """测试顶层 detect() 函数。"""

    def test_returns_loenv(self) -> None:
        result = detect()
        assert hasattr(result, "found")
        assert hasattr(result, "executable")
        assert hasattr(result, "program_dir")

    def test_not_found_when_no_lo(self) -> None:
        with mock.patch("pydoctrans.env._find_from_env", return_value=None), \
             mock.patch("pydoctrans.env._find_from_path", return_value=None), \
             mock.patch("pydoctrans.env._find_by_scanning", return_value=[]):
            result = detect()
            assert result.found is False
            assert result.executable == ""
