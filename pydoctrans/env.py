"""LO 环境检测模块。

自动检测 LibreOffice 安装路径、可执行文件和版本号，
支持 Linux（apt/rpm/手动安装）和 macOS 常见路径。
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class LoEnv:
    """LibreOffice 环境检测结果。"""

    executable: str
    """LO 可执行文件（soffice 或 libreoffice）的绝对路径。"""

    program_dir: Path
    """LO program 目录的绝对路径。"""

    version: Optional[str] = None
    """LO 版本号字符串，如 \"24.2.4.2\"。"""

    found: bool = True
    """是否成功检测到 LO 安装。"""

    search_paths: list[str] = field(default_factory=list)
    """检测时扫描过的路径列表（调试用）。"""


# Linux 常见的 LO 安装路径
_LINUX_SEARCH_ROOTS: list[str] = [
    "/opt",
    "/usr/lib",
    "/usr/lib64",
]

# macOS 常见路径
_MACOS_SEARCH_ROOTS: list[str] = [
    "/Applications",
]

# 在 program 目录下查找的可执行文件名
_EXECUTABLE_NAMES: list[str] = ["soffice", "libreoffice"]


def _find_program_dir_linux() -> Optional[Path]:
    """在 Linux 下搜索 LO program 目录。"""
    for root in _LINUX_SEARCH_ROOTS:
        # 匹配 /opt/libreoffice*/program
        pattern = os.path.join(root, "libreoffice*", "program")
        for path_str in sorted(glob.glob(pattern)):
            path = Path(path_str)
            if path.is_dir():
                return path
    return None


def _find_program_dir_macos() -> Optional[Path]:
    """在 macOS 下搜索 LO program 目录。"""
    for root in _MACOS_SEARCH_ROOTS:
        pattern = os.path.join(root, "LibreOffice*", "Contents", "MacOS")
        for path_str in sorted(glob.glob(pattern)):
            path = Path(path_str)
            if path.is_dir():
                return path
    return None


def _find_executable(program_dir: Path) -> Optional[str]:
    """在 program_dir 中查找 soffice 或 libreoffice 可执行文件。"""
    for name in _EXECUTABLE_NAMES:
        exe_path = program_dir / name
        if exe_path.is_file() and os.access(exe_path, os.X_OK):
            return str(exe_path)
    # 回退：用 shutil.which 在 PATH 中查找
    for name in _EXECUTABLE_NAMES:
        found = shutil.which(name)
        if found:
            return found
    return None


def _detect_version(executable: str) -> Optional[str]:
    """运行 LO 获取版本号。"""
    try:
        result = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            # 输出格式如: "LibreOffice 24.2.4.2 ..."
            return result.stdout.strip()
        # 有些版本把版本信息写到 stderr
        if result.stderr.strip():
            return result.stderr.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def _get_search_paths() -> list[str]:
    """收集所有被扫描过的候选路径（调试用）。"""
    paths: list[str] = []
    for root in _LINUX_SEARCH_ROOTS:
        pattern = os.path.join(root, "libreoffice*", "program")
        paths.extend(sorted(glob.glob(pattern)))
    for root in _MACOS_SEARCH_ROOTS:
        pattern = os.path.join(root, "LibreOffice*", "Contents", "MacOS")
        paths.extend(sorted(glob.glob(pattern)))
    return paths


def detect() -> LoEnv:
    """检测当前系统的 LibreOffice 安装。

    扫描顺序：Linux 路径 → macOS 路径 → PATH 回退。

    Returns:
        LoEnv 检测结果。若 found=False 表示未检测到可用 LO。
    """
    search_paths = _get_search_paths()

    # 按平台尝试查找
    program_dir: Optional[Path] = None
    executable: Optional[str] = None

    if os.name == "posix":
        # macOS
        if hasattr(os, "uname") and os.uname().sysname == "Darwin":
            program_dir = _find_program_dir_macos()
        else:
            # Linux
            program_dir = _find_program_dir_linux()

    if program_dir:
        executable = _find_executable(program_dir)

    # 回退：直接在 PATH 中查找
    if not executable:
        for name in _EXECUTABLE_NAMES:
            found = shutil.which(name)
            if found:
                executable = found
                # 尝试推算 program_dir
                real = Path(os.path.realpath(found))
                program_dir = real.parent
                break

    if not executable:
        return LoEnv(
            executable="",
            program_dir=Path("."),
            found=False,
            search_paths=search_paths,
        )

    version = _detect_version(executable)

    return LoEnv(
        executable=executable,
        program_dir=program_dir,
        version=version,
        found=True,
        search_paths=search_paths,
    )
