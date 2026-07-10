"""Sandbox 模块测试。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pydoctrans.sandbox import Sandbox


class TestSandbox:
    """测试 HOME 隔离沙箱。"""

    def test_creates_temp_home(self) -> None:
        with Sandbox() as sandbox:
            home = sandbox.home
            assert os.path.isdir(home)
            assert "lo_sandbox_" in home

    def test_home_is_writable(self) -> None:
        with Sandbox() as sandbox:
            test_file = Path(sandbox.home) / "test.txt"
            test_file.write_text("hello")
            assert test_file.read_text() == "hello"

    def test_isolation_unique_per_instance(self) -> None:
        homes: list[str] = []
        with Sandbox() as s1, Sandbox() as s2:
            homes = [s1.home, s2.home]
        assert homes[0] != homes[1]

    def test_cleanup_on_exit(self) -> None:
        home: str = ""
        with Sandbox() as sandbox:
            home = sandbox.home
        assert not os.path.exists(home)

    def test_cleanup_on_exception(self) -> None:
        home: str = ""
        try:
            with Sandbox() as sandbox:
                home = sandbox.home
                raise ValueError("simulated error")
        except ValueError:
            pass
        assert not os.path.exists(home)

    def test_home_unavailable_outside_context(self) -> None:
        sandbox = Sandbox()
        with pytest.raises(RuntimeError, match="未进入上下文"):
            _ = sandbox.home

    def test_respects_tmp_dir_env(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("TMP_DIR", str(tmp_path))
        with Sandbox() as sandbox:
            assert str(tmp_path) in sandbox.home
