"""工具函数。"""

from __future__ import annotations

import os


def merge_env(extra: dict[str, str]) -> dict[str, str]:
    """创建包含额外变量的子进程环境副本。

    将 extra 合并到 os.environ 的副本中，隔离 LD_LIBRARY_PATH 等
    可能干扰 LO 的环境变量。
    """
    env = os.environ.copy()
    env.update(extra)
    return env
