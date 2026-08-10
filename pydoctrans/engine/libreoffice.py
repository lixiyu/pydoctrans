"""LibreOffice 转换引擎。

通过 ``soffice --headless --convert-to`` 实现文档格式互转，
串联 Sandbox（HOME 隔离）+ Pool（并发控制）+ 超时控制。
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import time
from pathlib import Path

from pydoctrans.engine.base import ConversionResult, Engine
from pydoctrans.env import detect
from pydoctrans.pool import ConversionPool
from pydoctrans.sandbox import Sandbox, cleanup_orphan_sandboxes

logger = logging.getLogger(__name__)


def _kill_process_group(proc: subprocess.Popen | None) -> None:
    """SIGKILL 整个进程组并收割，防止 soffice.bin 孤儿/僵尸残留。

    LibreOffice 的 soffice 只是启动器，真正干活的是它 fork 出的 soffice.bin。
    只杀直接子进程会导致 soffice.bin 被孤儿化、继续占管道/CPU；这里按进程组
    整组击杀（配合 start_new_session=True 使用）。
    """
    if proc is None or proc.pid is None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        proc.communicate()  # 收割直接子进程，避免变真·僵尸
    except Exception:
        pass

# 模块级共享并发池
_pool: ConversionPool | None = None


def _get_pool() -> ConversionPool:
    global _pool
    if _pool is None:
        _pool = ConversionPool()
    return _pool


class ConversionError(Exception):
    """转换失败异常。"""

    def __init__(self, message: str, engine: str = "libreoffice") -> None:
        super().__init__(message)
        self.engine = engine


class LibreOfficeEngine(Engine):
    """LibreOffice 转换引擎。

    串联 Sandbox 沙箱隔离 + Pool 并发控制 + subprocess 超时控制。

    用法::

        engine = LibreOfficeEngine()
        result = engine.convert(docx_bytes, "report.docx", "pdf")
        with open("report.pdf", "wb") as f:
            f.write(result.data)
    """

    DEFAULT_TIMEOUT = 300

    def __init__(self) -> None:
        self._env_info = detect()
        if not self._env_info.found:
            raise RuntimeError("未检测到 LibreOffice 安装")
        cleanup_orphan_sandboxes()

    # ---- Engine 接口 ----

    @property
    def name(self) -> str:
        return "libreoffice"

    def convert(
        self,
        data: bytes,
        file_name: str,
        to: str,
        timeout: int | None = None,
    ) -> ConversionResult:
        """将文档转换为目标格式。

        Args:
            data: 源文档内容。
            file_name: 源文件名（含扩展名）。
            to: 目标格式，如 "pdf"、"odt"、"docx"。
            timeout: 超时秒数，默认 300。

        Returns:
            ConversionResult。

        Raises:
            ValueError: file_name 缺少扩展名。
            ConversionError: LO 转换返回非零退出码。
            TimeoutError: 转换超时。
        """
        if timeout is None:
            timeout = int(os.environ.get("LO_TIMEOUT", str(self.DEFAULT_TIMEOUT)))

        if "." not in file_name:
            raise ValueError(f"file_name 须包含扩展名，当前值: {file_name!r}")

        pool = _get_pool()
        start_time = time.monotonic()

        try:
            with pool.acquire(timeout=timeout):
                with Sandbox(str(self._env_info.program_dir)) as sandbox:
                    result_data = self._do_convert(
                        sandbox, data, file_name, to, timeout,
                    )
        except RuntimeError as e:
            raise ConversionError(str(e), engine=self.name) from e

        elapsed = time.monotonic() - start_time
        return ConversionResult(
            data=result_data,
            engine=self.name,
            to=to,
            meta={
                "elapsed_s": round(elapsed, 2),
                "lo_version": self._env_info.version,
            },
        )

    def health(self) -> dict:
        return {
            "status": "up",
            "engine": self.name,
            "version": self._env_info.version,
            "executable": self._env_info.executable,
            "pool": {
                "max_concurrent": _get_pool().max_concurrent,
                "available": _get_pool().available,
            },
        }

    # ---- 内部实现 ----

    def _do_convert(
        self,
        sandbox: Sandbox,
        data: bytes,
        file_name: str,
        to: str,
        timeout: int,
    ) -> bytes:
        """在沙箱中执行 LO 转换。"""
        home = Path(sandbox.home)
        input_path = home / file_name

        # 写入源文件
        input_path.write_bytes(data)

        # 构建 LO 命令
        cmd: list[str] = [
            self._env_info.executable,
            "--headless",
            "--convert-to",
            to,
            "--outdir",
            str(home),
            str(input_path),
        ]

        env = sandbox.get_env()

        proc = None
        try:
            # 自成进程组（start_new_session），超时才能整组 kill，
            # 避免 soffice 只是启动器、fork 出的 soffice.bin 成为孤儿继续占管道/CPU。
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                cwd=sandbox.home,
                start_new_session=True,
            )
            try:
                stdout, stderr = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired as e:
                _kill_process_group(proc)
                logger.error("LO 转换超时: %s → %s (%.0fs)", file_name, to, timeout)
                raise TimeoutError(
                    f"LibreOffice 转换超时（{timeout}s）: {file_name}"
                ) from e
            returncode = proc.returncode
        except TimeoutError:
            raise
        except Exception:
            # 启动/执行异常也尝试清理进程组，避免残留
            _kill_process_group(proc)
            raise

        if returncode != 0:
            stderr_tail = (stderr or "").strip()[-1000:]
            stdout_tail = (stdout or "").strip()[-500:]
            logger.error(
                "LO 转换失败 (rc=%d, file=%s): stderr=%s",
                returncode, file_name, stderr_tail,
            )
            raise ConversionError(
                f"LibreOffice 转换失败 (退出码 {returncode})",
                engine=self.name,
            )

        # 定位输出文件
        output_path = self._find_output(home, file_name, to)
        if output_path is None or not output_path.exists():
            available = [p.name for p in home.glob("*")]
            raise ConversionError(
                f"转换后未找到输出文件。沙箱内容: {available}",
                engine=self.name,
            )

        return output_path.read_bytes()

    @staticmethod
    def _find_output(home: Path, file_name: str, to: str) -> Path | None:
        """查找 LO 生成的输出文件。

        LO 的输出文件名规则：去掉原名扩展名，加上目标扩展名。
        例如：report.docx → report.pdf。

        但 LO 有时会在文件名中插入额外后缀（如 report_docx.pdf），
        所以需要两种策略查找。
        """
        stem = Path(file_name).stem
        # 策略 1：直接匹配
        expected = home / f"{stem}.{to}"
        if expected.exists():
            return expected
        # 策略 2：通配匹配（处理 LO 的文件名变体）
        candidates = sorted(
            home.glob(f"{stem}*.{to}"),
            key=lambda p: len(p.name),  # 最短的名字最可能是目标
        )
        if candidates:
            return candidates[0]
        return None
