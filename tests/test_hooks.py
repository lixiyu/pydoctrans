"""回调钩子测试。"""

from __future__ import annotations

import pytest

from pydoctrans import ConversionContext, convert
from pydoctrans.hooks import (
    HookExecutionError,
    run_after_hooks,
    run_before_hooks,
)


class TestConversionContext:
    """测试 ConversionContext。"""

    def test_creation(self) -> None:
        ctx = ConversionContext(
            data=b"hello",
            file_name="test.txt",
            to="pdf",
            engine="libreoffice",
        )
        assert ctx.data == b"hello"
        assert ctx.file_name == "test.txt"
        assert ctx.to == "pdf"
        assert ctx.engine == "libreoffice"
        assert ctx.meta == {}

    def test_meta_is_mutable(self) -> None:
        ctx = ConversionContext(data=b"x", file_name="f", to="pdf", engine="lo")
        ctx.meta["s3_url"] = "https://..."
        assert ctx.meta["s3_url"] == "https://..."


class TestRunBeforeHooks:
    """测试 before 钩子执行。"""

    def test_empty_list_is_noop(self) -> None:
        ctx = ConversionContext(data=b"x", file_name="f", to="pdf", engine="lo")
        run_before_hooks([], ctx)  # 不应抛异常

    def test_none_is_noop(self) -> None:
        ctx = ConversionContext(data=b"x", file_name="f", to="pdf", engine="lo")
        run_before_hooks(None, ctx)

    def test_runs_hooks_in_order(self) -> None:
        ctx = ConversionContext(data=b"x", file_name="f", to="pdf", engine="lo")
        order: list[str] = []

        def a(c: ConversionContext) -> None:
            order.append("a")

        def b(c: ConversionContext) -> None:
            order.append("b")

        run_before_hooks([a, b], ctx)
        assert order == ["a", "b"]

    def test_hook_can_modify_data(self) -> None:
        ctx = ConversionContext(data=b"orig", file_name="f", to="pdf", engine="lo")

        def prepend_header(c: ConversionContext) -> None:
            c.data = b"HEADER\n" + c.data

        run_before_hooks([prepend_header], ctx)
        assert ctx.data == b"HEADER\norig"

    def test_hook_can_modify_file_name(self) -> None:
        ctx = ConversionContext(data=b"x", file_name="bad name.docx", to="pdf", engine="lo")

        def sanitize(c: ConversionContext) -> None:
            c.file_name = c.file_name.replace(" ", "_")

        run_before_hooks([sanitize], ctx)
        assert ctx.file_name == "bad_name.docx"

    def test_hook_exception_aborts_conversion(self) -> None:
        ctx = ConversionContext(data=b"x", file_name="f", to="pdf", engine="lo")

        def reject_large(c: ConversionContext) -> None:
            if len(c.data) > 100:
                raise ValueError("file too large")

        # 不应抛异常（data 很小）
        run_before_hooks([reject_large], ctx)

        # 大文件应抛异常
        ctx.data = b"x" * 200
        with pytest.raises(ValueError, match="file too large"):
            run_before_hooks([reject_large], ctx)


class TestRunAfterHooks:
    """测试 after 钩子执行。"""

    def test_runs_in_order(self) -> None:
        ctx = ConversionContext(data=b"x", file_name="f", to="pdf", engine="lo")
        order: list[str] = []

        def a(c: ConversionContext) -> None:
            order.append("a")

        def b(c: ConversionContext) -> None:
            order.append("b")

        run_after_hooks([a, b], ctx)
        assert order == ["a", "b"]

    def test_hook_can_modify_data(self) -> None:
        ctx = ConversionContext(data=b"pdf_data", file_name="f", to="pdf", engine="lo")

        def watermark(c: ConversionContext) -> None:
            c.data = c.data + b" [watermarked]"

        run_after_hooks([watermark], ctx)
        assert ctx.data == b"pdf_data [watermarked]"

    def test_hook_can_write_meta(self) -> None:
        ctx = ConversionContext(data=b"pdf", file_name="f", to="pdf", engine="lo")

        def upload(c: ConversionContext) -> None:
            c.meta["upload_url"] = "https://s3/result.pdf"

        run_after_hooks([upload], ctx)
        assert ctx.meta["upload_url"] == "https://s3/result.pdf"

    def test_one_failure_does_not_block_others(self) -> None:
        ctx = ConversionContext(data=b"x", file_name="f", to="pdf", engine="lo")
        results: list[str] = []

        def succeed_1(c: ConversionContext) -> None:
            results.append("1")

        def fail(c: ConversionContext) -> None:
            raise RuntimeError("boom")

        def succeed_2(c: ConversionContext) -> None:
            results.append("2")

        with pytest.raises(HookExecutionError) as exc_info:
            run_after_hooks([succeed_1, fail, succeed_2], ctx)

        assert results == ["1", "2"]  # 两个都执行了
        assert len(exc_info.value.errors) == 1
        assert exc_info.value.errors[0][0] == "fail"

    def test_multiple_failures_aggregated(self) -> None:
        ctx = ConversionContext(data=b"x", file_name="f", to="pdf", engine="lo")

        def f1(c: ConversionContext) -> None:
            raise RuntimeError("e1")

        def f2(c: ConversionContext) -> None:
            raise RuntimeError("e2")

        with pytest.raises(HookExecutionError) as exc_info:
            run_after_hooks([f1, f2], ctx)

        assert len(exc_info.value.errors) == 2


class TestConvertWithHooks:
    """集成测试：convert() 带钩子。"""

    def test_before_hook_runs(self) -> None:
        called = False

        def tracker(c: ConversionContext) -> None:
            nonlocal called
            called = True

        result = convert(
            b"hello",
            to="pdf",
            file_name="test.txt",
            before=[tracker],
        )
        assert called
        assert len(result) > 0

    def test_after_hook_runs(self) -> None:
        called = False

        def tracker(c: ConversionContext) -> None:
            nonlocal called
            called = True

        result = convert(
            b"hello",
            to="pdf",
            file_name="test.txt",
            after=[tracker],
        )
        assert called
        assert len(result) > 0

    def test_before_can_abort(self) -> None:
        def reject(c: ConversionContext) -> None:
            raise ValueError("rejected")

        with pytest.raises(ValueError, match="rejected"):
            convert(
                b"hello",
                to="pdf",
                file_name="test.txt",
                before=[reject],
            )

    def test_after_can_modify_output(self) -> None:
        def append_text(c: ConversionContext) -> None:
            c.data = c.data + b" [appended]"

        result = convert(
            b"hello",
            to="pdf",
            file_name="test.txt",
            after=[append_text],
        )
        assert result.endswith(b" [appended]")

    def test_after_can_record_meta(self) -> None:
        meta_store: dict = {}

        def record(c: ConversionContext) -> None:
            meta_store["size"] = len(c.data)
            c.meta["to"] = c.to

        convert(
            b"hello",
            to="pdf",
            file_name="test.txt",
            after=[record],
        )
        assert meta_store["size"] > 0
