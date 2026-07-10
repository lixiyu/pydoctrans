"""Pool 模块测试。"""

from __future__ import annotations

import pytest

from pydoctrans.pool import ConversionPool


class TestConversionPool:
    """测试 Semaphore 并发控制池。"""

    def test_default_max_concurrent(self) -> None:
        pool = ConversionPool()
        assert pool.max_concurrent == 10

    def test_custom_max_concurrent(self) -> None:
        pool = ConversionPool(max_concurrent=3)
        assert pool.max_concurrent == 3

    def test_max_concurrent_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv("MAX_CONCURRENT", "5")
        pool = ConversionPool()
        assert pool.max_concurrent == 5

    def test_max_concurrent_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="必须 >= 1"):
            ConversionPool(max_concurrent=0)

    def test_acquire_and_release(self) -> None:
        pool = ConversionPool(max_concurrent=2)
        assert pool.available == 2

        with pool.acquire():
            assert pool.available == 1
            with pool.acquire():
                assert pool.available == 0

        assert pool.available == 2

    def test_acquire_timeout(self) -> None:
        pool = ConversionPool(max_concurrent=1)
        with pool.acquire():
            # 槽位已满，第二次 acquire 应超时
            with pytest.raises(RuntimeError, match="未能获取转换槽位"):
                pool.acquire(timeout=0.1)

    def test_release_on_exception(self) -> None:
        pool = ConversionPool(max_concurrent=1)
        try:
            with pool.acquire():
                assert pool.available == 0
                raise ValueError("simulated")
        except ValueError:
            pass
        assert pool.available == 1
