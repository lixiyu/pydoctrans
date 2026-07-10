"""LO 环境检测模块。

自动检测 LibreOffice 安装路径、可执行文件和版本号，
支持 Linux（apt/rpm/手动安装）和 macOS 常见路径。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class LoEnv:
    """LibreOffice 环境检测结果。"""

    executable: str
    """LO 可执行文件的绝对路径。"""

    program_dir: Path
    """LO program 目录的绝对路径。"""

    version: Optional[str] = None
    """LO 版本号字符串。"""

    found: bool = True

    search_paths: list[str] = field(default_factory=list)


def _resolve_program_dir(exe: str) -> Optional[str]:
    """从可执行文件路径推导 program 目录。

    /opt/libreoffice26.2/program/soffice → /opt/libreoffice26.2/program
    /usr/bin/libreoffice → 跟随 symlink 推导
    """
    real = os.path.realpath(exe)
    parent = os.path.dirname(real)
    if os.path.basename(parent) == "program":
        return parent
    return None


def _find_by_which() -> Optional[tuple[str, str]]:
    """通过 PATH 环境变量查找 LO。

    优先级：
    1. libreoffice26.2 → Docker 手动安装版
    2. libreoffice    → apt 安装版
    3. soffice        → macOS / 通用
    """
    for name in ("libreoffice26.2", "libreoffice", "soffice"):
        found = shutil.which(name)
        if found:
            prog_dir = _resolve_program_dir(found)
            if prog_dir:
                return found, prog_dir
    return None


def _find_in_known_paths() -> Optional[tuple[str, str]]:
    """在已知路径中搜索 LO program 目录。"""
    candidates = [
        "/opt/libreoffice26.2/program",   # Docker 手动安装
        "/opt/libreoffice26.4/program",
        "/opt/libreoffice25/program",
        "/usr/lib/libreoffice/program",   # apt 安装
        "/usr/lib64/libreoffice/program", # RPM 系
    ]
    for path in candidates:
        if not os.path.isdir(path):
            continue
        for name in ("soffice", "libreoffice"):
            exe = os.path.join(path, name)
            if os.access(exe, os.X_OK):
                return exe, path
    return None


def _find_macos() -> Optional[tuple[str, str]]:
    """macOS 常见路径。"""
    for name in ("/Applications/LibreOffice.app/Contents/MacOS/soffice",
                 "/Applications/LibreOffice.app/Contents/MacOS/libreoffice"):
        if os.access(name, os.X_OK):
            prog_dir = os.path.dirname(name)
            return name, prog_dir
    return None


def _detect_version(executable: str) -> Optional[str]:
    """运行 LO 获取版本号。"""
    try:
        result = subprocess.run(
            [executable, "--version"],
            capture_output=True, text=True, timeout=10,
        )
        output = (result.stdout + result.stderr).strip()
        m = re.search(r"LibreOffice\s+([\d.]+)", output)
        if m:
            return m.group(1)
        return output[:80] if output else None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def detect() -> LoEnv:
    """检测当前系统的 LibreOffice 安装。

    优先级：PATH → 已知路径 → macOS 路径。

    Returns:
        LoEnv 检测结果。found=False 表示未检测到可用 LO。
    """
    # 1. PATH 查找
    result = _find_by_which()
    # 2. 已知路径
    if not result:
        result = _find_in_known_paths()
    # 3. macOS
    if not result and os.uname().sysname == "Darwin":
        result = _find_macos()

    if not result:
        return LoEnv(executable="", program_dir=Path("."), found=False)

    exe, prog_dir = result
    version = _detect_version(exe)

    return LoEnv(
        executable=exe,
        program_dir=Path(prog_dir),
        version=version,
        found=True,
    )
