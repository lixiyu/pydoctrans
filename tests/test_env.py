"""Env 模块测试。"""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

from pydoctrans.env import (
    _find_executable,
    _find_program_dir_linux,
    _find_program_dir_macos,
    detect,
)


class TestFindProgramDirLinux:
    """测试 Linux 路径检测。"""

    def test_finds_libreoffice_in_opt(self, tmp_path: Path) -> None:
        program_dir = tmp_path / "opt" / "libreoffice26.2" / "program"
        program_dir.mkdir(parents=True)

        with mock.patch("pydoctrans.env._LINUX_SEARCH_ROOTS", [str(tmp_path / "opt")]):
            result = _find_program_dir_linux()
            assert result == program_dir

    def test_finds_libreoffice_in_usr_lib(self, tmp_path: Path) -> None:
        program_dir = tmp_path / "usr" / "lib" / "libreoffice" / "program"
        program_dir.mkdir(parents=True)

        with mock.patch("pydoctrans.env._LINUX_SEARCH_ROOTS", [str(tmp_path / "usr" / "lib")]):
            result = _find_program_dir_linux()
            assert result == program_dir

    def test_returns_none_when_not_found(self, tmp_path: Path) -> None:
        with mock.patch("pydoctrans.env._LINUX_SEARCH_ROOTS", [str(tmp_path / "empty")]):
            result = _find_program_dir_linux()
            assert result is None


class TestFindProgramDirMacos:
    """测试 macOS 路径检测。"""

    def test_finds_libreoffice_app(self, tmp_path: Path) -> None:
        app_dir = tmp_path / "Applications" / "LibreOffice.app" / "Contents" / "MacOS"
        app_dir.mkdir(parents=True)

        with mock.patch("pydoctrans.env._MACOS_SEARCH_ROOTS", [str(tmp_path / "Applications")]):
            result = _find_program_dir_macos()
            assert result == app_dir

    def test_returns_none_when_not_found(self, tmp_path: Path) -> None:
        with mock.patch("pydoctrans.env._MACOS_SEARCH_ROOTS", [str(tmp_path / "noapps")]):
            result = _find_program_dir_macos()
            assert result is None


class TestFindExecutable:
    """测试可执行文件查找。"""

    def test_finds_soffice_in_program_dir(self, tmp_path: Path) -> None:
        soffice = tmp_path / "soffice"
        soffice.touch(mode=0o755)

        result = _find_executable(tmp_path)
        assert result == str(soffice)

    def test_finds_libreoffice_when_soffice_absent(self, tmp_path: Path) -> None:
        libreoffice = tmp_path / "libreoffice"
        libreoffice.touch(mode=0o755)

        result = _find_executable(tmp_path)
        assert result == str(libreoffice)

    def test_prefers_soffice_over_libreoffice(self, tmp_path: Path) -> None:
        soffice = tmp_path / "soffice"
        soffice.touch(mode=0o755)
        (tmp_path / "libreoffice").touch(mode=0o755)

        result = _find_executable(tmp_path)
        assert result == str(soffice)

    def test_returns_none_when_neither_found(self, tmp_path: Path) -> None:
        with mock.patch("shutil.which", return_value=None):
            result = _find_executable(tmp_path)
            assert result is None


class TestDetect:
    """测试顶层 detect() 函数。"""

    def test_detect_returns_loenv_dataclass(self) -> None:
        result = detect()
        # 无论是否找到 LO，都应返回 LoEnv 实例
        assert hasattr(result, "found")
        assert hasattr(result, "executable")
        assert hasattr(result, "program_dir")
        assert hasattr(result, "version")
        assert hasattr(result, "search_paths")

    def test_detect_not_found_when_no_lo(self) -> None:
        with mock.patch("shutil.which", return_value=None):
            with mock.patch("os.name", "posix"):
                with mock.patch("os.uname") as mock_uname:
                    mock_uname.return_value = mock.Mock(sysname="Linux")
                    with mock.patch(
                        "pydoctrans.env._find_program_dir_linux", return_value=None
                    ):
                        result = detect()
                        assert result.found is False
                        assert result.executable == ""
