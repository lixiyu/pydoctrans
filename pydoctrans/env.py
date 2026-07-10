"""LO 环境检测模块。

自动检测 LibreOffice 安装路径、可执行文件和版本号。
兼容 Linux（apt/rpm/deb/Snap/Flatpak/源码编译）和 macOS（dmg/Homebrew）。
"""

from __future__ import annotations

import glob
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 在每个候选目录中，优先找 soffice，其次 libreoffice
_EXE_NAMES = ("soffice", "libreoffice")


@dataclass
class LoEnv:
    """LibreOffice 环境检测结果。"""

    executable: str
    program_dir: Path
    version: Optional[str] = None
    found: bool = True
    search_paths: list[str] = field(default_factory=list)


# ---- 工具 ----

def _pick_exe(program_dir: str) -> Optional[str]:
    """在 program_dir 中按优先顺序找可执行文件：soffice > libreoffice。"""
    for name in _EXE_NAMES:
        exe = os.path.join(program_dir, name)
        if os.access(exe, os.X_OK):
            return exe
    return None


def _program_dir_from_exe(exe: str) -> Optional[str]:
    """从可执行文件路径推导 program 目录。跟随 symlink。"""
    real = os.path.realpath(exe)
    parent = os.path.dirname(real)
    return parent if os.path.basename(parent) == "program" else None


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
    except Exception:
        return None


def _install_guide() -> str:
    """返回平台相关的安装建议。"""
    if hasattr(os, "uname") and os.uname().sysname == "Darwin":
        return (
            "brew install --cask libreoffice"
        )
    return (
        "Ubuntu/Debian: sudo apt install libreoffice\n"
        "  CentOS/RHEL:   sudo dnf install libreoffice\n"
        "  Snap:          sudo snap install libreoffice\n"
        "  Flatpak:       flatpak install org.libreoffice.LibreOffice\n"
        "  手动下载:      https://www.libreoffice.org/download/"
    )


# ---- 1. 环境变量 ----

def _find_from_env() -> Optional[tuple[str, str]]:
    """从环境变量获取 LO 路径。"""
    exe = os.environ.get("LO_EXECUTABLE", "").strip()
    prog = os.environ.get("LO_PROGRAM_DIR", "").strip()

    # LO_EXECUTABLE 优先：直接指定可执行文件
    if exe and os.access(exe, os.X_OK):
        prog_dir = _program_dir_from_exe(exe) or os.path.dirname(exe)
        return exe, prog_dir

    # LO_PROGRAM_DIR：指定 program 目录，从中找可执行文件
    if prog and os.path.isdir(prog):
        picked = _pick_exe(prog)
        if picked:
            return picked, prog

    return None


# ---- 2. PATH 查找 ----

def _find_from_path() -> Optional[tuple[str, str]]:
    """通过 which 在 PATH 中查找 LO。"""
    for name in ("libreoffice26.2", "libreoffice", "soffice"):
        found = shutil.which(name)
        if found:
            prog_dir = _program_dir_from_exe(found)
            if prog_dir:
                return found, prog_dir
    return None


# ---- 3. 目录遍历 ----

_LINUX_CANDIDATES = [
    "/opt",
    "/usr/lib/libreoffice/program",
    "/usr/lib64/libreoffice/program",
    "/usr/local",
    "/snap/libreoffice/current/usr/lib/libreoffice/program",
    "/var/lib/flatpak/app/org.libreoffice.LibreOffice",
]

_MACOS_CANDIDATES = [
    "/Applications",
    "/usr/local/Caskroom/libreoffice",
    "/opt/homebrew/Caskroom/libreoffice",
]


def _scan_roots(roots: list[str], pattern: str) -> list[str]:
    """在 roots 中扫描 LO program 目录。"""
    dirs: list[str] = []
    for root in roots:
        full = os.path.join(root, pattern) if "*" not in root else root
        for path in sorted(glob.glob(full)):
            if os.path.isdir(path) and _pick_exe(path):
                dirs.append(path)
    return dirs


def _find_by_scanning() -> list[str]:
    """遍历所有已知路径，找到所有有可执行文件的 program 目录。"""
    found: list[str] = []

    if os.name != "posix":
        return found

    is_macos = hasattr(os, "uname") and os.uname().sysname == "Darwin"

    # Linux：在根目录下找 libreoffice*/program
    if not is_macos:
        found.extend(_scan_roots(_LINUX_CANDIDATES, "libreoffice*/program"))
    else:
        # macOS：在候选根目录下找 LibreOffice*.app/Contents/MacOS
        found.extend(_scan_roots(_MACOS_CANDIDATES, "LibreOffice*.app/Contents/MacOS"))
        # Homebrew 路径下再深入一层
        for candidate in _MACOS_CANDIDATES[1:]:
            found.extend(_scan_roots([candidate], "*/LibreOffice.app/Contents/MacOS"))

    return found


# ---- 顶层 ----

def detect() -> LoEnv:
    """检测当前系统的 LibreOffice 安装。

    优先级：环境变量 → PATH → 目录遍历。

    Returns:
        LoEnv。found=False 表示未检测到可用 LO（不抛异常）。
    """
    search_paths: list[str] = []
    result: Optional[tuple[str, str]] = None

    # 1. 环境变量
    result = _find_from_env()

    # 2. PATH
    if not result:
        result = _find_from_path()

    # 3. 目录遍历
    if not result:
        scanned = _find_by_scanning()
        search_paths = scanned
        if scanned:
            # 取第一个（glob 已排序，最新版本靠前）
            prog_dir = scanned[0]
            exe = _pick_exe(prog_dir)
            if exe:
                result = (exe, prog_dir)

    if not result:
        logger.warning(
            "未检测到 LibreOffice。设置 LO_EXECUTABLE 或 LO_PROGRAM_DIR 环境变量。\n"
            "安装: %s",
            _install_guide(),
        )
        return LoEnv(
            executable="",
            program_dir=Path("."),
            found=False,
            search_paths=search_paths,
        )

    exe, prog_dir = result
    version = _detect_version(exe)

    return LoEnv(
        executable=exe,
        program_dir=Path(prog_dir),
        version=version,
        found=True,
        search_paths=search_paths,
    )
