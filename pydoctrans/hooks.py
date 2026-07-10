"""回调钩子系统。

提供转换前/后的钩子注入点，支持水印、加密、上传、校验等自定义逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


# ---- ConversionContext ----


@dataclass
class ConversionContext:
    """转换上下文，在钩子之间传递。

    钩子可以读写此对象的字段，实现数据传递与副作用。
    """

    data: bytes
    """当前文件内容。before 阶段为源文件，after 阶段为转换结果。"""

    file_name: str
    """源文件名（如 \"report.docx\"）。钩子可以修改。"""

    to: str
    """目标格式（如 \"pdf\"）。"""

    engine: str
    """执行转换的引擎名称。"""

    meta: dict[str, Any] = field(default_factory=dict)
    """自由读写字典，钩子间传递状态用。

    用法::

        def upload(ctx: ConversionContext) -> None:
            url = s3.put(ctx.data)
            ctx.meta["s3_url"] = url
    """


# ---- Hook 协议 ----


class BeforeHook(Protocol):
    """转换前钩子。

    可以修改 ctx.data、ctx.file_name 等字段。
    抛出异常可中止本次转换。
    """

    def __call__(self, ctx: ConversionContext) -> None: ...


class AfterHook(Protocol):
    """转换后钩子。

    可以修改 ctx.data（如水印注入）、写入 ctx.meta（如上传 URL）。
    """

    def __call__(self, ctx: ConversionContext) -> None: ...


# ---- 钩子执行器 ----


def run_before_hooks(
    before: list[BeforeHook] | None,
    ctx: ConversionContext,
) -> None:
    """按序执行所有 before 钩子。任一抛出异常即中止。"""
    if not before:
        return
    for hook in before:
        hook(ctx)


def run_after_hooks(
    after: list[AfterHook] | None,
    ctx: ConversionContext,
) -> None:
    """按序执行所有 after 钩子。单个失败不影响后续钩子执行。"""
    if not after:
        return
    errors: list[tuple[str, Exception]] = []
    for i, hook in enumerate(after):
        try:
            hook(ctx)
        except Exception as e:
            # 用钩子函数名标识，匿名函数显示索引
            name = getattr(hook, "__name__", f"hook_{i}")
            errors.append((name, e))
    if errors:
        names = ", ".join(n for n, _ in errors)
        raise HookExecutionError(
            f"{len(errors)} 个 after 钩子执行失败: {names}",
            errors=errors,
        )


class HookExecutionError(Exception):
    """钩子执行异常。"""

    def __init__(self, message: str, errors: list[tuple[str, Exception]]) -> None:
        super().__init__(message)
        self.errors = errors
