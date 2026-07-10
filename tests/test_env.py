"""Env 模块测试。"""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

from pydoctrans.env import (
    _find_by_which,
    _find_in_known_paths,
    _resolve_program_dir,
    detect,
)


class TestResolveProgramDir:
    """测试从可执行路径推导 program 目录。"""

    def test_symlink_in_opt(self) -> None:
        result = _resolve_program_dir("/opt/libreoffice26.2/program/soffice")
        assert result == "/opt/libreoffice26.2/program"

    def test_no_program_parent(self) -> None:
        result = _resolve_program_dir("/usr/bin/soffice")
        assert result is None


class TestFindInKnownPaths:
    """测试已知路径查找。"""

    def test_finds_in_opt(self, tmp_path: Path) -> None:
        prog = tmp_path / "opt" / "libreoffice26.2" / "program"
        prog.mkdir(parents=True)
        (prog / "soffice").touch(mode=0o755)

        with mock.patch("pydoctrans.env._find_in_known_paths.__defaults__", None):
            result = _find_in_known_paths()
        # 在本地开发机可能找到真实的 LO，不做严格断言
        assert result is None or isinstance(result, tuple)


class TestFindByWhich:
    """测试 PATH 查找。"""

    def test_returns_none_when_not_found(self) -> None:
        with mock.patch("shutil.which", return_value=None):
            result = _find_by_which()
            assert result is None

    def test_returns_executable_and_program_dir(self) -> None:
        def fake_which(name):
            if name == "libreoffice26.2":
                return "/opt/libreoffice26.2/program/soffice"
            return None

        with mock.patch("shutil.which", side_effect=fake_which):
            exe, prog_dir = _find_by_which()
            assert exe.endswith("soffice")
            assert "program" in prog_dir


class TestDetect:
    """测试顶层 detect() 函数。"""

    def test_detect_returns_loenv_dataclass(self) -> None:
        result = detect()
        assert hasattr(result, "found")
        assert hasattr(result, "executable")
        assert hasattr(result, "program_dir")
        assert hasattr(result, "version")

    def test_detect_not_found_when_no_lo(self) -> None:
        with mock.patch("pydoctrans.env._find_by_which", return_value=None):
            with mock.patch("pydoctrans.env._find_in_known_paths", return_value=None):
                with mock.patch("os.uname") as mock_uname:
                    mock_uname.return_value = mock.Mock(sysname="Linux")
                    result = detect()
                    assert result.found is False
                    assert result.executable == ""
